"""
Moruk AI OS - Logger
Zentrales Logging-System mit File-Output, Rotation und Crash-Tracking.
"""

import logging
import logging.handlers
import traceback
import re
import sys
from datetime import datetime
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
LOG_DIR = DATA_DIR / "logs"

# Max 5MB pro Log-Datei, max 3 Backup-Dateien = max ~20MB total
MAX_LOG_BYTES = 5 * 1024 * 1024   # 5 MB
LOG_BACKUP_COUNT = 3

# Patterns für sensitive Daten die nie geloggt werden dürfen
_SENSITIVE_PATTERNS = [
    (re.compile(r'(sk-[a-zA-Z0-9]{20,})', re.IGNORECASE), '***API_KEY***'),
    (re.compile(r'(Bearer\s+[a-zA-Z0-9\-._~+/]+=*)', re.IGNORECASE), 'Bearer ***'),
    (re.compile(r'("api_key"\s*:\s*")[^"]+(")', re.IGNORECASE), r'\1***\2'),
    (re.compile(r'("password"\s*:\s*")[^"]+(")', re.IGNORECASE), r'\1***\2'),
    (re.compile(r'("token"\s*:\s*")[^"]+(")', re.IGNORECASE), r'\1***\2'),
]


class SensitiveDataFilter(logging.Filter):
    """Filtert API Keys und Passwörter aus Log-Einträgen."""
    def filter(self, record: logging.LogRecord) -> bool:
        msg = str(record.getMessage())
        for pattern, replacement in _SENSITIVE_PATTERNS:
            msg = pattern.sub(replacement, msg)
        record.msg = msg
        record.args = ()
        return True


def setup_logger() -> logging.Logger:
    """Erstellt und konfiguriert den Moruk Logger mit Rotation."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("moruk")
    logger.setLevel(logging.DEBUG)

    # Alte Handler entfernen (bei Reimport)
    logger.handlers.clear()

    sensitive_filter = SensitiveDataFilter()

    # Rotating File Handler — max 5MB, 3 Backups
    log_file = LOG_DIR / "moruk.log"
    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=MAX_LOG_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.addFilter(sensitive_filter)
    file_format = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S"
    )
    file_handler.setFormatter(file_format)
    logger.addHandler(file_handler)

    # Console Handler — nur Warnings+
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.WARNING)
    console_handler.addFilter(sensitive_filter)
    console_format = logging.Formatter("[%(levelname)s] %(message)s")
    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)

    return logger


def install_crash_handler(logger: logging.Logger):
    """Installiert globalen Exception Handler für unerwartete Crashes."""
    crash_log = LOG_DIR / "crashes.log"

    def handle_exception(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return

        tb_text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        logger.critical(f"UNHANDLED CRASH:\n{tb_text}")

        # Crash log mit Größenlimit (max 1MB)
        try:
            if crash_log.exists() and crash_log.stat().st_size > 1 * 1024 * 1024:
                # Ältere Hälfte wegwerfen
                content = crash_log.read_text(encoding="utf-8", errors="replace")
                crash_log.write_text(content[len(content)//2:], encoding="utf-8")
            with open(crash_log, "a", encoding="utf-8") as f:
                f.write(f"\n{'='*60}\n")
                f.write(f"CRASH: {datetime.now().isoformat()}\n")
                f.write(f"{'='*60}\n")
                f.write(tb_text)
                f.write("\n")
        except Exception:
            pass

        sys.__excepthook__(exc_type, exc_value, exc_tb)

    sys.excepthook = handle_exception


def get_logger(name: str = "moruk") -> logging.Logger:
    """Holt einen benannten Sub-Logger."""
    return logging.getLogger(f"moruk.{name}")


# Convenience
log = setup_logger()
