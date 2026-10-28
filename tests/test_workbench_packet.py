"""The workbench's output contract, the fixed docs and the per-job packet."""

import copy
import json

import pytest
from fake_drive import FakeDrive

from strelitzia.database import init_db
from strelitzia.scoring import workbench as wb
from strelitzia.storage.drive import DOC_MIME, DriveClient
from workbench_helpers import BASE_RESUME, add_job_row, good_result, inputs, job, library


def test_schema_accepts_a_sample_result():
    assert wb.schema_errors(good_result(), wb.RESULT_SCHEMA) == []
    assert wb.schema_errors(good_result(), wb.result_schema(library())) == []


def test_schema_accepts_null_cover_letter_and_no_notes():
    data = good_result()
    data["cover_letter"] = None
    del data["notes_for_user"]
    assert wb.schema_errors(data, wb.RESULT_SCHEMA) == []


def test_schema_errors_name_the_problem():
    data = good_result()
    data["resume"]["headline"] = "x" * 301
    del data["resume"]["skills"]
    data["extra"] = 1
    data["resume"]["roles"][0]["bullets"][0]["project_ids"] = ["nope"]
    errors = wb.schema_errors(data, wb.result_schema(library()))
    assert any("headline" in e and "at most 300" in e for e in errors)
    assert any('missing "skills"' in e for e in errors)
    assert any('unexpected key "extra"' in e for e in errors)
    assert any('"nope" is not allowed' in e for e in errors)


def test_schema_rejects_wrong_version_and_bool_as_int():
    data = good_result()
    data["strelitzia"] = True
    assert wb.schema_errors(data, wb.RESULT_SCHEMA)


def test_rules_cover_the_rules_and_the_draft_format():
    html = wb.rules_text()
    assert "```json" not in html and "project_ids" not in html
    for phrase in ("required qualification you rate claimable", "most recent role", "exact term",
                   "Never claim a tool or skill the packet lists as not in my material", "Working with me", "No keyword lists", "No hidden text", "character band",
                   "ask me for more material", "never split one project into task bullets",
                   "3 paragraphs", "250 words", "spearheaded", "## Dropped roles", "## Notes for me",
                   "Evidence: ", "never create a new Doc", "Resume draft", "Instructions version: "):
        assert phrase in html, phrase
    assert "Cover every" not in html and "Write fresh from the facts" not in html
    assert len(wb.RULES_VERSION) == 8 and wb.RULES_VERSION in wb.job_packet(job(), library(), BASE_RESUME).text


def test_packet_carries_the_full_rules():
    p = wb.job_packet(job(), library(), BASE_RESUME)
    assert f"Rules version: {wb.RULES_VERSION} (the Rules section" in p.text
    rules = p.text.split("\n## Rules\n", 1)[1]
    for heading in ("Honesty", "Wording", "Cover letter", "Output format"):
        assert f"## Rules: {heading}" in rules, heading
    assert "No hidden text" in rules and "## Dropped roles" in rules
    assert "<h2>Rules: Output format</h2>" in p.html
    assert "Rules section" in p.prompt


def test_project_instructions_are_versioned_and_point_at_the_packet():
    text = wb.project_instructions()
    assert text.splitlines()[0] == f"Instructions version: {wb.INSTRUCTIONS_VERSION}"
    assert len(wb.INSTRUCTIONS_VERSION) == 8 and wb.PROJECT_INSTRUCTIONS in text
    assert "Rules section" in text and "knowledge" not in text
    assert wb.instructions_version_warning(wb.INSTRUCTIONS_VERSION) is None
    assert "didn't say" in wb.instructions_version_warning(None)
    old = wb.instructions_version_warning("0ld0ld00")
    assert "0ld0ld00" in old and wb.INSTRUCTIONS_VERSION in old and "Claude setup" in old


def test_packet_lists_terms_and_qualifications():
    p = wb.job_packet(job(), library(), BASE_RESUME)
    assert p.name == "Initech – Senior Data Engineer – Claude packet"
    assert "Required tools and skills" in p.text and "Required qualifications" in p.text
    assert "Preferred tools and skills" in p.text
    assert "Airflow: in your material (projects orders-pipeline; base resume data-engineer-acme, skills)" in p.text
    assert "Kubernetes: not in your material: leave out of Skills and bullets" in p.text
    assert "Terraform: not in your material" in p.text
    assert "UNEVIDENCED" not in p.text and "Not claimable" not in p.text
    quals = p.text.split("## Required qualifications")[1].split("##")[0]
    assert "Assess each against the Content Library, Base Resume and About me" in quals
    assert "claimable / partly / not" in quals
    assert "- 3+ years building data pipelines with Spark (possible evidence: base resume data-engineer-acme)" in quals
    assert "not in your material" not in quals
    assert ("data-engineer-acme: Data Engineer at Acme Corp (Jan 2024 – Present); exactly 2 bullets, each 91-111 "
            "characters;") in p.text
    assert "data-analyst-intern-globex: Data Analyst Intern at Globex (Jun 2022 – Aug 2022); exactly 1 bullet," in p.text
    assert "each bullet 91-111 characters. The counts and the band are binding" in p.text
    assert "projects: orders-pipeline, quality-dashboard" in p.text
    assert "Customer Data Platform (CDP)" in p.text
    assert "<h2>Required qualifications</h2>" in p.html


