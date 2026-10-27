"""The Profile Docs (profile-docs-1-sync Task 3): setup and pull against a fake Drive."""

from pathlib import Path

import pytest
from fake_drive import FakeDrive

from strelitzia import config, users
from strelitzia import profile_sync as ps
from strelitzia.database import init_db
from strelitzia.profile import load_profile, save_profile
from strelitzia.storage.drive import DOC_MIME, DriveClient

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SAMPLE = (FIXTURES / "content_library_sample.md").read_text(encoding="utf-8")
DOCS_EXPORT = (FIXTURES / "content_library_docs_export.md").read_text(encoding="utf-8")
RESUME = "Test Person\nData Engineer, Acme\n"


@pytest.fixture(autouse=True)
def _root(monkeypatch, tmp_path):
    monkeypatch.setenv("DRIVE_ROOT_FOLDER", "Strelitzia")
    monkeypatch.setattr(config, "CONTENT_LIBRARY_PATH", tmp_path / "app" / "content_library.md")
    monkeypatch.setattr(config, "RESUME_PATH", tmp_path / "app" / "resume.txt")


@pytest.fixture
def drive():
    return FakeDrive()


def _client(drive):
    return DriveClient(drive, text_media_factory=lambda text, mime: text.encode("utf-8"))


@pytest.fixture
def client(drive):
    return _client(drive)


@pytest.fixture
def conn(tmp_path):
    return init_db(tmp_path / "ps.db")


@pytest.fixture
def owner(conn):
    return users.owner(conn).id


def _seed_db(conn, user_id, library=SAMPLE, resume=RESUME):
    p = load_profile(conn, user_id)
    p.content_library_md, p.resume_text = library, resume
    save_profile(conn, user_id, p)


def _docs(drive):
    return {f["name"]: f for f in drive.store.values() if f["mimeType"] == DOC_MIME and not f["trashed"]}


def test_setup_seeds_from_the_database(drive, client, conn, owner):
    _seed_db(conn, owner)
    docs = ps.setup_profile_docs(client, conn, owner, overwrite=False)
    found = _docs(drive)
    assert set(found) == {"Content Library", "Base Resume"}
    assert found["Content Library"]["content"] == SAMPLE.encode()
    assert found["Base Resume"]["content"] == RESUME.encode()
    for f in found.values():
        assert drive.path_of(f["id"])[:2] == ["Strelitzia", "Profile"]
    assert docs.library["id"] == found["Content Library"]["id"] and docs.library["url"]
    assert docs.library["synced_at"] and docs.library["modified"]
    assert ps.profile_docs(conn, owner) == docs


def test_setup_seeds_from_templates_when_the_database_is_empty(drive, client, conn):
    alice = users.invite(conn, "alice@example.com").id
    ps.setup_profile_docs(client, conn, alice, overwrite=False)
    found = _docs(drive)
    assert found["Content Library"]["content"] == ps.TEMPLATE_LIBRARY.encode()
    assert found["Base Resume"]["content"] == ps.TEMPLATE_RESUME.encode()
    # The template is a valid library, so pulling it straight back works.
    assert ps.pull_profile(client, conn, alice, is_owner=False).ok


def test_setup_refuses_without_overwrite(drive, client, conn, owner):
    ps.setup_profile_docs(client, conn, owner, overwrite=False)
    with pytest.raises(ps.ProfileDocsExist) as e:
        ps.setup_profile_docs(client, conn, owner, overwrite=False)
    assert set(e.value.names) == {"Content Library", "Base Resume"}
    # Another machine (no stored ids) still finds them by name in Profile/.
    for kind in ("library", "resume"):
        conn.execute("DELETE FROM app_state WHERE key = ?", (f"{owner}:profile_doc:{kind}",))
    assert set(ps.existing_docs(_client(drive), conn, owner)) == set(e.value.names)


def test_overwrite_updates_in_place(drive, client, conn, owner):
    first = ps.setup_profile_docs(client, conn, owner, overwrite=False)
    _seed_db(conn, owner)
    second = ps.setup_profile_docs(client, conn, owner, overwrite=True)
    assert second.library["id"] == first.library["id"] and second.resume["id"] == first.resume["id"]
    assert len(_docs(drive)) == 2
    assert drive.store[first.library["id"]]["content"] == SAMPLE.encode()


