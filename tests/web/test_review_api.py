"""Recruiter review routes: create a review of a job's latest draft, paste graders' replies, list reviews."""

import copy
import json

import pytest
from web_helpers import act_as, add_job, second_user

from strelitzia.scoring import review

API = "/strelitzia/dashboard/api"
URL = "https://example.com/jobs/01"
KEY = "key01"


def _draft(conn, version, user_id=None):
    cols = "id, job_url, version, rules_version, resume_json, resume_text, cover_json, coverage_json, created_at"
    values = [f"d{version}-{user_id or 'me'}", URL, version, "r1", "{}", f"Alex Tester\nResume take {version}\n",
              json.dumps({"paragraphs": ["Dear team, I like Initech."]}), "{}", f"2026-10-0{version}T00:00:00+00:00"]
    if user_id:
        cols, values = cols + ", user_id", [*values, user_id]
    conn.execute(f"INSERT INTO drafts ({cols}) VALUES ({', '.join('?' * len(values))})", tuple(values))
    conn.commit()


@pytest.fixture
def job(conn):
    add_job(conn, URL, title="Data Engineer", company="Initech", job_key=KEY,
            details_json=json.dumps({"skills_required": ["Airflow"], "skills_preferred": ["dbt"]}))
    return KEY


def _reply(overall="B", verdict="maybe") -> str:
    criteria = {key: {"grade": overall, "evidence": "\"Resume take 2\"", "fix": "Say more."}
                for key in review.CRITERIA_KEYS}
    data = {"review": 1, "prompt_version": review.PROMPT_VERSION,
            "resume": {"criteria": criteria, "overall": overall},
            "cover_letter": {"criteria": copy.deepcopy(criteria), "overall": "C+"},
            "verdict": verdict, "top_fixes": ["a", "b", "c"]}
    return "My review.\n```json\n" + json.dumps(data) + "\n```"


def test_full_flow_for_two_graders(client, conn, job):
    _draft(conn, 1)
    _draft(conn, 2)
    res = client.post(f"{API}/jobs/{KEY}/reviews")
    assert res.status_code == 201, res.text
    created = res.json()
    review_id = created["id"]
    assert created["draft_version"] == 2 and created["replies"] == []
    assert [c["key"] for c in created["criteria"]] == list(review.CRITERIA_KEYS)
    assert "You are a recruiter hiring for Data Engineer at Initech" in created["prompt"]
    assert "Resume take 2" in created["prompt"] and "Dear team, I like Initech." in created["prompt"]

    res = client.post(f"{API}/reviews/{review_id}/replies",
                      json={"grader": "chatgpt", "model_label": "GPT-5 Thinking", "text": _reply("B+", "yes")})
    assert res.status_code == 200, res.text
    assert res.json()["warnings"] == []
    res = client.post(f"{API}/reviews/{review_id}/replies",
                      json={"grader": "claude-opus", "model_label": "Opus 5.5", "text": _reply("B-", "maybe")})
    assert res.status_code == 200, res.text
    body = res.json()["review"]
    assert [(r["grader"], r["model_label"], r["overall_resume"], r["overall_cover"], r["verdict"])
            for r in body["replies"]] == [("claude-opus", "Opus 5.5", "B-", "C+", "maybe"),
                                          ("chatgpt", "GPT-5 Thinking", "B+", "C+", "yes")]
    assert body["replies"][1]["reply"]["resume"]["criteria"]["relevance"]["fix"] == "Say more."

    fetched = client.get(f"{API}/reviews/{review_id}").json()
    assert fetched["prompt"] == created["prompt"] and len(fetched["replies"]) == 2

    listed = client.get(f"{API}/reviews").json()
    assert [r["id"] for r in listed] == [review_id]
    assert {g["grader"]: g["overall_resume"] for g in listed[0]["grades"]} == {"claude-opus": "B-", "chatgpt": "B+"}
    assert listed[0]["job"] == {"key": KEY, "title": "Data Engineer", "company": "Initech"}
    assert [r["id"] for r in client.get(f"{API}/jobs/{KEY}/reviews").json()] == [review_id]


