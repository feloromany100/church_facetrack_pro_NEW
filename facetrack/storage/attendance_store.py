"""
Attendance data store.
Wraps an in-memory list + writes to the real session SQLite DB.
Swap the in-memory list for a full query layer with zero UI changes.
"""
import time
import uuid
import logging
import threading
from datetime import datetime, timedelta
from typing import List, Optional
import random
import os

from facetrack.models.person import AttendanceRecord, PersonGroup
from facetrack.data.attendance_repository import AttendanceRepository

logger = logging.getLogger("AttendanceStore")


class AttendanceStore:
    """
    In-memory + SQLite attendance store.

    Use as a context manager or call close() explicitly when done.
    The store must be closed to flush the background writer thread.

        with AttendanceStore(db_path) as store:
            store.log(...)
    """

    def __init__(self, csv_path: Optional[str] = None, seed_dummy: bool = False):
        """
        csv_path:   path used to derive the SQLite database path.
                    If None, defaults to "attendance.db".
        seed_dummy: if True, populate store with synthetic records for UI development.
                    NEVER set this to True in production — it creates fabricated
                    attendance history.  Default: False.
        """
        self._records: List[AttendanceRecord] = []
        self._lock = threading.Lock()  # guards _records and _last_logged

        # Initialize SQLite Repository
        if not csv_path:
            csv_path = "attendance.db"
        db_path = csv_path.replace(".csv", ".db")
        self._repository = AttendanceRepository(db_path)

        # Per-person cooldown: name → last logged timestamp
        self._last_logged: dict = {}

        # Load cooldown from config (default 300s)
        try:
            from facetrack.services.config_service import ConfigService
            self._cooldown: float = float(ConfigService().load().COOLDOWN_SECONDS)
        except Exception:
            self._cooldown = 300.0

        # Restore historical records from the SQLite database on startup
        self._load_from_db()

        if seed_dummy:
            self._seed_dummy_data()

    # ── Context manager ───────────────────────────────────────────────────────
    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    # ── Write ─────────────────────────────────────────────────────────────────
    def set_cooldown(self, seconds: float):
        """Update the per-person cooldown at runtime (called from Settings)."""
        with self._lock:
            self._cooldown = max(0.0, float(seconds))

    def log(self, person_name: str, person_id: Optional[str],
            camera_id: int, camera_name: str,
            confidence: float, group: PersonGroup,
            is_unknown: bool = False) -> Optional[AttendanceRecord]:
        now = time.time()
        with self._lock:
            last = self._last_logged.get(person_name, 0.0)
            if now - last < self._cooldown:
                return None
            self._last_logged[person_name] = now

            rec = AttendanceRecord(
                id=str(uuid.uuid4()),
                person_id=person_id or "",
                person_name=person_name,
                camera_id=camera_id,
                camera_name=camera_name,
                timestamp=datetime.now(),
                confidence=confidence,
                group=group,
                is_unknown=is_unknown,
            )
            self._records.append(rec)
            self._repository.save(rec)

        return rec

    # ── Read ──────────────────────────────────────────────────────────────────
    def get_all(self) -> List[AttendanceRecord]:
        with self._lock:
            return list(reversed(self._records))

    def get_today(self) -> List[AttendanceRecord]:
        today = datetime.now().date()
        with self._lock:
            return [r for r in self._records if r.timestamp.date() == today]

    def get_known_today(self) -> int:
        return sum(1 for r in self.get_today() if not r.is_unknown)

    def get_unknown_today(self) -> int:
        return sum(1 for r in self.get_today() if r.is_unknown)

    def search(self, query: str = "", camera_id: Optional[int] = None,
               date: Optional[datetime] = None) -> List[AttendanceRecord]:
        with self._lock:
            results = list(self._records)
        if query:
            q = query.lower()
            results = [r for r in results if q in r.person_name.lower()]
        if camera_id is not None:
            results = [r for r in results if r.camera_id == camera_id]
        if date:
            results = [r for r in results if r.timestamp.date() == date.date()]
        return list(reversed(results))

    def weekly_counts(self) -> List[int]:
        today = datetime.now().date()
        with self._lock:
            records = list(self._records)
        counts = []
        for i in range(6, -1, -1):
            day = today - timedelta(days=i)
            counts.append(sum(1 for r in records if r.timestamp.date() == day))
        return counts

    # ── Cleanup ───────────────────────────────────────────────────────────────
    def close(self):
        """Gracefully shutdown the background writer thread."""
        if hasattr(self, "_repository") and self._repository:
            self._repository.close()

    # ── DB restore ────────────────────────────────────────────────────────────────
    def _load_from_db(self):
        """
        Populate the in-memory record list from SQLite on startup.
        """
        if not hasattr(self, "_repository") or self._repository is None:
            return
        try:
            import sqlite3
            with sqlite3.connect(self._repository.db_path) as conn:
                rows = conn.execute(
                    "SELECT id, person_id, person_name, camera_id, camera_name, "
                    "timestamp, confidence, person_group, is_unknown "
                    "FROM attendance ORDER BY timestamp"
                ).fetchall()

            with self._lock:
                for row in rows:
                    try:
                        rec = AttendanceRecord(
                            id=row[0],
                            person_id=row[1] or "",
                            person_name=row[2],
                            camera_id=row[3] or 0,
                            camera_name=row[4] or "",
                            timestamp=datetime.fromisoformat(row[5]),
                            confidence=float(row[6]) if row[6] is not None else 0.0,
                            group=PersonGroup(row[7]) if row[7] else PersonGroup.VISITOR,
                            is_unknown=bool(row[8]),
                        )
                        self._records.append(rec)
                        self._last_logged[rec.person_name] = rec.timestamp.timestamp()
                    except Exception:
                        pass  # Corrupt row — skip it

            logger.info("Restored %d attendance records from SQLite", len(self._records))

        except Exception as exc:
            logger.warning("Could not restore attendance history from SQLite: %s", exc)

    # ── Dummy seed ────────────────────────────────────────────────────────────────
    def _seed_dummy_data(self):
        names = [
            ("Mina Samir",  "p001", PersonGroup.SERVANT),
            ("Mary Hanna",  "p002", PersonGroup.YOUTH),
            ("Bishoy Nabil","p003", PersonGroup.SERVANT),
            ("Sara Emad",   "p004", PersonGroup.YOUTH),
            ("Fady Gerges", "p005", PersonGroup.VISITOR),
            ("Unknown",     None,   PersonGroup.UNKNOWN),
        ]
        cameras = [(0, "Main Hall"), (1, "Entrance"), (2, "Youth Room")]
        now = datetime.now()
        for i in range(120):
            name, pid, group = random.choice(names)
            cam_id, cam_name = random.choice(cameras)
            ts = now - timedelta(
                days=random.randint(0, 6),
                hours=random.randint(0, 5),
                minutes=random.randint(0, 59),
            )
            rec = AttendanceRecord(
                id=str(uuid.uuid4()),
                person_id=pid or "",
                person_name=name,
                camera_id=cam_id,
                camera_name=cam_name,
                timestamp=ts,
                confidence=round(random.uniform(0.70, 0.99), 2) if pid else 0.0,
                group=group,
                is_unknown=(pid is None),
            )
            self._records.append(rec)
        self._records.sort(key=lambda r: r.timestamp)