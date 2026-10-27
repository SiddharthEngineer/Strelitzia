"""Claude workbench routes: the packet and draft Docs, Check & format, and the setup page."""

import json
from pathlib import Path

import pytest
from fake_drive import FakeDrive, fake_media
from web_helpers import add_job

from strelitzia import config
from strelitzia.database import job_key
from strelitzia.scoring import pdf as pdf_mod
from strelitzia.scoring import workbench as wb
from strelitzia.storage.drive import DOC_MIME, DriveClient
from strelitzia.web import app as app_mod
from workbench_helpers import POSTING, fake_render_pdf, good_result, inputs, job, reply

REAL_DRIVE_CLIENT = app_mod._drive_client
URL = job()["url"]
KEY = job_key(URL)
_REAL_FOR_USER = wb.Inputs.__dict__["for_user"]


@pytest.fixture(autouse=True)
def _workbench(monkeypatch, tmp_path):
    monkeypatch.setattr(pdf_mod, "render_pdf", fake_render_pdf)
    monkeypatch.setattr(wb.Inputs, "for_user", classmethod(lambda cls, conn, user_id: inputs()))
    monkeypatch.setattr(config, "TAILORED_DIR", tmp_path / "tailored")
    monkeypatch.setattr(config, "COVER_LETTER_DIR", tmp_path / "cover")
    monkeypatch.setattr(app_mod, "_drive_client", lambda request: None)
    monkeypatch.setenv("DRIVE_ROOT_FOLDER", "Strelitzia")


@pytest.fixture
def the_job(conn):
    j = job()
    add_job(conn, URL, title=j["title"], company=j["company"], site=j["site"], job_key=KEY,
            full_description=j["full_description"], details_json=json.dumps(POSTING))
    return KEY


@pytest.fixture
def drive(monkeypatch):
    fake = FakeDrive()
    client = DriveClient(fake, media_factory=fake_media, html_media_factory=lambda html: html.encode("utf-8"),
                         text_media_factory=lambda text, mime: text.encode("utf-8"))
    monkeypatch.setattr(app_mod, "_drive_client", lambda request: client)
    return fake


def _fill_drafts(conn, drive, data):
    """Write `data` into the job's draft Docs, as Claude would."""
    from strelitzia.scoring import draft_docs as dd
    from workbench_helpers import library

    row = dict(conn.execute("SELECT * FROM jobs").fetchone())
    drive.edit(row["resume_draft_doc_id"], dd.resume_draft_text(data, library(), wb.RULES_VERSION).encode())
    drive.edit(row["cover_draft_doc_id"], dd.cover_draft_text(data["cover_letter"], wb.RULES_VERSION).encode())


def _check(client, conn, drive, key, data):
    """Open the job in Claude, have "Claude" fill the drafts with `data`, then Check & format."""
    assert client.post(f"/strelitzia/dashboard/api/jobs/{key}/packet").status_code == 200
    _fill_drafts(conn, drive, data)
    return client.post(f"/strelitzia/dashboard/api/jobs/{key}/drafts/check")


def test_packet_without_drive_is_409(client, the_job):
    r = client.post(f"/strelitzia/dashboard/api/jobs/{the_job}/packet")
    assert r.status_code == 409 and r.json()["detail"] == "Connect Google Drive on the Claude setup page"


def test_packet_with_drive_writes_docs_and_a_short_prompt(client, conn, the_job, drive):
    body = client.post(f"/strelitzia/dashboard/api/jobs/{the_job}/packet").json()
    assert body["doc_url"] and "inline" not in body
    assert len(body["prompt"]) <= wb.PROMPT_MAX and "Claude packet" in body["prompt"]
    names = sorted(f["name"] for f in drive.store.values() if f["mimeType"] == DOC_MIME)
    assert names == sorted([f"Initech – {job()['title']} – Claude packet",  # the rules are a download now
                            f"Initech - {job()['title']} - Resume draft",
                            f"Initech - {job()['title']} - Cover letter draft"])
    detail = client.get(f"/strelitzia/dashboard/api/jobs/{the_job}").json()
    assert detail["packet_doc_url"] == body["doc_url"] == detail["links"]["packet"]


