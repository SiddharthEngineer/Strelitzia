"""Recruiter review: one job's latest draft (resume and cover letter), graded A+ to F- per criterion by a recruiter.

A review is a self-contained prompt (`review_prompt`): the grader plays a recruiter hiring for the job, with the job
description as the hiring criteria, and grades each document on the six criteria in
agents/research/recruiter-panel.md, with evidence and a fix for each. The user pastes it into any chat model
(Claude, ChatGPT, Gemini) and pastes the reply back (`import_reply`); each grader keeps its latest reply, so the
graders can be compared. Nothing here calls a model.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from strelitzia.database import Connection, job_company
from strelitzia.scoring.targets import targets
from strelitzia.scoring.workbench import DESCRIPTION_MAX, _Doc, _obj, extract_json, posting_of, schema_errors

REVIEW_VERSION = 1
GRADES = ("A+", "A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D+", "D", "D-", "F+", "F", "F-")
VERDICTS = ("yes", "maybe", "no")
GRADERS = ("claude-haiku", "claude-sonnet", "claude-opus", "chatgpt", "gemini", "other")
MODEL_LABEL_MAX = 100
TOP_FIXES = 3

# (key, name, what it means). Each is graded separately for the resume and the cover letter.
CRITERIA = (
    ("relevance", "Relevance", "The posting's required and preferred qualifications are shown. Quote the evidence; "
                               "partial evidence counts partly."),
    ("evidence", "Evidence", "Claims are backed by concrete work, scope and results. Nothing inferred or inflated."),
    ("human_tone", "Human tone", "Reads as written by the candidate. No AI tells: stock phrases, rule-of-three lists, "
                                 "buzzwords."),
    ("specificity", "Specificity", "Written for this company and role, not a template. This weighs most for the "
                                   "cover letter."),
    ("clarity", "Clarity", "A recruiter sees the fit in 10 seconds: scannable, no filler."),
    ("polish", "Polish", "Grammar, consistency and length: the resume fits one page, the cover letter stays under "
                         "about 350 words."),
)
CRITERIA_KEYS = tuple(key for key, _, _ in CRITERIA)


def grade_points(grade: str) -> int:
    """A+ = 14 ... F- = 0, for averages.

    Raises:
        ValueError: not one of GRADES.
    """
    return len(GRADES) - 1 - GRADES.index(grade)


# ── The prompt ────────────────────────────────────────────────────────────

_GRADE = {"type": "string", "enum": list(GRADES)}
_CRITERION = _obj({"grade": _GRADE, "evidence": {"type": "string"}, "fix": {"type": "string"}})
_DOC = _obj({"criteria": _obj({key: _CRITERION for key in CRITERIA_KEYS}), "overall": _GRADE})
_COVER = {**_DOC, "type": ["object", "null"]}
REPLY_SCHEMA = _obj({
    "review": {"type": "integer", "enum": [REVIEW_VERSION]},
    "prompt_version": {"type": "string"},
    "resume": _DOC,
    "cover_letter": _COVER,
    "verdict": {"type": "string", "enum": list(VERDICTS)},
    "top_fixes": {"type": "array", "items": {"type": "string"}},
}, required=["review", "resume", "cover_letter", "verdict", "top_fixes"])

_EXAMPLE_CRITERIA = {
    "relevance": {"grade": "B+", "evidence": "\"Migrated the nightly orders pipeline from cron to Airflow\" shows "
                                             "Airflow; nothing shows Terraform (preferred).",
                  "fix": "Name the Terraform module you wrote for the staging stack in the second role."},
    "evidence": {"grade": "A-", "evidence": "\"cut missed morning loads from weekly to rare\"",
                 "fix": "Give the feed count for the ingestion bullet."},
    "human_tone": {"grade": "B", "evidence": "\"passionate about leveraging cutting-edge technologies\"",
                   "fix": "Replace the headline with one plain sentence on the work you want next."},
    "specificity": {"grade": "C+", "evidence": "Nothing in the headline mentions payments data.",
                    "fix": "Lead with the payments reconciliation project."},
    "clarity": {"grade": "A", "evidence": "The current title and Airflow are in the first two lines.",
                "fix": "Drop the Interests section."},
    "polish": {"grade": "A-", "evidence": "Dates use two formats (\"Jan 2024\" and \"2023-06\").",
               "fix": "Use \"Jan 2024\" everywhere."},
}
EXAMPLE_REPLY = {
    "review": REVIEW_VERSION,
    "prompt_version": "<the Prompt version at the top of this prompt>",
    "resume": {"criteria": _EXAMPLE_CRITERIA, "overall": "B+"},
    "cover_letter": {"criteria": {key: {"grade": "<grade>", "evidence": "<quote>", "fix": "<one concrete fix>"}
                                  for key in CRITERIA_KEYS}, "overall": "B-"},
    "verdict": "maybe",
    "top_fixes": ["<the most important fix>", "<the second>", "<the third>"],
}

_ROLE = ("You are a recruiter hiring for {title} at {company}. The job description below is your hiring criteria. "
         "You are screening one application: a resume and a cover letter. Decide whether you would invite the "
         "candidate to a phone screen, and tell them exactly what to fix.")


def _criteria_doc() -> _Doc:
    d = _Doc("How to grade")
    d.p("Grade the resume and the cover letter separately, each on every criterion below. Grade as a busy recruiter "
        "would: a 6-10 second first scan, a keyword match against the posting, then a hiring manager's careful read. "
        "Only what is written counts: never infer experience that isn't in the document.")
    d.h("Criteria")
    d.ul([f"{name} ({key}): {meaning}" for key, name, meaning in CRITERIA])
    d.h("Scale")
    d.p("Use exactly one of these 15 grades, best first: " + " ".join(GRADES) + ". A means a recruiter would find "
        "nothing to change; C is a typical, unremarkable application; F means it would get the application rejected.")
    d.p("For every grade, quote the evidence from the document (the shortest phrase that shows it, or say what is "
        "missing) and give one concrete fix the candidate can make. Then give each document an overall grade.")
    d.h("Verdict")
    d.p("Would you invite this candidate to a phone screen: yes, maybe or no? Then list the top three fixes across "
        "both documents, most important first.")
    return d


def _reply_doc() -> _Doc:
    d = _Doc("Reply format")
    d.p("Write your review in plain words first if you like. Then end your reply with exactly one ```json block in "
        "this format. Use only the keys shown, every criterion key for each document, and grades exactly as written "
        "in the scale. Set prompt_version to the Prompt version at the top of this prompt. If there is no cover "
        "letter, set cover_letter to null.")
    d.pre(json.dumps(EXAMPLE_REPLY, indent=2))
    return d


PROMPT_VERSION = hashlib.sha256(
    "\n".join((_ROLE, _criteria_doc().text(), _reply_doc().text())).encode("utf-8")).hexdigest()[:8]


def cover_text(draft: dict) -> str:
    """The draft's cover letter as plain text (paragraphs separated by blank lines), or "" when it has none."""
    try:
        letter = json.loads(draft.get("cover_json") or "null")
    except ValueError:
        return ""
    paragraphs = letter.get("paragraphs") if isinstance(letter, dict) else None
    if not isinstance(paragraphs, list):
        return ""
    return "\n\n".join(p.strip() for p in paragraphs if isinstance(p, str) and p.strip())


