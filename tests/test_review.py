"""Recruiter review (strelitzia.scoring.review): the scale, the prompt and importing pasted replies."""

import copy
import json

import pytest

from strelitzia import users
from strelitzia.database import init_db
from strelitzia.scoring import review
from workbench_helpers import add_job_row

URL = "https://example.com/jobs/01"
LETTER = {"paragraphs": ["I want to build Initech's payments pipelines.", "At Acme I moved orders to Airflow."],
          "evidence_slugs": []}


@pytest.fixture
def conn(tmp_path):
    return init_db(tmp_path / "review.db")


def _me(conn):
    return users.owner(conn).id


def add_draft(conn, version=1, letter=LETTER, text="Alex Tester\nData engineer, Airflow pipelines\n"):
    draft_id = f"d-{version}"
    conn.execute(
        "INSERT INTO drafts (id, job_url, version, rules_version, resume_json, resume_text, cover_json, "
        "coverage_json, created_at) VALUES (?, ?, ?, 'r1', '{}', ?, ?, '{}', ?)",
        (draft_id, URL, version, text, json.dumps(letter), f"2026-10-0{version}T00:00:00+00:00"),
    )
    conn.commit()
    return draft_id


@pytest.fixture
def job(conn):
    return add_job_row(conn, url=URL, job_key="key01", title="Data Engineer", company="Initech",
                       full_description="We need a data engineer who knows Airflow.",
                       details_json=json.dumps({"skills_required": ["Airflow"], "skills_preferred": ["Terraform"]}))


def good_reply(**overrides) -> dict:
    criteria = {key: {"grade": "B+", "evidence": "\"Airflow pipelines\"", "fix": "Add a number."}
                for key in review.CRITERIA_KEYS}
    data = {"review": 1, "prompt_version": review.PROMPT_VERSION,
            "resume": {"criteria": criteria, "overall": "B+"},
            "cover_letter": {"criteria": copy.deepcopy(criteria), "overall": "C"},
            "verdict": "maybe", "top_fixes": ["One", "Two", "Three"]}
    data.update(overrides)
    return data


def fenced(data, tag="json") -> str:
    return f"Here is my review.\n\n```{tag}\n{json.dumps(data, indent=2)}\n```\n"


def test_grade_scale():
    assert len(review.GRADES) == 15
    assert review.grade_points("A+") == 14 and review.grade_points("C") == 7 and review.grade_points("F-") == 0
    assert [review.grade_points(g) for g in review.GRADES] == list(range(14, -1, -1))
    with pytest.raises(ValueError):
        review.grade_points("E")


def test_prompt_has_the_role_every_criterion_both_documents_and_the_format(conn, job):
    add_draft(conn)
    draft = review.latest_draft(conn, _me(conn), URL)
    prompt = review.review_prompt(job, draft)
    assert "You are a recruiter hiring for Data Engineer at Initech" in prompt
    assert "job description below is your hiring criteria" in prompt
    assert f"Prompt version: {review.PROMPT_VERSION}" in prompt
    for _key, name, _meaning in review.CRITERIA:
        assert name in prompt
    assert " ".join(review.GRADES) in prompt
    assert "We need a data engineer who knows Airflow." in prompt
    assert "- Airflow" in prompt and "- Terraform" in prompt
    assert "Data engineer, Airflow pipelines" in prompt
    assert "I want to build Initech's payments pipelines.\n\nAt Acme I moved orders to Airflow." in prompt
    assert '"top_fixes"' in prompt and "```json" in prompt
    # Self-contained: nothing points at a project, connector or file.
    for word in ("project instructions", "connector", "attached"):
        assert word not in prompt.lower()


def test_prompt_without_a_cover_letter_asks_for_null(conn, job):
    add_draft(conn, letter=None)
    prompt = review.review_prompt(job, review.latest_draft(conn, _me(conn), URL))
    assert "There is no cover letter: set cover_letter to null." in prompt


def test_prompt_version_ignores_the_job_and_draft():
    # It hashes only the fixed parts, so two jobs' prompts share it.
    a = review.review_prompt({"title": "A", "company": "X"}, {"resume_text": "one"})
    b = review.review_prompt({"title": "B", "company": "Y"}, {"resume_text": "two"})
    assert f"Prompt version: {review.PROMPT_VERSION}" in a and f"Prompt version: {review.PROMPT_VERSION}" in b
    assert len(review.PROMPT_VERSION) == 8


