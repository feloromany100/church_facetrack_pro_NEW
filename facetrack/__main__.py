"""
facetrack/__main__.py — unified entry point.

    python -m facetrack              # PySide6 UI (default)
    python -m facetrack --headless   # OpenCV mosaic, no GUI
    python -m facetrack --demo       # PySide6 UI with synthetic data
"""

import os
import sys
import argparse

# Ensure the project root is in the Python path regardless of how the script is run
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

def main():
    # Central logging for both UI/headless entry points
    from facetrack.infra.logging import setup_logging
    setup_logging()

    parser = argparse.ArgumentParser(prog="facetrack")
    parser.add_argument("--headless", action="store_true",
                        help="Run OpenCV mosaic mode (no PySide6 UI)")
    parser.add_argument("--demo", action="store_true",
                        help="Seed synthetic attendance data (development only)")
    args = parser.parse_args()

    if args.headless:
        from headless.main import main as headless_main
        headless_main()
    else:
        from PySide6.QtWidgets import QApplication
        from facetrack.ui.main_window import MainWindow
        from facetrack.ui.theme import apply_theme

        app = QApplication(sys.argv)
        app.setApplicationName("Church FaceTrack Pro")
        app.setOrganizationName("FaceTrack")
        apply_theme(app)

        window = MainWindow(demo_mode=args.demo)
        window.show()
        sys.exit(app.exec())

if __name__ == "__main__":
    main()