def review_prompt(job: dict, draft: dict) -> str:
    """The text to paste into any chat model: role, criteria and scale, the posting, both documents, reply format.

    Self-contained: it needs no project, connector or file.
    """
    title = job.get("title") or "this role"
    company = job_company(job)
    d = _Doc(f"Recruiter review: {title} at {company}")
    d.p(f"Prompt version: {PROMPT_VERSION}")
    d.p(_ROLE.format(title=title, company=company))
    d.include(_criteria_doc(), "How to grade")
    d.h("The job description (your hiring criteria)")
    d.pre((job.get("full_description") or job.get("description") or "")[:DESCRIPTION_MAX].strip() or "(none)")
    posting_targets = targets(posting_of(job))
    for kind, label in (("required", "Required qualifications"), ("preferred", "Preferred qualifications")):
        listed = [t.text for t in posting_targets if t.kind == kind]
        if listed:
            d.p(label + ":").ul(listed)
        else:
            d.p(f"{label}: none listed.")
    d.h("The resume")
    d.pre((draft.get("resume_text") or "").strip() or "(none)")
    d.h("The cover letter")
    letter = cover_text(draft)
    if letter:
        d.pre(letter)
    else:
        d.p("There is no cover letter: set cover_letter to null.")
    d.include(_reply_doc(), "Reply format")
    return d.text()


# ── Reviews ───────────────────────────────────────────────────────────────

class NoDraft(LookupError):
    """The job has no accepted draft to review."""


