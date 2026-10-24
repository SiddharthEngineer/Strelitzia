"""Google sign-in (strelitzia.web.auth) with Google's token endpoint and ID-token check mocked."""

from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

from strelitzia import users
from strelitzia.database import close_connection, get_connection, init_db
from strelitzia.web import auth

OWNER = "owner@example.com"


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "auth.db"
    init_db(path)
    yield path
    close_connection(path)


@pytest.fixture
def conn(db):
    return get_connection(db)


@pytest.fixture
def auth_on(monkeypatch):
    monkeypatch.setenv("STRELITZIA_GOOGLE_CLIENT_ID", "client-123")
    monkeypatch.setenv("STRELITZIA_GOOGLE_CLIENT_SECRET", "shh")
    monkeypatch.setenv("STRELITZIA_OWNER_EMAIL", OWNER)
    monkeypatch.setenv("STRELITZIA_PUBLIC_URL", "https://strelitzia.example.net")


@pytest.fixture
def google(monkeypatch):
    """Mocks the token exchange and the ID-token check; set `google.claims` to what Google vouches for."""

    class Google:
        claims = {"email": OWNER, "email_verified": True, "name": "Owner"}
        token_requests: list[dict] = []

    def fake_post(url, data=None, timeout=None):
        assert url == auth.GOOGLE_TOKEN_URL
        Google.token_requests.append(data)
        return httpx.Response(200, json={"id_token": "signed.jwt", "access_token": "at"})

    def fake_verify(token, request, audience, clock_skew_in_seconds=0):
        assert token == "signed.jwt" and audience == "client-123" and clock_skew_in_seconds > 0
        return dict(Google.claims)

    monkeypatch.setattr(auth.httpx, "post", fake_post)
    monkeypatch.setattr(auth.id_token, "verify_oauth2_token", fake_verify)
    return Google


@pytest.fixture
def client(db):
    app = FastAPI()
    app.state.db = db
    app.include_router(auth.router)
    app.include_router(auth.drive_router)

    @app.get("/strelitzia/dashboard/api/whoami")
    def whoami(user: users.User = Depends(auth.current_user)):
        return {"email": user.email}

    app.add_middleware(SessionMiddleware, secret_key="test-secret", session_cookie=auth.SESSION_COOKIE)
    with TestClient(app, follow_redirects=False) as c:
        yield c


def sign_in(client, state=None):
    login = client.get("/strelitzia/dashboard/api/auth/login")
    assert login.status_code == 303
    query = parse_qs(urlparse(login.headers["location"]).query)
    return client.get("/strelitzia/dashboard/api/auth/callback", params={"code": "c0de", "state": state or query["state"][0]})


def test_login_redirects_to_google_with_state(auth_on, client):
    resp = client.get("/strelitzia/dashboard/api/auth/login")
    url = urlparse(resp.headers["location"])
    assert f"{url.scheme}://{url.netloc}{url.path}" == auth.GOOGLE_AUTH_URL
    query = parse_qs(url.query)
    assert query["client_id"] == ["client-123"]
    assert query["scope"] == ["openid email profile"]
    assert query["redirect_uri"] == ["https://strelitzia.example.net/strelitzia/dashboard/api/auth/callback"]
    assert len(query["state"][0]) >= 32


def test_owner_signs_in(auth_on, client, conn, google):
    owner = users.owner(conn)
    resp = sign_in(client)
    assert resp.status_code == 303 and resp.headers["location"] == "/strelitzia/dashboard/"
    assert google.token_requests[-1]["code"] == "c0de"
    assert google.token_requests[-1]["redirect_uri"] == "https://strelitzia.example.net/strelitzia/dashboard/api/auth/callback"
    me = client.get("/strelitzia/dashboard/api/auth/me").json()
    assert me == {"enabled": True, "user": {"email": OWNER, "name": None, "role": "owner"}, "mode": "google",
                  "identity": None, "reason": None, "logout_url": None, "site_header_url": None, "site_admin": False, "users_url": None}
    assert client.get("/strelitzia/dashboard/api/whoami").json() == {"email": owner.email}


