"""Sign-in for the dashboard: the invite allowlist, behind one of three modes (`auth_mode`).

- off: no STRELITZIA_GOOGLE_CLIENT_ID and no proxy mode. Every request acts as the owner, as before accounts existed.
- google: STRELITZIA_GOOGLE_CLIENT_ID is set. The built-in OAuth 2.0 authorization-code flow: the owner
  (STRELITZIA_OWNER_EMAIL) and invited emails get a session cookie holding their user id; anyone else is sent back to
  /strelitzia/dashboard/?auth=not_invited (a disabled account to ?auth=disabled).
- proxy: STRELITZIA_AUTH_MODE=proxy. A reverse proxy (engineerfamily's nginx auth_request, or oauth2-proxy) has already
  signed the visitor in and sets X-Auth-Request-Email (and X-Auth-Request-Preferred-Username). Those headers are the
  whole proof of identity, so they are read only in this mode, and it is safe only when nothing but the proxy can
  reach the server. Sign-in and sign-out are the site's (STRELITZIA_SITE_LOGIN_URL / STRELITZIA_SITE_LOGOUT_URL).
  When the proxy also sends X-Auth-Request-Access: strelitzia (engineerfamily's nginx, from its Users page), that
  grant replaces the invite list: the account is created or re-activated, and its monthly cap is the one the
  proxy sends (`site_grant`). Without that header, the invite list decides as before.
"""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal
from urllib.parse import unquote, urlencode, urlsplit

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from google.auth.exceptions import GoogleAuthError
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from google.oauth2.credentials import Credentials

from strelitzia import users
from strelitzia.config import env
from strelitzia.database import Connection, get_connection
from strelitzia.storage import drive
from strelitzia.web.paths import API_PREFIX
from strelitzia.web.paths import PREFIX as UI_PREFIX

PREFIX = f"{API_PREFIX}/auth"
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"
SCOPES = "openid email profile"
SESSION_COOKIE = "strelitzia_session"
SESSION_MAX_AGE = 30 * 24 * 3600
CLOCK_SKEW_SECONDS = 30  # tolerated drift between this server's clock and Google's when checking the ID token
PUBLIC_API_PATHS = (f"{API_PREFIX}/health",)
PROXY_EMAIL_HEADER = "X-Auth-Request-Email"
PROXY_NAME_HEADER = "X-Auth-Request-Preferred-Username"
ACCESS_HEADER = "X-Auth-Request-Access"  # "strelitzia" when the site grants this visitor the dashboard
ADMIN_HEADER = "X-Auth-Request-Admin"  # "1" for a site admin
CAP_HEADER = "X-Auth-Request-Cap-Usd"  # the monthly Claude cap in USD, or "none"
SITE_ACCESS = "strelitzia"
REFUSALS = ("not_invited", "disabled")  # the 401 details that say why a signed-in site account can't use the dashboard
LAST_LOGIN_EVERY = timedelta(hours=1)  # proxy mode: how often `me` refreshes last_login_at

DRIVE_PREFIX = f"{API_PREFIX}/drive"
DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.file"
SETUP_PAGE = f"{UI_PREFIX}/claude-setup"

router = APIRouter(prefix=PREFIX)
drive_router = APIRouter(prefix=DRIVE_PREFIX)
log = logging.getLogger(__name__)


def auth_mode() -> Literal["off", "google", "proxy"]:
    if (env("AUTH_MODE") or "").strip().lower() == "proxy":
        return "proxy"
    return "google" if env("GOOGLE_CLIENT_ID") else "off"


def auth_enabled() -> bool:
    return auth_mode() != "off"


def proxy_identity(request: Request) -> tuple[str, str | None] | None:
    """The email and display name the proxy vouches for, or None without an email. Call it only in proxy mode."""
    email = request.headers.get(PROXY_EMAIL_HEADER, "").strip().lower()
    if not email:
        return None
    name = unquote(request.headers.get(PROXY_NAME_HEADER, "")).strip()
    return email, name or None


@dataclass
class SiteGrant:
    """The site's say on this visitor: dashboard access is implied, plus admin and the monthly cap (None = none)."""
    admin: bool
    cap_usd: float | None


_logged_bad_cap = False


def _parse_cap(raw: str) -> float | None:
    raw = raw.strip()
    if raw.lower() == "none":
        return None
    try:
        cap = float(raw)
    except ValueError:
        cap = -1.0
    if cap >= 0 and cap != float("inf"):
        return cap
    global _logged_bad_cap
    if not _logged_bad_cap:
        _logged_bad_cap = True
        log.warning("malformed %s %r; using the default cap", CAP_HEADER, raw)
    return users.DEFAULT_CAP_USD


