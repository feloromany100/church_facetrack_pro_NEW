-- Enable PRAGMAs for high-performance Enterprise SQLite
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;
PRAGMA strict = ON; -- Enforce strict typing (SQLite 3.37+)

-- 1. CAMERAS TABLE
-- Stores camera specific thresholds and physical locations.
CREATE TABLE IF NOT EXISTS cameras (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    location TEXT NOT NULL,
    stream_url TEXT,
    base_similarity_threshold REAL DEFAULT 0.45, -- Per-camera AI tuning
    is_active INTEGER CHECK(is_active IN (0, 1)) DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. PERSONS TABLE
-- Core identity table representing known individuals.
CREATE TABLE IF NOT EXISTS persons (
    id TEXT PRIMARY KEY, -- UUID
    full_name TEXT NOT NULL,
    person_group TEXT NOT NULL, -- Enum: SERVANT, CONGREGATION, VISITOR, BANNED
    notes TEXT,
    is_active INTEGER CHECK(is_active IN (0, 1)) DEFAULT 1, -- Soft Delete
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. EMBEDDINGS METADATA TABLE
-- Maps the FAISS int64 vector indexes back to physical persons and image sources.
CREATE TABLE IF NOT EXISTS embeddings_metadata (
    faiss_id INTEGER PRIMARY KEY, -- Must match FAISS index ID exactly
    person_id TEXT NOT NULL,
    source_image_path TEXT NOT NULL,
    quality_score REAL, -- Blurriness/Alignment metric when enrolled
    is_active INTEGER CHECK(is_active IN (0, 1)) DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (person_id) REFERENCES persons(id) ON DELETE CASCADE
);

-- 4. SESSIONS TABLE
-- Groups attendance events into logical blocks (e.g. "Sunday Liturgy 9AM").
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY, -- UUID
    name TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('ACTIVE', 'COMPLETED', 'ARCHIVED')),
    started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ended_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 5. UNKNOWN FACES TABLE
-- Persistent tracking of unidentified faces across frames. 
-- Allows future merging into 'persons' when identified.
CREATE TABLE IF NOT EXISTS unknown_faces (
    id TEXT PRIMARY KEY, -- UUID (e.g., track_id from ByteTrack)
    session_id TEXT NOT NULL,
    camera_id INTEGER NOT NULL,
    first_seen_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    best_capture_path TEXT, -- Path to highest quality crop
    status TEXT NOT NULL CHECK(status IN ('TRACKING', 'RESOLVED', 'IGNORED')) DEFAULT 'TRACKING',
    resolved_to_person_id TEXT, -- Populated if later identified
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (camera_id) REFERENCES cameras(id),
    FOREIGN KEY (resolved_to_person_id) REFERENCES persons(id)
);

-- 6. ATTENDANCE RECORDS TABLE (The Core Fact Table)
-- Extremely high-volume table indexing every confirmed AI lock.
CREATE TABLE IF NOT EXISTS attendance_records (
    id TEXT PRIMARY KEY, -- UUID
    session_id TEXT NOT NULL,
    camera_id INTEGER NOT NULL,
    person_id TEXT, -- NULL if logging an unknown face's movement
    unknown_face_id TEXT, -- NULL if logging a known person
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    confidence REAL NOT NULL CHECK(confidence >= 0.0 AND confidence <= 1.0),
    bbox_x INTEGER,
    bbox_y INTEGER,
    bbox_width INTEGER,
    bbox_height INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (camera_id) REFERENCES cameras(id),
    FOREIGN KEY (person_id) REFERENCES persons(id),
    FOREIGN KEY (unknown_face_id) REFERENCES unknown_faces(id),
    -- Constraint: Record must be for a known person OR an unknown face, not both/neither
    CHECK ((person_id IS NOT NULL AND unknown_face_id IS NULL) OR (person_id IS NULL AND unknown_face_id IS NOT NULL))
);

-- 7. ALERTS TABLE
-- Tracks smart alerts pushed to the UI for immediate attention.
CREATE TABLE IF NOT EXISTS alerts (
    id TEXT PRIMARY KEY, -- UUID
    type TEXT NOT NULL, -- Enum: 'UNKNOWN_FACE', 'BANNED_PERSON', 'CAMERA_OFFLINE'
    severity TEXT NOT NULL CHECK(severity IN ('INFO', 'WARNING', 'DANGER', 'CRITICAL')),
    message TEXT NOT NULL,
    camera_id INTEGER,
    reference_person_id TEXT, -- Optional link to the triggering identity
    is_read INTEGER CHECK(is_read IN (0, 1)) DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (camera_id) REFERENCES cameras(id),
    FOREIGN KEY (reference_person_id) REFERENCES persons(id)
);

-- =========================================================================
-- INDEXES (Crucial for Real-Time UI Queries & Dashboard Analytics)
-- =========================================================================

-- Attendance Lookups (Most heavily queried)
CREATE INDEX IF NOT EXISTS idx_attendance_session_time ON attendance_records(session_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_attendance_person_time ON attendance_records(person_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_attendance_camera_time ON attendance_records(camera_id, timestamp DESC);

-- Unknown Faces (For the Review Dashboard)
CREATE INDEX IF NOT EXISTS idx_unknowns_status_time ON unknown_faces(status, last_seen_at DESC);

-- Alerts (For fast unread counts)
CREATE INDEX IF NOT EXISTS idx_alerts_read_status ON alerts(is_read, created_at DESC);

-- Fast FAISS Metadata mapping
CREATE INDEX IF NOT EXISTS idx_embeddings_person ON embeddings_metadata(person_id);
