"""The draft Docs: a readable resume and cover-letter format that Claude (or the user) writes into two Google Docs.

`resume_draft_text` / `cover_draft_text` render a result (or a skeleton) to seed the Docs, and the parsers read a
Doc's markdown export back into the same result dict a JSON paste produces, so `workbench.check_result` and the
renderer stay the single source of rules. Unknown `##` sections are kept as role keys, so a typo in a role key is
reported by the schema check (with the valid keys) instead of being dropped.

Resume Doc:

    Rules version: 1a2b3c4d
    Instructions version: 5e6f7a8b
    Summary: Data engineer with 6 years in finance analytics, moving 40M rows a night

    ## <role-key>
    - Bullet text written for the posting [project-slug, other-slug]

    ## Dropped roles
    - <role-key>

    ## Skills
    - Languages: Python, SQL

    ## Notes for me
    Free text.

`Summary:` is optional (empty = none; an old `Headline:` line still parses as the Summary). The two version
lines are what Claude read in the packet and its project instructions (`workbench` warns when
either is missing or old). Cover letter Doc: an optional `Rules version:` line, the paragraphs separated by blank lines, then a last line
`Evidence: slug-a, slug-b`.
"""

from __future__ import annotations

import re

from strelitzia.scoring.content_library import ContentLibrary, normalize_docs_markdown

DROPPED, SKILLS, NOTES = "Dropped roles", "Skills", "Notes for me"
_SECTIONS = {DROPPED.lower(): DROPPED, SKILLS.lower(): SKILLS, NOTES.lower(): NOTES}
PLACEHOLDER_BULLET = "Replace this line with a bullet for this role"
COVER_PLACEHOLDER = "Write the cover letter here: three paragraphs, then a last line \"Evidence: slug-a, slug-b\"."

_HEADING = re.compile(r"^#{1,3}\s+(.+?)\s*#*\s*$")
_BULLET = re.compile(r"^\s*[-*+]\s+(.*)$")
_TAGS = re.compile(r"\s*\[([^\[\]]*)\]\s*$")
_KEY_LINE = re.compile(r"^\s*(rules version|instructions version|summary|headline)\s*:\s*(.*?)\s*$", re.I)
_VERSION_KEYS = {"rules version": "rules", "instructions version": "instructions"}
_EVIDENCE = re.compile(r"^\s*evidence\s*:\s*(.*?)\s*$", re.I)


class DraftFormatError(ValueError):
    """A draft Doc doesn't follow the format; `errors` name the line or section of each problem."""

    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


def _lines(text: str) -> list[str]:
    return normalize_docs_markdown(text or "").split("\n")


def _slugs(raw: str) -> list[str]:
    return [s.strip().strip("`") for s in raw.split(",") if s.strip().strip("`")]


# ── Resume ────────────────────────────────────────────────────────────────

def resume_draft_text(result: dict | None, library: ContentLibrary, rules_version: str,
                      instructions_version: str = "") -> str:
    """The resume Doc's text: the result's resume, or (result=None) a skeleton with one section per library role."""
    library.ensure_keys()
    out = [f"Rules version: {rules_version}", f"Instructions version: {instructions_version}"]
    if result is None:
        out += ["Summary: ", ""]
        for role in library.roles:
            slug = role.projects[0].slug if role.projects else "project-slug"
            out += [f"## {role.key}", f"- {PLACEHOLDER_BULLET} [{slug}]", ""]
        out += [f"## {DROPPED}", "", f"## {SKILLS}", "", f"## {NOTES}", ""]
        return "\n".join(out).rstrip() + "\n"
    resume = result.get("resume") or {}
    out += [f"Summary: {resume.get('headline') or ''}", ""]
    for role in resume.get("roles") or []:
        out.append(f"## {role['role_key']}")
        out += [f"- {b['text']} [{', '.join(b.get('project_ids') or [])}]" for b in role.get("bullets") or []]
        out.append("")
    out.append(f"## {DROPPED}")
    out += [f"- {key}" for key in resume.get("dropped_roles") or []]
    out += ["", f"## {SKILLS}"]
    out += [f"- {s['category']}: {s['items']}" for s in resume.get("skills") or []]
    out += ["", f"## {NOTES}"]
    if (result.get("notes_for_user") or "").strip():
        out.append(result["notes_for_user"].strip())
    return "\n".join(out).rstrip() + "\n"


