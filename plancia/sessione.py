"""Chi ha chiamato il server MCP adesso, letto dall'ambiente del processo.

Un task creato via `plancia_task_add` senza sapere chi lo ha scritto è una nota
in bottiglia: nessuno sa a quale conversazione tornare per riprenderlo (vedi
docs/RICOGNIZIONE-dati-mcp-hook.md, punto 2: "Il server MCP è cieco sulla
sessione che lo ospita"). Questo modulo risponde a "chi sono", senza mai
chiedere niente all'utente e senza aggiungere un solo campo agli schemi dei
tool (misurato: un campo su uno dei sei tool di prima classe si paga a ogni
sessione, vedi mcp.py:195-209).

Fonti, in ordine, per Claude Code:
- `CLAUDE_CODE_SESSION_ID` nell'ambiente: è l'id della trascrizione, misurato
  dal consiglio il 16/09/2026 (docs/CONSIGLIO-2026-09-16-verdetto.md, punto 4 e
  nota 5). Un subagente eredita quello del padre interattivo
  (`CLAUDE_CODE_CHILD_SESSION=1`), quindi un task scritto da un subagente punta
  comunque alla conversazione giusta. `CLAUDE_CODE_HOST_SESSION_ID` è stato
  misurato diverso a parità di sessione e non è affidabile: non si legge qui.
- Il pid contro cui si confronta `~/.claude/sessions/<pid>.json` è
  `CLAUDE_PID` se c'è nell'ambiente, altrimenti `os.getppid()` (il processo
  interattivo che ha lanciato il server MCP). Se il file esiste e il suo
  `sessionId` diverge dalla variabile, vince il file (`origine="file"`); se la
  variabile manca del tutto, vince il file quando c'è, altrimenti non si trova
  niente (`origine="nessuna"`). Misurato il 16/09/2026 su questa macchina, 8
  processi `plancia-mcp` vivi via `ps eww`: nessuno porta `CLAUDE_PID`
  nell'ambiente, e per tutti e 8 il ppid del server coincide esattamente col
  pid nel nome del file di sessione (es. pid 32434 → ppid 32410 →
  `sessions/32410.json`, `sessionId` uguale a `CLAUDE_CODE_SESSION_ID`). La
  frase "il file lo scrive l'app dopo l'avvio del processo" di una versione
  precedente di questo modulo diceva che `CLAUDE_PID` "non arriva mai": era
  troppo assoluta. Misurato che nell'app desktop c'è; negli 8 server MCP
  visti qui no, quindi per loro il ramo che lo leggeva direttamente da
  `os.environ` non scattava mai in produzione, e il ripiego resta
  `os.getppid()`.

Per Codex non esiste un id di sessione verificato per il processo MCP (il
consiglio lo dichiara debito, punto 14 del verdetto): si ripiega sul rollout
più recente la cui `cwd` coincide con quella corrente. Il piano indicava di
riusare `plancia/lavagna.py:78-118`, ma a quelle righe (rilette sul commit
f2a2076, quello citato dal lotto) c'è `da_codex()`, che legge gli obiettivi dal
database SQLite di Codex (`goals_1.sqlite`) e non ha niente a che fare con i
file di rollout o con una cwd: non è la funzione riusabile che il testo
indicava. Si segue quindi la clausola di ripiego dello stesso lotto ("se non è
[riusabile], copiane il minimo in sessione.py senza toccare lavagna.py"): la
scansione dei rollout qui sotto è una versione minima, che legge solo le prime
righe di ogni file invece del file intero come fa `codex.sync()` per
l'indicizzazione completa.
"""

import json
import os
import re
import socket
import sys
from pathlib import Path

from . import codex, config

# La cartella base di Codex (~/.codex) ha un'unica fonte: codex.CODEX_HOME.
# Prima di questa correzione sessione.py ne teneva una copia propria,
# calcolata separatamente da CODEX_HOME nell'ambiente: le prove che
# sovrascrivevano una sola delle due copie lasciavano l'altra sul valore vero,
# e un domani i due moduli potevano leggere due cartelle diverse. Qui sotto si
# legge sempre `codex.CODEX_HOME` al momento della chiamata (mai una copia
# congelata all'import), cosi' un solo punto va sovrascritto nelle prove.