def _rows(conn: Connection, sql: str, params: tuple = ()) -> list[dict]:
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def latest_draft(conn: Connection, user_id: str, job_url: str) -> dict | None:
    rows = _rows(conn, "SELECT * FROM drafts WHERE user_id = ? AND job_url = ? ORDER BY version DESC LIMIT 1",
                 (user_id, job_url))
    return rows[0] if rows else None


def create_review(conn: Connection, user_id: str, job: dict) -> str:
    """A new review of the job's latest draft; its id.

    Raises:
        NoDraft: the job has no draft yet.
    """
    draft = latest_draft(conn, user_id, job["url"])
    if draft is None:
        raise NoDraft("This job has no draft to review yet. Import a resume for it first.")
    review_id = uuid.uuid4().hex
    conn.execute("INSERT INTO reviews (id, user_id, job_url, draft_id, prompt_version, created_at) "
                 "VALUES (?, ?, ?, ?, ?, ?)",
                 (review_id, user_id, job["url"], draft["id"], PROMPT_VERSION, datetime.now(UTC).isoformat()))
    conn.commit()
    return review_id


def _json(text: str | None, default=None):
    try:
        return json.loads(text) if text else default
    except ValueError:
        return default


def _grades(conn: Connection, review_ids: list[str]) -> dict[str, list[dict]]:
    """{review_id: its graders' replies in GRADERS order}."""
    if not review_ids:
        return {}
    marks = ", ".join("?" * len(review_ids))
    out: dict[str, list[dict]] = {}
    for g in _rows(conn, f"SELECT * FROM review_grades WHERE review_id IN ({marks})", tuple(review_ids)):
        out.setdefault(g["review_id"], []).append(g)
    order = {name: i for i, name in enumerate(GRADERS)}
    for replies in out.values():
        replies.sort(key=lambda g: order.get(g["grader"], len(GRADERS)))
    return out


def _summary(review: dict, job: dict | None, replies: list[dict]) -> dict:
    return {
        "id": review["id"], "job_url": review["job_url"], "draft_id": review["draft_id"],
        "prompt_version": review["prompt_version"], "created_at": review["created_at"],
        "job": {"key": job.get("job_key"), "title": job.get("title"), "company": job_company(job)} if job else None,
        "grades": [{key: g[key] for key in ("grader", "model_label", "overall_resume", "overall_cover", "verdict",
                                            "created_at")} for g in replies],
    }


def list_reviews(conn: Connection, user_id: str, job_url: str | None = None) -> list[dict]:
    """The user's reviews (of one job, if given), newest first, each with every grader's overall grades."""
    sql, params = "SELECT * FROM reviews WHERE user_id = ?", (user_id,)
    if job_url is not None:
        sql, params = sql + " AND job_url = ?", (*params, job_url)
    reviews = _rows(conn, sql + " ORDER BY created_at DESC, id", params)
    jobs = {j["url"]: j for j in _rows(conn, "SELECT url, job_key, title, company, site, strategy FROM jobs "
                                             "WHERE user_id = ?", (user_id,))}
    grades = _grades(conn, [r["id"] for r in reviews])
    return [_summary(r, jobs.get(r["job_url"]), grades.get(r["id"], [])) for r in reviews]


def get_review(conn: Connection, user_id: str, review_id: str) -> dict:
    """The review with its prompt and every grader's whole reply.

    Raises:
        KeyError: no such review for this user.
    """
    rows = _rows(conn, "SELECT * FROM reviews WHERE id = ? AND user_id = ?", (review_id, user_id))
    if not rows:
        raise KeyError(review_id)
    review = rows[0]
    jobs = _rows(conn, "SELECT * FROM jobs WHERE user_id = ? AND url = ?", (user_id, review["job_url"]))
    drafts = _rows(conn, "SELECT * FROM drafts WHERE user_id = ? AND id = ?", (user_id, review["draft_id"]))
    job, draft = (jobs[0] if jobs else None), (drafts[0] if drafts else None)
    replies = _grades(conn, [review_id]).get(review_id, [])
    out = _summary(review, job, replies)
    out["draft_version"] = draft.get("version") if draft else None
    out["current_prompt_version"] = PROMPT_VERSION
    out["prompt"] = review_prompt(job, draft) if job and draft else None
    out["replies"] = [{**{k: g[k] for k in ("grader", "model_label", "overall_resume", "overall_cover", "verdict",
                                             "created_at")}, "reply": _json(g["detail_json"], {})} for g in replies]
    return out


