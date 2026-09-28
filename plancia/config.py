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
    # Compartimenti: gruppi di lavoro sulla stessa macchina che non si vedono
    # (vedi plancia/compartimenti.py e bin/plancia-guardiano). `guardiano` e'
    # "spento" (default: l'hook esce subito), "solo-registro" (scrive in
    # guardiano.log cosa AVREBBE negato, non nega mai) o "bloccante" (nega
    # davvero). `compartimenti` e' {nome: {"cartelle", "sessioni",
    # "drive_ids"}} per i compartimenti nominati (elenchi di permessi) e la
    # voce speciale "predefinito": {"manifesto_divieti", "divieti",
    # "comandi_vietati"} (elenco di divieti). L'hook legge config.json da solo,
    # senza importare questo modulo (che crea cartelle): qui le chiavi stanno
    # perche' `plancia config` le mostri e perche' un solo posto le elenchi.
    "guardiano": "spento",
    "compartimenti": {},
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


def load_config_verificata() -> dict:
    """Come `load_config()`, ma per chi deve sapere se `cartelle_escluse` e
    `sessioni_escluse` sono davvero utilizzabili invece di riceverle in
    silenzio come vuote.

    `load_config()` inghiotte ogni errore di lettura o di parsing e torna i
    default: comodo per chi legge `port` o `code_roots`, disastroso per le due
    chiavi private, perché "file rotto" e "niente è escluso" diventano la
    stessa cosa. Misurato (vedi plancia/esclusi.py:valida): un `config.json`
    con una virgola finale fa tornare `load_config()` ai default, e il sync
    dopo farebbe entrare tutto il privato come se la regola non fosse mai
    stata scritta.

    Torna `cfg` con due chiavi in più: `esclusi_ok` (bool) ed
    `esclusi_errore` (stringa o None). Quando `esclusi_ok` è falso, chi
    chiama deve trattare la sessione come "non so cosa è escluso" —
    fail-closed: niente sync di sessioni/turni/memoria/Codex/lavagna/git
    locali, niente purga (vedi ingest.sync), nessuna scrittura in coda
    (vedi bin/plancia-hook, che tiene una copia di questa stessa regola
    perché non importa il pacchetto). Quando è vero, `cartelle_escluse` e
    `sessioni_escluse` sono già validate: percorsi assoluti, esistenti,
    nella grafia vera del disco.
    """
    cfg = dict(DEFAULTS)
    if not CONFIG_FILE.exists():
        cfg["esclusi_ok"], cfg["esclusi_errore"] = True, None
        return cfg
    try:
        testo = CONFIG_FILE.read_text("utf-8")
    except OSError as exc:
        cfg["esclusi_ok"] = False
        cfg["esclusi_errore"] = f"{CONFIG_FILE} non leggibile: {exc}"
        return cfg
    try:
        letta = json.loads(testo)
    except Exception as exc:
        cfg["esclusi_ok"] = False
        cfg["esclusi_errore"] = f"{CONFIG_FILE} non è JSON valido: {exc}"
        return cfg
    if not isinstance(letta, dict):
        cfg["esclusi_ok"] = False
        cfg["esclusi_errore"] = f"{CONFIG_FILE} non è un oggetto JSON"
        return cfg
    cfg.update(letta)

    # Import qui dentro, non in cima al file: esclusi.py importa config, e in
    # cima sarebbe un giro (config -> esclusi -> config) risolto solo per
    # fortuna dall'ordine di import di chi arriva per primo.
    from . import esclusi as _esclusi
    ok, errore, cartelle, sessioni = _esclusi.valida(cfg)
    cfg["esclusi_ok"] = ok
    cfg["esclusi_errore"] = errore
    if ok:
        cfg["cartelle_escluse"] = cartelle
        cfg["sessioni_escluse"] = sessioni
    return cfg


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