def test_packet_when_drive_fails_is_409(client, the_job, monkeypatch):
    def broken(request):
        raise RuntimeError("token expired")

    monkeypatch.setattr(app_mod, "_drive_client", broken)
    r = client.post(f"/strelitzia/dashboard/api/jobs/{the_job}/packet")
    assert r.status_code == 409 and "token expired" in r.json()["detail"]


def test_the_paste_endpoint_is_gone(client, the_job):
    r = client.post(f"/strelitzia/dashboard/api/jobs/{the_job}/result", json={"text": reply(good_result())})
    assert r.status_code in (404, 405)


def test_bad_drafts_are_422_with_a_fix_prompt(client, conn, the_job, drive):
    data = good_result()
    data["resume"]["skills"].append({"category": "Cloud", "items": "Kubernetes"})
    r = _check(client, conn, drive, the_job, data)
    assert r.status_code == 422
    body = r.json()
    assert any("Kubernetes" in e for e in body["errors"])
    assert body["fix_prompt"].startswith("These problems were found:") and "Kubernetes" in body["fix_prompt"]
    assert conn.execute("SELECT draft_version FROM jobs").fetchone()[0] is None


def test_good_drafts_save_and_bump_the_version(client, conn, the_job, drive):
    r = _check(client, conn, drive, the_job, good_result())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["outcome"]["draft_version"] == 1
    d = body["job"]
    assert d["draft_version"] == 1 and d["draft_rules_version"] == wb.RULES_VERSION
    assert d["coverage"]["pct_required"] == 80.0 and d["unmet"] == ["Kubernetes", "Terraform"]
    assert [h["version"] for h in d["draft_history"]] == [1]
    assert d["links"]["resume"] and d["links"]["cover_letter"]
    assert "resume_pdf" not in d["links"]  # moved to Drive
    assert client.get(d["links"]["resume_docx"]).content  # the DOCX stays local

    _fill_drafts(conn, drive, good_result(headline="Data engineer for Airflow pipelines"))
    d2 = client.post(f"/strelitzia/dashboard/api/jobs/{the_job}/drafts/check").json()["job"]
    assert d2["draft_version"] == 2
    assert [h["version"] for h in d2["draft_history"]] == [1, 2]


def test_submitting_records_the_draft_and_rules_version(client, conn, the_job, drive):
    _check(client, conn, drive, the_job, good_result())
    d = client.post(f"/strelitzia/dashboard/api/jobs/{the_job}/status", json={"status": "submitted"}).json()
    assert d["submitted_draft_version"] == 1 and d["submitted_rules_version"] == wb.RULES_VERSION


def test_missing_file_is_404(client, the_job):
    assert client.get(f"/strelitzia/dashboard/api/jobs/{the_job}/files/resume_pdf").status_code == 404
    assert client.get(f"/strelitzia/dashboard/api/jobs/{the_job}/files/other").status_code == 422


def test_setup_without_drive(client):
    s = client.get("/strelitzia/dashboard/api/claude/setup").json()
    assert s["drive"] is False and s["rules_version"] == wb.RULES_VERSION
    assert "docs" not in s and s["profile_docs"] is None
    assert "rules_markdown" not in s and "rules_url" not in s  # the rules travel in each packet
    assert s["project_instructions"] == wb.project_instructions() and s["project_name"] == "Strelitzia Resumes"
    assert s["instructions_version"] == wb.INSTRUCTIONS_VERSION
    assert client.post("/strelitzia/dashboard/api/claude/docs").status_code in (404, 405)  # removed


def test_a_saved_draft_marks_the_job_in_progress(client, conn, the_job, drive):
    _check(client, conn, drive, the_job, good_result())
    d = client.get(f"/strelitzia/dashboard/api/jobs/{the_job}").json()
    assert d["status"] == "in_progress" and d["status_color"] == "yellow"
    assert d["events"][0]["source"] == "workbench"


def test_a_saved_draft_keeps_a_status_the_user_set(client, conn, the_job, drive):
    client.post(f"/strelitzia/dashboard/api/jobs/{the_job}/status", json={"status": "submitted"})
    _check(client, conn, drive, the_job, good_result())
    d = client.get(f"/strelitzia/dashboard/api/jobs/{the_job}").json()
    assert d["status"] == "submitted" and len(d["events"]) == 1