def test_owner_row_from_before_owner_email_is_rekeyed(client, conn, auth_on, google):
    # The database (and its owner row) was created before STRELITZIA_OWNER_EMAIL was set.
    placeholder = users.owner(conn)
    assert placeholder.email == users.FALLBACK_OWNER_EMAIL
    google.claims = {"email": "Owner@Example.com", "email_verified": True, "name": "Owner"}
    assert sign_in(client).headers["location"] == "/strelitzia/dashboard/"
    rekeyed = users.owner(conn)
    assert (rekeyed.id, rekeyed.email, rekeyed.name) == (placeholder.id, OWNER, "Owner")
    assert client.get("/strelitzia/dashboard/api/auth/me").json()["user"]["role"] == "owner"


def test_invited_user_signs_in_and_is_activated(auth_on, client, conn, google):
    invited = users.invite(conn, "friend@example.com")
    google.claims = {"email": "friend@example.com", "email_verified": True, "name": "Friend"}
    assert sign_in(client).headers["location"] == "/strelitzia/dashboard/"
    assert users.get(conn, invited.id).status == "active"
    assert client.get("/strelitzia/dashboard/api/whoami").json() == {"email": "friend@example.com"}
    assert client.get("/strelitzia/dashboard/api/auth/me").json()["user"] == {"email": "friend@example.com", "name": "Friend",
                                                              "role": "user"}


def test_uninvited_email_gets_no_session(auth_on, client, conn, google):
    google.claims = {"email": "stranger@example.com", "email_verified": True}
    resp = sign_in(client)
    assert resp.headers["location"] == "/strelitzia/dashboard/?auth=not_invited"
    assert users.by_email(conn, "stranger@example.com") is None
    assert client.get("/strelitzia/dashboard/api/auth/me").json() == {
        "enabled": True, "user": None, "mode": "google", "identity": None, "reason": None, "logout_url": None,
        "site_header_url": None, "site_admin": False, "users_url": None}
    assert client.get("/strelitzia/dashboard/api/whoami").status_code == 401


def test_unverified_email_is_refused(auth_on, client, conn, google):
    users.invite(conn, "friend@example.com")
    google.claims = {"email": "friend@example.com", "email_verified": False}
    assert sign_in(client).headers["location"] == "/strelitzia/dashboard/?auth=unverified"
    assert client.get("/strelitzia/dashboard/api/whoami").status_code == 401


def test_bad_state_is_rejected(auth_on, client, google):
    resp = sign_in(client, state="forged")
    assert resp.headers["location"] == "/strelitzia/dashboard/?auth=error"
    assert google.token_requests == []
    assert client.get("/strelitzia/dashboard/api/whoami").status_code == 401


def test_callback_without_a_login_is_rejected(auth_on, client, google):
    for state in ("anything", "\u00e9t\u00e9"):  # a non-ASCII state is refused too, not a 500
        resp = client.get("/strelitzia/dashboard/api/auth/callback", params={"code": "c0de", "state": state})
        assert resp.headers["location"] == "/strelitzia/dashboard/?auth=error"
    assert google.token_requests == []


def test_state_is_single_use(auth_on, client, google):
    login = client.get("/strelitzia/dashboard/api/auth/login")
    state = parse_qs(urlparse(login.headers["location"]).query)["state"][0]
    assert client.get("/strelitzia/dashboard/api/auth/callback", params={"code": "c0de", "state": state}).status_code == 303
    client.post("/strelitzia/dashboard/api/auth/logout")
    assert client.get("/strelitzia/dashboard/api/auth/callback", params={"code": "c0de", "state": state}).headers["location"] \
        == "/strelitzia/dashboard/?auth=error"
    assert len(google.token_requests) == 1


