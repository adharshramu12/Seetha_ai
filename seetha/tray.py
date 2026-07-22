"""
System tray integration.

Seetha lives in the background like a real assistant: closing the main
window minimizes to the tray, and the tray menu (or Ctrl+Space) brings
her back.
"""

from PIL import Image

from seetha.logger import setup_logger

logger = setup_logger()


def create_tray(icon_path, on_show, on_command_bar, on_quit):
    """
    Starts the tray icon on its own thread.
    All callbacks are invoked from the tray thread — callers must
    marshal to the Tk main loop themselves (root.after).
    Returns the pystray Icon, or None if pystray is unavailable.
    """
    try:
        import pystray
    except ImportError:
        logger.warning("pystray not installed — tray icon disabled. (pip install pystray)")
        return None

    try:
        img = Image.open(icon_path).convert("RGBA")
        img.thumbnail((64, 64))
    except Exception as e:
        logger.warning(f"Tray icon image failed ({e}); using a plain square.")
        img = Image.new("RGBA", (64, 64), (13, 17, 23, 255))

    menu = pystray.Menu(
        pystray.MenuItem("Show Seetha", lambda icon, item: on_show(), default=True),
        pystray.MenuItem("Command Bar  (Ctrl+Space)", lambda icon, item: on_command_bar()),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit Seetha", lambda icon, item: on_quit()),
    )

    icon = pystray.Icon("SeethaAI", img, "Seetha AI — click to open", menu)
    try:
        icon.run_detached()
        logger.info("Tray icon active.")
    except Exception as e:
        logger.warning(f"Tray icon failed to start: {e}")
        return None
    return icon
