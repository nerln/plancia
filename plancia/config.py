"""Percorsi, costanti e configurazione utente di Plancia.

Tutto sta nella libreria standard: nessuna dipendenza da installare, nessun
ambiente virtuale da tenere vivo. L'app deve funzionare anche fra due anni.
"""

import json
import os
import secrets
from pathlib import Path

HOME = Path.home()
CLAUDE_DIR = Path(os.environ.get("CLAUDE_CONFIG_DIR", HOME / ".claude"))
CLAUDE_PROJECTS = CLAUDE_DIR / "projects"
CLAUDE_SKILLS = CLAUDE_DIR / "skills"
CLAUDE_PLUGINS = CLAUDE_DIR / "plugins"
CLAUDE_ROUTINES = CLAUDE_DIR / "scheduled-tasks"
CLAUDE_SETTINGS = CLAUDE_DIR / "settings.json"
CLAUDE_JSON = HOME / ".claude.json"

DATA_DIR = Path(os.environ.get("PLANCIA_HOME", HOME / ".plancia"))
DB_PATH = DATA_DIR / "plancia.db"
QUEUE_DIR = DATA_DIR / "queue"
QUEUE_FILE = QUEUE_DIR / "hooks.jsonl"
TOKEN_FILE = DATA_DIR / "token"
BRIEFING_FILE = DATA_DIR / "briefing.md"
CONFIG_FILE = DATA_DIR / "config.json"
LOG_FILE = DATA_DIR / "plancia.log"

ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT / "web"
SEED_FILE = ROOT / "plancia" / "seed.json"
USER_SEED = DATA_DIR / "seed.json"

DEFAULT_PORT = 7773

DEFAULTS = {
    "port": DEFAULT_PORT,
    "gh_user": "",
    "code_roots": [str(HOME / "dev")],
    "sync_on_serve": True,
    "sync_interval_minutes": 15,
    "gh_enabled": True,
    "locale": "it",
    # Cartelle private: tutto quello che sta sotto una di queste non deve mai
    # entrare nell'archivio (vedi plancia/esclusi.py, che legge queste due
    # chiavi e basta). Vuote di default: con le liste vuote il comportamento
    # non cambia di un byte.
    "cartelle_escluse": [],
    "sessioni_escluse": [],
}


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    QUEUE_DIR.mkdir(parents=True, exist_ok=True)


def load_config() -> dict:
    ensure_dirs()
    cfg = dict(DEFAULTS)
    if CONFIG_FILE.exists():
        try:
            cfg.update(json.loads(CONFIG_FILE.read_text("utf-8")))
        except Exception:
            pass
    return cfg


def save_config(cfg: dict) -> None:
    ensure_dirs()
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), "utf-8")


def get_token() -> str:
    """Token locale per le scritture via HTTP. Vive solo su questa macchina."""
    ensure_dirs()
    if TOKEN_FILE.exists():
        tok = TOKEN_FILE.read_text("utf-8").strip()
        if tok:
            return tok
    tok = secrets.token_urlsafe(24)
    TOKEN_FILE.write_text(tok, "utf-8")
    try:
        TOKEN_FILE.chmod(0o600)
    except Exception:
        pass
    return tok