def test_bullet_band_and_exact_counts_are_checked():
    data = good_result()
    data["resume"]["roles"][1]["bullets"][0]["text"] = "Trained a churn model in Python with scikit-learn, AUC 0.83"
    _, errors, _ = wb.check_result(data, job(), inputs())
    assert any("is 59 characters; at least 91, so it prints as two lines" in e for e in errors), errors
    data = good_result()
    data["resume"]["roles"] = data["resume"]["roles"][:1]
    _, errors, _ = wb.check_result(data, job(), inputs())
    assert "Role 'data-analyst-intern-globex' is required (exactly 1 bullet) but missing" in errors


def test_a_role_planned_at_zero_must_be_left_out(monkeypatch):
    from strelitzia.scoring import tailor

    monkeypatch.setattr(tailor, "bullet_plan", lambda lib, base, budget: {"data-engineer-acme": 2,
                                                                          "data-analyst-intern-globex": 0})
    _, errors, _ = wb.check_result(good_result(), job(), inputs())
    assert "Role 'data-analyst-intern-globex' gets 0 bullets on this page; leave it out (under Dropped roles)" in errors
    assert "0 bullets: leave it out, under Dropped roles" in wb.packet_for(job(), inputs()).text


def test_packet_gives_an_unmatched_sentence_no_verdict():
    posting = {"required_qualifications": ["Deep familiarity with corporate bonds, Treasury rates and credit spreads"]}
    p = wb.job_packet(job(details_json=json.dumps(posting)), library(), BASE_RESUME)
    assert "corporate bonds, Treasury rates and credit spreads (possible evidence: none found by word match)" in p.text
    assert "UNEVIDENCED" not in p.text and "not in your material" not in p.text


def test_drive_prompt_is_short_and_names_the_docs():
    p = wb.job_packet(job(), library(), BASE_RESUME)
    assert len(p.prompt) <= wb.PROMPT_MAX
    assert "'Initech – Senior Data Engineer – Claude packet'" in p.prompt
    assert "'Initech - Senior Data Engineer - Resume draft'" in p.prompt
    assert "'Initech - Senior Data Engineer - Cover letter draft'" in p.prompt
    assert "edit only those two Docs" in p.prompt and "JSON" not in p.prompt
    long = wb.job_packet(job(title="Very long title " * 30), library(), BASE_RESUME, current=good_result())
    assert len(long.prompt) <= wb.PROMPT_MAX and "current draft" in long.prompt
    assert "## Current draft" in long.text and json.dumps(good_result()["resume"]["headline"]) not in long.text


def test_packet_points_at_the_current_draft():
    p = wb.job_packet(job(), library(), BASE_RESUME, current=copy.deepcopy(good_result()))
    assert "## Current draft" in p.text and "draft Docs" in p.text
    assert "Start from the current draft in them." in p.prompt


def test_packet_without_posting_details():
    p = wb.job_packet(job(details_json=None), library(), "")
    assert "None listed in the posting." in p.text


def test_packet_for_uses_resume_fixed_role_facts():
    ins = inputs()
    ins.fixed = {**ins.fixed, "roles": {"data-engineer-acme": {"title": "Senior Data Engineer", "company": "Acme Corp",
                                                                "dates": "2021 – 2024"}}}
    p = wb.packet_for(job(), ins)
    assert "data-engineer-acme: Senior Data Engineer at Acme Corp (2021 – 2024)" in p.text


# ── Draft Docs with the packet (docs-drafts-2-api Task 1) ──

@pytest.fixture
def drive(monkeypatch):
    monkeypatch.setenv("DRIVE_ROOT_FOLDER", "Strelitzia")
    return FakeDrive()


@pytest.fixture
def client(drive):
    return DriveClient(drive, text_media_factory=lambda text, mime: text.encode("utf-8"))


@pytest.fixture
def conn(tmp_path):
    return init_db(tmp_path / "wb.db")


def _row(conn):
    return dict(conn.execute("SELECT * FROM jobs").fetchone())


def _draft_docs(drive):
    return {f["name"]: f for f in drive.store.values()
            if f["mimeType"] == DOC_MIME and "draft" in f["name"] and not f["trashed"]}


