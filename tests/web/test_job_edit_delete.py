"""Editing a job's details and deleting a job (job-edit-delete, issue #98)."""

import pytest
from web_helpers import act_as, add_job, second_user

from strelitzia import database, users
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


def _seed_everything(conn, user_id):
    """One row for URL in every side table, owned by `user_id`."""
    rows = [
        ("status_events", {"id": f"se-{user_id}", "url": URL, "to_status": "submitted"}),
        ("dashboard_tasks", {"id": f"t-{user_id}", "url": URL, "kind": "intake", "state": "queued"}),
        ("contacts", {"id": f"c-{user_id}", "name": "Sam"}),
        ("job_contacts", {"job_url": URL, "contact_id": f"c-{user_id}", "relation": "recruiter"}),
        ("interviews", {"id": f"i-{user_id}", "job_url": URL, "stage": "phone"}),
        ("drafts", {"id": f"d-{user_id}", "job_url": URL, "version": 1}),
        ("panel_runs", {"id": f"r-{user_id}", "status": "open"}),
        ("llm_usage", {"id": f"u-{user_id}", "job_url": URL, "cost_usd": 0.01}),
    ]
    for table, row in rows:
        row = {**row, "user_id": user_id}
        conn.execute(f"INSERT INTO {table} ({', '.join(row)}) VALUES ({', '.join('?' * len(row))})",
                     tuple(row.values()))
    conn.execute("INSERT INTO panel_items (run_id, item_no, job_url) VALUES (?, 1, ?)", (f"r-{user_id}", URL))
    conn.execute("INSERT INTO panel_grades (run_id, item_no, grader, winner) VALUES (?, 1, 'you', 'first')",
                 (f"r-{user_id}",))
    conn.commit()


def _count(conn, table, where, params):
    return conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {where}", params).fetchone()[0]


def test_delete_removes_the_job_and_everything_that_belongs_to_it(client, conn, job, monkeypatch):
    owner = users.owner(conn)
    other = second_user(conn)
    add_job(conn, URL, user_id=other.id, job_key=KEY)  # the same posting, tracked by another user
    _seed_everything(conn, owner.id)
    _seed_everything(conn, other.id)

    r = client.delete(f"{API}/jobs/{KEY}")
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True

    for uid, left in ((owner.id, 0), (other.id, 1)):
        assert _count(conn, "jobs", "user_id = ? AND url = ?", (uid, URL)) == left
        for table, column in database.JOB_TABLES.items():
            assert _count(conn, table, f"user_id = ? AND {column} = ?", (uid, URL)) == left, table
        assert _count(conn, "panel_items", "run_id = ?", (f"r-{uid}",)) == left
        assert _count(conn, "panel_grades", "run_id = ?", (f"r-{uid}",)) == left
        assert _count(conn, "panel_runs", "id = ?", (f"r-{uid}",)) == left  # an open run can't be graded without it
        assert _count(conn, "contacts", "user_id = ?", (uid,)) == 1  # contacts are shared across jobs: they stay
        assert _count(conn, "llm_usage", "user_id = ? AND job_url = ?", (uid, URL)) == 1  # the spend history stays
    assert client.get(f"{API}/jobs/{KEY}").status_code == 404
    act_as(monkeypatch, other)
    assert client.get(f"{API}/jobs/{KEY}").status_code == 200


def test_delete_keeps_a_complete_panel_run_without_the_job(client, conn, job):
    owner = users.owner(conn)
    _seed_everything(conn, owner.id)
    conn.execute("UPDATE panel_runs SET status = 'complete'")
    conn.execute("INSERT INTO panel_items (run_id, item_no, job_url) VALUES (?, 2, 'https://example.com/other')",
                 (f"r-{owner.id}",))
    conn.execute("INSERT INTO panel_grades (run_id, item_no, grader, winner) VALUES (?, 2, 'you', 'tie')",
                 (f"r-{owner.id}",))
    conn.commit()
    assert client.delete(f"{API}/jobs/{KEY}").status_code == 200
    assert _count(conn, "panel_runs", "id = ?", (f"r-{owner.id}",)) == 1
    assert [r[0] for r in conn.execute("SELECT item_no FROM panel_items").fetchall()] == [2]
    assert [r[0] for r in conn.execute("SELECT item_no FROM panel_grades").fetchall()] == [2]


def test_delete_says_the_drive_folder_stays(client, conn, job):
    folder = "https://drive.google.com/drive/folders/abc"
    conn.execute("UPDATE jobs SET drive_folder_url = ? WHERE url = ?", (folder, URL))
    conn.commit()
    body = client.delete(f"{API}/jobs/{KEY}").json()
    assert body["drive_folder"] == folder and "Google Drive" in body["message"]


