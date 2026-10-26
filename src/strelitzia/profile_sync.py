"""The Profile Docs in Google Drive (`Strelitzia/Profile/`): the source of truth for the content library and the
base resume.

`setup_profile_docs` creates the two Docs from the database copy (or example templates), and `pull_profile` reads
them back into the database (`user_profiles`) and, for the owner, the local files the CLI uses. A pull with any
problem saves nothing, so a broken Doc never replaces good data.

The Drive scope is drive.file, so the app only sees Docs it created: setup never overwrites without `overwrite=True`.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from strelitzia import config
from strelitzia.database import get_state, set_state
from strelitzia.profile import load_profile, save_profile
from strelitzia.scoring.content_library import normalize_docs_markdown, parse_content_library_text
from strelitzia.storage.drive_layout import PROFILE_DOCS, profile_folder_path

log = logging.getLogger(__name__)

_STATE_KEY = "{}:profile_doc:{}"  # user id, kind
# How each Doc is uploaded (Google converts it to a formatted Doc) and exported.
_MIME = {"library": "text/markdown", "resume": "text/plain"}

# Example text for a user with nothing in the database yet (no personal data).
TEMPLATE_LIBRARY = """# Content library

Each role is a `## CURRENT ROLE` or `## PRIOR ROLE` heading, and each project under it a `###` heading. Every project
needs the fields below; Angles is a comma-separated list of tags. Replace this example with your own work.

## CURRENT ROLE — Job Title, Company (Jan 2024–Present)

### Example Project (Jan 2024–present)

- **Context:** What the project was and why it mattered.
- **Scope/Scale:** How big it was: users, data, teams, money.
- **Tools/Actions:** What you used and what you did.
- **Outcome/Metrics:** What changed, with numbers.
- **Angles:** PIPELINE, LEADERSHIP

## PRIOR ROLE — Job Title, Company (Jun 2022–Dec 2023)

### Another Example Project (Jun 2022–Dec 2023)

- **Context:** What the project was and why it mattered.
- **Scope/Scale:** How big it was.
- **Tools/Actions:** What you used and what you did.
- **Outcome/Metrics:** What changed, with numbers.
- **Angles:** ANALYTICS
"""

TEMPLATE_RESUME = """Your Name
City, Country · you@example.com · linkedin.com/in/you

SUMMARY
One or two lines on what you do and what you are looking for.

EXPERIENCE
Job Title, Company (Jan 2024–Present)
- What you did, with numbers.

Job Title, Company (Jun 2022–Dec 2023)
- What you did, with numbers.

EDUCATION
Degree, School (2022)