def test_a_rejected_check_leaves_the_status_alone(client, conn, the_job, drive):
    client.post(f"/strelitzia/dashboard/api/jobs/{the_job}/packet")
    assert client.post(f"/strelitzia/dashboard/api/jobs/{the_job}/drafts/check").status_code == 422  # the skeleton
    assert client.get(f"/strelitzia/dashboard/api/jobs/{the_job}").json()["status"] == "active"


# --- Per-user Drive (user-auth-6-drive) ---

@pytest.fixture
def per_user_drive(monkeypatch):
    """The real _drive_client, with DriveClient.for_user on a fake Drive; returns the user ids it was asked for."""
    from cryptography.fernet import Fernet

    from strelitzia.storage import drive as drive_mod
    monkeypatch.setattr(app_mod, "_drive_client", REAL_DRIVE_CLIENT)
    monkeypatch.setattr(drive_mod, "drive_libraries_installed", lambda: True)
    monkeypatch.setenv("STRELITZIA_TOKEN_KEY", Fernet.generate_key().decode())
    fake, asked = FakeDrive(), []

    def for_user(cls, conn, user_id):
        asked.append(user_id)
        return cls(fake, media_factory=fake_media, html_media_factory=lambda html: html.encode("utf-8"),
                   text_media_factory=lambda text, mime: text.encode("utf-8"))

    monkeypatch.setattr(DriveClient, "for_user", classmethod(for_user))
    return asked


def _connect(conn, user_id):
    from datetime import UTC, datetime, timedelta

    from google.oauth2.credentials import Credentials

    from strelitzia.storage.drive import save_user_token
    save_user_token(conn, user_id, Credentials(token="t", refresh_token="r", token_uri="https://oauth2.googleapis.com/token",
                                               client_id="c", client_secret="s",
                                               expiry=datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=1)))


def test_packet_uses_the_users_own_drive(client, conn, the_job, per_user_drive):
    from strelitzia import users
    owner = users.owner(conn).id
    assert client.post(f"/strelitzia/dashboard/api/jobs/{the_job}/packet").status_code == 409  # not connected
    assert per_user_drive == []
    _connect(conn, owner)
    body = client.post(f"/strelitzia/dashboard/api/jobs/{the_job}/packet").json()
    assert body["doc_url"] and body["resume_draft_url"]
    assert per_user_drive == [owner]


def test_setup_reports_the_users_drive_and_the_connect_url(client, conn, per_user_drive, monkeypatch):
    from strelitzia import users
    s = client.get("/strelitzia/dashboard/api/claude/setup").json()
    assert s["drive"] is False and s["drive_source"] is None and s["connect_url"] is None  # login off: no web client
    assert "Claude setup page" in s["drive_detail"]
    monkeypatch.setattr(app_mod.auth, "drive_connect_available", lambda: True)
    assert client.get("/strelitzia/dashboard/api/claude/setup").json()["connect_url"] == "/strelitzia/dashboard/api/drive/connect"
    _connect(conn, users.owner(conn).id)
    s = client.get("/strelitzia/dashboard/api/claude/setup").json()
    assert s["drive"] is True and s["drive_source"] == "user"


def test_no_content_library_says_where_to_add_it(client, the_job, drive, monkeypatch):
    monkeypatch.setattr(wb.Inputs, "for_user", _REAL_FOR_USER)  # the owner's profile has no content library here
    r = client.post(f"/strelitzia/dashboard/api/jobs/{the_job}/packet")
    assert r.status_code == 409 and r.json()["detail"] == (
        "No content library yet. Add your content library on the Profile page.")


def test_profile_docs_setup_without_drive_says_where_to_connect(client):
    r = client.post("/strelitzia/dashboard/api/profile/docs/setup", json={})
    assert r.status_code == 409 and r.json()["detail"] == "Connect Google Drive on the Claude setup page"


def test_owner_without_a_token_key_keeps_the_cli_token(client, conn, tmp_path, monkeypatch):
    """A local install with only `strelitzia drive auth` (no TOKEN_KEY) still gets Drive in the dashboard."""
    from strelitzia.storage import drive as drive_mod
    monkeypatch.setattr(app_mod, "_drive_client", REAL_DRIVE_CLIENT)
    monkeypatch.setattr(drive_mod, "drive_libraries_installed", lambda: True)
    token_file = tmp_path / "google_token.json"
    token_file.write_text("{}")
    monkeypatch.setattr(config, "GOOGLE_TOKEN_PATH", token_file)
    fake = FakeDrive()
    monkeypatch.setattr(DriveClient, "from_credentials",
                        classmethod(lambda cls: cls(fake, html_media_factory=lambda html: html.encode("utf-8"),
                                                    text_media_factory=lambda text, mime: text.encode("utf-8"))))
    s = client.get("/strelitzia/dashboard/api/claude/setup").json()
    assert s["drive"] is True and s["drive_source"] == "legacy"
    assert client.post("/strelitzia/dashboard/api/profile/docs/setup", json={}).status_code == 200


