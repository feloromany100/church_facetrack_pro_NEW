# Church FaceTrack Pro

## Quick start

```bash
pip install -e .
python -m facetrack              # PySide6 UI
python -m facetrack --headless   # OpenCV mosaic
python -m facetrack --demo       # UI with synthetic data
```

## Structure

```
facetrack/        installable package
  core/           frame_processor, video_capture, database
  managers/       temporal_consensus, identity_lock, etc.
  models/         pure dataclasses
  storage/        attendance_store, session_manager
  workers/        QThread workers
  ui/             PySide6 pages + components
headless/         OpenCV mosaic mode
  processes/      thin multiprocessing wrappers
photos/           enrolled face photos
data/             FAISS index + labels.json
Sessions/         runtime attendance output
```
