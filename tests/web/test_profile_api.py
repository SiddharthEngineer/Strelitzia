"""Profile page API: the fields, and the Profile Docs (setup and sync) that hold the content library and resume. Fake data only."""

from unittest.mock import patch

import pytest
from web_helpers import act_as, second_user

from strelitzia import config, users
from strelitzia import profile as store

LIBRARY = "# Content library\n\n## CURRENT ROLE: Widget Engineer, Acme\n\n### Project: Widgets\n- Built widgets.\n"


@pytest.fixture(autouse=True)
def _no_budget_no_files(monkeypatch, tmp_path):
    """No global budget, and no app-dir files for the app's start to import into the owner's profile."""
    monkeypatch.delenv("LLM_MONTHLY_BUDGET_USD", raising=False)
    for attr in ("PROFILE_PATH", "RESUME_PATH", "RESUME_PDF_PATH", "CONTENT_LIBRARY_PATH", "RESUME_FIXED_PATH"):
        monkeypatch.setattr(config, attr, tmp_path / "no-app-dir" / attr.lower())


def test_get_starts_empty_with_the_education_options(client):
    body = client.get("/strelitzia/dashboard/api/profile").json()
    assert body["profile"]["first_name"] == "" and body["profile"]["skills"] == []
    assert body["profile"]["years_experience"] is None and body["profile"]["education_level"] is None
    assert body["has_resume"] is False and body["resume_file_name"] is None
    assert body["content_library_md"] == "" and body["content_library_error"] is None
    assert body["options"]["education_level"] == list(store.PROFILE_EDUCATION_LEVELS)


def test_put_saves_the_fields_and_keeps_the_rest(client, conn):
    owner = users.owner(conn).id
    store.save_profile(conn, owner, store.UserProfile(resume_text="old resume", content_library_md=LIBRARY,
                                                      extras={"resume_facts": {"x": 1}}))
    r = client.put("/strelitzia/dashboard/api/profile", json={
        "first_name": " Ada ", "last_name": "Example", "phone": "555-000-0000", "email": "ada@example.com",
        "linkedin_url": "https://www.linkedin.com/in/example", "github_url": "https://github.com/example",
        "location": "Springfield", "current_job_title": "Widget Engineer", "years_experience": 4.5,
        "education_level": "masters", "skills": ["Python", " python ", "SQL", ""],
        "content_library_md": "ignored: the library is edited in its Profile Doc"})
    assert r.status_code == 200, r.text
    assert r.json()["profile"]["first_name"] == "Ada" and r.json()["profile"]["skills"] == ["Python", "SQL"]
    assert r.json()["content_library_error"] is None
    saved = store.load_profile(conn, owner)
    assert (saved.phone, saved.years_experience, saved.education_level) == ("555-000-0000", 4.5, "masters")
    assert saved.content_library_md == LIBRARY
    assert saved.resume_text == "old resume" and saved.extras == {"resume_facts": {"x": 1}}
    assert client.get("/strelitzia/dashboard/api/profile").json()["profile"]["phone"] == "555-000-0000"


@pytest.mark.parametrize("field,value", [
    ("email", "not-an-email"),
    ("linkedin_url", "https://evil.example.com/in/x"),
    ("linkedin_url", "linkedin.com/in/x"),
    ("github_url", "https://github.com.evil.com/x"),
    ("github_url", "javascript:alert(1)"),
    ("years_experience", -1),
    ("education_level", "wizard"),
    ("education_level", "unknown"),
])
def test_put_rejects_bad_values(client, conn, field, value):
    r = client.put("/strelitzia/dashboard/api/profile", json={field: value})
    assert r.status_code == 422
    assert not store.has_profile(conn, users.owner(conn).id)


def test_profiles_are_per_user(client, conn, monkeypatch):
    client.put("/strelitzia/dashboard/api/profile", json={"first_name": "Owner"})
    act_as(monkeypatch, second_user(conn))
    assert client.get("/strelitzia/dashboard/api/profile").json()["profile"]["first_name"] == ""
    client.put("/strelitzia/dashboard/api/profile", json={"first_name": "Bo"})
    assert store.load_profile(conn, users.owner(conn).id).first_name == "Owner"


def test_download_without_a_file_is_a_404(client):
    assert client.get("/strelitzia/dashboard/api/profile/resume").status_code == 404


def test_mutations_need_the_header(app):
    from fastapi.testclient import TestClient

    with TestClient(app) as bare:
        assert bare.put("/strelitzia/dashboard/api/profile", json={}).status_code == 403
        assert bare.post("/strelitzia/dashboard/api/profile/docs/sync").status_code == 403