SKILLS
Skill one, skill two, skill three
"""


class ProfileDocsExist(Exception):
    """Setup would overwrite Profile Docs the user already has."""

    def __init__(self, names: list[str]):
        super().__init__("These Profile Docs already exist: " + ", ".join(names))
        self.names = names


@dataclass
class ProfileDocs:  # stored per user in state "{user}:profile_doc:{kind}" as {"id","url","synced_at","modified"}
    library: dict | None = None
    resume: dict | None = None


@dataclass
class SyncResult:
    ok: bool
    problems: list[str]
    changed: bool


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _save_state(conn, user_id: str, kind: str, state: dict) -> None:
    set_state(conn, _STATE_KEY.format(user_id, kind), json.dumps(state))


def profile_docs(conn, user_id: str) -> ProfileDocs:
    out = ProfileDocs()
    for kind in PROFILE_DOCS:
        raw = get_state(conn, _STATE_KEY.format(user_id, kind))
        if raw:
            setattr(out, kind, json.loads(raw))
    return out


def existing_docs(client, conn, user_id: str) -> list[str]:
    """Names of the Profile Docs the app can still see: the stored ids, else same-named Docs in Profile/."""
    docs = profile_docs(conn, user_id)
    names, folder_id = [], None
    for kind, name in PROFILE_DOCS.items():
        stored = getattr(docs, kind) or {}
        meta = client.doc_meta(stored["id"]) if stored.get("id") else None
        if meta and not meta.get("trashed"):
            names.append(name)
            continue
        folder_id = folder_id or client.ensure_folder_path(profile_folder_path())
        if client.find_doc(folder_id, name):
            names.append(name)
    return names


def setup_profile_docs(client, conn, user_id: str, *, overwrite: bool) -> ProfileDocs:
    """Create the two Profile Docs from the database copy (example templates where it is empty).

    Raises ProfileDocsExist when the user already has them and not `overwrite`; with it they are updated in place.
    """
    if not overwrite:
        found = existing_docs(client, conn, user_id)
        if found:
            raise ProfileDocsExist(found)
    profile = load_profile(conn, user_id)
    library, resume = profile.content_library_md, profile.resume_text
    seed = {"library": library if library.strip() else TEMPLATE_LIBRARY,
            "resume": resume if resume.strip() else TEMPLATE_RESUME}
    docs = profile_docs(conn, user_id)
    folder_id = client.ensure_folder_path(profile_folder_path())
    for kind, name in PROFILE_DOCS.items():
        prev = getattr(docs, kind) or {}
        f = client.create_doc_from_text(folder_id, name, seed[kind], _MIME[kind], known_id=prev.get("id"))
        meta = client.doc_meta(f.id) or {}
        state = {"id": f.id, "url": f.url, "synced_at": _now(), "modified": meta.get("modifiedTime")}
        _save_state(conn, user_id, kind, state)
        setattr(docs, kind, state)
    conn.commit()
    return docs


def _library_problems(text: str) -> list[str]:
    name = PROFILE_DOCS["library"]
    try:
        library = parse_content_library_text(text)
    except ValueError as e:
        return [f"The {name} Doc couldn't be read: {e}"]
    projects = [p for r in library.roles for p in r.projects]
    if not projects:
        return [f"The {name} Doc has no projects: it needs `CURRENT ROLE` or `PRIOR ROLE` headings with a "
                "heading for each project under them."]
    return [f"The project “{p.name}” in the {name} Doc has no Angles." for p in projects if not p.angles]


def pull_profile(client, conn, user_id: str, *, is_owner: bool) -> SyncResult:
    """Read both Profile Docs into the database and, for the owner, the local files. Any problem saves nothing."""
    docs = profile_docs(conn, user_id)
    problems: list[str] = []
    texts: dict[str, str] = {}
    metas: dict[str, dict] = {}
    for kind, name in PROFILE_DOCS.items():
        stored = getattr(docs, kind) or {}
        meta = client.doc_meta(stored["id"]) if stored.get("id") else None
        if not meta or meta.get("trashed"):
            state = "isn't set up" if not stored.get("id") else "is in the trash" if meta else "is missing"
            problems.append(f"The {name} Doc {state}.")
            continue
        try:
            texts[kind] = client.export_text(meta["id"], _MIME[kind])
        except Exception as e:  # noqa: BLE001 -- any Drive error is reported, never raised
            log.warning("Exporting the %s Doc failed: %s", name, e)
            problems.append(f"The {name} Doc couldn't be read from Drive.")
            continue
        metas[kind] = meta
    if "library" in texts:
        texts["library"] = normalize_docs_markdown(texts["library"]).strip() + "\n"
        problems += _library_problems(texts["library"])
    if "resume" in texts:
        texts["resume"] = texts["resume"].replace("\r\n", "\n").strip() + "\n"
        if not texts["resume"].strip():
            problems.append(f"The {PROFILE_DOCS['resume']} Doc is empty.")
    if problems:
        return SyncResult(ok=False, problems=problems, changed=False)

    profile = load_profile(conn, user_id)
    changed = (profile.content_library_md, profile.resume_text) != (texts["library"], texts["resume"])
    profile.content_library_md, profile.resume_text = texts["library"], texts["resume"]
    save_profile(conn, user_id, profile)
    if is_owner:
        for path, text in ((config.CONTENT_LIBRARY_PATH, texts["library"]), (config.RESUME_PATH, texts["resume"])):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
    synced_at = _now()
    for kind in PROFILE_DOCS:
        state = dict(getattr(docs, kind), synced_at=synced_at, modified=metas[kind].get("modifiedTime"))
        state["url"] = metas[kind].get("webViewLink") or state.get("url", "")
        _save_state(conn, user_id, kind, state)
    conn.commit()
    return SyncResult(ok=True, problems=[], changed=changed)