def site_grant(request: Request) -> SiteGrant | None:
    """The site's grant, or None when the proxy sent no Access header for Strelitzia (an older proxy, or no access).
    Like the email header, it is proof only in proxy mode: call it only there. Parsed once per request."""
    if hasattr(request.state, "site_grant"):
        return request.state.site_grant
    grant = None
    if request.headers.get(ACCESS_HEADER, "").strip().lower() == SITE_ACCESS:
        grant = SiteGrant(admin=request.headers.get(ADMIN_HEADER, "").strip() == "1",
                          cap_usd=_parse_cap(request.headers.get(CAP_HEADER, "")))
    request.state.site_grant = grant
    return grant


def site_users_url() -> str:
    """The site's Users page, on PUBLIC_URL's origin (same-origin path without one)."""
    parts = urlsplit(public_url())
    origin = f"{parts.scheme}://{parts.netloc}" if parts.scheme and parts.netloc else ""
    return f"{origin}/users/"


def public_url() -> str:
    return (env("PUBLIC_URL") or "").rstrip("/")


def secure_cookie() -> bool:
    return public_url().startswith("https://")


def is_public_path(path: str) -> bool:
    """API paths that answer without a session: the health check and the sign-in flow itself."""
    return path in PUBLIC_API_PATHS or path.startswith(PREFIX + "/")


def _conn(request: Request) -> Connection:
    return get_connection(request.app.state.db)


def _redirect_uri(request: Request) -> str:
    base = public_url()
    return f"{base}{PREFIX}/callback" if base else str(request.url_for("auth_callback"))


def current_user(request: Request) -> users.User:
    """The signed-in user: the owner while login is off, the proxy's account in proxy mode, else the session's
    active account. 401 without one (in proxy mode with the reason: "not_invited" or "disabled")."""
    cached = getattr(request.state, "user", None)
    if cached is not None:
        return cached
    conn = _conn(request)
    mode = auth_mode()
    if mode == "off":
        user = users.owner(conn)
    elif mode == "proxy":
        identity = proxy_identity(request)
        if identity is None:
            raise HTTPException(401, "Not signed in")
        grant = site_grant(request)
        user = _account_for(conn, *identity, grant=grant)
        if user is None:
            raise HTTPException(401, _refusal(conn, identity[0]))
        if grant is not None and user.role != "owner" and user.monthly_cap_usd != grant.cap_usd:
            user = users.set_cap(conn, user.id, grant.cap_usd)
    else:
        uid = request.session.get("uid")
        user = users.get(conn, uid) if isinstance(uid, str) else None
        if user is None or user.status != "active":
            raise HTTPException(401, "Not signed in")
    request.state.user = user
    return user


def _refusal(conn: Connection, email: str) -> str:
    known = users.by_email(conn, email)
    return "disabled" if known and known.status == "disabled" else "not_invited"


def check_config() -> None:
    """With login on, refuse to start without the keys sign-in can't work without."""
    mode = auth_mode()
    if mode == "off":
        return
    if mode == "proxy":
        # SESSION_SECRET signs Drive connect's state; Drive connect itself still needs the Google client.
        missing = [f"STRELITZIA_{name}" for name in ("OWNER_EMAIL", "SESSION_SECRET") if not env(name)]
        if missing:
            raise RuntimeError(f"STRELITZIA_AUTH_MODE=proxy is set but {', '.join(missing)} is not "
                               "(see agents/DEPLOY.md, Google sign-in)")
        return
    missing = [f"STRELITZIA_{name}" for name in ("GOOGLE_CLIENT_SECRET", "SESSION_SECRET", "OWNER_EMAIL")
               if not env(name)]
    if missing:
        raise RuntimeError(f"STRELITZIA_GOOGLE_CLIENT_ID is set but {', '.join(missing)} is not "
                           "(see agents/DEPLOY.md, Google sign-in)")


def _sign_in(conn: Connection, email: str, name: str | None) -> users.User | None:
    """The account a verified Google email signs in as: the owner, an invited (or active) user, else None."""
    user = _account_for(conn, email, name)
    if user is not None:
        conn.execute("UPDATE users SET last_login_at = ? WHERE id = ?",
                     (datetime.now(timezone.utc).isoformat(), user.id))
        conn.commit()
    return user


def _account_for(conn: Connection, email: str, name: str | None,
                 grant: SiteGrant | None = None) -> users.User | None:
    """The owner (re-keyed from the placeholder if need be), else the site-granted or invited account, else None."""
    owner = users.owner(conn)
    email = email.strip().lower()
    if email == owner.email:
        return owner
    owner_email = (env("OWNER_EMAIL") or "").strip().lower()
    if email == owner_email and owner.email == users.FALLBACK_OWNER_EMAIL:
        # The owner row was created before OWNER_EMAIL was set: re-key it to the real address.
        if users.by_email(conn, email) is not None:
            log.warning("owner email %s is already taken by another account; not re-keying the owner", email)
            return owner
        conn.execute("UPDATE users SET email = ?, name = COALESCE(name, ?) WHERE id = ?", (email, name, owner.id))
        conn.commit()
        return users.get(conn, owner.id)
    user = users.by_email(conn, email)
    if user is not None and user.role == "owner":
        return user
    if grant is not None:
        return users.ensure_active(conn, email, name)
    return users.activate(conn, email, name)


