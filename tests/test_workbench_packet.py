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
    data["resume"]["headline"] = "x" * 111
    del data["resume"]["skills"]
    data["extra"] = 1
    data["resume"]["roles"][0]["bullets"][0]["project_ids"] = ["nope"]
    errors = wb.schema_errors(data, wb.result_schema(library()))
    assert any("headline" in e and "at most 110" in e for e in errors)
    assert any('missing "skills"' in e for e in errors)
    assert any('unexpected key "extra"' in e for e in errors)
    assert any('"nope" is not allowed' in e for e in errors)


def test_schema_rejects_wrong_version_and_bool_as_int():
    data = good_result()
    data["strelitzia"] = True
    assert wb.schema_errors(data, wb.RESULT_SCHEMA)


def test_rules_doc_covers_the_rules_and_the_draft_format():
    html = wb.rules_doc()
    assert "```json" not in html and "project_ids" not in html
    for phrase in ("every evidenced required qualification", "most recent role", "exact term",
                   "Never mention an unevidenced", "No keyword lists", "No hidden text", "230 characters",
                   "3 paragraphs", "250 words", "spearheaded", "## Dropped roles", "## Notes for me",
                   "Evidence: ", "never create a new Doc", "Resume draft"):
        assert phrase in html, phrase
    assert len(wb.RULES_VERSION) == 8 and wb.RULES_VERSION in wb.job_packet(job(), library(), BASE_RESUME).text


def test_library_doc_shows_slugs_and_base_resume():
    html = wb.library_doc(library(), BASE_RESUME)
    assert "Project slug: orders-pipeline" in html and "Role data-engineer-acme" in html
    assert "Data Analyst Intern at Globex" in html


def test_packet_lists_targets_and_unmet():
    p = wb.job_packet(job(), library(), BASE_RESUME)
    assert p.name == "Initech – Senior Data Engineer – Claude packet"
    assert "Required qualifications" in p.text and "Preferred qualifications" in p.text
    assert "Airflow: evidenced (projects orders-pipeline; base resume data-engineer-acme, skills)" in p.text
    assert "Kubernetes: UNEVIDENCED, do not claim" in p.text
    unmet = p.text.split("## Not claimable (unevidenced)")[1].split("##")[0]
    assert "- Kubernetes" in unmet and "- Terraform" in unmet and "Airflow" not in unmet
    assert "data-engineer-acme: Data Engineer at Acme Corp (Jan 2024 – Present); 1-2 bullets, required" in p.text
    assert "projects: orders-pipeline, quality-dashboard" in p.text
    assert "Customer Data Platform (CDP)" in p.text
    assert "<h2>Required qualifications</h2>" in p.html


def test_drive_prompt_is_short_and_names_the_docs():
    p = wb.job_packet(job(), library(), BASE_RESUME, inline=False)
    assert len(p.prompt) <= wb.PROMPT_MAX
    assert "'Initech – Senior Data Engineer – Claude packet'" in p.prompt
    assert "'Initech - Senior Data Engineer - Resume draft'" in p.prompt
    assert "'Initech - Senior Data Engineer - Cover letter draft'" in p.prompt
    assert "edit only those two Docs" in p.prompt and "JSON" not in p.prompt
    long = wb.job_packet(job(title="Very long title " * 30), library(), BASE_RESUME, current=good_result(),
                         inline=False)
    assert len(long.prompt) <= wb.PROMPT_MAX and "current draft" in long.prompt
    assert "## Current draft" in long.text and json.dumps(good_result()["resume"]["headline"]) not in long.text


def test_inline_prompt_carries_packet_rules_and_library():
    p = wb.job_packet(job(), library(), BASE_RESUME)
    assert p.text in p.prompt
    assert "Strelitzia rules" in p.prompt and "Project slug: churn-model" in p.prompt


def test_packet_includes_current_draft():
    current = good_result()
    p = wb.job_packet(job(), library(), BASE_RESUME, current=copy.deepcopy(current))
    assert "## Current draft" in p.text
    assert json.dumps(current["resume"]["headline"]) in p.text


def test_packet_without_posting_details():
    p = wb.job_packet(job(details_json=None), library(), "")
    assert "None listed in the posting." in p.text


def test_packet_for_uses_resume_fixed_role_facts():
    ins = inputs()
    ins.fixed = {**ins.fixed, "roles": {"data-engineer-acme": {"title": "Senior Data Engineer", "company": "Acme Corp",
                                                                "dates": "2021 – 2024"}}}
    p = wb.packet_for(job(), ins, inline=True)
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
    assert resume["content"].decode().startswith(f"Rules version: {wb.RULES_VERSION}\nHeadline: \n")
    assert b"## data-engineer-acme" in resume["content"] and b"Write the cover letter here" in cover["content"]
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
    assert b"Headline: Data engineer building Airflow and Spark pipelines" in resume["content"]
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
