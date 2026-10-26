"""Profile page API (profile-2-page Task 2): fields, content library, resume upload with a mocked parse. Fake data only."""

import json
from unittest.mock import MagicMock, patch

import pytest
from resume_files import make_docx, make_pdf
from web_helpers import act_as, second_user

from strelitzia import config, users
from strelitzia import profile as store
from strelitzia.llm import LLMStopRun
from strelitzia.scoring import resume_parse
from strelitzia.scoring.assessment import current_assessment_key
from strelitzia.scoring.resume_parse import DOCX_MIME

LINES = ["Ada Example", "ada@example.com", "Widget Engineer"]
LIBRARY = "# Content library\n\n## CURRENT ROLE: Widget Engineer, Acme\n\n### Project: Widgets\n- Built widgets.\n"
PARSED = {"first_name": "Ada", "last_name": "Example", "email": "ada@example.com", "phone": None,
          "linkedin_url": None, "github_url": None, "location": "Springfield, ST",
          "current_job_title": "Widget Engineer", "years_experience": 4, "education_level": "masters",
          "skills": ["Python", "SQL"]}


@pytest.fixture(autouse=True)
def _no_budget_no_files(monkeypatch, tmp_path):
    """No global budget, and no app-dir files for the app's start to import into the owner's profile."""
    monkeypatch.delenv("LLM_MONTHLY_BUDGET_USD", raising=False)
    for attr in ("PROFILE_PATH", "RESUME_PATH", "RESUME_PDF_PATH", "CONTENT_LIBRARY_PATH", "RESUME_FIXED_PATH"):
        monkeypatch.setattr(config, attr, tmp_path / "no-app-dir" / attr.lower())


def _llm(reply=PARSED):
    client = MagicMock()
    client.chat.return_value = json.dumps(reply)
    return patch.object(resume_parse, "get_client", return_value=client)


def _upload(client, data, name="cv.pdf", mime="application/pdf"):
    return client.post("/strelitzia/dashboard/api/profile/resume", files={"file": (name, data, mime)})


def test_get_starts_empty_with_the_education_options(client):
    body = client.get("/strelitzia/dashboard/api/profile").json()
    assert body["profile"]["first_name"] == "" and body["profile"]["skills"] == []
    assert body["profile"]["years_experience"] is None and body["profile"]["education_level"] is None
    assert body["has_resume"] is False and body["resume_file_name"] is None
    assert body["content_library_md"] == "" and body["content_library_error"] is None
    assert body["options"]["education_level"] == list(store.PROFILE_EDUCATION_LEVELS)


def test_put_saves_the_fields_and_keeps_the_rest(client, conn):
    owner = users.owner(conn).id
    store.save_profile(conn, owner, store.UserProfile(resume_text="old resume", extras={"resume_facts": {"x": 1}}))
    r = client.put("/strelitzia/dashboard/api/profile", json={
        "first_name": " Ada ", "last_name": "Example", "phone": "555-000-0000", "email": "ada@example.com",
        "linkedin_url": "https://www.linkedin.com/in/example", "github_url": "https://github.com/example",
        "location": "Springfield", "current_job_title": "Widget Engineer", "years_experience": 4.5,
        "education_level": "masters", "skills": ["Python", " python ", "SQL", ""], "content_library_md": LIBRARY})
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


def test_a_content_library_without_roles_shows_an_error_but_saves(client, conn):
    r = client.put("/strelitzia/dashboard/api/profile", json={"content_library_md": "just some notes"})
    assert r.status_code == 200
    assert "No roles found" in r.json()["content_library_error"]
    assert store.load_profile(conn, users.owner(conn).id).content_library_md == "just some notes"


def test_profiles_are_per_user(client, conn, monkeypatch):
    client.put("/strelitzia/dashboard/api/profile", json={"first_name": "Owner"})
    act_as(monkeypatch, second_user(conn))
    assert client.get("/strelitzia/dashboard/api/profile").json()["profile"]["first_name"] == ""
    client.put("/strelitzia/dashboard/api/profile", json={"first_name": "Bo"})
    assert store.load_profile(conn, users.owner(conn).id).first_name == "Owner"


def test_upload_stores_the_file_and_returns_a_draft_for_the_empty_fields(client, conn):
    owner = users.owner(conn).id
    client.put("/strelitzia/dashboard/api/profile", json={"first_name": "Adeline", "skills": ["Go"]})
    key_before = current_assessment_key(conn, user_id=owner)
    pdf = make_pdf(LINES)
    with _llm() as get_client:
        r = _upload(client, pdf)
    assert r.status_code == 200, r.text
    body = r.json()
    # first_name and skills are filled in already, so the draft leaves them alone.
    assert body["draft"] == {"last_name": "Example", "email": "ada@example.com", "location": "Springfield, ST",
                             "current_job_title": "Widget Engineer", "years_experience": 4.0,
                             "education_level": "masters"}
    assert body["parse_error"] is None and body["has_resume"] and body["resume_file_name"] == "cv.pdf"
    assert "Ada Example" in get_client.return_value.chat.call_args.args[0][1]["content"]
    saved = store.load_profile(conn, owner, with_file=True)
    assert saved.resume_file == pdf and saved.resume_mime == "application/pdf"
    assert saved.resume_text.splitlines() == LINES
    assert saved.last_name == "" and saved.skills == ["Go"]  # the draft isn't saved
    assert current_assessment_key(conn, user_id=owner) != key_before  # old assessments are stale

    download = client.get("/strelitzia/dashboard/api/profile/resume")
    assert download.status_code == 200 and download.content == pdf
    assert download.headers["content-type"] == "application/pdf"
    assert "cv.pdf" in download.headers["content-disposition"]