def _state_matches(state: str | None, expected: object) -> bool:
    return bool(state) and isinstance(expected, str) and secrets.compare_digest(state.encode(), expected.encode())


def _exchange_code(code: str, redirect_uri: str) -> dict | None:
    """Trade an authorization code for Google's token response, or None (logged, without the tokens)."""
    try:
        resp = httpx.post(GOOGLE_TOKEN_URL, timeout=15, data={
            "code": code,
            "client_id": env("GOOGLE_CLIENT_ID"),
            "client_secret": env("GOOGLE_CLIENT_SECRET") or "",
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        })
        body = resp.json() if resp.status_code == 200 else None
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("Google token exchange failed: %s", exc)
        return None
    if not isinstance(body, dict):
        log.warning("Google token exchange returned HTTP %s", resp.status_code)
        return None
    return body


def _back(outcome: str | None = None) -> RedirectResponse:
    return RedirectResponse(f"{UI_PREFIX}/" + (f"?auth={outcome}" if outcome else ""), status_code=303)


def _site_login_url() -> str:
    return env("SITE_LOGIN_URL") or "/auth/login"


def _site_logout_url() -> str:
    return env("SITE_LOGOUT_URL") or "/auth/logout"


@router.get("/login")
def login(request: Request):
    mode = auth_mode()
    if mode == "off":
        return _back()
    if mode == "proxy":
        url = _site_login_url()
        sep = "&" if "?" in url else "?"
        return RedirectResponse(f"{url}{sep}{urlencode({'next': f'{UI_PREFIX}/'})}", status_code=303)
    state = secrets.token_urlsafe(32)
    request.session["oauth_state"] = state
    params = {
        "client_id": env("GOOGLE_CLIENT_ID"),
        "redirect_uri": _redirect_uri(request),
        "response_type": "code",
        "scope": SCOPES,
        "state": state,
        "prompt": "select_account",
    }
    return RedirectResponse(f"{GOOGLE_AUTH_URL}?{urlencode(params)}", status_code=303)


@router.get("/callback", name="auth_callback")
def callback(request: Request, code: str | None = None, state: str | None = None, error: str | None = None):
    if auth_mode() != "google":
        raise HTTPException(404, "Login is off" if auth_mode() == "off" else "Sign-in is the site's")
    expected = request.session.pop("oauth_state", None)
    if not _state_matches(state, expected):
        # A forged callback, or a stale one (a second login tab, Back into the callback): nobody is signed in.
        log.warning("sign-in callback with a missing or wrong state")
        return _back("error")
    if error or not code:
        return _back("error")
    client_id = env("GOOGLE_CLIENT_ID")
    body = _exchange_code(code, _redirect_uri(request))
    token = body.get("id_token") if body else None
    if not isinstance(token, str) or not token:
        if body is not None:
            log.warning("Google token exchange returned no id_token")
        return _back("error")
    try:
        info = id_token.verify_oauth2_token(token, google_requests.Request(), client_id,
                                            clock_skew_in_seconds=CLOCK_SKEW_SECONDS)
    except (ValueError, GoogleAuthError) as exc:
        log.warning("Google ID token rejected: %s", exc)
        return _back("error")
    if not info.get("email_verified") or not info.get("email"):
        return _back("unverified")
    user = _sign_in(_conn(request), info["email"], info.get("name"))
    request.session.clear()
    if user is None:
        return _back(_refusal(_conn(request), info["email"]))
    request.session["uid"] = user.id
    return _back()


@router.post("/logout")
def logout(request: Request) -> dict:
    request.session.clear()
    if auth_mode() == "proxy":
        # The site's cookie is the site's to end: the dashboard POSTs this URL next.
        return {"ok": True, "logout_url": _site_logout_url()}
    return {"ok": True}


def _note_login(conn: Connection, user: users.User) -> None:
    """Proxy mode has no sign-in moment, so `me` records one, at most once every LAST_LOGIN_EVERY."""
    now = datetime.now(timezone.utc)
    try:
        last = datetime.fromisoformat(user.last_login_at) if user.last_login_at else None
    except ValueError:
        last = None
    if last is not None and last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    if last is not None and now - last < LAST_LOGIN_EVERY:
        return
    conn.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (now.isoformat(), user.id))
    conn.commit()