def test_reviews_newest_first(client, conn, job):
    _draft(conn, 1)
    first = client.post(f"{API}/jobs/{KEY}/reviews").json()["id"]
    conn.execute("UPDATE reviews SET created_at = '2026-01-01T00:00:00+00:00' WHERE id = ?", (first,))
    conn.commit()
    second = client.post(f"{API}/jobs/{KEY}/reviews").json()["id"]
    assert [r["id"] for r in client.get(f"{API}/reviews").json()] == [second, first]


def test_no_draft_is_409(client, job):
    res = client.post(f"{API}/jobs/{KEY}/reviews")
    assert res.status_code == 409 and "no draft" in res.json()["detail"]
    assert client.post(f"{API}/jobs/nope/reviews").status_code == 404


def test_bad_reply_is_422_with_errors(client, conn, job):
    _draft(conn, 1)
    review_id = client.post(f"{API}/jobs/{KEY}/reviews").json()["id"]
    res = client.post(f"{API}/reviews/{review_id}/replies",
                      json={"grader": "gemini", "text": _reply("E")})
    assert res.status_code == 422
    assert "is not allowed" in res.json()["detail"] and res.json()["errors"]
    assert client.post(f"{API}/reviews/{review_id}/replies",
                       json={"grader": "bard", "text": _reply()}).status_code == 422
    assert client.get(f"{API}/reviews/{review_id}").json()["replies"] == []


def test_old_prompt_version_warns(client, conn, job):
    _draft(conn, 1)
    review_id = client.post(f"{API}/jobs/{KEY}/reviews").json()["id"]
    text = _reply().replace(review.PROMPT_VERSION, "00000000")
    res = client.post(f"{API}/reviews/{review_id}/replies", json={"grader": "other", "text": text})
    assert res.status_code == 200 and "00000000" in res.json()["warnings"][0]


def test_another_users_review_is_404(client, conn, job, monkeypatch):
    _draft(conn, 1)
    review_id = client.post(f"{API}/jobs/{KEY}/reviews").json()["id"]
    act_as(monkeypatch, second_user(conn))
    assert client.get(f"{API}/reviews/{review_id}").status_code == 404
    assert client.post(f"{API}/reviews/{review_id}/replies",
                       json={"grader": "chatgpt", "text": _reply()}).status_code == 404
    assert client.get(f"{API}/reviews").json() == []
    assert client.get(f"{API}/jobs/{KEY}/reviews").status_code == 404  # the job is the owner's


def test_creating_a_review_uses_the_workbench_gate(client, conn, job, monkeypatch):
    other = second_user(conn)
    add_job(conn, URL, title="Data Engineer", company="Initech", job_key=KEY, user_id=other.id)
    _draft(conn, 1, user_id=other.id)
    act_as(monkeypatch, other)
    assert client.post(f"{API}/jobs/{KEY}/reviews").status_code == 403


def test_deleting_the_job_deletes_its_reviews(client, conn, job):
    _draft(conn, 1)
    review_id = client.post(f"{API}/jobs/{KEY}/reviews").json()["id"]
    client.post(f"{API}/reviews/{review_id}/replies", json={"grader": "chatgpt", "text": _reply()})
    assert client.delete(f"{API}/jobs/{KEY}").status_code == 200
    assert client.get(f"{API}/reviews/{review_id}").status_code == 404
    assert conn.execute("SELECT COUNT(*) FROM review_grades").fetchone()[0] == 0


def test_the_old_panel_still_answers(client):
    assert client.get(f"{API}/panel").status_code == 200


def test_graders_endpoint_compares_graders_per_user(client, conn, job, monkeypatch):
    _draft(conn, 1)
    review_id = client.post(f"{API}/jobs/{KEY}/reviews").json()["id"]
    for grader, overall, verdict in (("claude-opus", "A-", "yes"), ("gemini", "C", "yes")):
        res = client.post(f"{API}/reviews/{review_id}/replies", json={"grader": grader, "text": _reply(overall, verdict)})
        assert res.status_code == 200, res.text
    body = client.get(f"{API}/reviews/graders").json()
    assert body["reviews"] == 1
    assert [g["grader"] for g in body["graders"]] == ["claude-opus", "gemini"]
    assert all(g["verdict_agreement"] == 1.0 for g in body["graders"])
    assert body["graders"][0]["tendency"] == "lenient"
    act_as(monkeypatch, second_user(conn))
    assert client.get(f"{API}/reviews/graders").json()["graders"] == []
