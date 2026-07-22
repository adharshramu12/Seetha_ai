import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

def setup_logger(name="Seetha", log_filename="seetha.log", level=logging.INFO):
    """
    Sets up a logger with console and file handlers.
    Ensures safe, rotating, and structured logging in a standard User Data directory.
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Avoid duplicate handlers
    if logger.handlers:
        return logger
    
    # Formatter - Standardized Format
    formatter = logging.Formatter(
        '[%(asctime)s] [%(levelname)s] [%(filename)s:%(lineno)d] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Determine Log Directory (AppData/Local/Seetha/logs)
    # consistently use user's home directory to avoid permission issues in Program Files
    try:
        home = Path.home()
        log_dir = home / "AppData" / "Local" / "Seetha" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / log_filename
    except Exception as e:
        # Fallback to temp dir if AppData fails
        import tempfile
        log_path = Path(tempfile.gettempdir()) / log_filename
        print(f"Logger Warning: Could not use AppData. Fallback to {log_path}. Error: {e}")

    # File Handler (Rotating)
    try:
        # 10 MB max size, keep 5 backups
        file_handler = RotatingFileHandler(
            str(log_path), 
            maxBytes=10*1024*1024, 
            backupCount=5, 
            encoding='utf-8'
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(level)
        logger.addHandler(file_handler)
    except Exception as e:
        print(f"CRITICAL ERROR: Could not set up file logger at {log_path}: {e}")

    # Console Handler (Stdout) — force UTF-8 so emoji in log lines
    # (e.g. the reminder alarm clock) never crash the charmap codec
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)
    logger.addHandler(console_handler)
    
    return logger
