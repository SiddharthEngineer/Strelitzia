"""The Profile Docs in Google Drive (`Strelitzia/Profile/`): the source of truth for the content library and the
base resume, plus About me (the personal answers a cover letter needs).

`setup_profile_docs` creates the Docs from the database copy (or example templates), and `pull_profile` reads
them back into the database (`user_profiles`, and app_state for About me) and, for the owner, the local files the CLI
uses. A pull with any problem saves nothing, so a broken Doc never replaces good data. About me never blocks a pull:
its trouble is a warning, and a pull creates it when it is missing (users who set up before it existed).

The Drive scope is drive.file, so the app only sees Docs it created: setup never overwrites without `overwrite=True`.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime

from strelitzia import config
from strelitzia.database import get_state, set_state
from strelitzia.profile import load_profile, save_profile
from strelitzia.scoring.content_library import normalize_docs_markdown, parse_content_library_text
from strelitzia.storage.drive_layout import PROFILE_DOCS, profile_folder_path

log = logging.getLogger(__name__)

_STATE_KEY = "{}:profile_doc:{}"  # user id, kind
_ABOUT_KEY = "{}:profile_text:about"  # user id -> the About me Doc's text from the last pull
# How each Doc is uploaded (Google converts it to a formatted Doc) and exported.
_MIME = {"library": "text/markdown", "resume": "text/plain", "about": "text/markdown"}

# Example text for a user with nothing in the database yet (no personal data).
TEMPLATE_LIBRARY = """# Content library

Each role is a `## CURRENT ROLE` or `## PRIOR ROLE` heading, and each project under it a `###` heading. Every project
needs the fields below; Angles is a comma-separated list of tags. Responsibility (what you owned and for whom, one
line) and Detail (code-level facts for interviews) are optional. Replace this example with your own work.

## CURRENT ROLE — Job Title, Company (Jan 2024–Present)

### Example Project (Jan 2024–present)

- **Responsibility:** What you owned and for whom, in one line.
- **Context:** What the project was and why it mattered.
- **Scope/Scale:** How big it was: users, data, teams, money.
- **Tools/Actions:** What you used and what you did.
- **Outcome/Metrics:** What changed, with numbers.
- **Angles:** PIPELINE, LEADERSHIP
- **Detail:** How the code works: libraries, file formats, tricky parts.

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

# The questions answered once (agents/research/cover-letter.md §5); the per-job ones are the job page's notes.
ABOUT_QUESTIONS = (
    "How did you get into engineering or data? A specific moment, not a summary.",
    "What kind of problem makes you lose track of time? One example.",
    "The piece of work you're proudest of, and the hard decision in it.",
    "A time something broke in production or the data was wrong. What did you do?",
    "What would a former manager or teammate say you're unusually good at? Real feedback if you have it.",
    "What do you want to be much better at in 2-3 years?",
    "What kind of team and environment brings out your best work?",
    "Why these industries or domains? Up to 3, with a true reason for each.",
    "Values or working habits you care about, with an example of each.",
    "A non-work interest or side project worth mentioning (only if relevant or memorable).",
    "Anything a reader might misread on your resume (gap, short tenure, field change), with one line of context.",
    "Constraints: work authorisation or sponsorship, relocation, location or remote, start date.",
    "Three phrases you'd never say, plus a short sample of your own writing as a voice reference.",
)

TEMPLATE_ABOUT = "# About me\n\n" + (
    "Claude reads this for your cover letters: the things a resume never says. Write each answer under its question, "
    "in your own words, with a specific moment or example. Skip any that don't apply.\n\n"
) + "".join(f"## {i}. {q}\n\n" for i, q in enumerate(ABOUT_QUESTIONS, 1))


class ProfileDocsExist(Exception):
    """Setup would overwrite Profile Docs the user already has."""

    def __init__(self, names: list[str]):
        super().__init__("These Profile Docs already exist: " + ", ".join(names))
        self.names = names


@dataclass
class ProfileDocs:  # stored per user in state "{user}:profile_doc:{kind}" as {"id","url","synced_at","modified"}
    library: dict | None = None
    resume: dict | None = None
    about: dict | None = None


@dataclass
class SyncResult:
    ok: bool
    problems: list[str]
    changed: bool
    warnings: list[str] = field(default_factory=list)  # About me trouble: shown, but the pull still saved


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


def about_text(conn, user_id: str) -> str:
    """The About me Doc's text from the last pull ("" before one)."""
    return get_state(conn, _ABOUT_KEY.format(user_id)) or ""


def _existing_kinds(client, conn, user_id: str) -> dict[str, str]:
    """{kind: name} of the Profile Docs the app can still see: the stored ids, else same-named Docs in Profile/."""
    docs = profile_docs(conn, user_id)
    found, folder_id = {}, None
    for kind, name in PROFILE_DOCS.items():
        stored = getattr(docs, kind) or {}
        meta = client.doc_meta(stored["id"]) if stored.get("id") else None
        if meta and not meta.get("trashed"):
            found[kind] = name
            continue
        folder_id = folder_id or client.ensure_folder_path(profile_folder_path())
        if client.find_doc(folder_id, name):
            found[kind] = name
    return found


def existing_docs(client, conn, user_id: str) -> list[str]:
    """Names of the Profile Docs the app can still see: the stored ids, else same-named Docs in Profile/."""
    return list(_existing_kinds(client, conn, user_id).values())


