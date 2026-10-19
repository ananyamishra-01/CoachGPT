"""
Storage and authentication for CoachGPT, using SQLite from Python's standard
library. There is nothing to install and no database server to run: the whole
database is one file.

Security notes:
  * Passwords are never stored. Only a salted PBKDF2-SHA256 hash is saved.
  * Login tokens are random; only their SHA-256 hash is stored, so a copy of
    the database file cannot be used to hijack a session.

Location: by default the file lives in a hidden .coachgpt folder in your home
directory (outside OneDrive-synced folders, which can lock SQLite files). Set
DB_PATH in .env to put it somewhere else.
"""

import os
import json
import hmac
import time
import sqlite3
import secrets
import hashlib
from contextlib import contextmanager
from typing import Optional

DEFAULT_DB = os.path.join(os.path.expanduser("~"), ".coachgpt", "coachgpt.db")
DB_PATH = os.environ.get("DB_PATH") or DEFAULT_DB
TOKEN_TTL_SECONDS = 30 * 24 * 3600
PBKDF2_ROUNDS = 200_000


@contextmanager
def _conn():
    folder = os.path.dirname(DB_PATH)
    if folder:
        os.makedirs(folder, exist_ok=True)
    c = sqlite3.connect(DB_PATH, timeout=10)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    try:
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


def init_db() -> None:
    with _conn() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                pw_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tokens (
                token_hash TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS profiles (
                user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                data TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS progress (
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                entry_date TEXT NOT NULL,
                data TEXT NOT NULL,
                PRIMARY KEY (user_id, entry_date)
            );
            """
        )


# ---------------------------------------------------------------------------
# Passwords and tokens
# ---------------------------------------------------------------------------
def _hash_password(password: str, salt_hex: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), PBKDF2_ROUNDS
    ).hex()


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_user(username: str, password: str) -> Optional[int]:
    """Returns the new user's id, or None if the username is already taken."""
    salt = secrets.token_hex(16)
    try:
        with _conn() as c:
            cur = c.execute(
                "INSERT INTO users (username, pw_hash, salt, created_at) VALUES (?, ?, ?, ?)",
                (username, _hash_password(password, salt), salt, int(time.time())),
            )
            return cur.lastrowid
    except sqlite3.IntegrityError:
        return None


def verify_user(username: str, password: str) -> Optional[dict]:
    with _conn() as c:
        row = c.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if row is None:
        _hash_password(password, "00" * 16)  # keep timing similar for unknown users
        return None
    if hmac.compare_digest(_hash_password(password, row["salt"]), row["pw_hash"]):
        return {"id": row["id"], "username": row["username"]}
    return None


def create_token(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    with _conn() as c:
        c.execute(
            "INSERT INTO tokens (token_hash, user_id, created_at) VALUES (?, ?, ?)",
            (_hash_token(token), user_id, int(time.time())),
        )
    return token


def user_from_token(token: str) -> Optional[dict]:
    cutoff = int(time.time()) - TOKEN_TTL_SECONDS
    with _conn() as c:
        row = c.execute(
            """SELECT u.id, u.username FROM tokens t JOIN users u ON u.id = t.user_id
               WHERE t.token_hash = ? AND t.created_at >= ?""",
            (_hash_token(token), cutoff),
        ).fetchone()
    return {"id": row["id"], "username": row["username"]} if row else None


def delete_token(token: str) -> None:
    with _conn() as c:
        c.execute("DELETE FROM tokens WHERE token_hash = ?", (_hash_token(token),))


# ---------------------------------------------------------------------------
# Profile and progress
# ---------------------------------------------------------------------------
def get_profile(user_id: int) -> Optional[dict]:
    with _conn() as c:
        row = c.execute("SELECT data FROM profiles WHERE user_id = ?", (user_id,)).fetchone()
    return json.loads(row["data"]) if row else None


def save_profile(user_id: int, data: dict) -> None:
    with _conn() as c:
        c.execute(
            "INSERT INTO profiles (user_id, data) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET data = excluded.data",
            (user_id, json.dumps(data)),
        )


def get_progress(user_id: int) -> dict:
    """Returns {entry_date: data} for every logged day."""
    with _conn() as c:
        rows = c.execute(
            "SELECT entry_date, data FROM progress WHERE user_id = ?", (user_id,)
        ).fetchall()
    return {r["entry_date"]: json.loads(r["data"]) for r in rows}


def upsert_progress(user_id: int, entry_date: str, data: dict) -> None:
    with _conn() as c:
        c.execute(
            "INSERT INTO progress (user_id, entry_date, data) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id, entry_date) DO UPDATE SET data = excluded.data",
            (user_id, entry_date, json.dumps(data)),
        )