def test_upload_a_docx(client, conn):
    with _llm({"skills": ["Python"]}):
        r = _upload(client, make_docx(LINES), name="cv.docx", mime=DOCX_MIME)
    assert r.status_code == 200 and r.json()["draft"] == {"skills": ["Python"]}
    assert store.load_profile(conn, users.owner(conn).id).resume_mime == DOCX_MIME


@pytest.mark.parametrize("name,mime,data", [
    ("cv.txt", "text/plain", b"Ada Example, Widget Engineer"),
    ("cv.pdf", "application/pdf", b"%PDF-1.4" + b"0" * (6 * 1024 * 1024)),
    ("cv.pdf", "application/pdf", b"not a pdf"),
])
def test_bad_uploads_are_a_422_and_store_nothing(client, conn, name, mime, data):
    with _llm() as get_client:
        r = _upload(client, data, name=name, mime=mime)
    assert r.status_code == 422
    get_client.assert_not_called()
    assert not store.has_profile(conn, users.owner(conn).id)


def test_over_the_cap_is_a_402_and_nothing_is_parsed(client, conn, monkeypatch):
    user = users.invite(conn, "capped@example.com", cap=0.0)
    act_as(monkeypatch, user)
    with _llm() as get_client:
        r = _upload(client, make_pdf(LINES))
    assert r.status_code == 402
    get_client.return_value.chat.assert_not_called()
    assert store.load_profile(conn, user.id).resume_text.splitlines() == LINES  # the resume itself is kept


def test_without_an_api_key_the_resume_is_stored_with_a_parse_error(client, conn):
    with patch.object(resume_parse, "get_client") as get_client:
        get_client.return_value.chat.side_effect = LLMStopRun("auth", "ANTHROPIC_API_KEY is not set")
        r = _upload(client, make_pdf(LINES))
    assert r.status_code == 200
    assert r.json()["draft"] == {} and "ANTHROPIC_API_KEY" in r.json()["parse_error"]
    assert r.json()["has_resume"] is True


def test_download_without_a_file_is_a_404(client):
    assert client.get("/strelitzia/dashboard/api/profile/resume").status_code == 404


def test_mutations_need_the_header(app):
    from fastapi.testclient import TestClient

    with TestClient(app) as bare:
        assert bare.put("/strelitzia/dashboard/api/profile", json={}).status_code == 403
        assert _upload(bare, make_pdf(LINES)).status_code == 403


def test_a_put_leaves_the_fields_it_doesnt_send(client, conn):
    client.put("/strelitzia/dashboard/api/profile", json={"first_name": "Ada", "skills": ["Go"], "content_library_md": LIBRARY})
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


def test_drafted_links_the_put_would_reject_are_left_out(client):
    with _llm({**PARSED, "linkedin_url": "linkedin.com/in/ada", "github_url": "https://github.com/ada",
               "email": "ada at example"}):
        draft = _upload(client, make_pdf(LINES)).json()["draft"]
    assert "linkedin_url" not in draft and "email" not in draft
    assert draft["github_url"] == "https://github.com/ada"


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
    assert again.json()["existing"] == ["Strelitzia content library", "Strelitzia base resume"]
    retry = client.post("/strelitzia/dashboard/api/profile/docs/setup", json={"overwrite": True})
    assert retry.status_code == 200
    assert len([f for f in drive.store.values() if f["name"] == "Strelitzia content library"]) == 1

    lib_id = next(f["id"] for f in drive.store.values() if f["name"] == "Strelitzia content library")
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


def test_put_refuses_a_library_edit_once_docs_are_set_up(client, conn, drive):
    _seed(conn)
    client.post("/strelitzia/dashboard/api/profile/docs/setup", json={})
    current = client.get("/strelitzia/dashboard/api/profile").json()["content_library_md"]
    r = client.put("/strelitzia/dashboard/api/profile", json={"content_library_md": current + "\nmore"})
    assert r.status_code == 409 and r.json()["detail"] == "Edit your content library in the Google Doc"
    ok = client.put("/strelitzia/dashboard/api/profile", json={"first_name": "Ada", "content_library_md": current})
    assert ok.status_code == 200 and ok.json()["profile"]["first_name"] == "Ada"


def test_profile_docs_are_owner_only(client, conn, drive, monkeypatch):
    act_as(monkeypatch, second_user(conn))
    assert client.post("/strelitzia/dashboard/api/profile/docs/setup", json={}).status_code == 403
    assert client.post("/strelitzia/dashboard/api/profile/docs/sync").status_code == 403
