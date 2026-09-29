"""Un processo Claude tenuto caldo, invece di riaccenderlo a ogni frase.

Ogni `claude -p` costa cinque secondi di avvio prima ancora di pensare. In una
conversazione a voce sono cinque secondi di silenzio a domanda. Qui il processo
resta aperto in modalità stream: si avvia una volta e poi ogni turno costa solo
il tempo del modello, circa quattro secondi, con le prime parole a uno.

Tiene anche il filo del discorso, quindi "e ieri?" funziona.
"""

import json
import os
import subprocess
import threading
import time

from . import config, piattaforma, recap

# Dopo tanti turni la conversazione è lunga e costosa: si ricomincia.
MAX_TURNI = 20
# Dopo tanto silenzio non serve tenere un processo aperto.
SCADENZA = 900

ISTRUZIONI = """Sei l'assistente vocale di chi ti parla, dentro Plancia, l'archivio
di lavoro con l'IA dell'utente. Ti arrivano frasi dette a voce e trascritte,
quindi possono avere errori: interpretale con buon senso.

Hai i tool `plancia_*` sull'archivio: progetti, task, post, sessioni di Claude
Code e Codex, memoria. Usali invece di tirare a indovinare. Se ti chiede di
segnare, chiudere o aggiornare qualcosa, fallo: è l'archivio dell'utente, non
serve chiedere il permesso.

Rispondi sempre in {lingua}, al massimo quaranta parole, scritte per essere
ascoltate: una o due frasi, niente elenchi, niente markdown, niente trattini
lunghi, niente percorsi di file o sigle lette a voce. Se hai fatto qualcosa,
dillo corto e diretto."""

TOOL = [
    "mcp__plancia__plancia_briefing", "mcp__plancia__plancia_search",
    "mcp__plancia__plancia_projects", "mcp__plancia__plancia_project_update",
    "mcp__plancia__plancia_tasks", "mcp__plancia__plancia_task_add",
    "mcp__plancia__plancia_task_update", "mcp__plancia__plancia_posts",
    "mcp__plancia__plancia_post_add", "mcp__plancia__plancia_post_update",
    "mcp__plancia__plancia_sessions", "mcp__plancia__plancia_memory",
    "mcp__plancia__plancia_log", "mcp__plancia__plancia_recap",
]


class Agente:
    """Un processo per lingua. Non è thread safe da solo: c'è un lucchetto."""

    def __init__(self, lang="it"):
        self.lang = lang
        self.proc = None
        self.turni = 0
        self.ultimo = 0.0
        self.lucchetto = threading.Lock()

    # --- ciclo di vita -----------------------------------------------------

    def _vivo(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def _scaduto(self) -> bool:
        return self.turni >= MAX_TURNI or (time.time() - self.ultimo) > SCADENZA

    def avvia(self) -> bool:
        self.ferma()
        exe = recap.claude_bin()
        if not exe:
            return False
        cfg = config.load_config()
        cmd = [exe, "-p",
               "--model", cfg.get("modello_voce", "sonnet"),
               "--input-format", "stream-json",
               "--output-format", "stream-json",
               "--verbose",
               "--append-system-prompt",
               ISTRUZIONI.format(lingua=recap.NOMI_LINGUA.get(self.lang, "English")),
               "--allowedTools"] + TOOL
        try:
            self.proc = subprocess.Popen(
                cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, text=True, bufsize=1,
                cwd=str(config.DATA_DIR), env=dict(os.environ),
                **piattaforma.opzioni_figlio(), **piattaforma.opzioni_utf8())
        except Exception:
            self.proc = None
            return False
        self.turni = 0
        self.ultimo = time.time()
        return True

    def ferma(self):
        if self.proc is not None:
            try:
                if self.proc.stdin:
                    self.proc.stdin.close()
            except Exception:
                pass
            try:
                self.proc.terminate()
            except Exception:
                pass
        self.proc = None

    def scalda(self):
        """Avvia il processo senza chiedere niente, così la prima domanda vera
        non paga l'avvio. Si chiama quando si apre il pannello."""
        with self.lucchetto:
            if not self._vivo():
                self.avvia()

    # --- una domanda -------------------------------------------------------

    def chiedi(self, testo: str, timeout=90) -> str:
        with self.lucchetto:
            if self._vivo() and self._scaduto():
                self.ferma()
            if not self._vivo() and not self.avvia():
                return ""
            try:
                return self._turno(testo, timeout)
            except Exception:
                # un processo rotto non si recupera: si riparte pulito
                self.ferma()
                return ""

    def _turno(self, testo: str, timeout: float) -> str:
        msg = {"type": "user",
               "message": {"role": "user", "content": [{"type": "text", "text": testo}]}}
        self.proc.stdin.write(json.dumps(msg, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()

        scaduto = time.time() + timeout
        risposta = ""
        while time.time() < scaduto:
            riga = self.proc.stdout.readline()
            if not riga:
                break
            try:
                d = json.loads(riga)
            except Exception:
                continue
            if d.get("type") == "result":
                risposta = (d.get("result") or "").strip()
                break
        self.turni += 1
        self.ultimo = time.time()
        return risposta


# --------------------------------------------------------------------------
# uno per lingua, condivisi da tutto il processo del server
# --------------------------------------------------------------------------

_agenti = {}
_lucchetto = threading.Lock()


def per(lang: str) -> Agente:
    with _lucchetto:
        if lang not in _agenti:
            _agenti[lang] = Agente(lang)
        return _agenti[lang]


def chiedi(testo: str, lang: str, timeout=90) -> str:
    return per(lang).chiedi(testo, timeout)


def scalda(lang: str):
    threading.Thread(target=per(lang).scalda, daemon=True).start()


def stato() -> dict:
    return {lang: {"vivo": a._vivo(), "turni": a.turni,
                   "inattivo_da": round(time.time() - a.ultimo) if a.ultimo else None}
            for lang, a in _agenti.items()}


def spegni():
    for a in _agenti.values():
        a.ferma()
