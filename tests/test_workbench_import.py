"""Paste-back: extracting the JSON, the deterministic checks, and saving a draft."""

import copy
import json
from pathlib import Path

import pytest

from strelitzia import tracking, users
from strelitzia.database import init_db
from strelitzia.scoring import pdf as pdf_mod
from strelitzia.scoring import workbench as wb
from workbench_helpers import add_job_row, fake_render_pdf, good_result, inputs


@pytest.fixture
def conn(tmp_path):
    return init_db(tmp_path / "wb.db")


@pytest.fixture(autouse=True)
def _no_chromium(monkeypatch):
    monkeypatch.setattr(pdf_mod, "render_pdf", fake_render_pdf)


def _import(conn, tmp_path, data, **job_overrides):
    job = add_job_row(conn, **job_overrides) if not conn.execute("SELECT 1 FROM jobs").fetchone() else \
        dict(conn.execute("SELECT * FROM jobs").fetchone())
    return wb.import_data(conn, job, data, inputs=inputs(), out_dir=tmp_path / "out")


# ── checks ──

def test_check_errors_give_a_fix_prompt(conn, tmp_path):
    data = good_result()
    data["resume"]["skills"].append({"category": "Cloud", "items": "Kubernetes"})
    out = _import(conn, tmp_path, data)
    assert not out.ok and out.fix_prompt.startswith("These problems were found:\n1. ")


def test_unevidenced_skill_in_a_bullet_is_an_error(conn, tmp_path):
    data = good_result()
    data["resume"]["roles"][0]["bullets"][0]["text"] = "Deployed the orders pipeline on Kubernetes with Airflow"
    out = _import(conn, tmp_path, data)
    assert not out.ok
    assert any("'Kubernetes' is not backed" in e and "data-engineer-acme bullet 1" in e for e in out.errors)
    assert "Kubernetes" in out.fix_prompt
    assert not (tmp_path / "out").exists() or not list((tmp_path / "out").iterdir())
    assert conn.execute("SELECT draft_version FROM jobs").fetchone()[0] is None


def test_a_qualification_sentence_is_claude_s_call(conn, tmp_path):
    """No word match backs the sentence, yet the draft may state it: Claude judges qualifications, not the app."""
    from workbench_helpers import POSTING

    sentence = "Comfortable pricing corporate bonds against Treasury rates and credit spreads"
    posting = {**POSTING, "required_qualifications": [*POSTING["required_qualifications"], sentence]}
    data = good_result()
    data["resume"]["roles"][0]["bullets"][0]["text"] = (
        "Migrated the nightly orders pipeline from cron to Airflow and Spark, cutting runtime from 6 hours to "
        "45 minutes for desks pricing corporate bonds against Treasury rates and credit spreads")
    out = _import(conn, tmp_path, data, details_json=json.dumps(posting))
    assert out.ok, out.errors
    assert out.unmet == ["Kubernetes", "Terraform"] and sentence in out.coverage["covered"]


def test_rules_ask_and_assess(conn):
    rules = wb.rules_text()
    assert "Working with me" in rules and "one at a time" in rules and "only if I agree" in rules
    assert "claimable, partly or not" in rules and "work authorisation come from About me" in rules
    assert "only when I agree" in wb.PROJECT_INSTRUCTIONS and "unevidenced" not in wb.PROJECT_INSTRUCTIONS


def test_unevidenced_skill_in_skills_and_headline(conn, tmp_path):
    data = good_result(headline="Terraform data engineer",
                       skills=[{"category": "Tools", "items": "Airflow, Kubernetes"}])
    out = _import(conn, tmp_path, data)
    assert any("'Kubernetes'" in e and "Skills (Tools)" in e for e in out.errors)
    assert any("'Terraform'" in e and "Summary" in e for e in out.errors)
    assert any("Skill 'Kubernetes' (Tools) is not in your content library" in e for e in out.errors)


def test_watchlist_term_in_a_bullet_is_an_error(conn, tmp_path):
    data = good_result()
    data["resume"]["roles"][1]["bullets"][0]["text"] = "Rewrote the churn model in Scala"
    out = _import(conn, tmp_path, data)
    assert any("'scala' is not in your content library" in e for e in out.errors)


def test_number_not_in_the_facts_is_an_error(conn, tmp_path):
    data = good_result()
    data["resume"]["roles"][0]["bullets"][0]["text"] = "Cut pipeline runtime by 95% with Airflow"
    out = _import(conn, tmp_path, data)
    assert any("Number(s) 95 not in the facts of orders-pipeline" in e for e in out.errors)