def test_delete_another_users_job_is_404(client, conn, job, monkeypatch):
    act_as(monkeypatch, second_user(conn))
    assert client.delete(f"{API}/jobs/{KEY}").status_code == 404
    assert _count(conn, "jobs", "url = ?", (URL,)) == 1
    assert client.delete(f"{API}/jobs/doesnotexist").status_code == 404


def test_delete_cancels_the_jobs_queued_tasks(client, conn, job):
    task = client.post(f"{API}/jobs/{KEY}/rescore").json()
    assert task["state"] == "queued"
    client.delete(f"{API}/jobs/{KEY}")
    assert client.get(f"{API}/tasks/{task['id']}").status_code == 404
    assert conn.execute("SELECT 1 FROM dashboard_tasks WHERE state = 'queued'").fetchone() is None


def test_delete_covers_every_table_with_a_job_url(conn):
    """A new side table keyed by a job's url must be added to JOB_TABLES (or KEPT_JOB_TABLES) deliberately."""
    found = set()
    for (table,) in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall():
        if table != "jobs" and database.table_columns(conn, table) & {"url", "job_url"}:
            found.add(table)
    assert found == {*database.JOB_TABLES, *database.KEPT_JOB_TABLES, "panel_items"}


def test_hand_edits_survive_extraction_and_classify(client, conn, job):
    from strelitzia.enrichment.classify import run_classify
    from strelitzia.enrichment.extract import _save_posting
    from strelitzia.enrichment.posting_model import JobPosting, Location

    _patch(client, work_mode="remote", deadline="2026-12-01", location="Denver, CO")
    row = conn.execute("SELECT location_city, location_state, edited_fields FROM jobs WHERE url = ?", (URL,)).fetchone()
    assert (row[0], row[1]) == ("Denver", "CO")  # the Jobs location filter matches the parsed parts too
    assert row[2] == '["deadline", "location", "work_mode"]'
    owner = users.owner(conn).id
    run_classify(conn)
    posting = JobPosting(work_mode="onsite", application_deadline="2027-01-31", seniority="senior",
                         locations=[Location(city="Austin", state="TX", country="US")])
    _save_posting(conn, owner, URL, posting)
    conn.commit()
    d = client.get(f"{API}/jobs/{KEY}").json()
    assert (d["work_mode"], d["deadline"], d["location_city"], d["seniority"]) == ("remote", "2026-12-01", "Denver",
                                                                                   "senior")


def test_extraction_still_fills_fields_nobody_edited(client, conn, job):
    from strelitzia.enrichment.extract import _save_posting
    from strelitzia.enrichment.posting_model import JobPosting

    _patch(client, salary="$1")
    _save_posting(conn, users.owner(conn).id, URL, JobPosting(work_mode="hybrid", application_deadline="2027-01-31"))
    conn.commit()
    d = client.get(f"{API}/jobs/{KEY}").json()
    assert (d["work_mode"], d["deadline"], d["salary"]) == ("hybrid", "2027-01-31", "$1")


def test_the_assessment_sees_the_corrected_company(conn, job):
    import json

    from strelitzia.scoring.assessment import posting_document

    row = dict(conn.execute("SELECT * FROM jobs WHERE url = ?", (URL,)).fetchone())
    row["details_json"] = json.dumps({"company": "Acme Inc (from the posting)"})
    assert posting_document(row)["company"] == "Acme Inc (from the posting)"
    row.update(company="Acme Robotics", edited_fields='["company"]')
    assert posting_document(row)["company"] == "Acme Robotics"


def test_delete_removes_local_draft_files_but_not_another_users(client, conn, job, tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    mine = {n: out / n for n in ("A_x.txt", "A_x.pdf", "A_x_RESULT.json", "A_x_REPORT.json", "A_x_CL.pdf", "A_x_CL.txt")}
    shared = {n: out / n for n in ("B_y.txt", "B_y_RESULT.json")}
    unrelated = out / "C_z.pdf"
    for p in (*mine.values(), *shared.values(), unrelated):
        p.write_text("x")
    conn.execute("UPDATE jobs SET tailored_resume_path = ?, cover_letter_path = ? WHERE url = ?",
                 (str(mine["A_x.txt"]), str(mine["A_x_CL.pdf"]), URL))
    other_url = "https://example.com/jobs/shared"
    add_job(conn, other_url, job_key=job_key(other_url), tailored_resume_path=str(shared["B_y.txt"]))
    add_job(conn, other_url, user_id=second_user(conn).id, job_key=job_key(other_url),
            tailored_resume_path=str(shared["B_y.txt"]))
    conn.commit()
    assert client.delete(f"{API}/jobs/{KEY}").status_code == 200
    assert not any(p.exists() for p in mine.values())
    assert client.delete(f"{API}/jobs/{job_key(other_url)}").status_code == 200
    assert all(p.exists() for p in shared.values()) and unrelated.exists()  # the other user's row still uses them