@router.get("/me")
def me(request: Request) -> dict:
    mode = auth_mode()
    reason = None
    try:
        user = current_user(request)
    except HTTPException as exc:
        user = None
        if exc.detail in REFUSALS:
            reason = exc.detail
    identity = proxy_identity(request) if mode == "proxy" else None
    grant = site_grant(request) if mode == "proxy" else None
    if mode == "proxy" and user is not None:
        _note_login(_conn(request), user)
    return {
        "enabled": mode != "off",
        "user": {"email": user.email, "name": user.name, "role": user.role} if user else None,
        "mode": mode,
        "identity": {"email": identity[0], "name": identity[1]} if identity else None,
        "reason": reason,
        "logout_url": _site_logout_url() if mode == "proxy" else None,
        "site_header_url": env("SITE_HEADER_URL") or None,
        "site_admin": bool(grant and grant.admin),
        "users_url": site_users_url() if grant else None,
    }


# --- Connect Google Drive (a second, optional consent after sign-in; strelitzia.storage.drive stores the token) ---

def drive_connect_available() -> bool:
    """The web OAuth client and the token key are both set, so a user can connect their own Drive."""
    return all(env(name) for name in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "TOKEN_KEY"))


def _drive_redirect_uri(request: Request) -> str:
    base = public_url()
    return f"{base}{DRIVE_PREFIX}/callback" if base else str(request.url_for("drive_callback"))


def _setup_page(outcome: str) -> RedirectResponse:
    return RedirectResponse(f"{SETUP_PAGE}?drive={outcome}", status_code=303)


@drive_router.get("/connect")
def drive_connect(request: Request):
    user = current_user(request)
    if not drive_connect_available():
        return _setup_page("unavailable")
    state = secrets.token_urlsafe(32)
    request.session["drive_state"] = state
    params = {
        "client_id": env("GOOGLE_CLIENT_ID"),
        "redirect_uri": _drive_redirect_uri(request),
        "response_type": "code",
        "scope": DRIVE_SCOPE,
        "state": state,
        # offline + consent: Google only returns a refresh token on a fresh consent.
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "login_hint": user.email,  # the account picker starts on the signed-in account
    }
    return RedirectResponse(f"{GOOGLE_AUTH_URL}?{urlencode(params)}", status_code=303)


@drive_router.get("/callback", name="drive_callback")
def drive_callback(request: Request, code: str | None = None, state: str | None = None, error: str | None = None,
                   scope: str | None = None):
    user = current_user(request)
    if not drive_connect_available():
        return _setup_page("unavailable")
    if not _state_matches(state, request.session.pop("drive_state", None)):
        log.warning("Drive connect callback with a missing or wrong state")
        return _setup_page("error")
    if error or not code:
        return _setup_page("denied" if error == "access_denied" else "error")
    body = _exchange_code(code, _drive_redirect_uri(request))
    if body is None:
        return _setup_page("error")
    granted = str(body.get("scope") or scope or "").split()
    access, refresh = body.get("access_token"), body.get("refresh_token")
    if DRIVE_SCOPE not in granted:
        return _setup_page("denied")  # the user unticked the Drive box on the consent screen
    if not isinstance(access, str) or not isinstance(refresh, str) or not refresh:
        log.warning("Drive token exchange returned no refresh token")
        return _setup_page("error")
    expires_in = body.get("expires_in")
    expiry = (datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(seconds=int(expires_in))
              if isinstance(expires_in, int | float) else None)  # google-auth wants naive UTC
    creds = Credentials(token=access, refresh_token=refresh, token_uri=GOOGLE_TOKEN_URL,
                        client_id=env("GOOGLE_CLIENT_ID"), client_secret=env("GOOGLE_CLIENT_SECRET"),
                        scopes=[DRIVE_SCOPE], expiry=expiry)
    try:
        drive.save_user_token(_conn(request), user.id, creds)
    except drive.DriveNotConfigured as exc:
        log.warning("Couldn't store the Drive token: %s", exc)
        return _setup_page("error")
    return _setup_page("connected")


@drive_router.post("/disconnect")
def drive_disconnect(request: Request) -> dict:
    """Forget the user's Drive token, revoking it at Google first (best effort: it's forgotten either way)."""
    conn, user = _conn(request), current_user(request)
    refresh = drive.stored_refresh_token(conn, user.id)
    if refresh:
        try:
            resp = httpx.post(GOOGLE_REVOKE_URL, timeout=15, data={"token": refresh})
            if resp.status_code != 200:
                log.warning("Google didn't revoke the Drive token (HTTP %s)", resp.status_code)
        except httpx.HTTPError as exc:
            log.warning("Couldn't revoke the Drive token at Google: %s", type(exc).__name__)
    drive.disconnect(conn, user.id)
    return {"ok": True}