def parse_resume_draft(text: str) -> tuple[dict, dict[str, str | None], str]:
    """(resume dict, {"rules", "instructions"} versions (None when missing), notes for the user) from the resume Doc.

    Raises:
        DraftFormatError: with one message per problem, each naming its line or section.
    """
    errors: list[str] = []
    headline, versions = "", {"rules": None, "instructions": None}
    in_summary = False  # lines right after "Summary:" continue it (a 1-2 line Summary may wrap)
    roles: list[dict] = []
    dropped: list[str] = []
    skills: list[dict] = []
    notes: list[str] = []
    seen: set[str] = set()
    section: str | None = None  # a known section name, or a role key
    current: dict | None = None
    heading_line = 0
    has_items = False  # the current role has list items (even bad ones, which are reported on their own)

    def close_role() -> None:
        if current is not None and not has_items:
            errors.append(f"Line {heading_line}: the role \"{current['role_key']}\" has no bullets; add bullets or "
                          f"list it under \"## {DROPPED}\"")

    for no, line in enumerate(_lines(text), 1):
        if not line.strip():
            if section == NOTES and notes:
                notes.append("")
            continue
        heading = _HEADING.match(line)
        if heading:
            close_role()
            name = heading.group(1).replace("**", "").strip()
            section, current, heading_line, has_items = _SECTIONS.get(name.lower(), name), None, no, False
            if section not in _SECTIONS.values():
                if section in seen:
                    errors.append(f"Line {no}: the role \"{section}\" appears twice")
                seen.add(section)
                current = {"role_key": section, "bullets": []}
                roles.append(current)
            continue
        if section == NOTES:
            notes.append(line.strip())
            continue
        if section is None:
            key = _KEY_LINE.match(line)
            if key and key.group(1).lower() in ("summary", "headline"):
                headline, in_summary = key.group(2), True
            elif key:
                versions[_VERSION_KEYS[key.group(1).lower()]] = key.group(2) or None
                in_summary = False
            elif in_summary:
                headline = f"{headline} {line.strip()}".strip()
            else:
                errors.append(f"Line {no}: only the \"Rules version:\", \"Instructions version:\" and \"Summary:\" "
                              "lines go above the first ## heading")
            continue
        bullet = _BULLET.match(line)
        if not bullet:
            errors.append(f"Line {no}: \"{line.strip()[:60]}\" isn't a \"- \" list item (under \"## {section}\")")
            continue
        item = bullet.group(1).strip()
        has_items = True
        if section == DROPPED:
            dropped.append(item)
        elif section == SKILLS:
            category, sep, items = item.partition(":")
            if not sep or not category.strip():
                errors.append(f"Line {no}: a skills line is \"- Category: skill, skill\"")
            else:
                skills.append({"category": category.strip(), "items": items.strip()})
        else:
            tags = _TAGS.search(item)
            body = item[:tags.start()].strip() if tags else item
            if body.startswith(PLACEHOLDER_BULLET):
                errors.append(f"Line {no}: replace the placeholder bullet with a real one")
            elif not tags or not _slugs(tags.group(1)):
                errors.append(f"Line {no}: bullet has no [slug] tags at the end")
            elif not body:
                errors.append(f"Line {no}: bullet has tags but no text")
            else:
                current["bullets"].append({"text": body, "project_ids": _slugs(tags.group(1))})
    close_role()
    if errors:
        raise DraftFormatError(errors)
    resume = {"headline": headline, "roles": roles, "skills": skills, "dropped_roles": dropped}
    return resume, versions, "\n".join(notes).strip()


# ── Cover letter ──────────────────────────────────────────────────────────

def cover_draft_text(cover: dict | None, rules_version: str) -> str:
    """The cover letter Doc's text: the paragraphs and the Evidence line, or (cover=None) a placeholder.

    The Rules version line is written only when one is given (the app seeds the Docs without it).
    """
    out = [f"Rules version: {rules_version}", ""] if rules_version else []
    if cover is None:
        return "\n".join(out + [COVER_PLACEHOLDER]) + "\n"
    for paragraph in cover.get("paragraphs") or []:
        out += [paragraph.strip(), ""]
    out.append("Evidence: " + ", ".join(cover.get("evidence_slugs") or []))
    return "\n".join(out) + "\n"


def _cover_lines(text: str) -> tuple[list[str], str | None]:
    """The letter's lines without the leading version lines, and the Rules version."""
    lines, version = _lines(text), None
    while (first := next((i for i, x in enumerate(lines) if x.strip()), None)) is not None:
        key = _KEY_LINE.match(lines[first])
        if not key or key.group(1).lower() not in _VERSION_KEYS:
            break
        if key.group(1).lower() == "rules version":
            version = key.group(2) or None
        lines = lines[:first] + lines[first + 1:]
    return lines, version


def parse_cover_draft(text: str) -> dict | None:
    """{"paragraphs", "evidence_slugs"} from the cover letter Doc, or None when it's empty (or the placeholder).

    Raises:
        DraftFormatError: no last "Evidence:" line.
    """
    lines, _ = _cover_lines(text)
    body = "\n".join(lines).strip()
    if not body or body == COVER_PLACEHOLDER:
        return None
    rows = body.split("\n")
    evidence = _EVIDENCE.match(rows[-1])
    if not evidence:
        raise DraftFormatError(["The last line must be \"Evidence: slug-a, slug-b\" (the projects the letter draws "
                                "on)"])
    paragraphs = [" ".join(x.strip() for x in p.split("\n") if x.strip())
                  for p in re.split(r"\n\s*\n", "\n".join(rows[:-1]))]
    return {"paragraphs": [p for p in paragraphs if p], "evidence_slugs": _slugs(evidence.group(1))}


# ── Both ──────────────────────────────────────────────────────────────────

def drafts_to_result(resume_text: str, cover_text: str) -> dict:
    """The full result dict (as a JSON paste would give) from the two draft Docs.

    The rules version comes from the resume Doc, else the cover letter Doc; the instructions version from the resume
    Doc. Each is left out when missing.

    Raises:
        DraftFormatError: the problems in both Docs, each prefixed with the Doc it is in.
    """
    from strelitzia.scoring.workbench import SCHEMA_VERSION

    errors: list[str] = []
    resume = cover = None
    versions: dict[str, str | None] = {}
    notes = None
    try:
        resume, versions, notes = parse_resume_draft(resume_text)
    except DraftFormatError as e:
        errors += [f"Resume draft, {m[0].lower()}{m[1:]}" for m in e.errors]
    try:
        cover = parse_cover_draft(cover_text)
    except DraftFormatError as e:
        errors += [f"Cover letter draft: {m}" for m in e.errors]
    if errors:
        raise DraftFormatError(errors)
    out = {"strelitzia": SCHEMA_VERSION, "resume": resume, "cover_letter": cover, "notes_for_user": notes or ""}
    rules = versions.get("rules") or _cover_lines(cover_text)[1]
    if rules:
        out["rules_version"] = rules
    if versions.get("instructions"):
        out["instructions_version"] = versions["instructions"]
    return out
