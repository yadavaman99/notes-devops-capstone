
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from app import app, init_db


@pytest.fixture
def client(tmp_path):
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test-secret-key"
    app.config["DATABASE"] = str(tmp_path / "test_notes.db")

    init_db()

    with app.test_client() as client:
        yield client


def register_user(client):
    return client.post(
        "/register",
        data={
            "username": "testuser",
            "password": "test123"
        },
        follow_redirects=True
    )


def login_user(client):
    return client.post(
        "/login",
        data={
            "username": "testuser",
            "password": "test123"
        },
        follow_redirects=True
    )


def test_home_redirects_to_login(client):
    response = client.get("/")
    assert response.status_code == 302


def test_user_registration(client):
    response = register_user(client)
    assert response.status_code == 200
    assert b"Login" in response.data


def test_user_login(client):
    register_user(client)
    response = login_user(client)
    assert response.status_code == 200
    assert b"My Notes" in response.data


def test_add_note(client):
    register_user(client)
    login_user(client)

    response = client.post(
        "/add",
        data={
            "title": "Test Note",
            "content": "This is a test note"
        },
        follow_redirects=True
    )

    assert response.status_code == 200
    assert b"Test Note" in response.data


def test_edit_note(client):
    register_user(client)
    login_user(client)

    client.post(
        "/add",
        data={
            "title": "Old Title",
            "content": "Old Content"
        }
    )

    with client.session_transaction() as session:
        user_id = session["user_id"]

    with app.app_context():
        import sqlite3
        db = sqlite3.connect(app.config["DATABASE"])
        note_id = db.execute(
            "SELECT id FROM notes WHERE user_id = ?",
            (user_id,)
        ).fetchone()[0]
        db.close()

    response = client.post(
        f"/edit/{note_id}",
        data={
            "title": "Updated Title",
            "content": "Updated Content"
        },
        follow_redirects=True
    )

    assert response.status_code == 200
    assert b"Updated Title" in response.data


def test_delete_note(client):
    register_user(client)
    login_user(client)

    client.post(
        "/add",
        data={
            "title": "Delete Me",
            "content": "This note will be deleted"
        }
    )

    with client.session_transaction() as session:
        user_id = session["user_id"]

    with app.app_context():
        import sqlite3
        db = sqlite3.connect(app.config["DATABASE"])
        note_id = db.execute(
            "SELECT id FROM notes WHERE user_id = ?",
            (user_id,)
        ).fetchone()[0]
        db.close()

    response = client.post(
        f"/delete/{note_id}",
        follow_redirects=True
    )

    assert response.status_code == 200
    assert b"Delete Me" not in response.data


def test_notes_api(client):
    register_user(client)
    login_user(client)

    response = client.post(
        "/api/notes",
        json={
            "title": "API Note",
            "content": "Created through API"
        }
    )

    assert response.status_code == 201

    response = client.get("/api/notes")
    assert response.status_code == 200
    assert b"API Note" in response.data
