"""Rotating log handler — persistent, survives reboots"""
import logging, logging.handlers, os

LOG_DIR  = "/home/jarvis/.openclaw/workspace/osint/logs"
LOG_FILE = os.path.join(LOG_DIR, "herkulio.log")
os.makedirs(LOG_DIR, exist_ok=True)

def setup():
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    # Console
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    root.addHandler(ch)
    # Rotating file — 5MB × 7 files = max 35MB logs
    fh = logging.handlers.RotatingFileHandler(
        LOG_FILE, maxBytes=5*1024*1024, backupCount=7, encoding="utf-8")
    fh.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s"))
    root.addHandler(fh)
    logging.info("Herkulio logging initialized → %s", LOG_FILE)