def test_rejected_id_token_signs_nobody_in(auth_on, client, google, monkeypatch):
    def reject(token, request, audience, clock_skew_in_seconds=0):
        raise ValueError("Token expired")

    monkeypatch.setattr(auth.id_token, "verify_oauth2_token", reject)
    assert sign_in(client).headers["location"] == "/strelitzia/dashboard/?auth=error"
    assert client.get("/strelitzia/dashboard/api/whoami").status_code == 401


def test_token_endpoint_trouble_signs_nobody_in(auth_on, client, google, monkeypatch):
    responses = iter([httpx.Response(200, text="<html>captive portal</html>"), httpx.Response(400, json={}),
                      httpx.Response(200, json={"access_token": "no id token"})])
    monkeypatch.setattr(auth.httpx, "post", lambda url, data=None, timeout=None: next(responses))
    for _ in range(3):
        assert sign_in(client).headers["location"] == "/strelitzia/dashboard/?auth=error"
    assert client.get("/strelitzia/dashboard/api/whoami").status_code == 401


def test_google_cert_fetch_failure_signs_nobody_in(auth_on, client, google, monkeypatch):
    from google.auth.exceptions import TransportError

    def unreachable(token, request, audience, clock_skew_in_seconds=0):
        raise TransportError("Could not fetch certificates")

    monkeypatch.setattr(auth.id_token, "verify_oauth2_token", unreachable)
    assert sign_in(client).headers["location"] == "/strelitzia/dashboard/?auth=error"


def test_sign_in_records_last_login(auth_on, client, conn, google):
    sign_in(client)
    first = conn.execute("SELECT last_login_at FROM users WHERE role = 'owner'").fetchone()[0]
    assert first
    conn.execute("UPDATE users SET last_login_at = '2000-01-01' WHERE role = 'owner'")
    conn.commit()
    sign_in(client)
    assert conn.execute("SELECT last_login_at FROM users WHERE role = 'owner'").fetchone()[0] > "2000-01-01"


def test_login_on_needs_the_other_keys(monkeypatch):
    monkeypatch.setenv("STRELITZIA_GOOGLE_CLIENT_ID", "client-123")
    for name in ("GOOGLE_CLIENT_SECRET", "SESSION_SECRET", "OWNER_EMAIL"):
        monkeypatch.delenv(f"STRELITZIA_{name}", raising=False)
    with pytest.raises(RuntimeError, match="OWNER_EMAIL"):
        auth.check_config()
    monkeypatch.setenv("STRELITZIA_GOOGLE_CLIENT_SECRET", "s")
    monkeypatch.setenv("STRELITZIA_SESSION_SECRET", "s")
    monkeypatch.setenv("STRELITZIA_OWNER_EMAIL", OWNER)
    auth.check_config()


def test_disabled_user_gets_401(auth_on, client, conn, google):
    friend = users.invite(conn, "friend@example.com")
    google.claims = {"email": "friend@example.com", "email_verified": True}
    sign_in(client)
    assert client.get("/strelitzia/dashboard/api/whoami").status_code == 200
    users.set_status(conn, friend.id, "disabled")
    assert client.get("/strelitzia/dashboard/api/whoami").status_code == 401
    assert client.get("/strelitzia/dashboard/api/auth/me").json()["user"] is None
    # and they can't sign back in, and are told why
    assert sign_in(client).headers["location"] == "/strelitzia/dashboard/?auth=disabled"
    assert client.get("/strelitzia/dashboard/api/whoami").status_code == 401


def test_logout_ends_the_session(auth_on, client, google):
    sign_in(client)
    assert client.get("/strelitzia/dashboard/api/whoami").status_code == 200
    assert client.post("/strelitzia/dashboard/api/auth/logout").json() == {"ok": True}
    assert client.get("/strelitzia/dashboard/api/whoami").status_code == 401