def setup_profile_docs(client, conn, user_id: str, *, overwrite: bool) -> ProfileDocs:
    """Create the Profile Docs from the database copy (example templates where it is empty).

    Raises ProfileDocsExist when the user already has them and not `overwrite`; with it they are updated in place.
    A user with only About me missing (set up before it existed) gets just that Doc, the other two untouched.
    """
    kinds = list(PROFILE_DOCS)
    if not overwrite:
        found = _existing_kinds(client, conn, user_id)
        kinds = [k for k in PROFILE_DOCS if k not in found]
        if found and kinds != ["about"]:
            raise ProfileDocsExist(list(found.values()))
    profile = load_profile(conn, user_id)
    library, resume, about = profile.content_library_md, profile.resume_text, about_text(conn, user_id)
    seed = {"library": library if library.strip() else TEMPLATE_LIBRARY,
            "resume": resume if resume.strip() else TEMPLATE_RESUME,
            "about": about if about.strip() else TEMPLATE_ABOUT}
    docs = profile_docs(conn, user_id)
    folder_id = client.ensure_folder_path(profile_folder_path())
    for kind in kinds:
        name = PROFILE_DOCS[kind]
        prev = getattr(docs, kind) or {}
        f = client.create_doc_from_text(folder_id, name, seed[kind], _MIME[kind], known_id=prev.get("id"))
        state = {"id": f.id, "url": f.url, "synced_at": _now(), "modified": f.modified}
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


def has_about_answers(text: str) -> bool:
    """Whether the About me text has at least one answer: any text under a `##` question heading."""
    in_question = False
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            in_question = line.lstrip().startswith("##")
        elif in_question and line.strip(" \t*_-\\"):
            return True
    return False


def _normalize_about(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\u00a0", " ").lstrip("\ufeff")
    return re.sub(r"\\([\\`*_{}\[\]()#+\-.!])", r"\1", text).strip() + "\n"


def _pull_about(client, conn, user_id: str, stored: dict) -> tuple[dict | None, str | None, list[str]]:
    """(Doc state, text, warnings) for About me, creating the Doc when the user has none yet."""
    name = PROFILE_DOCS["about"]
    try:
        meta = client.doc_meta(stored["id"]) if stored.get("id") else None
        if meta and meta.get("trashed"):
            return None, None, [f"The {name} Doc is in the trash: restore it, or empty the trash and sync again "
                                "for a new one."]
        if not meta:
            seed = about_text(conn, user_id)
            f = client.create_doc_from_text(client.ensure_folder_path(profile_folder_path()), name,
                                            seed if seed.strip() else TEMPLATE_ABOUT, _MIME["about"],
                                            known_id=stored.get("id"))
            meta = {"id": f.id, "webViewLink": f.url, "modifiedTime": f.modified}
        text = _normalize_about(client.export_text(meta["id"], _MIME["about"]))
    except Exception as e:  # noqa: BLE001 -- any Drive error is a warning, never raised
        log.warning("Reading the %s Doc from Drive failed: %s", name, e)
        return None, None, [f"The {name} Doc couldn't be read from Drive."]
    state = dict(stored, id=meta["id"], synced_at=_now(), modified=meta.get("modifiedTime"))
    state["url"] = meta.get("webViewLink") or state.get("url", "")
    warnings = [] if has_about_answers(text) else [
        f"The {name} Doc has no answers yet: Claude needs them for your cover letters."]
    return state, text, warnings


def pull_profile(client, conn, user_id: str, *, is_owner: bool) -> SyncResult:
    """Read the Profile Docs into the database and, for the owner, the local files. Any problem saves nothing.

    About me is read after the other two pass; its trouble comes back as warnings and saves the rest anyway.
    """
    docs = profile_docs(conn, user_id)
    problems: list[str] = []
    texts: dict[str, str] = {}
    metas: dict[str, dict] = {}
    for kind, name in PROFILE_DOCS.items():
        if kind == "about":
            continue
        stored = getattr(docs, kind) or {}
        try:
            meta = client.doc_meta(stored["id"]) if stored.get("id") else None
            if not meta or meta.get("trashed"):
                state = "isn't set up" if not stored.get("id") else "is in the trash" if meta else "is missing"
                problems.append(f"The {name} Doc {state}.")
                continue
            texts[kind] = client.export_text(meta["id"], _MIME[kind])
        except Exception as e:  # noqa: BLE001 -- any Drive error is reported, never raised
            log.warning("Reading the %s Doc from Drive failed: %s", name, e)
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
    about_state, about, warnings = _pull_about(client, conn, user_id, docs.about or {})

    # The owner's files are written to temporary files first, so a failed write leaves everything as it was.
    files = [(config.CONTENT_LIBRARY_PATH, texts["library"]), (config.RESUME_PATH, texts["resume"])] if is_owner else []
    staged = []
    try:
        for path, text in files:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(path.name + ".tmp")
            tmp.write_text(text, encoding="utf-8")
            staged.append((tmp, path))
        profile = load_profile(conn, user_id)
        changed = (profile.content_library_md, profile.resume_text) != (texts["library"], texts["resume"])
        if about is not None:
            changed = changed or about != about_text(conn, user_id)
            set_state(conn, _ABOUT_KEY.format(user_id), about)
            _save_state(conn, user_id, "about", about_state)
        profile.content_library_md, profile.resume_text = texts["library"], texts["resume"]
        synced_at = _now()
        for kind in ("library", "resume"):
            state = dict(getattr(docs, kind), synced_at=synced_at, modified=metas[kind].get("modifiedTime"))
            state["url"] = metas[kind].get("webViewLink") or state.get("url", "")
            _save_state(conn, user_id, kind, state)
        save_profile(conn, user_id, profile)  # commits the sync state with it
    except BaseException:
        conn.rollback()
        for tmp, _ in staged:
            tmp.unlink(missing_ok=True)
        raise
    for tmp, path in staged:
        os.replace(tmp, path)
    return SyncResult(ok=True, problems=[], changed=changed, warnings=warnings)
