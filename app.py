
import os
import sqlite3
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "development-key-change-later")
app.config["DATABASE"] = os.environ.get("DB_PATH", "notes.db")


def get_db():
    connection = sqlite3.connect(app.config["DATABASE"])
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    with get_db() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)


def login_required(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            if request.path.startswith("/api/"):
                return jsonify({"error": "Login required"}), 401
            return redirect(url_for("login"))
        return function(*args, **kwargs)
    return wrapper


@app.route("/")
def home():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not username or not password:
            return render_template("register.html", error="All fields are required.")

        if len(password) < 6:
            return render_template("register.html", error="Password must contain at least 6 characters.")

        try:
            with get_db() as db:
                db.execute(
                    "INSERT INTO users (username, password) VALUES (?, ?)",
                    (username, generate_password_hash(password))
                )
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            return render_template("register.html", error="Username already exists.")

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        with get_db() as db:
            user = db.execute(
                "SELECT * FROM users WHERE username = ?",
                (username,)
            ).fetchone()

        if user and check_password_hash(user["password"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            return redirect(url_for("dashboard"))

        return render_template("login.html", error="Invalid username or password.")

    return render_template("login.html")


@app.route("/dashboard")
@login_required
def dashboard():
    with get_db() as db:
        notes = db.execute(
            "SELECT * FROM notes WHERE user_id = ? ORDER BY id DESC",
            (session["user_id"],)
        ).fetchall()

    return render_template("dashboard.html", notes=notes)


@app.route("/add", methods=["POST"])
@login_required
def add_note():
    title = request.form.get("title", "").strip()
    content = request.form.get("content", "").strip()

    if not title or not content:
        return redirect(url_for("dashboard"))

    with get_db() as db:
        db.execute(
            "INSERT INTO notes (user_id, title, content) VALUES (?, ?, ?)",
            (session["user_id"], title, content)
        )

    return redirect(url_for("dashboard"))


@app.route("/edit/<int:note_id>", methods=["GET", "POST"])
@login_required
def edit_note(note_id):
    with get_db() as db:
        note = db.execute(
            "SELECT * FROM notes WHERE id = ? AND user_id = ?",
            (note_id, session["user_id"])
        ).fetchone()

        if note is None:
            return "Note not found", 404

        if request.method == "POST":
            title = request.form.get("title", "").strip()
            content = request.form.get("content", "").strip()

            if not title or not content:
                return render_template("edit_note.html", note=note, error="All fields are required.")

            db.execute(
                "UPDATE notes SET title = ?, content = ? WHERE id = ? AND user_id = ?",
                (title, content, note_id, session["user_id"])
            )
            return redirect(url_for("dashboard"))

    return render_template("edit_note.html", note=note)


@app.route("/delete/<int:note_id>", methods=["POST"])
@login_required
def delete_note(note_id):
    with get_db() as db:
        db.execute(
            "DELETE FROM notes WHERE id = ? AND user_id = ?",
            (note_id, session["user_id"])
        )

    return redirect(url_for("dashboard"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/api/notes", methods=["GET", "POST"])
@login_required
def notes_api():
    if request.method == "GET":
        with get_db() as db:
            notes = db.execute(
                "SELECT id, title, content, created_at FROM notes WHERE user_id = ? ORDER BY id DESC",
                (session["user_id"],)
            ).fetchall()

        return jsonify([dict(note) for note in notes])

    data = request.get_json(silent=True) or {}
    title = str(data.get("title", "")).strip()
    content = str(data.get("content", "")).strip()

    if not title or not content:
        return jsonify({"error": "Title and content are required"}), 400

    with get_db() as db:
        cursor = db.execute(
            "INSERT INTO notes (user_id, title, content) VALUES (?, ?, ?)",
            (session["user_id"], title, content)
        )
        note_id = cursor.lastrowid

    return jsonify({"message": "Note created", "id": note_id}), 201


@app.route("/api/notes/<int:note_id>", methods=["PUT", "DELETE"])
@login_required
def single_note_api(note_id):
    with get_db() as db:
        note = db.execute(
            "SELECT * FROM notes WHERE id = ? AND user_id = ?",
            (note_id, session["user_id"])
        ).fetchone()

        if note is None:
            return jsonify({"error": "Note not found"}), 404

        if request.method == "DELETE":
            db.execute(
                "DELETE FROM notes WHERE id = ? AND user_id = ?",
                (note_id, session["user_id"])
            )
            return jsonify({"message": "Note deleted"})

        data = request.get_json(silent=True) or {}
        title = str(data.get("title", "")).strip()
        content = str(data.get("content", "")).strip()

        if not title or not content:
            return jsonify({"error": "Title and content are required"}), 400

        db.execute(
            "UPDATE notes SET title = ?, content = ? WHERE id = ? AND user_id = ?",
            (title, content, note_id, session["user_id"])
        )

    return jsonify({"message": "Note updated"})


@app.errorhandler(404)
def page_not_found(error):
    if request.path.startswith("/api/"):
        return jsonify({"error": "Resource not found"}), 404
    return "Page not found", 404


@app.errorhandler(500)
def internal_error(error):
    if request.path.startswith("/api/"):
        return jsonify({"error": "Internal server error"}), 500
    return "Something went wrong. Please try again.", 500


init_db()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
