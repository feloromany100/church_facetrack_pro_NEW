"""
SQLite-backed repository for attendance records.
Runs writes in a background thread to avoid blocking the main or camera threads.
Uses WAL mode for high concurrency.
"""
import os
import sqlite3
import threading
import queue
import logging
from datetime import datetime
from typing import Optional

from facetrack.models.person import AttendanceRecord, PersonGroup

logger = logging.getLogger("AttendanceRepository")

class AttendanceRepository:
    """
    Handles durable persistence of attendance records.
    All writes are queued and processed by a background thread asynchronously.
    """
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._write_queue = queue.Queue()
        self._stop_event = threading.Event()
        
        self._init_db()
        
        self._worker_thread = threading.Thread(
            target=self._writer_loop, 
            name="AttendanceWriterThread",
            daemon=False  # Not daemon, so we can flush on exit
        )
        self._worker_thread.start()

    def _init_db(self):
        """Create the table and set WAL mode on the main thread."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute("PRAGMA synchronous=NORMAL;")
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS attendance (
                        id TEXT PRIMARY KEY,
                        person_id TEXT,
                        person_name TEXT NOT NULL,
                        camera_id INTEGER,
                        camera_name TEXT,
                        timestamp TEXT NOT NULL,
                        confidence REAL,
                        person_group TEXT,
                        is_unknown BOOLEAN
                    )
                    """
                )
        except Exception as e:
            logger.error(f"Failed to initialize SQLite attendance DB: {e}")

    def save(self, record: AttendanceRecord):
        """Push a record to the background writer queue. Returns immediately."""
        if self._stop_event.is_set():
            logger.warning("Attempted to save record after repository was closed.")
            return
        self._write_queue.put(record)

    def _writer_loop(self):
        """Background thread that pulls from the queue and writes to SQLite."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            
            while not self._stop_event.is_set() or not self._write_queue.empty():
                try:
                    record = self._write_queue.get(timeout=1.0)
                except queue.Empty:
                    continue

                if record is None:  # Sentinel value indicating shutdown
                    self._write_queue.task_done()
                    break

                try:
                    conn.execute(
                        """
                        INSERT INTO attendance (
                            id, person_id, person_name, camera_id, camera_name, 
                            timestamp, confidence, person_group, is_unknown
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            record.id,
                            record.person_id,
                            record.person_name,
                            record.camera_id,
                            record.camera_name,
                            record.timestamp.isoformat(),
                            record.confidence,
                            record.group.value if isinstance(record.group, PersonGroup) else str(record.group),
                            1 if record.is_unknown else 0
                        )
                    )
                    conn.commit()
                except Exception as e:
                    logger.error(f"Failed to insert attendance record {record.id}: {e}")
                finally:
                    self._write_queue.task_done()
            
            conn.close()
        except Exception as e:
            logger.error(f"Writer loop encountered fatal error: {e}")

    def close(self):
        """Gracefully drain the queue and stop the background thread."""
        # Signal the loop to stop and inject a sentinel to break waits
        self._stop_event.set()
        self._write_queue.put(None)
        
        # Wait for the thread to flush remaining records and exit
        if self._worker_thread.is_alive():
            self._worker_thread.join(timeout=3.0)
            if self._worker_thread.is_alive():
                logger.warning("Attendance writer thread did not exit cleanly within timeout.")
