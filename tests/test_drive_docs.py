"""Google Docs for the per-job packet (with the rules) and drafts, against a fake Drive."""

import pytest
from fake_drive import FakeDrive, fake_media

from strelitzia.database import init_db
from strelitzia.scoring import workbench as wb
from strelitzia.storage.drive import DOC_MIME, DriveClient
from workbench_helpers import add_job_row, inputs


def _html_media(html: str) -> bytes:
    return html.encode("utf-8")


@pytest.fixture
def drive():
    return FakeDrive()


@pytest.fixture
def client(drive):
    return DriveClient(drive, media_factory=fake_media, html_media_factory=_html_media)


@pytest.fixture
def conn(tmp_path):
    return init_db(tmp_path / "wb.db")


@pytest.fixture(autouse=True)
def _root(monkeypatch):
    monkeypatch.setenv("DRIVE_ROOT_FOLDER", "Strelitzia")


def _docs(drive):
    return [f for f in drive.store.values() if f["mimeType"] == DOC_MIME]


def test_upsert_doc_creates_a_google_doc_then_updates_it(drive, client):
    folder = client.ensure_folder_path(("Strelitzia", "_Claude"))
    first = client.upsert_doc(folder, "Strelitzia rules", "<p>one</p>")
    assert first.created and first.url
    (doc,) = _docs(drive)
    assert doc["name"] == "Strelitzia rules" and doc["parents"] == [folder] and doc["content"] == b"<p>one</p>"

    second = client.upsert_doc(folder, "Strelitzia rules", "<p>two</p>")
    assert not second.created and second.id == first.id
    assert drive.calls["update"] == 1 and len(_docs(drive)) == 1
    assert drive.store[first.id]["content"] == b"<p>two</p>"


def test_upsert_doc_prefers_the_known_id_and_skips_trashed(drive, client):
    folder = client.ensure_folder_path(("Strelitzia", "Acme"))
    first = client.upsert_doc(folder, "Old name", "<p>a</p>")
    again = client.upsert_doc(folder, "New name", "<p>b</p>", known_id=first.id)
    assert again.id == first.id and not again.created

    drive.store[first.id]["trashed"] = True
    fresh = client.upsert_doc(folder, "New name", "<p>c</p>", known_id=first.id)
    assert fresh.created and fresh.id != first.id


def test_publish_packet_writes_the_job_folder_and_records_the_doc(drive, client, conn):
    job = add_job_row(conn)
    doc_id, url = wb.publish_packet(client, conn, job, inputs())
    doc = drive.store[doc_id]
    assert doc["mimeType"] == DOC_MIME and url
    path = drive.path_of(doc_id)
    assert path[0] == "Strelitzia" and path[-1] == f"{job['company']} – {job['title']} – Claude packet"
    assert b"Required qualifications" in doc["content"]
    # The rules travel in the packet: nothing goes to the old Strelitzia/_Claude folder.
    assert b"<h2>Rules: Honesty</h2>" in doc["content"] and b"## Notes for me" in doc["content"]
    assert wb.RULES_VERSION.encode() in doc["content"]
    assert not any("_Claude" in drive.path_of(d["id"]) for d in _docs(drive))
    row = dict(conn.execute("SELECT packet_doc_id, packet_doc_url FROM jobs").fetchone())
    assert row == {"packet_doc_id": doc_id, "packet_doc_url": url}

    job = dict(conn.execute("SELECT * FROM jobs").fetchone())
    again_id, _ = wb.publish_packet(client, conn, job, inputs())
    assert again_id == doc_id and len(_docs(drive)) == 1
