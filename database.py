"""
Lightweight async SQLite persistence layer used by every cog.

One Database instance is created in bot.py and attached to the bot as
`bot.db`. All methods are safe to call concurrently — aiosqlite serializes
access on a single connection, and every write that must not double-process
an application uses a conditional UPDATE (`WHERE status = 'pending'`) so two
staff members clicking Accept/Deny at the same instant can't both succeed.
"""

import json
import os
from datetime import datetime, timezone
from typing import Any, Optional

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS guild_config (
    guild_id INTEGER PRIMARY KEY,
    verification_channel_id INTEGER,
    review_channel_id INTEGER,
    log_channel_id INTEGER,
    unverified_role_id INTEGER,
    verified_role_id INTEGER,
    member_role_id INTEGER,
    staff_role_id INTEGER,
    questions TEXT NOT NULL DEFAULT '["Waa maxay magaca game-ka aad ku dheesho?"]',
    cooldown_minutes INTEGER NOT NULL DEFAULT 60,
    rejoin_policy TEXT NOT NULL DEFAULT 'permanent'
);

CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    answers TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    reviewer_id INTEGER,
    submitted_at TEXT NOT NULL,
    reviewed_at TEXT,
    deny_reason TEXT,
    message_id INTEGER
);
CREATE INDEX IF NOT EXISTS idx_apps_guild_user ON applications(guild_id, user_id);
CREATE INDEX IF NOT EXISTS idx_apps_status ON applications(guild_id, status);

