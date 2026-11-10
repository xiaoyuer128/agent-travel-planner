import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


class Conflict(Exception):
    pass


class SessionStore:
    """Atomic per-turn commits; optimistic locking also protects multiple workers."""
    def __init__(self, path, owner='legacy'):
        self.owner = owner
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS chat_sessions (
                id TEXT PRIMARY KEY, title TEXT NOT NULL, revision INTEGER NOT NULL,
                updated TEXT NOT NULL, payload TEXT NOT NULL)""")
            if 'owner' not in [r[1] for r in conn.execute('PRAGMA table_info(chat_sessions)')]:
                conn.execute("ALTER TABLE chat_sessions ADD COLUMN owner TEXT NOT NULL DEFAULT 'legacy'")
            conn.execute('CREATE INDEX IF NOT EXISTS sessions_owner ON chat_sessions(owner,updated)')

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path, timeout=10)
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def create(self):
        session = {"id": uuid4().hex, "title": "新的旅行", "revision": 0,
                   "preferences": {}, "plan": None, "versions": [], "messages": [], "trace": []}
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as conn:
            conn.execute("INSERT INTO chat_sessions(id,title,revision,updated,payload,owner) VALUES (?, ?, ?, ?, ?, ?)",
                         (session["id"], session["title"], 0, now, json.dumps(session), self.owner))
        return session

    def get(self, session_id):
        with self.connect() as conn:
            row = conn.execute("SELECT payload FROM chat_sessions WHERE id=? AND owner=?", (session_id,self.owner)).fetchone()
        if not row:
            raise KeyError(session_id)
        return json.loads(row[0])

    def list(self):
        with self.connect() as conn:
            rows = conn.execute("SELECT id,title,revision,updated FROM chat_sessions WHERE owner=? ORDER BY updated DESC",(self.owner,)).fetchall()
        return [dict(zip(("id", "title", "revision", "updated"), row)) for row in rows]

    def save(self, session, expected):
        session["revision"] = expected + 1
        with self.connect() as conn:
            result = conn.execute("""UPDATE chat_sessions SET title=?,revision=?,updated=?,payload=?
                WHERE id=? AND revision=? AND owner=?""", (session["title"], session["revision"],
                datetime.now(timezone.utc).isoformat(), json.dumps(session, ensure_ascii=False),
                session["id"], expected,self.owner))
            if result.rowcount != 1:
                raise Conflict("会话已更新，请刷新后重试")
        return session