def test_cover_letter_checks(conn, tmp_path):
    data = good_result()
    data["cover_letter"]["paragraphs"] = data["cover_letter"]["paragraphs"][:2] + [
        "I also ran Kubernetes for 7 teams, and I am excited to join."]
    out = _import(conn, tmp_path, data)
    joined = "\n".join(out.errors)
    assert "Cover letter number(s) 7" in joined
    assert "Cover letter mentions 'Kubernetes'" in joined
    assert "Banned words: i am excited" in joined


def test_number_in_the_headline_must_be_known(conn, tmp_path):
    out = _import(conn, tmp_path, good_result(headline="Data engineer with 10 years leading a team of 37"))
    assert any("Number(s) 10, 37 in the Summary" in e for e in out.errors), out.errors
    assert _import(conn, tmp_path, good_result(headline="Data engineer moving 40 million rows a day")).ok


def test_unknown_tool_in_parentheses_in_skills_is_an_error(conn, tmp_path):
    data = good_result()
    data["resume"]["skills"][0]["items"] = "Python (PyTorch), SQL"
    out = _import(conn, tmp_path, data)
    assert any("Skill 'Python (PyTorch)'" in e for e in out.errors)
    data["resume"]["skills"][0]["items"] = "Python (scikit-learn), SQL"
    assert _import(conn, tmp_path, data).ok


def test_cover_letter_may_use_numbers_from_the_posting(conn, tmp_path):
    data = good_result()
    data["cover_letter"]["paragraphs"][2] = ("Your platform serves 20 million riders, and I have built on a customer "
                                             "data platform before. Happy to walk through any of this.")
    assert not _import(conn, tmp_path, data).ok
    conn.execute("UPDATE jobs SET full_description = full_description || ' Our platform serves 20 million riders.'")
    conn.commit()
    out = _import(conn, tmp_path, data)
    assert out.ok, out.errors


def test_jobs_with_the_same_site_and_title_keep_separate_files(conn, tmp_path):
    a = _import(conn, tmp_path, good_result())
    b_job = add_job_row(conn, url="https://example.com/jobs/43", job_key="fed987cba654")
    b = wb.import_data(conn, b_job, good_result(headline="Data engineer for Airflow pipelines"),
                         inputs=inputs(), out_dir=tmp_path / "out")
    assert a.ok and b.ok
    assert a.files["resume"] != b.files["resume"] and a.files["resume_docx"] != b.files["resume_docx"]
    rows = {r["url"]: dict(r) for r in conn.execute("SELECT * FROM jobs").fetchall()}
    first = wb.current_result(rows["https://example.com/jobs/42"])
    assert first["resume"]["headline"] == "Data engineer building Airflow and Spark pipelines"


def test_slug_role_count_wording_checks(conn, tmp_path):
    data = good_result()
    data["resume"]["roles"][0]["bullets"].append(
        {"text": "Ran the pipeline — every night, a robust setup " + "x" * 220, "project_ids": ["orders-pipeline"]})
    out = _import(conn, tmp_path, data)
    joined = "\n".join(out.errors)
    assert "Role 'data-engineer-acme' has 3 bullets; it needs 1-2" in joined
    assert "Em or en dash" in joined and "Banned words in data-engineer-acme bullet 3: robust" in joined
    assert "at most 230" in joined
    bad_slug = good_result()
    bad_slug["resume"]["roles"][1]["bullets"][0]["project_ids"] = ["orders-pipeline"]
    out = wb.import_data(conn, dict(conn.execute("SELECT * FROM jobs").fetchone()), bad_slug,
                           inputs=inputs(), out_dir=tmp_path / "out")
    assert "does not belong to role 'data-analyst-intern-globex'" in out.errors[0]


# ── success ──

