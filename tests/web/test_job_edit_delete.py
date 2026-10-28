"""Editing a job's details and deleting a job (job-edit-delete, issue #98)."""

import pytest
from web_helpers import act_as, add_job, second_user

from strelitzia import users
from strelitzia.database import job_key

URL = "https://boards.example.com/acme/jobs/7"
KEY = job_key(URL)
API = "/strelitzia/dashboard/api"


@pytest.fixture
def job(conn):
    add_job(conn, URL, title="Data Scientist", company="Acme", location="Austin, TX", work_mode="onsite",
            salary="$100k", deadline="2099-12-31", fit_score=70, assessed_at="2026-10-01T00:00:00+00:00",
            job_key=KEY)
    return URL


def _patch(client, **fields):
    return client.patch(f"{API}/jobs/{KEY}", json=fields)


@pytest.mark.parametrize("field,value,expected", [
    ("title", "  Senior Data Scientist ", "Senior Data Scientist"),
    ("company", "Acme Robotics", "Acme Robotics"),
    ("location", "Remote, US", "Remote, US"),
    ("location", "", None),
    ("work_mode", "hybrid", "hybrid"),
    ("salary", "$120k - $150k", "$120k - $150k"),
    ("salary", None, None),
    ("deadline", "2026-12-01", "2026-12-01"),
    ("deadline", None, None),
])
def test_patch_saves_each_field(client, conn, job, field, value, expected):
    r = _patch(client, **{field: value})
    assert r.status_code == 200, r.text
    assert r.json()[field] == expected
    row = conn.execute(f"SELECT {field} FROM jobs WHERE url = ?", (URL,)).fetchone()
    assert row[0] == expected


def test_patch_changes_only_the_fields_sent(client, job):
    d = _patch(client, location="Denver, CO").json()
    assert (d["title"], d["company"], d["salary"], d["deadline"]) == ("Data Scientist", "Acme", "$100k", "2099-12-31")


@pytest.mark.parametrize("fields", [{"title": ""}, {"title": "   "}, {"company": None}, {"work_mode": "moon"},
                                    {"deadline": "soon"}])
def test_patch_rejects_bad_values(client, conn, job, fields):
    assert _patch(client, **fields).status_code == 422
    assert conn.execute("SELECT title, company FROM jobs WHERE url = ?", (URL,)).fetchone()[:] == ("Data Scientist",
                                                                                                 "Acme")


@pytest.mark.parametrize("fields,stale", [
    ({"title": "ML Engineer"}, True),
    ({"company": "Globex"}, True),
    ({"title": "Data Scientist"}, False),  # unchanged
    ({"location": "Remote", "salary": "$1", "deadline": "2026-12-01", "work_mode": "remote"}, False),
])
def test_editing_title_or_company_makes_the_score_stale(client, job, fields, stale):
    assert _patch(client).json()["score_stale"] is False
    assert _patch(client, **fields).json()["score_stale"] is stale


def test_a_rescore_after_the_edit_clears_score_stale(client, conn, job):
    assert _patch(client, title="ML Engineer").json()["score_stale"] is True
    conn.execute("UPDATE jobs SET assessed_at = '2999-01-01T00:00:00+00:00' WHERE url = ?", (URL,))
    conn.commit()
    assert client.get(f"{API}/jobs/{KEY}").json()["score_stale"] is False


def test_an_unscored_job_is_never_score_stale(client, conn, job):
    conn.execute("UPDATE jobs SET fit_score = NULL, assessed_at = NULL WHERE url = ?", (URL,))
    conn.commit()
    assert _patch(client, title="ML Engineer").json()["score_stale"] is False


def test_patch_another_users_job_is_404(client, conn, job, monkeypatch):
    act_as(monkeypatch, second_user(conn))
    assert _patch(client, title="Mine now").status_code == 404
    act_as(monkeypatch, users.owner(conn))
    assert client.get(f"{API}/jobs/{KEY}").json()["title"] == "Data Scientist"