def test_a_put_leaves_the_fields_it_doesnt_send(client, conn):
    store.save_profile(conn, users.owner(conn).id, store.UserProfile(content_library_md=LIBRARY))
    client.put("/strelitzia/dashboard/api/profile", json={"first_name": "Ada", "skills": ["Go"]})
    r = client.put("/strelitzia/dashboard/api/profile", json={"phone": "555-000-0000"})
    assert r.status_code == 200
    saved = store.load_profile(conn, users.owner(conn).id)
    assert (saved.first_name, saved.skills, saved.content_library_md) == ("Ada", ["Go"], LIBRARY)


@pytest.mark.parametrize("body", [{"phone": 5551234}, {"first_name": []}, {"skills": "Python"}])
def test_wrong_types_are_a_422(client, body):
    assert client.put("/strelitzia/dashboard/api/profile", json=body).status_code == 422


def test_a_put_never_writes_the_resume_text_back(client, conn):
    """A Save that loaded the profile before an upload committed mustn't put the old resume text back."""
    owner = users.owner(conn).id
    store.save_profile(conn, owner, store.UserProfile(resume_text="old resume"))
    stale = store.load_profile(conn, owner)
    store.save_resume_file(conn, owner, "cv.pdf", store.PDF_MIME, b"%PDF", "new resume")
    with patch.object(store, "load_profile", return_value=stale):
        assert client.put("/strelitzia/dashboard/api/profile", json={"phone": "1"}).status_code == 200
    assert store.load_profile(conn, owner).resume_text == "new resume"


# --- Profile Docs endpoints (profile-docs-2-api Task 2) ---

@pytest.fixture
def drive(monkeypatch, tmp_path):
    from fake_drive import FakeDrive

    from strelitzia.storage.drive import DriveClient
    from strelitzia.web import app as app_mod

    monkeypatch.setenv("DRIVE_ROOT_FOLDER", "Strelitzia")
    fake = FakeDrive()
    client = DriveClient(fake, text_media_factory=lambda text, mime: text.encode("utf-8"))
    monkeypatch.setattr(app_mod, "_drive_client", lambda request: client)
    return fake


def _library_text():
    from pathlib import Path
    return (Path(__file__).resolve().parents[1] / "fixtures" / "content_library_sample.md").read_text(encoding="utf-8")


def _seed(conn, library=None):
    owner = users.owner(conn).id
    store.save_profile(conn, owner, store.UserProfile(content_library_md=library or _library_text(),
                                                      resume_text="Test Person\nData Engineer\n"))
    return owner


def test_profile_docs_setup_overwrite_and_sync(client, conn, drive):
    _seed(conn)
    assert client.get("/strelitzia/dashboard/api/profile").json()["profile_docs"] is None
    r = client.post("/strelitzia/dashboard/api/profile/docs/setup", json={"overwrite": False})
    assert r.status_code == 200, r.text
    docs = r.json()["profile_docs"]
    assert docs["library"]["url"] and docs["library"]["synced_at"] and docs["resume"]["url"]

    again = client.post("/strelitzia/dashboard/api/profile/docs/setup", json={"overwrite": False})
    assert again.status_code == 409
    assert again.json()["existing"] == ["Content Library", "Base Resume"]
    retry = client.post("/strelitzia/dashboard/api/profile/docs/setup", json={"overwrite": True})
    assert retry.status_code == 200
    assert len([f for f in drive.store.values() if f["name"] == "Content Library"]) == 1

    lib_id = next(f["id"] for f in drive.store.values() if f["name"] == "Content Library")
    drive.edit(lib_id, _library_text().replace("Superset, SQL checks.", "Superset, SQL checks, pandas.").encode())
    s = client.post("/strelitzia/dashboard/api/profile/docs/sync").json()
    assert s["ok"] is True and s["changed"] is True and s["problems"] == []
    assert "pandas" in s["content_library_md"]

    drive.edit(lib_id, b"# Nothing here\n")
    s = client.post("/strelitzia/dashboard/api/profile/docs/sync").json()
    assert s["ok"] is False and s["problems"] and "pandas" in s["content_library_md"]


def test_sync_before_setup_is_409(client, conn, drive):
    assert client.post("/strelitzia/dashboard/api/profile/docs/sync").status_code == 409


def test_setup_needs_drive(client, conn):
    r = client.post("/strelitzia/dashboard/api/profile/docs/setup", json={})
    assert r.status_code == 409 and "Connect Google Drive" in r.json()["detail"]


def test_profile_docs_are_owner_only(client, conn, drive, monkeypatch):
    act_as(monkeypatch, second_user(conn))
    assert client.post("/strelitzia/dashboard/api/profile/docs/setup", json={}).status_code == 403
    assert client.post("/strelitzia/dashboard/api/profile/docs/sync").status_code == 403


# --- Sync now drafts the blank fields from the Base Resume ---