def test_valid_result_writes_files_and_bumps_the_version(conn, tmp_path):
    out = _import(conn, tmp_path, good_result())
    assert out.ok, out.errors
    assert out.draft_version == 1
    assert Path(out.files["resume"]).exists()
    prefix = Path(out.files["resume"]).with_suffix("")
    for suffix in (".json", "_RESULT.json", "_REPORT.json", ".txt"):
        assert Path(f"{prefix}{suffix}").exists(), suffix
    sidecar = json.loads(Path(f"{prefix}.json").read_text())
    assert sidecar["headline"] == "Data engineer building Airflow and Spark pipelines"
    assert sidecar["job_url"] == "https://example.com/jobs/42"
    assert out.unmet == ["Kubernetes", "Terraform"]
    assert "Airflow" in out.coverage["covered"] and "Kubernetes" in out.coverage["missing"]
    assert out.coverage["pct_required"] == 80.0

    row = dict(conn.execute("SELECT * FROM jobs").fetchone())
    assert row["draft_version"] == 1 and row["draft_rules_version"] == wb.RULES_VERSION
    assert row["tailored_resume_path"] == out.files["resume"] and row["tailored_at"]
    assert json.loads(row["tailor_report"])["unmet"] == ["Kubernetes", "Terraform"]
    assert row["resume_docx_path"] == out.files["resume_docx"] == f"{prefix}.docx"
    assert Path(out.files["resume_docx"]).exists()
    assert row["cover_letter_path"] == out.files["cover_letter"] and row["cover_letter_at"]
    assert Path(out.files["cover_letter"]).exists() and Path(out.files["cover_letter"]).with_suffix(".txt").exists()
    assert not list((tmp_path / "out").glob("*.staging.*"))
    assert wb.current_result(row)["resume"]["headline"] == sidecar["headline"]

    second = good_result(headline="Data engineer for Airflow pipelines")
    out2 = wb.import_data(conn, row, second, inputs=inputs(), out_dir=tmp_path / "out")
    assert out2.ok and out2.draft_version == 2
    assert conn.execute("SELECT draft_version FROM jobs").fetchone()[0] == 2


def test_dropped_bullets_become_warnings(conn, tmp_path, monkeypatch):
    calls = []

    def overflow_once(html, output_path):
        calls.append(1)
        info = fake_render_pdf(html, output_path)
        return {**info, "overflow": len(calls) == 1, "pages": 2 if len(calls) == 1 else 1}

    monkeypatch.setattr(pdf_mod, "render_pdf", overflow_once)
    out = _import(conn, tmp_path, good_result())
    assert out.ok and any(w.startswith("Dropped to fit one page:") for w in out.warnings)


def test_still_overflowing_is_an_error(conn, tmp_path, monkeypatch):
    monkeypatch.setattr(pdf_mod, "render_pdf", lambda html, p: {**fake_render_pdf(html, p), "overflow": True})
    out = _import(conn, tmp_path, good_result())
    assert not out.ok and "longer than one page" in out.errors[0] and out.fix_prompt


def test_submitted_records_draft_and_rules_version(conn, tmp_path):
    out = _import(conn, tmp_path, copy.deepcopy(good_result()))
    assert out.ok
    tracking.set_status(conn, users.owner(conn).id, "https://example.com/jobs/42", "submitted")
    row = dict(conn.execute("SELECT * FROM jobs").fetchone())
    assert row["submitted_draft_version"] == 1 and row["submitted_rules_version"] == wb.RULES_VERSION


def test_a_draft_is_the_jobs_users_only(conn, tmp_path):
    mine = add_job_row(conn)
    other = users.invite(conn, "b@example.com").id
    conn.execute("INSERT INTO jobs (user_id, url, title, job_key) VALUES (?, ?, 'Theirs', 'theirs')",
                 (other, mine["url"]))
    conn.commit()
    out = wb.import_data(conn, mine, copy.deepcopy(good_result()), inputs=inputs(), out_dir=tmp_path / "out")
    assert out.ok
    assert [tuple(r) for r in conn.execute("SELECT user_id, version FROM drafts").fetchall()] == [(mine["user_id"], 1)]
    theirs = dict(conn.execute("SELECT * FROM jobs WHERE user_id = ?", (other,)).fetchone())
    assert theirs["draft_version"] is None and theirs["user_status"] is None
    assert tracking.status_events(conn, other, mine["url"]) == []
    assert len(tracking.status_events(conn, mine["user_id"], mine["url"])) == 1


# ── Rules and instructions versions ──

@pytest.mark.parametrize("used, warned", [(wb.RULES_VERSION, None), (None, "didn't say"), ("0ld0ld00", "0ld0ld00")])
def test_rules_version_warning(conn, tmp_path, used, warned):
    data = good_result()
    if used:
        data["rules_version"] = used
    outcome = _import(conn, tmp_path, data)
    assert outcome.ok, outcome.errors
    found = [w for w in outcome.warnings if "rules" in w and wb.RULES_VERSION in w]
    if warned is None:
        assert found == []
    else:
        assert len(found) == 1 and warned in found[0] and "Open in Claude" in found[0]


@pytest.mark.parametrize("used, warned", [(wb.INSTRUCTIONS_VERSION, None), (None, "didn't say"),
                                         ("0ld0ld00", "old instructions (version 0ld0ld00)")])