# Stesso pattern di plancia/codex.py: il nome del file è
# rollout-<data con trattini>-<uuid>, e la data ha trattini anche lei, quindi
# l'id si prende dal fondo con una regex, non con uno split.
_UUID_RE = re.compile(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$")

# Quante righe leggere al massimo da un rollout prima di arrendersi: la cwd
# sta quasi sempre nelle primissime righe (session_meta o turn_context).
_RIGHE_MAX = 40


def _file_session_id(pid):
    """Il campo sessionId di ~/.claude/sessions/<pid>.json, o None."""
    if not pid:
        return None
    path = config.CLAUDE_DIR / "sessions" / ("%s.json" % pid)
    try:
        dati = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return None
    return dati.get("sessionId") or None


def _e_codex(argv):
    """True se il comando con cui il server è stato lanciato porta --agente codex.

    Lo aggiunge `codex.registra_mcp()` al blocco che scrive in config.toml: è
    così che il server, lanciato da Codex, sa di esserlo (bin/plancia-mcp non
    legge argv per altro, quindi qui non c'è conflitto con nessun altro flag).
    """
    for i, a in enumerate(argv):
        if a == "--agente" and i + 1 < len(argv) and argv[i + 1] == "codex":
            return True
        if a == "--agente=codex":
            return True
    return False


def _rollout_piu_recente(cwd):
    """L'id del rollout Codex più recente la cui cwd coincide con `cwd`, o None."""
    cartella = codex.CODEX_HOME / "sessions"
    if not cartella.is_dir():
        return None
    cwd_vera = os.path.realpath(cwd)
    migliore = None  # (mtime, uuid)
    for path in cartella.glob("*/*/*/rollout-*.jsonl"):
        m = _UUID_RE.search(path.stem)
        if not m:
            continue
        trovata = None
        try:
            with open(str(path), "r", encoding="utf-8", errors="replace") as fh:
                for _ in range(_RIGHE_MAX):
                    riga = fh.readline()
                    if not riga:
                        break
                    try:
                        d = json.loads(riga)
                    except Exception:
                        continue
                    if d.get("type") in ("session_meta", "turn_context"):
                        c = (d.get("payload") or {}).get("cwd")
                        if c:
                            trovata = c
                            break
            # Confronto per percorso risolto, non per stringa: su questa
            # macchina /tmp è un symlink a /private/tmp (lo scratchpad delle
            # sessioni ci vive sotto), quindi due grafie diverse della stessa
            # cartella non devono contarsi come cwd diverse.
            if trovata is None or os.path.realpath(trovata) != cwd_vera:
                continue
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if migliore is None or mtime > migliore[0]:
            migliore = (mtime, m.group(1))
    return migliore[1] if migliore else None


def corrente(argv=None):
    """Chi ha chiamato il server MCP adesso.

    Restituisce {"session_id": str|None, "cwd": str, "agent": "claude"|"codex",
    "host": str, "origine": "env"|"file"|"codex-rollout"|"nessuna"}.
    `argv` è un parametro opzionale solo per le prove (di norma è `sys.argv`).

    Il valore "ppid" previsto dal testo del lotto per l'enumerazione di
    `origine` non compare mai: quando il ritrovamento passa dal ppid invece
    che da CLAUDE_PID, l'origine resta comunque "file" (è lì che il
    session_id è stato letto), e quando neanche il ppid trova un file
    l'origine è "nessuna" — "ppid" con `session_id=None` direbbe che l'id
    viene dal ppid quando in realtà non c'è nessun id. Vedi la prova 3 del
    lotto, che già impone "file" in questo caso.
    """
    if argv is None:
        argv = sys.argv
    try:
        cwd = os.getcwd()
    except OSError:
        # La cartella in cui il server è partito non esiste più: scenario
        # reale su questa macchina, dove le copie in ~/dev/plancia-copie/
        # <lotto> vengono cancellate a fine lotto mentre la sessione aperta
        # lì tiene vivo il suo plancia-mcp (misurato: vedi mcp.py, dove
        # plancia_task_add avvolge corrente() in un try proprio per questo).
        # Prima si ripiegava su PWD, ma è la variabile della shell che ha
        # lanciato il processo, non della cartella in cui gira adesso: dopo
        # un cd la shell la aggiorna, il server no, e la scritta finiva per
        # mentire su dove è partito invece di dire onestamente "non lo so
        # più" (misurato dal tester di L0-SESSIONE, docs/lotti/LOTTO-L2-RIPRENDI.md
        # §7).
        cwd = ""
    host = socket.gethostname()

    if _e_codex(argv):
        sid = _rollout_piu_recente(cwd)
        return {"session_id": sid, "cwd": cwd, "agent": "codex", "host": host,
                "origine": "codex-rollout" if sid else "nessuna"}

    env_sid = os.environ.get("CLAUDE_CODE_SESSION_ID") or None

    if env_sid:
        # Il pid del confronto è CLAUDE_PID se c'è nell'ambiente, altrimenti
        # il ppid: misurato il 16/09/2026 che CLAUDE_PID c'è nell'app
        # desktop ma non in nessuno degli 8 processi server MCP visti su
        # questa macchina, e che per quegli 8 il ppid del server coincide
        # col pid nel nome del file di sessione (dettagli nella docstring
        # del modulo, che è la fonte: qui si ripete solo la conclusione).
        pid_confronto = os.environ.get("CLAUDE_PID") or os.getppid()
        dal_file = _file_session_id(pid_confronto)
        if dal_file and dal_file != env_sid:
            return {"session_id": dal_file, "cwd": cwd, "agent": "claude",
                    "host": host, "origine": "file"}
        return {"session_id": env_sid, "cwd": cwd, "agent": "claude",
                "host": host, "origine": "env"}

    dal_file = _file_session_id(os.getppid())
    if dal_file:
        return {"session_id": dal_file, "cwd": cwd, "agent": "claude",
                "host": host, "origine": "file"}
    return {"session_id": None, "cwd": cwd, "agent": "claude", "host": host,
            "origine": "nessuna"}