PARSED = {"first_name": "Ada", "last_name": "Example", "email": "ada@example.com", "phone": None,
          "linkedin_url": "https://linkedin.com/in/example", "github_url": "not a link", "location": "Springfield",
          "current_job_title": "Widget Engineer", "years_experience": 4, "education_level": "masters",
          "skills": ["Python", "SQL"]}


def _llm(reply=PARSED, error=None):
    import json
    from unittest.mock import MagicMock

    from strelitzia.scoring import resume_parse

    llm = MagicMock()
    if error:
        llm.chat.side_effect = error
    else:
        llm.chat.return_value = json.dumps(reply)
    return patch.object(resume_parse, "get_client", return_value=llm)


def _resume_id(drive):
    return next(f["id"] for f in drive.store.values() if f["name"] == "Base Resume")


def _sync(client):
    r = client.post("/strelitzia/dashboard/api/profile/docs/sync")
    assert r.status_code == 200, r.text
    return r.json()


def test_sync_drafts_only_the_blank_fields_and_saves_nothing(client, conn, drive):
    owner = _seed(conn)
    client.put("/strelitzia/dashboard/api/profile", json={"first_name": "Adeline", "skills": ["Go"]})
    client.post("/strelitzia/dashboard/api/profile/docs/setup", json={"overwrite": False})
    with _llm() as get_client:
        body = _sync(client)
    assert body["ok"] is True and body["parse_error"] is None
    # first_name and skills are set, phone isn't stated, and the bad GitHub link would block Save.
    assert body["draft"] == {"last_name": "Example", "email": "ada@example.com",
                             "linkedin_url": "https://linkedin.com/in/example", "location": "Springfield",
                             "current_job_title": "Widget Engineer", "years_experience": 4.0,
                             "education_level": "masters"}
    assert "Test Person" in get_client.return_value.chat.call_args.args[0][1]["content"]
    saved = store.load_profile(conn, owner)
    assert saved.last_name == "" and saved.first_name == "Adeline"


def test_sync_parses_each_resume_text_once(client, conn, drive):
    _seed(conn)
    client.post("/strelitzia/dashboard/api/profile/docs/setup", json={"overwrite": False})
    with _llm() as get_client:
        assert _sync(client)["draft"]
        assert _sync(client)["draft"] == {}  # same resume: no new call, even with blanks left
        assert get_client.return_value.chat.call_count == 1
        drive.edit(_resume_id(drive), b"Test Person\nSenior Data Engineer\n")
        assert _sync(client)["draft"]
        assert get_client.return_value.chat.call_count == 2


def test_sync_skips_the_parse_when_nothing_is_blank(client, conn, drive):
    _seed(conn)
    client.put("/strelitzia/dashboard/api/profile", json={
        "first_name": "A", "last_name": "B", "phone": "1", "email": "a@example.com",
        "linkedin_url": "https://linkedin.com/in/a", "github_url": "https://github.com/a", "location": "X",
        "current_job_title": "Y", "years_experience": 1, "education_level": "masters", "skills": ["Z"]})
    client.post("/strelitzia/dashboard/api/profile/docs/setup", json={"overwrite": False})
    with _llm() as get_client:
        assert _sync(client)["draft"] == {}
    get_client.assert_not_called()


def test_a_sync_with_problems_does_not_parse(client, conn, drive):
    _seed(conn)
    client.post("/strelitzia/dashboard/api/profile/docs/setup", json={"overwrite": False})
    drive.edit(_resume_id(drive), b"   ")
    with _llm() as get_client:
        body = _sync(client)
    assert body["ok"] is False and body["draft"] == {}
    get_client.assert_not_called()


def test_a_failed_parse_keeps_the_sync_and_retries_next_time(client, conn, drive):
    _seed(conn)
    client.post("/strelitzia/dashboard/api/profile/docs/setup", json={"overwrite": False})
    with _llm(error=RuntimeError("boom")):
        body = _sync(client)
    assert body["ok"] is True and body["draft"] == {}
    assert "couldn't be read to fill in your profile (RuntimeError)" in body["parse_error"]
    with _llm() as get_client:
        assert _sync(client)["draft"]
    assert get_client.return_value.chat.call_count == 1


def test_over_budget_the_sync_still_works(client, conn, drive, monkeypatch):
    from strelitzia.llm import LLMStopRun
    from strelitzia.scoring import resume_parse

    _seed(conn)
    client.post("/strelitzia/dashboard/api/profile/docs/setup", json={"overwrite": False})

    def stop(**kwargs):
        raise LLMStopRun("budget", "Over the monthly budget.")

    monkeypatch.setattr(resume_parse, "check_budget", stop)
    with _llm() as get_client:
        body = _sync(client)
    assert body["ok"] is True and body["draft"] == {} and "Over the monthly budget" in body["parse_error"]
    get_client.assert_not_called()