def test_pull_saves_the_database_and_the_owners_files(drive, client, conn, owner):
    docs = ps.setup_profile_docs(client, conn, owner, overwrite=False)
    drive.edit(docs.library["id"], DOCS_EXPORT.encode())
    drive.edit(docs.resume["id"], RESUME.encode())
    result = ps.pull_profile(client, conn, owner, is_owner=True)
    assert result == ps.SyncResult(ok=True, problems=[], changed=True)
    saved = load_profile(conn, owner)
    assert "## CURRENT ROLE — Data Engineer, Acme" in saved.content_library_md
    assert "\\" not in saved.content_library_md and saved.resume_text == RESUME
    assert config.CONTENT_LIBRARY_PATH.read_text(encoding="utf-8") == saved.content_library_md
    assert config.RESUME_PATH.read_text(encoding="utf-8") == RESUME
    state = ps.profile_docs(conn, owner)
    assert state.library["modified"] == drive.store[docs.library["id"]]["modifiedTime"]
    assert state.library["synced_at"] >= docs.library["synced_at"]
    assert not ps.pull_profile(client, conn, owner, is_owner=True).changed


def test_pull_for_a_non_owner_leaves_local_files_alone(drive, client, conn):
    alice = users.invite(conn, "alice@example.com").id
    _seed_db(conn, alice)
    ps.setup_profile_docs(client, conn, alice, overwrite=False)
    assert ps.pull_profile(client, conn, alice, is_owner=False).ok
    assert load_profile(conn, alice).content_library_md.startswith("# Content Library")
    assert not config.CONTENT_LIBRARY_PATH.exists() and not config.RESUME_PATH.exists()


@pytest.mark.parametrize("library, expected", [
    ("Just some notes, no roles.", "has no projects"),
    (SAMPLE.replace("- **Angles:** ML.\n", ""), "“Churn Model” in the Content Library Doc has no Angles"),
])
def test_a_library_problem_saves_nothing(drive, client, conn, owner, library, expected):
    _seed_db(conn, owner)
    docs = ps.setup_profile_docs(client, conn, owner, overwrite=False)
    drive.edit(docs.library["id"], library.encode())
    drive.edit(docs.resume["id"], b"A new resume\n")
    result = ps.pull_profile(client, conn, owner, is_owner=True)
    assert not result.ok and not result.changed and len(result.problems) == 1 and expected in result.problems[0]
    saved = load_profile(conn, owner)
    assert (saved.content_library_md, saved.resume_text) == (SAMPLE, RESUME)
    assert not config.CONTENT_LIBRARY_PATH.exists() and not config.RESUME_PATH.exists()
    assert ps.profile_docs(conn, owner) == docs


def test_a_trashed_or_missing_doc_is_reported(drive, client, conn, owner):
    _seed_db(conn, owner)
    docs = ps.setup_profile_docs(client, conn, owner, overwrite=False)
    drive.store[docs.resume["id"]]["trashed"] = True
    result = ps.pull_profile(client, conn, owner, is_owner=True)
    assert not result.ok and result.problems == ["The Base Resume Doc is in the trash."]
    del drive.store[docs.library["id"]]
    result = ps.pull_profile(client, conn, owner, is_owner=True)
    assert result.problems == ["The Content Library Doc is missing.",
                               "The Base Resume Doc is in the trash."]
    assert load_profile(conn, owner).content_library_md == SAMPLE


def test_pull_before_setup(client, conn, owner):
    result = ps.pull_profile(client, conn, owner, is_owner=True)
    assert result.problems == ["The Content Library Doc isn't set up.",
                               "The Base Resume Doc isn't set up."]


def test_a_drive_error_is_a_problem_not_a_missing_doc(drive, client, conn, owner, monkeypatch):
    _seed_db(conn, owner)
    ps.setup_profile_docs(client, conn, owner, overwrite=False)

    def boom(*a, **kw):
        raise RuntimeError("503")
    monkeypatch.setattr(client, "doc_meta", boom)
    result = ps.pull_profile(client, conn, owner, is_owner=True)
    assert result.problems == ["The Content Library Doc couldn't be read from Drive.",
                               "The Base Resume Doc couldn't be read from Drive."]
    assert load_profile(conn, owner).content_library_md == SAMPLE


def test_a_failed_local_write_saves_nothing(drive, client, conn, owner, monkeypatch):
    _seed_db(conn, owner)
    docs = ps.setup_profile_docs(client, conn, owner, overwrite=False)
    drive.edit(docs.resume["id"], b"A new resume\n")
    monkeypatch.setattr(config, "RESUME_PATH", config.RESUME_PATH.parent / "bad\0name")  # the write raises
    with pytest.raises(ValueError):
        ps.pull_profile(client, conn, owner, is_owner=True)
    assert load_profile(conn, owner).resume_text == RESUME
    assert ps.profile_docs(conn, owner) == docs
    assert not config.CONTENT_LIBRARY_PATH.exists()
    assert not list(config.CONTENT_LIBRARY_PATH.parent.glob("*.tmp"))