def test_owner_keeps_the_cli_token_while_the_dashboard_cant_connect(client, conn, tmp_path, monkeypatch):
    """Login off (no web OAuth client) with TOKEN_KEY set and nothing stored: the CLI's token still works."""
    from cryptography.fernet import Fernet

    from strelitzia.storage import drive as drive_mod
    monkeypatch.setattr(drive_mod, "drive_libraries_installed", lambda: True)
    monkeypatch.setenv("STRELITZIA_TOKEN_KEY", Fernet.generate_key().decode())
    token_file = tmp_path / "google_token.json"
    token_file.write_text("{}")
    monkeypatch.setattr(config, "GOOGLE_TOKEN_PATH", token_file)
    s = client.get("/strelitzia/dashboard/api/claude/setup").json()
    assert s["drive"] is True and s["drive_source"] == "legacy" and s["connect_url"] is None


# --- Profile Docs: pulled before every use (profile-docs-2-api Task 1) ---

SAMPLE_LIBRARY = (Path(__file__).resolve().parents[1] / "fixtures" / "content_library_sample.md").read_text(encoding="utf-8")


@pytest.fixture
def profile_docs(conn, drive, monkeypatch, tmp_path):
    """The owner's Profile Docs set up on the fake Drive (the real Inputs.for_user reads the pulled copy)."""
    from strelitzia import profile_sync, users
    from strelitzia.profile import load_profile, save_profile

    monkeypatch.setattr(wb.Inputs, "for_user", _REAL_FOR_USER)
    monkeypatch.setattr(config, "CONTENT_LIBRARY_PATH", tmp_path / "app" / "content_library.md")
    monkeypatch.setattr(config, "RESUME_PATH", tmp_path / "app" / "resume.txt")
    owner = users.owner(conn).id
    p = load_profile(conn, owner)
    p.content_library_md, p.resume_text = SAMPLE_LIBRARY, "Test Person\nData Engineer, Acme\n"
    save_profile(conn, owner, p)
    client = app_mod._drive_client(None)
    docs = profile_sync.setup_profile_docs(client, conn, owner, overwrite=False)
    return {"owner": owner, "library": docs.library["id"], "resume": docs.resume["id"]}


def test_a_doc_edit_shows_up_in_the_next_packet(client, conn, the_job, drive, profile_docs):
    edited = SAMPLE_LIBRARY.replace("Airflow, Spark, dbt;", "Airflow, Spark, dbt, Kubernetes;")
    drive.edit(profile_docs["library"], edited.encode("utf-8"))
    r = client.post(f"/strelitzia/dashboard/api/jobs/{the_job}/packet")
    assert r.status_code == 200, r.text
    packet = next(f for f in drive.store.values() if f["name"].endswith("Claude packet"))
    assert b"Kubernetes: evidenced" in packet["content"]
    assert "Kubernetes" in client.get("/strelitzia/dashboard/api/profile").json()["content_library_md"]


def test_a_doc_problem_stops_the_packet(client, conn, the_job, drive, profile_docs):
    broken = SAMPLE_LIBRARY.replace("## CURRENT ROLE", "CURRENT ROLE").replace("## PRIOR ROLE", "PRIOR ROLE")
    drive.edit(profile_docs["library"], broken.encode("utf-8"))
    r = client.post(f"/strelitzia/dashboard/api/jobs/{the_job}/packet")
    assert r.status_code == 409
    body = r.json()
    assert body["detail"] == "Your Profile Docs have problems" and body["problems"]
    assert not any(f["name"].endswith("Claude packet") for f in drive.store.values())
    assert client.get("/strelitzia/dashboard/api/profile").json()["content_library_md"] == SAMPLE_LIBRARY


