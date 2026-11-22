import json
import sqlite3
from collections import deque
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from sessions import HISTORY_TURNS, Session

LEASE_SECONDS = 180
VISIBLE_TURNS = 30


class ConversationMissing(Exception):
    pass


class ConversationBusy(Exception):
    pass


class QuotaExceeded(Exception):
    def __init__(self, retry_after: int):
        self.retry_after = retry_after


class Store:
    def __init__(self, path: Path, retention_days: int):
        self.path = path
        self.retention_seconds = retention_days * 86400
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY, owner TEXT NOT NULL, title TEXT NOT NULL,
                    updated INTEGER NOT NULL, state TEXT NOT NULL,
                    lease TEXT, lease_until INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS conversations_owner ON conversations(owner, updated);
                CREATE INDEX IF NOT EXISTS conversations_expiry ON conversations(updated);
                CREATE TABLE IF NOT EXISTS quotas (
                    scope TEXT NOT NULL, bucket INTEGER NOT NULL, count INTEGER NOT NULL,
                    PRIMARY KEY(scope, bucket)
                );
            """)

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
        finally:
            connection.close()

    def charge(self, owner, settings, now):
        windows = (("visitor:" + owner, 60, settings.visitor_limit),
                   ("site:minute", 60, settings.site_limit), ("site:day", 86400, settings.daily_limit))
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM quotas WHERE bucket < ?", (now - 86400,))
            db.execute("DELETE FROM conversations WHERE updated < ? AND lease_until <= ?",
                       (now - self.retention_seconds, now))
            for scope, window, limit in windows:
                bucket = now - now % window
                row = db.execute("SELECT count FROM quotas WHERE scope=? AND bucket=?", (scope, bucket)).fetchone()
                if row and row["count"] >= limit:
                    raise QuotaExceeded(bucket + window - now)
                db.execute("""INSERT INTO quotas VALUES (?, ?, 1)
                              ON CONFLICT(scope, bucket) DO UPDATE SET count=count+1""", (scope, bucket))
            db.commit()

    def begin(self, owner, conversation_id, now):
        lease = uuid4().hex
        if conversation_id is None:
            return uuid4().hex, lease, Session(), [], None
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM conversations WHERE id=? AND owner=? AND updated>=?",
                             (conversation_id, owner, now - self.retention_seconds)).fetchone()
            if not row:
                raise ConversationMissing
            if row["lease_until"] > now:
                raise ConversationBusy
            db.execute("UPDATE conversations SET lease=?, lease_until=? WHERE id=?",
                       (lease, now + LEASE_SECONDS, conversation_id))
            db.commit()
        state = json.loads(row["state"])
        session = Session(turns=deque(state["turns"], maxlen=HISTORY_TURNS), favorites=state["favorites"])
        return conversation_id, lease, session, state["visible"], row["title"]

    def finish(self, owner, conversation_id, lease, session, visible, title, message, result, now):
        state = json.dumps({"turns": list(session.turns), "favorites": session.favorites,
                            "visible": [*visible, {"message": message, **result}][-VISIBLE_TURNS:]},
                           ensure_ascii=False)
        with self.connect() as db:
            if title is None:
                db.execute("""INSERT INTO conversations(id, owner, title, updated, state)
                              VALUES (?, ?, ?, ?, ?)""", (conversation_id, owner, message[:42], now, state))
            elif not db.execute("""UPDATE conversations SET updated=?, state=?, lease=NULL, lease_until=0
                                  WHERE id=? AND owner=? AND lease=?""",
                                (now, state, conversation_id, owner, lease)).rowcount:
                raise ConversationBusy

    def release(self, owner, conversation_id, lease):
        with self.connect() as db:
            db.execute("UPDATE conversations SET lease=NULL, lease_until=0 WHERE owner=? AND id=? AND lease=?",
                       (owner, conversation_id, lease))

    def list(self, owner, now):
        with self.connect() as db:
            rows = db.execute("""SELECT id,title,updated FROM conversations
                                 WHERE owner=? AND updated>=? ORDER BY updated DESC,rowid DESC LIMIT 30""",
                              (owner, now - self.retention_seconds)).fetchall()
        return [{"id": str(UUID(hex=row["id"])), "title": row["title"],
                 "updated": datetime.fromtimestamp(row["updated"], timezone.utc).isoformat()} for row in rows]

    def read(self, owner, conversation_id, now):
        with self.connect() as db:
            row = db.execute("SELECT state FROM conversations WHERE owner=? AND id=? AND updated>=?",
                             (owner, conversation_id, now - self.retention_seconds)).fetchone()
        if not row:
            raise ConversationMissing
        state = json.loads(row["state"])
        return {"turns": state["visible"], "favorite_ids": state["favorites"]}

    def delete(self, owner, conversation_id, now):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT lease_until FROM conversations WHERE owner=? AND id=?",
                             (owner, conversation_id)).fetchone()
            if not row:
                raise ConversationMissing
            if row["lease_until"] > now:
                raise ConversationBusy
            db.execute("DELETE FROM conversations WHERE owner=? AND id=?", (owner, conversation_id))
            db.commit()