def test_example_reply_matches_the_schema():
    example = copy.deepcopy(review.EXAMPLE_REPLY)
    for item in example["cover_letter"]["criteria"].values():
        item["grade"] = "B"
    assert review.schema_errors(example, review.REPLY_SCHEMA) == []


def test_create_review_uses_the_latest_draft(conn, job):
    add_draft(conn, 1)
    add_draft(conn, 2)
    review_id = review.create_review(conn, _me(conn), job)
    got = review.get_review(conn, _me(conn), review_id)
    assert got["draft_id"] == "d-2" and got["draft_version"] == 2
    assert got["prompt_version"] == review.PROMPT_VERSION
    assert got["job"]["key"] == "key01" and got["replies"] == []


def test_create_review_without_a_draft(conn, job):
    with pytest.raises(review.NoDraft):
        review.create_review(conn, _me(conn), job)


@pytest.mark.parametrize("grader", review.GRADERS)
def test_good_reply_imports_for_each_grader(conn, job, grader):
    add_draft(conn)
    review_id = review.create_review(conn, _me(conn), job)
    outcome = review.import_reply(conn, _me(conn), review_id, grader, "Some Model 5", fenced(good_reply()))
    assert outcome.ok, outcome.errors
    assert outcome.warnings == []
    [reply] = review.get_review(conn, _me(conn), review_id)["replies"]
    assert reply["grader"] == grader and reply["model_label"] == "Some Model 5"
    assert (reply["overall_resume"], reply["overall_cover"], reply["verdict"]) == ("B+", "C", "maybe")
    assert reply["reply"]["resume"]["criteria"]["evidence"]["fix"] == "Add a number."


@pytest.mark.parametrize("text", [
    fenced(good_reply(), tag="json"),  # Claude
    fenced(good_reply(), tag=""),  # ChatGPT sometimes drops the tag
    fenced(good_reply(), tag="JSON"),
    json.dumps(good_reply()),  # Gemini: bare JSON as the whole reply
    "  \n" + json.dumps(good_reply(), indent=2) + "\n",
], ids=["fenced-json", "fenced-untagged", "fenced-upper", "bare", "bare-padded"])
def test_reply_formats_from_each_chat(conn, job, text):
    add_draft(conn)
    review_id = review.create_review(conn, _me(conn), job)
    outcome = review.import_reply(conn, _me(conn), review_id, "gemini", "", text)
    assert outcome.ok, outcome.errors


def test_reimport_replaces_that_graders_reply(conn, job):
    add_draft(conn)
    review_id = review.create_review(conn, _me(conn), job)
    me = _me(conn)
    assert review.import_reply(conn, me, review_id, "chatgpt", "GPT-5", fenced(good_reply())).ok
    assert review.import_reply(conn, me, review_id, "claude-opus", "Opus", fenced(good_reply())).ok
    assert review.import_reply(conn, me, review_id, "chatgpt", "GPT-5 Thinking",
                               fenced(good_reply(verdict="yes"))).ok
    replies = review.get_review(conn, me, review_id)["replies"]
    assert [(r["grader"], r["model_label"], r["verdict"]) for r in replies] == [
        ("claude-opus", "Opus", "maybe"), ("chatgpt", "GPT-5 Thinking", "yes")]


def test_grades_as_models_write_them_are_tidied(conn, job):
    add_draft(conn)
    review_id = review.create_review(conn, _me(conn), job)
    data = good_reply(verdict="Maybe")
    data["resume"]["overall"] = " a− "
    data["resume"]["criteria"]["polish"]["grade"] = "b+"
    assert review.import_reply(conn, _me(conn), review_id, "chatgpt", "", fenced(data)).ok
    [reply] = review.get_review(conn, _me(conn), review_id)["replies"]
    assert reply["overall_resume"] == "A-" and reply["verdict"] == "maybe"
    assert reply["reply"]["resume"]["criteria"]["polish"]["grade"] == "B+"


def _import(conn, job, text, grader="chatgpt"):
    if review.latest_draft(conn, _me(conn), URL) is None:
        add_draft(conn)
    review_id = review.create_review(conn, _me(conn), job)
    return review.import_reply(conn, _me(conn), review_id, grader, "", text), review_id