def test_instructions_version_warning(conn, tmp_path, used, warned):
    data = good_result()
    data["rules_version"] = wb.RULES_VERSION
    if used:
        data["instructions_version"] = used
    outcome = _import(conn, tmp_path, data)
    assert outcome.ok, outcome.errors
    found = [w for w in outcome.warnings if "instructions" in w]
    if warned is None:
        assert found == []
    else:
        assert len(found) == 1 and warned in found[0] and wb.INSTRUCTIONS_VERSION in found[0]
        assert "Claude setup" in found[0] and "Strelitzia Resumes" in found[0]


# ── Draft Docs (docs-drafts-1-format Task 3) ──

def _draft_texts(data):
    from strelitzia.scoring import draft_docs as dd
    from workbench_helpers import library

    return (dd.resume_draft_text(data, library(), wb.RULES_VERSION, wb.INSTRUCTIONS_VERSION),
            dd.cover_draft_text(data["cover_letter"], wb.RULES_VERSION))


def test_import_drafts_accepts_a_rendered_valid_draft(conn, tmp_path):
    job = add_job_row(conn)
    resume_text, cover_text = _draft_texts(good_result())
    outcome = wb.import_drafts(conn, job, resume_text, cover_text, inputs=inputs(), out_dir=tmp_path / "out")
    assert outcome.ok, outcome.errors
    assert outcome.draft_version == 1 and outcome.files["resume"] and outcome.files["cover_letter"]
    assert not any("version" in w for w in outcome.warnings), outcome.warnings


def test_import_drafts_rejects_a_broken_draft_and_saves_nothing(conn, tmp_path):
    job = add_job_row(conn)
    resume_text, cover_text = _draft_texts(good_result())
    outcome = wb.import_drafts(conn, job, resume_text.replace(" [orders-pipeline]", ""), cover_text,
                               inputs=inputs(), out_dir=tmp_path / "out")
    assert not outcome.ok and outcome.errors[0].startswith("Resume draft, line")
    assert outcome.fix_prompt.endswith("Fix them in the two draft Docs and change nothing else.")
    assert "JSON" not in outcome.fix_prompt
    assert conn.execute("SELECT draft_version FROM jobs").fetchone()[0] is None


def test_import_drafts_check_errors_ask_for_doc_fixes(conn, tmp_path):
    job = add_job_row(conn)
    data = good_result()
    data["resume"]["skills"].append({"category": "Cloud", "items": "Kubernetes"})
    outcome = wb.import_drafts(conn, job, *_draft_texts(data), inputs=inputs(), out_dir=tmp_path / "out")
    assert not outcome.ok and any("Kubernetes" in e for e in outcome.errors)
    assert "draft Docs" in outcome.fix_prompt


def test_import_data_is_the_paste_path_without_extraction(conn, tmp_path):
    job = add_job_row(conn)
    outcome = wb.import_data(conn, job, good_result(), inputs=inputs(), out_dir=tmp_path / "out")
    assert outcome.ok and outcome.draft_version == 1


@pytest.mark.parametrize("version, warned", [("0ld0ld00", "Claude used rules version 0ld0ld00"),
                                             (None, "didn't say which rules version")])
def test_import_drafts_warns_about_the_resume_docs_rules_version(conn, tmp_path, version, warned):
    job = add_job_row(conn)
    resume_text, cover_text = _draft_texts(good_result())
    resume_text = resume_text.replace(f"Rules version: {wb.RULES_VERSION}\n",
                                      f"Rules version: {version}\n" if version else "")
    cover_text = cover_text.replace(f"Rules version: {wb.RULES_VERSION}\n", "")
    outcome = wb.import_drafts(conn, job, resume_text, cover_text, inputs=inputs(), out_dir=tmp_path / "out")
    assert outcome.ok, outcome.errors
    assert any(warned in w and wb.RULES_VERSION in w for w in outcome.warnings)


def test_import_drafts_warns_when_the_instructions_are_old(conn, tmp_path):
    job = add_job_row(conn)
    resume_text, cover_text = _draft_texts(good_result())
    resume_text = resume_text.replace(f"Instructions version: {wb.INSTRUCTIONS_VERSION}\n", "Instructions version: \n")
    outcome = wb.import_drafts(conn, job, resume_text, cover_text, inputs=inputs(), out_dir=tmp_path / "out")
    assert outcome.ok, outcome.errors
    assert [w for w in outcome.warnings if "version" in w] == [wb.instructions_version_warning(None)]


def test_the_rules_ask_for_the_version_line_at_the_top_of_the_resume_draft():
    text = wb.rules_text()
    assert "The first line of the resume draft is \"Rules version: \"" in text