CREATE TABLE IF NOT EXISTS verified_members (
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    verified_at TEXT NOT NULL,
    staff_prefix INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, user_id)
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, path: str):
        self.path = path
        self._conn: Optional[aiosqlite.Connection] = None

    async def connect(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(SCHEMA)
        await self._conn.commit()

    async def close(self):
        if self._conn:
            await self._conn.close()

    # ------------------------------------------------------------------
    # Guild configuration
    # ------------------------------------------------------------------
    async def get_guild_config(self, guild_id: int) -> Optional[dict]:
        cur = await self._conn.execute(
            "SELECT * FROM guild_config WHERE guild_id = ?", (guild_id,)
        )
        row = await cur.fetchone()
        if not row:
            return None
        data = dict(row)
        data["questions"] = json.loads(data["questions"])
        return data

    async def upsert_guild_config(self, guild_id: int, **fields: Any) -> dict:
        existing = await self.get_guild_config(guild_id)
        if "questions" in fields and isinstance(fields["questions"], list):
            fields["questions"] = json.dumps(fields["questions"])

        if existing is None:
            columns = ["guild_id"] + list(fields.keys())
            placeholders = ", ".join("?" for _ in columns)
            values = [guild_id] + list(fields.values())
            await self._conn.execute(
                f"INSERT INTO guild_config ({', '.join(columns)}) VALUES ({placeholders})",
                values,
            )
        else:
            if fields:
                set_clause = ", ".join(f"{k} = ?" for k in fields.keys())
                values = list(fields.values()) + [guild_id]
                await self._conn.execute(
                    f"UPDATE guild_config SET {set_clause} WHERE guild_id = ?", values
                )
        await self._conn.commit()
        return await self.get_guild_config(guild_id)

    # ------------------------------------------------------------------
    # Applications
    # ------------------------------------------------------------------
    async def create_application(self, guild_id: int, user_id: int, answers: dict) -> int:
        cur = await self._conn.execute(
            "INSERT INTO applications (guild_id, user_id, answers, status, submitted_at) "
            "VALUES (?, ?, ?, 'pending', ?)",
            (guild_id, user_id, json.dumps(answers), _now()),
        )
        await self._conn.commit()
        return cur.lastrowid

    async def set_application_message(self, application_id: int, message_id: int):
        await self._conn.execute(
            "UPDATE applications SET message_id = ? WHERE id = ?",
            (message_id, application_id),
        )
        await self._conn.commit()

    async def get_application(self, application_id: int) -> Optional[dict]:
        cur = await self._conn.execute(
            "SELECT * FROM applications WHERE id = ?", (application_id,)
        )
        row = await cur.fetchone()
        if not row:
            return None
        data = dict(row)
        data["answers"] = json.loads(data["answers"])
        return data

    async def get_application_by_message(self, message_id: int) -> Optional[dict]:
        cur = await self._conn.execute(
            "SELECT * FROM applications WHERE message_id = ?", (message_id,)
        )
        row = await cur.fetchone()
        if not row:
            return None
        data = dict(row)
        data["answers"] = json.loads(data["answers"])
        return data

    async def get_latest_application(self, guild_id: int, user_id: int) -> Optional[dict]:
        cur = await self._conn.execute(
            "SELECT * FROM applications WHERE guild_id = ? AND user_id = ? "
            "ORDER BY id DESC LIMIT 1",
            (guild_id, user_id),
        )
        row = await cur.fetchone()
        if not row:
            return None
        data = dict(row)
        data["answers"] = json.loads(data["answers"])
        return data

    async def has_pending_application(self, guild_id: int, user_id: int) -> bool:
        cur = await self._conn.execute(
            "SELECT 1 FROM applications WHERE guild_id = ? AND user_id = ? AND status = 'pending' LIMIT 1",
            (guild_id, user_id),
        )
        return (await cur.fetchone()) is not None

    async def list_pending_applications(self, guild_id: int, limit: int = 25) -> list[dict]:
        cur = await self._conn.execute(
            "SELECT * FROM applications WHERE guild_id = ? AND status = 'pending' "
            "ORDER BY id ASC LIMIT ?",
            (guild_id, limit),
        )
        rows = await cur.fetchall()
        results = []
        for row in rows:
            data = dict(row)
            data["answers"] = json.loads(data["answers"])
            results.append(data)
        return results

    async def list_applications_by_user(self, guild_id: int, user_id: int, limit: int = 10) -> list[dict]:
        cur = await self._conn.execute(
            "SELECT * FROM applications WHERE guild_id = ? AND user_id = ? "
            "ORDER BY id DESC LIMIT ?",
            (guild_id, user_id, limit),
        )
        rows = await cur.fetchall()
        results = []
        for row in rows:
            data = dict(row)
            data["answers"] = json.loads(data["answers"])
            results.append(data)
        return results

    async def finalize_application(
        self,
        application_id: int,
        status: str,
        reviewer_id: int,
        deny_reason: Optional[str] = None,
    ) -> bool:
        """Atomically flips a pending application to accepted/denied.

        Returns False (and changes nothing) if the application was already
        processed by someone else — this is what prevents double-processing
        when two staff click Accept/Deny at the same time.
        """
        cur = await self._conn.execute(
            "UPDATE applications SET status = ?, reviewer_id = ?, reviewed_at = ?, deny_reason = ? "
            "WHERE id = ? AND status = 'pending'",
            (status, reviewer_id, _now(), deny_reason, application_id),
        )
        await self._conn.commit()
        return cur.rowcount > 0

    async def stats(self, guild_id: int) -> dict:
        cur = await self._conn.execute(
            "SELECT status, COUNT(*) as c FROM applications WHERE guild_id = ? GROUP BY status",
            (guild_id,),
        )
        rows = await cur.fetchall()
        counts = {"pending": 0, "accepted": 0, "denied": 0}
        for row in rows:
            counts[row["status"]] = row["c"]
        cur = await self._conn.execute(
            "SELECT COUNT(*) as c FROM applications WHERE guild_id = ?", (guild_id,)
        )
        total = (await cur.fetchone())["c"]
        counts["total"] = total
        return counts

    # ------------------------------------------------------------------
    # Verified members / rejoin handling / staff prefix state
    # ------------------------------------------------------------------
    async def mark_verified(self, guild_id: int, user_id: int):
        await self._conn.execute(
            "INSERT INTO verified_members (guild_id, user_id, verified_at, staff_prefix) "
            "VALUES (?, ?, ?, 0) "
            "ON CONFLICT(guild_id, user_id) DO UPDATE SET verified_at = excluded.verified_at",
            (guild_id, user_id, _now()),
        )
        await self._conn.commit()

    async def unmark_verified(self, guild_id: int, user_id: int):
        await self._conn.execute(
            "DELETE FROM verified_members WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )
        await self._conn.commit()

    async def is_previously_verified(self, guild_id: int, user_id: int) -> bool:
        cur = await self._conn.execute(
            "SELECT 1 FROM verified_members WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )
        return (await cur.fetchone()) is not None

    async def set_staff_prefix_flag(self, guild_id: int, user_id: int, value: bool):
        await self._conn.execute(
            "INSERT INTO verified_members (guild_id, user_id, verified_at, staff_prefix) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(guild_id, user_id) DO UPDATE SET staff_prefix = excluded.staff_prefix",
            (guild_id, user_id, _now(), int(value)),
        )
        await self._conn.commit()

    async def has_staff_prefix(self, guild_id: int, user_id: int) -> bool:
        cur = await self._conn.execute(
            "SELECT staff_prefix FROM verified_members WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )
        row = await cur.fetchone()
        return bool(row and row["staff_prefix"])