def test_wrong_grade_string_is_a_clear_error(conn, job):
    data = good_reply()
    data["resume"]["criteria"]["clarity"]["grade"] = "E"
    outcome, review_id = _import(conn, job, fenced(data))
    assert not outcome.ok
    assert "$.resume.criteria.clarity.grade" in outcome.errors[0] and '"E" is not allowed' in outcome.errors[0]
    assert review.get_review(conn, _me(conn), review_id)["replies"] == []


def test_missing_criterion_is_a_clear_error(conn, job):
    data = good_reply()
    del data["cover_letter"]["criteria"]["human_tone"]
    outcome, _ = _import(conn, job, fenced(data))
    assert not outcome.ok
    assert '$.cover_letter.criteria: missing "human_tone"' in outcome.errors[0]


def test_wrong_or_missing_prompt_version_warns(conn, job):
    outcome, _ = _import(conn, job, fenced(good_reply(prompt_version="deadbeef")))
    assert outcome.ok
    assert any("deadbeef" in w and review.PROMPT_VERSION in w for w in outcome.warnings)
    data = good_reply()
    del data["prompt_version"]
    outcome, _ = _import(conn, job, fenced(data), grader="gemini")
    assert outcome.ok and any("doesn't say which prompt version" in w for w in outcome.warnings)


def test_top_fixes(conn, job):
    outcome, _ = _import(conn, job, fenced(good_reply(top_fixes=["Only one"])))
    assert outcome.ok and any("1 top fixes, not 3" in w for w in outcome.warnings)
    outcome, _ = _import(conn, job, fenced(good_reply(top_fixes=[])), grader="gemini")
    assert not outcome.ok and "no top fixes" in outcome.errors[0]


def test_cover_letter_null_when_the_draft_has_none(conn, job):
    add_draft(conn, letter=None)
    review_id = review.create_review(conn, _me(conn), job)
    outcome = review.import_reply(conn, _me(conn), review_id, "chatgpt", "", fenced(good_reply(cover_letter=None)))
    assert outcome.ok and outcome.warnings == []
    assert review.get_review(conn, _me(conn), review_id)["replies"][0]["overall_cover"] is None


def test_cover_letter_null_when_the_draft_has_one_warns(conn, job):
    outcome, _ = _import(conn, job, fenced(good_reply(cover_letter=None)))
    assert outcome.ok and any("didn't grade the cover letter" in w for w in outcome.warnings)


def test_other_errors(conn, job):
    add_draft(conn)
    me = _me(conn)
    review_id = review.create_review(conn, me, job)
    assert "Unknown grader" in review.import_reply(conn, me, review_id, "bard", "", fenced(good_reply())).errors[0]
    assert review.import_reply(conn, me, "nope", "chatgpt", "", fenced(good_reply())).errors == ["No such review."]
    assert "Nothing was pasted" in review.import_reply(conn, me, review_id, "chatgpt", "", "  ").errors[0]
    assert "at most" in review.import_reply(conn, me, review_id, "chatgpt", "x" * 101, fenced(good_reply())).errors[0]
    assert "unexpected key" in review.import_reply(conn, me, review_id, "chatgpt", "",
                                                   fenced(good_reply(score=3))).errors[0]
    assert "not allowed" in review.import_reply(conn, me, review_id, "chatgpt", "",
                                                fenced(good_reply(verdict="strong yes"))).errors[0]


def test_list_reviews_newest_first_with_grades(conn, job):
    add_draft(conn)
    me = _me(conn)
    first = review.create_review(conn, me, job)
    second = review.create_review(conn, me, job)
    conn.execute("UPDATE reviews SET created_at = '2026-01-01T00:00:00+00:00' WHERE id = ?", (first,))
    conn.commit()
    assert review.import_reply(conn, me, second, "gemini", "Gemini 3 Pro", fenced(good_reply())).ok
    listed = review.list_reviews(conn, me)
    assert [r["id"] for r in listed] == [second, first]
    assert listed[0]["grades"][0]["grader"] == "gemini"
    assert listed[0]["grades"][0]["overall_resume"] == "B+"
    assert listed[0]["job"]["title"] == "Data Engineer"
    assert [r["id"] for r in review.list_reviews(conn, me, job_url="https://example.com/other")] == []