def test_login_off_acts_as_owner(client, conn, monkeypatch):
    monkeypatch.delenv("STRELITZIA_GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("APPLYPILOT_GOOGLE_CLIENT_ID", raising=False)
    assert not auth.auth_enabled()
    owner = users.owner(conn)
    assert client.get("/strelitzia/dashboard/api/whoami").json() == {"email": owner.email}
    assert client.get("/strelitzia/dashboard/api/auth/me").json() == {
        "enabled": False, "user": {"email": owner.email, "name": None, "role": "owner"}, "mode": "off",
        "identity": None, "reason": None, "logout_url": None, "site_header_url": None, "site_admin": False, "users_url": None}
    assert client.get("/strelitzia/dashboard/api/auth/login").headers["location"] == "/strelitzia/dashboard/"
    assert client.get("/strelitzia/dashboard/api/auth/callback", params={"code": "c", "state": "s"}).status_code == 404


# --- Connect Google Drive (user-auth-6-drive) ---

DRIVE_CALLBACK = "https://strelitzia.example.net/strelitzia/dashboard/api/drive/callback"


@pytest.fixture
def token_key(monkeypatch):
    from cryptography.fernet import Fernet
    monkeypatch.setenv("STRELITZIA_TOKEN_KEY", Fernet.generate_key().decode())


@pytest.fixture
def drive_google(google, monkeypatch):
    """The sign-in mock, plus Drive's token exchange: set `drive_google.drive_token` to Google's reply."""
    sign_in_post = auth.httpx.post

    class DriveGoogle:
        drive_token = {"access_token": "drive-access", "refresh_token": "drive-refresh", "expires_in": 3599,
                       "scope": f"openid {auth.DRIVE_SCOPE}", "token_type": "Bearer"}
        requests: list[dict] = []
        revoked: list[str] = []

    def fake_post(url, data=None, timeout=None):
        if url == auth.GOOGLE_REVOKE_URL:
            DriveGoogle.revoked.append(data["token"])
            return httpx.Response(200)
        if data and data.get("redirect_uri") == DRIVE_CALLBACK:
            DriveGoogle.requests.append(data)
            return httpx.Response(200, json=DriveGoogle.drive_token)
        return sign_in_post(url, data=data, timeout=timeout)

    monkeypatch.setattr(auth.httpx, "post", fake_post)
    return DriveGoogle


def connect_drive(client, state=None):
    start = client.get("/strelitzia/dashboard/api/drive/connect")
    assert start.status_code == 303
    query = parse_qs(urlparse(start.headers["location"]).query)
    return client.get("/strelitzia/dashboard/api/drive/callback", params={"code": "drive-c0de", "state": state or query["state"][0]})


def _token_rows(conn):
    return dict(conn.execute("SELECT user_id, token_enc FROM user_drive").fetchall())


def test_drive_connect_asks_only_for_drive_file_offline(auth_on, token_key, client, google):
    sign_in(client)
    start = client.get("/strelitzia/dashboard/api/drive/connect")
    assert start.status_code == 303
    url = urlparse(start.headers["location"])
    query = {k: v[0] for k, v in parse_qs(url.query).items()}
    assert f"{url.scheme}://{url.netloc}{url.path}" == auth.GOOGLE_AUTH_URL
    assert query["scope"] == "https://www.googleapis.com/auth/drive.file"
    assert query["access_type"] == "offline" and query["prompt"] == "consent"
    assert query["include_granted_scopes"] == "true"
    assert query["redirect_uri"] == DRIVE_CALLBACK and query["client_id"] == "client-123" and query["state"]
    assert query["login_hint"] == OWNER


def test_drive_connect_stores_a_token_for_the_session_user_only(auth_on, token_key, client, conn, google,
                                                                drive_google, monkeypatch):
    from strelitzia.storage import drive
    monkeypatch.setattr(drive, "drive_libraries_installed", lambda: True)
    friend = users.invite(conn, "friend@example.com")
    google.claims = {"email": "friend@example.com", "email_verified": True}
    sign_in(client)
    done = connect_drive(client)
    assert done.headers["location"] == "/strelitzia/dashboard/claude-setup?drive=connected"
    assert drive_google.requests[-1]["code"] == "drive-c0de"
    rows = _token_rows(conn)
    assert list(rows) == [friend.id]
    assert "drive-refresh" not in rows[friend.id] and "refresh_token" not in rows[friend.id]
    creds = drive.load_user_credentials(conn, friend.id)
    assert creds.refresh_token == "drive-refresh" and creds.token == "drive-access" and creds.client_id == "client-123"
    assert drive.user_drive_status(conn, users.owner(conn).id)[0] == "not_authorized"


def test_drive_callback_with_a_wrong_state_stores_nothing(auth_on, token_key, client, conn, google, drive_google):
    sign_in(client)
    assert connect_drive(client, state="forged").headers["location"] == "/strelitzia/dashboard/claude-setup?drive=error"
    assert client.get("/strelitzia/dashboard/api/drive/callback", params={"code": "c", "state": "s"}).headers["location"] == (
        "/strelitzia/dashboard/claude-setup?drive=error")
    assert _token_rows(conn) == {}


def test_drive_consent_without_the_drive_scope_is_denied(auth_on, token_key, client, conn, google, drive_google):
    sign_in(client)
    drive_google.drive_token = dict(drive_google.drive_token, scope="openid email")
    assert connect_drive(client).headers["location"] == "/strelitzia/dashboard/claude-setup?drive=denied"
    start = client.get("/strelitzia/dashboard/api/drive/connect")
    state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
    denied = client.get("/strelitzia/dashboard/api/drive/callback", params={"error": "access_denied", "state": state})
    assert denied.headers["location"] == "/strelitzia/dashboard/claude-setup?drive=denied"
    assert _token_rows(conn) == {}


def test_drive_token_without_a_refresh_token_is_an_error(auth_on, token_key, client, conn, google, drive_google):
    sign_in(client)
    drive_google.drive_token = {k: v for k, v in drive_google.drive_token.items() if k != "refresh_token"}
    assert connect_drive(client).headers["location"] == "/strelitzia/dashboard/claude-setup?drive=error"
    assert _token_rows(conn) == {}


def test_drive_connect_needs_a_session_and_the_token_key(auth_on, client, google, monkeypatch):
    assert client.get("/strelitzia/dashboard/api/drive/connect").status_code == 401
    monkeypatch.delenv("STRELITZIA_TOKEN_KEY", raising=False)
    monkeypatch.delenv("APPLYPILOT_TOKEN_KEY", raising=False)
    sign_in(client)
    assert client.get("/strelitzia/dashboard/api/drive/connect").headers["location"] == "/strelitzia/dashboard/claude-setup?drive=unavailable"


def test_drive_disconnect(auth_on, token_key, client, conn, google, drive_google):
    sign_in(client)
    connect_drive(client)
    assert list(_token_rows(conn)) == [users.owner(conn).id]
    assert client.post("/strelitzia/dashboard/api/drive/disconnect").json() == {"ok": True}
    assert _token_rows(conn) == {}
    assert drive_google.revoked == ["drive-refresh"]


def test_drive_disconnect_forgets_the_token_when_google_is_unreachable(auth_on, token_key, client, conn, google,
                                                                       drive_google, monkeypatch):
    sign_in(client)
    connect_drive(client)
    post = auth.httpx.post

    def unreachable(url, data=None, timeout=None):
        if url == auth.GOOGLE_REVOKE_URL:
            raise httpx.ConnectError("no route")
        return post(url, data=data, timeout=timeout)

    monkeypatch.setattr(auth.httpx, "post", unreachable)
    assert client.post("/strelitzia/dashboard/api/drive/disconnect").json() == {"ok": True}
    assert _token_rows(conn) == {}


# --- Proxy mode (site-sso-3-proxy-mode): the reverse proxy signs visitors in and passes the email in a header ---

ME = "/strelitzia/dashboard/api/auth/me"
JOBS = "/strelitzia/dashboard/api/jobs"


def as_email(email, name=None):
    headers = {"X-Strelitzia": "1", auth.PROXY_EMAIL_HEADER: email}
    if name is not None:
        headers[auth.PROXY_NAME_HEADER] = name
    return headers


@pytest.fixture
def proxy_on(monkeypatch):
    monkeypatch.setenv("STRELITZIA_AUTH_MODE", "proxy")
    monkeypatch.setenv("STRELITZIA_OWNER_EMAIL", OWNER)
    monkeypatch.setenv("STRELITZIA_SESSION_SECRET", "test-secret")


@pytest.fixture
def session_secret(monkeypatch):
    monkeypatch.setenv("STRELITZIA_SESSION_SECRET", "test-secret")


@pytest.fixture
def full_client(db, web_dir):
    """The whole app (its require_session middleware included), on the same database as `conn`."""
    from strelitzia.web.app import create_app

    with TestClient(create_app(static_dir=web_dir, db=db), follow_redirects=False) as c:
        yield c


def test_proxy_mode_needs_the_mode_setting(monkeypatch):
    assert auth.auth_mode() == "off"
    monkeypatch.setenv("STRELITZIA_GOOGLE_CLIENT_ID", "client-123")
    assert auth.auth_mode() == "google"
    monkeypatch.setenv("STRELITZIA_AUTH_MODE", "proxy")
    assert auth.auth_mode() == "proxy" and auth.auth_enabled()


def test_proxy_invited_email_reaches_the_api(proxy_on, full_client, conn):
    invited = users.invite(conn, "friend@example.com")
    assert full_client.get(JOBS, headers=as_email(" Friend@Example.com ", "Friend%20F%C3%A9")).status_code == 200
    activated = users.get(conn, invited.id)
    assert (activated.status, activated.name) == ("active", "Friend Fé")
    me = full_client.get(ME, headers=as_email("friend@example.com")).json()
    assert me["user"] == {"email": "friend@example.com", "name": "Friend Fé", "role": "user"}
    assert me["mode"] == "proxy" and me["reason"] is None and me["logout_url"] == "/auth/logout"


def test_proxy_without_the_header_is_401(proxy_on, full_client):
    resp = full_client.get(JOBS, headers={"X-Strelitzia": "1"})
    assert resp.status_code == 401 and resp.json() == {"detail": "Not signed in"}
    me = full_client.get(ME).json()
    assert me["enabled"] and me["user"] is None and me["identity"] is None and me["reason"] is None


def test_proxy_uninvited_email_is_told_why(proxy_on, full_client, conn):
    resp = full_client.get(JOBS, headers=as_email("stranger@example.com"))
    assert resp.status_code == 401 and resp.json() == {"detail": "not_invited"}
    me = full_client.get(ME, headers=as_email("stranger@example.com", "Stranger")).json()
    assert me["user"] is None and me["reason"] == "not_invited"
    assert me["identity"] == {"email": "stranger@example.com", "name": "Stranger"}
    assert users.by_email(conn, "stranger@example.com") is None


def test_proxy_disabled_account_is_told_why(proxy_on, full_client, conn):
    friend = users.invite(conn, "friend@example.com")
    assert full_client.get(JOBS, headers=as_email("friend@example.com")).status_code == 200
    users.set_status(conn, friend.id, "disabled")
    resp = full_client.get(JOBS, headers=as_email("friend@example.com"))
    assert resp.status_code == 401 and resp.json() == {"detail": "disabled"}
    assert full_client.get(ME, headers=as_email("friend@example.com")).json()["reason"] == "disabled"


def test_proxy_rekeys_the_placeholder_owner(full_client, conn, proxy_on):
    # The database (and its owner row) was created before STRELITZIA_OWNER_EMAIL was set.
    placeholder = users.owner(conn)
    assert placeholder.email == users.FALLBACK_OWNER_EMAIL
    me = full_client.get(ME, headers=as_email("Owner@Example.com", "Owner")).json()
    assert me["user"] == {"email": OWNER, "name": "Owner", "role": "owner"}
    assert users.owner(conn).id == placeholder.id


def test_proxy_admin_routes_are_owner_only(proxy_on, full_client, conn):
    users.invite(conn, "friend@example.com")
    assert full_client.get("/strelitzia/dashboard/api/admin/users", headers=as_email("friend@example.com")).status_code == 403
    assert full_client.get("/strelitzia/dashboard/api/admin/users", headers=as_email(OWNER)).status_code == 200


def test_proxy_headers_are_ignored_in_google_mode(auth_on, session_secret, full_client, conn):
    users.invite(conn, "friend@example.com")
    for email in (OWNER, "friend@example.com"):
        assert full_client.get(JOBS, headers=as_email(email)).status_code == 401
        me = full_client.get(ME, headers=as_email(email)).json()
        assert me["user"] is None and me["identity"] is None and me["mode"] == "google" and me["logout_url"] is None


def test_proxy_headers_are_ignored_with_login_off(full_client, conn):
    users.invite(conn, "friend@example.com")
    me = full_client.get(ME, headers=as_email("friend@example.com")).json()
    assert me["user"]["role"] == "owner" and me["identity"] is None and me["mode"] == "off"


def test_proxy_login_sends_to_the_site(proxy_on, client, monkeypatch):
    resp = client.get("/strelitzia/dashboard/api/auth/login")
    assert resp.status_code == 303
    assert resp.headers["location"] == "/auth/login?next=%2Fstrelitzia%2Fdashboard%2F"
    monkeypatch.setenv("STRELITZIA_SITE_LOGIN_URL", "https://example.net/auth/login?prompt=select_account")
    assert client.get("/strelitzia/dashboard/api/auth/login").headers["location"] == (
        "https://example.net/auth/login?prompt=select_account&next=%2Fstrelitzia%2Fdashboard%2F")
    assert client.get("/strelitzia/dashboard/api/auth/callback", params={"code": "c", "state": "s"}).status_code == 404


def test_proxy_logout_points_at_the_site(proxy_on, client, monkeypatch):
    monkeypatch.setenv("STRELITZIA_SITE_LOGOUT_URL", "https://example.net/auth/logout")
    resp = client.post("/strelitzia/dashboard/api/auth/logout")
    assert resp.json() == {"ok": True, "logout_url": "https://example.net/auth/logout"}


def test_site_header_url_in_any_mode(client, monkeypatch):
    assert client.get(ME).json()["site_header_url"] is None
    monkeypatch.setenv("STRELITZIA_SITE_HEADER_URL", "/shared/site-header.js")
    assert client.get(ME).json()["site_header_url"] == "/shared/site-header.js"


def test_proxy_me_records_last_login_at_most_hourly(proxy_on, client, conn):
    def last_login():
        return conn.execute("SELECT last_login_at FROM users WHERE role = 'owner'").fetchone()[0]

    client.get(ME, headers=as_email(OWNER))
    first = last_login()
    assert first
    client.get(ME, headers=as_email(OWNER))
    assert last_login() == first
    client.get("/strelitzia/dashboard/api/whoami", headers=as_email(OWNER))
    assert last_login() == first
    conn.execute("UPDATE users SET last_login_at = '2000-01-01T00:00:00+00:00' WHERE role = 'owner'")
    conn.commit()
    client.get(ME, headers=as_email(OWNER))
    assert last_login() > "2000-01-01"


def test_proxy_config_needs_owner_and_session_secret(monkeypatch):
    monkeypatch.setenv("STRELITZIA_AUTH_MODE", "proxy")
    with pytest.raises(RuntimeError, match="OWNER_EMAIL"):
        auth.check_config()
    monkeypatch.setenv("STRELITZIA_OWNER_EMAIL", OWNER)
    with pytest.raises(RuntimeError, match="SESSION_SECRET"):
        auth.check_config()
    monkeypatch.setenv("STRELITZIA_SESSION_SECRET", "s")
    auth.check_config()  # no Google secret needed
    assert not auth.drive_connect_available()


# --- Site grant (site-perms-4): engineerfamily's nginx says who may use the dashboard and with what cap ---

def granted(email, name=None, cap="5", admin="0"):
    return {**as_email(email, name), auth.ACCESS_HEADER: "strelitzia", auth.ADMIN_HEADER: admin,
            auth.CAP_HEADER: cap}


def test_grant_creates_and_activates_an_unknown_email(proxy_on, full_client, conn):
    assert full_client.get(JOBS, headers=granted("New@Example.com", "New%20Person", cap="1.5")).status_code == 200
    user = users.by_email(conn, "new@example.com")
    assert (user.role, user.status, user.name, user.monthly_cap_usd) == ("user", "active", "New Person", 1.5)


def test_grant_reactivates_a_disabled_account(proxy_on, full_client, conn):
    friend = users.invite(conn, "friend@example.com")
    users.set_status(conn, friend.id, "disabled")
    assert full_client.get(JOBS, headers=granted("friend@example.com")).status_code == 200
    assert users.get(conn, friend.id).status == "active"


def test_grant_writes_the_cap(proxy_on, full_client, conn):
    friend = users.invite(conn, "friend@example.com")
    full_client.get(JOBS, headers=granted("friend@example.com", cap="0"))
    assert users.get(conn, friend.id).monthly_cap_usd == 0
    full_client.get(JOBS, headers=granted("friend@example.com", cap="none"))
    assert users.get(conn, friend.id).monthly_cap_usd is None
    full_client.get(JOBS, headers=granted("friend@example.com", cap="lots"))
    assert users.get(conn, friend.id).monthly_cap_usd == users.DEFAULT_CAP_USD


def test_grant_leaves_the_owner_alone(proxy_on, full_client, conn):
    owner = users.owner(conn)
    full_client.get(JOBS, headers=granted(OWNER, cap="1"))
    after = users.get(conn, owner.id)
    assert (after.role, after.status, after.monthly_cap_usd) == ("owner", "active", None)


def test_grant_is_shown_in_me(proxy_on, full_client, conn, monkeypatch):
    monkeypatch.setenv("STRELITZIA_PUBLIC_URL", "https://preprod.example.net/strelitzia/dashboard")
    me = full_client.get(ME, headers=granted("friend@example.com", admin="1", cap="none")).json()
    assert me["user"]["email"] == "friend@example.com"
    assert me["site_admin"] is True and me["users_url"] == "https://preprod.example.net/users/"
    me = full_client.get(ME, headers=granted("friend@example.com")).json()
    assert me["site_admin"] is False
    me = full_client.get(ME, headers=as_email("friend@example.com")).json()
    assert me["site_admin"] is False and me["users_url"] is None


def test_without_the_access_header_the_invite_list_decides(proxy_on, full_client, conn):
    for headers in (as_email("stranger@example.com"),
                    {**as_email("stranger@example.com"), auth.ACCESS_HEADER: "other", auth.CAP_HEADER: "1"}):
        resp = full_client.get(JOBS, headers=headers)
        assert resp.status_code == 401 and resp.json() == {"detail": "not_invited"}
    assert users.by_email(conn, "stranger@example.com") is None


def test_grant_headers_are_ignored_in_google_mode(auth_on, session_secret, full_client, conn):
    assert full_client.get(JOBS, headers=granted("stranger@example.com")).status_code == 401
    assert users.by_email(conn, "stranger@example.com") is None