# ── Import ────────────────────────────────────────────────────────────────

@dataclass
class ImportOutcome:
    ok: bool
    errors: list[str]
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"ok": self.ok, "errors": self.errors, "warnings": self.warnings}


def _clean_grade(value: object) -> object:
    """A grade as written ("a-", " B+ ", a typographic minus) as the grade it means; anything else unchanged."""
    if not isinstance(value, str):
        return value
    return value.strip().upper().replace("\u2212", "-").replace("\u2013", "-")


def _normalize(data: object) -> None:
    """Tidy the grades and the verdict in place, so the schema check only rejects real mistakes."""
    if not isinstance(data, dict):
        return
    for doc in (data.get("resume"), data.get("cover_letter")):
        if not isinstance(doc, dict):
            continue
        if "overall" in doc:
            doc["overall"] = _clean_grade(doc["overall"])
        criteria = doc.get("criteria")
        for item in criteria.values() if isinstance(criteria, dict) else ():
            if isinstance(item, dict) and "grade" in item:
                item["grade"] = _clean_grade(item["grade"])
    if isinstance(data.get("verdict"), str):
        data["verdict"] = data["verdict"].strip().lower()


def prompt_version_warning(used: str | None) -> str | None:
    """A warning when the reply names no prompt version or an old one (a prompt copied before an update)."""
    if used == PROMPT_VERSION:
        return None
    again = "copy the prompt again and rerun it in a new chat if you want a review against the current criteria"
    if not used:
        return f"The reply doesn't say which prompt version it graded (current: {PROMPT_VERSION}); {again}."
    return f"The reply graded prompt version {used}, not the current {PROMPT_VERSION}; {again}."


def import_reply(conn: Connection, user_id: str, review_id: str, grader: str, model_label: str | None,
                 text: str) -> ImportOutcome:
    """Validate a pasted reply and store it as `grader`'s reply to the review (replacing its earlier one)."""
    if grader not in GRADERS:
        return ImportOutcome(False, [f"Unknown grader {grader!r} (use one of: {', '.join(GRADERS)})"])
    if not conn.execute("SELECT 1 FROM reviews WHERE id = ? AND user_id = ?", (review_id, user_id)).fetchone():
        return ImportOutcome(False, ["No such review."])
    label = (model_label or "").strip()
    if len(label) > MODEL_LABEL_MAX:
        return ImportOutcome(False, [f"The model name is {len(label)} characters, at most {MODEL_LABEL_MAX}."])
    try:
        data, where = extract_json(text)
    except ValueError as e:
        return ImportOutcome(False, [str(e)])
    _normalize(data)
    errors = schema_errors(data, REPLY_SCHEMA)
    if errors:
        return ImportOutcome(False, [f"{where} doesn't match the review format: " + "; ".join(errors[:8])])
    fixes = [f for f in data["top_fixes"] if f.strip()]
    if not fixes:
        return ImportOutcome(False, [f"{where} lists no top fixes; ask for the top {TOP_FIXES} fixes."])
    warnings = [w for w in (prompt_version_warning(data.get("prompt_version")),) if w]
    if len(fixes) != TOP_FIXES:
        warnings.append(f"The reply lists {len(fixes)} top fixes, not {TOP_FIXES}.")
    letters = _rows(conn, "SELECT d.cover_json FROM reviews r JOIN drafts d ON d.id = r.draft_id WHERE r.id = ?",
                    (review_id,))
    has_letter = bool(letters and cover_text(letters[0]))
    cover = data["cover_letter"]
    if has_letter and cover is None:
        warnings.append("The reply didn't grade the cover letter, though the prompt has one.")
    elif not has_letter and cover is not None:
        warnings.append("The reply graded a cover letter, but this draft has none; its grades are kept as given.")
    now = datetime.now(UTC).isoformat()
    conn.execute("DELETE FROM review_grades WHERE review_id = ? AND grader = ?", (review_id, grader))
    conn.execute(
        "INSERT INTO review_grades (review_id, grader, model_label, overall_resume, overall_cover, verdict, "
        "detail_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (review_id, grader, label, data["resume"]["overall"], cover["overall"] if cover else None, data["verdict"],
         json.dumps(data, ensure_ascii=False), now),
    )
    conn.commit()
    return ImportOutcome(True, [], warnings=warnings)
