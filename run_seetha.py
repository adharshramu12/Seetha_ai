"""
Seetha AI - packaged-build entry point.

PyInstaller needs a plain script (not `python -m seetha.main`), so this
thin wrapper is what build_exe.bat points at. Keep all real logic in
seetha/main.py.
"""
from seetha.main import launch_app
from seetha.logger import setup_logger

if __name__ == "__main__":
    try:
        launch_app()
    except Exception as e:
        setup_logger().critical(f"Fatal Application Crash: {e}", exc_info=True)