def test_first_open_creates_seeded_drafts(drive, client, conn):
    job = add_job_row(conn)
    urls = wb.publish_drafts(client, conn, job, inputs())
    assert set(urls) == {"resume", "cover"} and all(urls.values())
    docs = _draft_docs(drive)
    resume = docs["Initech - Senior Data Engineer - Resume draft"]
    cover = docs["Initech - Senior Data Engineer - Cover letter draft"]
    assert drive.path_of(resume["id"])[:3] == ["Strelitzia", "Initech", "Senior Data Engineer"]
    # The version lines start empty: Claude fills them from the packet and its instructions, never from the seed.
    assert resume["content"].decode().startswith("Rules version: \nInstructions version: \nSummary: \n")
    assert b"## data-engineer-acme" in resume["content"] and b"Write the cover letter here" in cover["content"]
    assert not cover["content"].startswith(b"Rules version")
    row = _row(conn)
    assert row["resume_draft_doc_id"] == resume["id"] and row["cover_draft_doc_url"] == urls["cover"]
    assert row["drafts_written_at"] == max(resume["modifiedTime"], cover["modifiedTime"])


def test_drafts_seed_from_the_current_draft(drive, client, conn, tmp_path, monkeypatch):
    from strelitzia.scoring import pdf as pdf_mod
    from workbench_helpers import fake_render_pdf

    monkeypatch.setattr(pdf_mod, "render_pdf", fake_render_pdf)
    job = add_job_row(conn)
    assert wb.import_data(conn, job, good_result(), inputs=inputs(), out_dir=tmp_path / "out").ok
    wb.publish_drafts(client, conn, _row(conn), inputs())
    resume = next(f for n, f in _draft_docs(drive).items() if n.endswith("Resume draft"))
    assert b"Summary: Data engineer building Airflow and Spark pipelines" in resume["content"]
    assert b"[orders-pipeline]" in resume["content"]


def test_reopen_after_an_outside_edit_leaves_the_drafts_alone(drive, client, conn, tmp_path, monkeypatch):
    from strelitzia.scoring import pdf as pdf_mod
    from workbench_helpers import fake_render_pdf

    monkeypatch.setattr(pdf_mod, "render_pdf", fake_render_pdf)
    job = add_job_row(conn)
    wb.publish_drafts(client, conn, job, inputs())
    resume_id = _row(conn)["resume_draft_doc_id"]
    drive.edit(resume_id, b"Claude's draft")
    # Even with a newer accepted draft, an edited Doc is kept.
    assert wb.import_data(conn, _row(conn), good_result(), inputs=inputs(), out_dir=tmp_path / "out").ok
    calls = dict(drive.calls)
    wb.publish_drafts(client, conn, _row(conn), inputs())
    assert drive.store[resume_id]["content"] == b"Claude's draft"
    assert len(_draft_docs(drive)) == 2
    # The unedited cover letter Doc is reseeded with the newer draft.
    cover = drive.store[_row(conn)["cover_draft_doc_id"]]
    assert b"Evidence: orders-pipeline, quality-dashboard" in cover["content"]
    assert drive.calls["update"] == calls.get("update", 0) + 1 and drive.calls["create"] == calls["create"]


def test_reopen_without_changes_writes_nothing(drive, client, conn):
    job = add_job_row(conn)
    wb.publish_drafts(client, conn, job, inputs())
    calls = dict(drive.calls)
    wb.publish_drafts(client, conn, _row(conn), inputs())
    assert drive.calls["create"] == calls["create"] and drive.calls.get("update", 0) == calls.get("update", 0)


def test_a_deleted_draft_is_created_again(drive, client, conn):
    job = add_job_row(conn)
    wb.publish_drafts(client, conn, job, inputs())
    old = _row(conn)["resume_draft_doc_id"]
    drive.store[old]["trashed"] = True
    wb.publish_drafts(client, conn, _row(conn), inputs())
    assert _row(conn)["resume_draft_doc_id"] != old and len(_draft_docs(drive)) == 2


def test_rules_shape_bullets_around_responsibilities():
    rules = wb.rules_text()
    for check in ("1. Responsibility:", "2. Beneficiary:", "3. Evidence:", "4. Ownership:", "5. Tool justification:",
                  "6. Distinctness:"):
        assert check in rules, check
    for phrase in ("Start from my base resume's bullet", "Fold small technical work", "Name 1-3 tools per bullet",
                   "Skills holds the full inventory", "Order bullets in each role by relevance",
                   "Responsibility line", "never make a bullet out of Detail alone",
                   "Before: \"Wrote the export in Python", "After: \"Owned ingestion orchestration"):
        assert phrase in rules, phrase
    working = rules.split("## Working with me", 1)[1].split("## Wording", 1)[0]
    for phrase in ("Before drafting, show me your plan", "no outcome or number, ask me for one",
                   "unsure whether a Summary helps, ask me"):
        assert phrase in working, phrase


def test_rules_make_the_summary_optional_with_a_reason():
    rules = wb.rules_text()
    assert "Headline" not in rules
    assert "Summary: leave it empty unless my current title doesn't match the role" in rules
    assert "no tool list" in rules and "Say why in Notes for me" in rules
    assert "Summary: \n" in rules