def test_profile_docs_need_drive(client, conn, the_job, drive, profile_docs, monkeypatch):
    monkeypatch.setattr(app_mod, "_drive_client", lambda request: None)
    r = client.post(f"/strelitzia/dashboard/api/jobs/{the_job}/packet")
    assert r.status_code == 409 and r.json()["detail"] == "Connect Google Drive on the Claude setup page"


def test_without_profile_docs_the_database_copy_is_used(client, conn, the_job, drive, monkeypatch):
    from strelitzia import users
    from strelitzia.profile import load_profile, save_profile

    monkeypatch.setattr(wb.Inputs, "for_user", _REAL_FOR_USER)
    owner = users.owner(conn).id
    p = load_profile(conn, owner)
    p.content_library_md = SAMPLE_LIBRARY.replace("Airflow, Spark, dbt;", "Airflow, Spark, dbt, Kubernetes;")
    save_profile(conn, owner, p)
    assert client.post(f"/strelitzia/dashboard/api/jobs/{the_job}/packet").status_code == 200
    packet = next(f for f in drive.store.values() if f["name"].endswith("Claude packet"))
    assert b"Kubernetes: evidenced" in packet["content"]
    assert drive.calls["export"] == 0


def test_rules_download_is_gone(client):
    assert client.get("/strelitzia/dashboard/api/claude/rules.md").status_code == 404


def test_setup_shows_the_profile_docs(client, conn, the_job, drive, profile_docs):
    s = client.get("/strelitzia/dashboard/api/claude/setup").json()
    assert s["profile_docs"]["library"]["url"] and s["profile_docs"]["resume"]["synced_at"]


# --- Draft Docs and Check & format (docs-drafts-2-api Task 2) ---

def test_packet_creates_the_draft_docs(client, conn, the_job, drive):
    body = client.post(f"/strelitzia/dashboard/api/jobs/{the_job}/packet").json()
    assert body["resume_draft_url"] and body["cover_draft_url"]
    assert "Resume draft" in body["prompt"] and "Cover letter draft" in body["prompt"]
    d = client.get(f"/strelitzia/dashboard/api/jobs/{the_job}").json()
    assert d["resume_draft_url"] == body["resume_draft_url"] and d["cover_draft_url"] == body["cover_draft_url"]
    assert d["links"]["resume_draft"] == body["resume_draft_url"]


def test_check_valid_drafts_saves_and_uploads_the_pdfs(client, conn, the_job, drive):
    client.post(f"/strelitzia/dashboard/api/jobs/{the_job}/packet")
    _fill_drafts(conn, drive, good_result())
    r = client.post(f"/strelitzia/dashboard/api/jobs/{the_job}/drafts/check")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["outcome"]["draft_version"] == 1
    assert not any("rules version" in w for w in body["outcome"]["warnings"])
    d = body["job"]
    assert d["draft_version"] == 1 and d["links"]["resume"] and d["links"]["cover_letter"]
    pdfs = [f["name"] for f in drive.store.values() if f["name"].endswith(".pdf")]
    assert len(pdfs) == 2


def test_check_a_bullet_without_tags_is_422_naming_the_line(client, conn, the_job, drive):
    client.post(f"/strelitzia/dashboard/api/jobs/{the_job}/packet")
    _fill_drafts(conn, drive, good_result())
    row = dict(conn.execute("SELECT * FROM jobs").fetchone())
    doc = drive.store[row["resume_draft_doc_id"]]
    drive.edit(doc["id"], doc["content"].replace(b" [orders-pipeline]", b"", 1))
    r = client.post(f"/strelitzia/dashboard/api/jobs/{the_job}/drafts/check")
    assert r.status_code == 422
    body = r.json()
    assert body["errors"][0].startswith("Resume draft, line 6:") and "no [slug] tags" in body["errors"][0]
    assert body["fix_prompt"].endswith("Fix them in the two draft Docs and change nothing else.")
    assert conn.execute("SELECT draft_version FROM jobs").fetchone()[0] is None


def test_check_before_the_drafts_exist_is_409(client, the_job, drive):
    r = client.post(f"/strelitzia/dashboard/api/jobs/{the_job}/drafts/check")
    assert r.status_code == 409 and r.json()["detail"].startswith("Open the job in Claude first")


def test_check_needs_drive(client, the_job):
    r = client.post(f"/strelitzia/dashboard/api/jobs/{the_job}/drafts/check")
    assert r.status_code == 409 and r.json()["detail"] == "Connect Google Drive on the Claude setup page"
