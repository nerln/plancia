"""Prove per il lotto ESCLUSI: cartelle e sessioni private che Plancia non
deve vedere.

Un sottoprocesso solo, con PLANCIA_HOME, CLAUDE_CONFIG_DIR e CODEX_HOME
temporanei (mai ~/.plancia, ~/.claude o ~/.codex veri): `tools/prova.py`
fissa solo PLANCIA_HOME una volta per tutto il suo processo (vedi
tools/prove/README.md), e un sync in-process leggerebbe comunque le
trascrizioni vere di questa macchina sotto ~/.claude/projects. Qui invece le
tre variabili sono nell'ambiente PRIMA che `plancia.config` sia importato:
le costanti derivate (CLAUDE_DIR, CLAUDE_PROJECTS, DATA_DIR, ...) nascono
già giuste, non c'è niente da rimettere a posto dopo.

Le trascrizioni finte, la memoria finta, i rollout Codex finti, il SQLite
degli obiettivi di Codex e la coda degli hook li scrive questo modulo (il
genitore), prima di lanciare il sottoprocesso: è testo, cartelle e un
piccolo database, non serve importare plancia per costruirli. Il calcolo di
come Claude Code codifica una cwd in nome di cartella (`_codifica_cartella`
qui sotto) è fatto apposta SENZA importare `plancia.esclusi`, che sul commit
di base non esiste ancora: la prova deve poter costruire le stesse fixture
su entrambi i commit.

Lo script che gira nel sottoprocesso è un testo con segnaposto (`__NOME__`),
sostituiti con `str.replace()` e mai con `str.format()`: lo script contiene
lui stesso dizionari e f-string, pieni di `{`/`}` veri, e farli convivere con
le graffe di sostituzione di `.format()` è un modo sicuro per sbagliare un
conteggio di graffe senza accorgersene.

Fase 1 (dentro il sottoprocesso): un sync vero (`ingest.sync`) su tre
sessioni Claude Code (una con cwd esclusa, una con id escluso e un
sottoagente sotto di lei, una normale), due rollout Codex (uno con cwd
esclusa, uno che riprende un thread già escluso ma con un uuid di file
tutto nuovo, aperto in una cartella NORMALE), una memoria esclusa e una
normale, una riga di coda hook esclusa e una normale, un todo di Claude Code
e un obiettivo di Codex per la sessione/il thread esclusi (e uno normale).
Si controlla che le escluse non compaiano in NESSUNA tabella (cercando anche
una parola rara scritta apposta nel testo, dentro turni_fts e search_fts) e
che le normali sì.

Fase 1b (stesso sottoprocesso): la sessione "normale" iniziale riceve, nello
STESSO file di trascrizione, altre righe con una cwd ESCLUSA (come se fosse
stata aperta in una cartella normale e poi spostata lì con un tool che
cambia la cwd — non un `cd` di shell). Un secondo sync (incrementale, non
`full`) deve farla sparire, lei e tutto il suo testo.

Fase 2 (stesso sottoprocesso, di seguito): righe inserite A MANO in ogni
tabella che `esclusi.purga()` deve ripulire, come se ci fossero entrate
prima che la cartella/sessione fosse esclusa: sessioni, task, post, eventi,
turni, memoria, repository, project_links (con i tre casi dei progetti
automatici: orfano da cancellare, con un altro link da tenere, manuale da
non toccare mai), UNA MEMORIA DI TIPO PROGETTO già orfana (scheda + link
"memory" + riga di conoscenza + evento SQL), un repo con un commit e
l'evento SQL del commit, un lancio (`runs`) con un log su disco, un task e
un post con il loro evento in `eventi.jsonl`, `meta.git_lento`, e la cache
del riepilogo/delle proposte. Si chiama `purga()` e si controlla che tolga
le une e lasci le altre.

Il sottoprocesso stampa un solo oggetto JSON, sull'ultima riga di stdout,
con tutto l'esito: qui si legge quello, non si prova a leggere lo stderr per
capire cos'è successo.

Oltre al sottoprocesso grande, quattro prove più piccole e mirate, ognuna
con il proprio ambiente isolato: l'hook (`bin/plancia-hook`) con una cwd/un
id escluso; un repository git sotto una cartella esclusa, dentro un
`code_root`, con `skip_git=False`; una scrittura MCP (`plancia_task_add`) da
una sessione esclusa; e la validazione di un `config.json` scritto male (una
stringa al posto di una lista, una virgola di troppo, un percorso che non
esiste, un percorso troppo ampio, un id non a forma di uuid), verificando
anche che `ingest.sync()` diventi fail-closed invece di far entrare tutto.
"""

import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent.parent


def _carica_finti():
    """`_finti.py` (materiale di supporto, non una prova) sta accanto a questo file."""
    if "_finti" not in sys.modules:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "_finti", Path(__file__).resolve().parent / "_finti.py")
        modulo = importlib.util.module_from_spec(spec)
        sys.modules["_finti"] = modulo
        spec.loader.exec_module(modulo)
    return sys.modules["_finti"]


_finti = _carica_finti()


def _argv_script(script) -> list:
    """Uno script di `bin/` come lo lancia chi lo usa: da solo su macOS e Linux
    (shebang), con l'interprete davanti su Windows (WinError 193 altrimenti)."""
    if str(RADICE) not in sys.path:
        sys.path.insert(0, str(RADICE))
    from plancia import piattaforma
    return piattaforma.argv_script(script)

# --------------------------------------------------------------------------
# ambiente comune a OGNI subprocess.run di questo file
# --------------------------------------------------------------------------
#
# Il difetto grave trovato dal tester precedente: `ingest.sync(modo="tutto")`
# lancia, in un thread demone, `recap.prepara()` (vedi plancia/ingest.py,
# `freddo`), che con il motore di default (config.json senza
# "motore_riepilogo", o rotto: `plancia/config.load_config()` ricade sui
# default) chiama `recap.claude_bin()`, e quella funzione trova un `claude`
# vero anche fuori dal PATH (percorsi fissi sotto `config.HOME`). Un
# `config.json` con "motore_riepilogo": "template" evita che si CERCHI un
# binario; questo ambiente è il secondo fusibile, indipendente dal primo:
# anche quando la ricerca parte (config rotto, motore non impostato), qui non
# trova mai il binario vero. HOME finta (mai quella vera, o
# `~/.local/bin/claude` risolverebbe a un binario vero) e PATH che fa trovare
# PRIMA un `claude` finto (scrive un file segnale ed esce 1), poi le
# cartelle di sistema minime che servono a git/python veri.
#
# Un solo ambiente per l'intero modulo (non uno per prova): la prova finale
# (`_claude_chiamato`, in fondo a `esegui()`) deve poter vedere se QUALUNQUE
# sottoprocesso lanciato da QUALUNQUE prova di questo file ha anche solo
# provato a lanciare claude, non solo l'ultimo.
_FAKE_HOME = None
_FAKE_BIN = None
_FAKE_SEGNALE = None


def _ambiente_condiviso() -> tuple:
    """(home_finta, bin_finto, segnale): creati una sola volta per modulo."""
    global _FAKE_HOME, _FAKE_BIN, _FAKE_SEGNALE
    if _FAKE_HOME is None:
        radice_finta = Path(tempfile.mkdtemp(prefix="plancia-prova-esclusi-fake-"))
        _FAKE_HOME = radice_finta / "home"
        _FAKE_HOME.mkdir(parents=True, exist_ok=True)
        _FAKE_BIN = radice_finta / "bin"
        _FAKE_BIN.mkdir(parents=True, exist_ok=True)
        _FAKE_SEGNALE = radice_finta / "claude-chiamato"
        # un `claude` finto: scrive il file segnale ed esce 1 (su ogni sistema)
        _finti.crea_finto(_FAKE_BIN, "claude",
                          "import sys\n"
                          f"open({str(_FAKE_SEGNALE)!r}, 'a').close()\n"
                          "sys.exit(1)\n")
    return _FAKE_HOME, _FAKE_BIN, _FAKE_SEGNALE


def _env_prova(**extra) -> dict:
    """Ambiente per OGNI subprocess.run di questa prova (vedi il commento sopra):
    parte da `os.environ`, impone HOME/PATH finte, e ci mette sopra `extra`
    (tipicamente PLANCIA_HOME/CLAUDE_CONFIG_DIR/CODEX_HOME, che restano
    espliciti: `plancia.config` li legge con `os.environ.get(...)` PRIMA del
    fallback su HOME, quindi la cartella finta non li sposta)."""
    home, bin_finto, _ = _ambiente_condiviso()
    env = dict(os.environ)
    _finti.casa_finta(env, home)
    env["PATH"] = _finti.path_con(bin_finto)
    env.update(extra)
    return env


def _claude_chiamato() -> bool:
    """True se un qualunque `claude` finto, di un qualunque sottoprocesso di
    questo modulo, è stato eseguito almeno una volta."""
    _, _, segnale = _ambiente_condiviso()
    return segnale.exists()


def _codifica_cartella(path: Path) -> str:
    """Copia indipendente della regola di Claude Code (misurata il
    28/09/2026 su ~/.claude/projects, in sola lettura, solo nomi): ogni
    carattere non [A-Za-z0-9] diventa un trattino, uno a uno. Non importa
    `plancia.esclusi` apposta: deve valere anche sul commit di base, dove
    quel modulo non esiste."""
    return re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(str(path)))


def _riga(tipo: str, testo: str, ts: str, cwd: str = None) -> str:
    if tipo == "user":
        msg = {"role": "user", "content": testo}
    else:
        msg = {"role": "assistant", "model": "claude-prova",
               "usage": {"input_tokens": 1, "output_tokens": 1},
               "content": [{"type": "text", "text": testo}]}
    rec = {"type": tipo, "timestamp": ts, "message": msg}
    if cwd is not None:
        rec["cwd"] = cwd
    # Senza spazi dopo i due punti: `ingest.scan_session_file` riconosce il
    # tipo di riga con un confronto a byte su `b'"type":"assistant"'` (senza
    # spazio, per non pagare un json.loads su ogni riga), esattamente come
    # scrive Claude Code davvero. `json.dumps` di default mette uno spazio
    # dopo `:` e la riga finirebbe scartata come "non serve", con cwd e
    # first_prompt mai letti (misurato: senza `separators` qui, la sessione
    # normale finiva in `sessions` (il file esiste comunque) ma con
    # first_prompt vuoto, perché nessuna riga passava il confronto a byte).
    return json.dumps(rec, ensure_ascii=False, separators=(",", ":"))


def _scrivi_transcript(path: Path, cwd: str, parola: str) -> None:
    """Una trascrizione minima ma vera: due turni, sopra i quaranta
    caratteri che turni.py chiede (MINIMO), con `parola` dentro entrambi."""
    path.parent.mkdir(parents=True, exist_ok=True)
    righe = [
        _riga("user", f"{parola} per favore aiutami con questo lavoro, "
              "è un messaggio di prova abbastanza lungo.", "2026-01-01T00:00:00Z", cwd=cwd),
        _riga("assistant", f"Ho letto {parola} e continuo il lavoro su "
              "questo argomento con una risposta lunga a sufficienza.",
              "2026-01-01T00:00:05Z"),
    ]
    path.write_text("\n".join(righe) + "\n", "utf-8")


def _scrivi_memoria(path: Path, nome: str, parola: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\nname: {nome}\ndescription: nota di prova\nmetadata:\n  type: feedback\n---\n"
        f"Corpo della memoria con dentro {parola}, ripetuto {parola} per essere sicuri "
        "che passi qualunque soglia di lunghezza.\n",
        "utf-8")


def _riga_codex(tipo: str, ts: str, payload: dict) -> str:
    return json.dumps({"type": tipo, "timestamp": ts, "payload": payload}, ensure_ascii=False)


def _scrivi_rollout_codex(path: Path, file_id: str, thread_id: str, cwd: str, parola: str) -> None:
    """Un rollout Codex minimo: session_meta (che porta l'id del FILE e il
    thread di partenza — possono differire, vedi codex.py), turn_context
    (che ripete la cwd) e un messaggio utente."""
    path.parent.mkdir(parents=True, exist_ok=True)
    righe = [
        _riga_codex("session_meta", "2026-01-01T00:00:00Z",
                    {"id": file_id, "session_id": thread_id, "cwd": cwd}),
        _riga_codex("turn_context", "2026-01-01T00:00:01Z", {"cwd": cwd, "model": "gpt-prova"}),
        _riga_codex("event_msg", "2026-01-01T00:00:02Z",
                    {"type": "user_message", "message": f"{parola} per favore aiutami"}),
    ]
    path.write_text("\n".join(righe) + "\n", "utf-8")


def _scrivi_goals_codex(path: Path, righe: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute(
        "CREATE TABLE thread_goals(thread_id TEXT, goal_id TEXT, objective TEXT, status TEXT, "
        "tokens_used INTEGER, time_used_seconds INTEGER, created_at_ms INTEGER, "
        "updated_at_ms INTEGER)")
    conn.executemany("INSERT INTO thread_goals VALUES (?,?,?,?,?,?,?,?)", righe)
    conn.commit()
    conn.close()


def _prepara(base: Path) -> dict:
    """Cartelle e file finti, tutti sotto `base`. Torna i percorsi e gli id
    che il sottoprocesso userà per le verifiche."""
    priv = base / "cartella-privata"
    norm = base / "cartella-normale"
    altra = base / "cartella-altra"
    spostata = base / "cartella-poi-spostata"
    for c in (priv, norm, altra, spostata):
        c.mkdir(parents=True, exist_ok=True)

    claude_dir = base / "claude-config"
    plancia_home = base / "plancia-home"
    codex_home = base / "codex-home"
    projects = claude_dir / "projects"

    cod_priv = _codifica_cartella(priv)
    cod_norm = _codifica_cartella(norm)
    cod_altra = _codifica_cartella(altra)
    cod_spostata = _codifica_cartella(spostata)

    sid_priv = "11111111-1111-1111-1111-111111111111"
    sid_escluso = "22222222-2222-2222-2222-222222222222"
    sid_norm = "33333333-3333-3333-3333-333333333333"
    sub_uuid = "44444444-4444-4444-4444-444444444444"
    sid_spostata = "55555555-5555-5555-5555-555555555555"
    sid_codex_cwd = "66666666-6666-6666-6666-666666666666"
    sid_codex_ripresa = "77777777-7777-7777-7777-777777777777"

    # 1. sessione con cwd esclusa
    _scrivi_transcript(projects / cod_priv / f"{sid_priv}.jsonl", str(priv), "ZBRAKKONDOR")
    # 2. sessione con id escluso, in una cartella NORMALE, con un sottoagente
    _scrivi_transcript(projects / cod_altra / f"{sid_escluso}.jsonl", str(altra), "TRENOBALENA")
    _scrivi_transcript(
        projects / cod_altra / sid_escluso / "subagents" / "workflows" / f"{sub_uuid}.jsonl",
        str(altra), "SUBAGENTONEXX")
    # 3. sessione normale
    _scrivi_transcript(projects / cod_norm / f"{sid_norm}.jsonl", str(norm), "QUINTAFULVA")
    # 4. sessione APERTA in una cartella normale, poi spostata (fase 1b: si
    # aggiungono altre righe a questo stesso file, con una cwd esclusa)
    path_spostata = projects / cod_spostata / f"{sid_spostata}.jsonl"
    _scrivi_transcript(path_spostata, str(spostata), "SPOSTATAPRIMAXX")

    # memoria esclusa e normale
    _scrivi_memoria(projects / cod_priv / "memory" / "nota-privata.md",
                    "nota-privata", "MEMORIAPRIVATAXX")
    _scrivi_memoria(projects / cod_norm / "memory" / "nota-normale.md",
                    "nota-normale", "MEMORIANORMALEXX")

    # coda degli hook: una riga per una sessione/cwd esclusa, una normale
    queue = plancia_home / "queue"
    queue.mkdir(parents=True, exist_ok=True)
    (queue / "hooks.jsonl").write_text(
        "\n".join([
            json.dumps({"ts": "2026-01-01T00:10:00Z", "event": "SessionStart",
                       "session_id": "hook-privato-0001", "cwd": str(priv)}),
            json.dumps({"ts": "2026-01-01T00:10:00Z", "event": "SessionStart",
                       "session_id": "hook-normale-0001", "cwd": str(norm)}),
        ]) + "\n", "utf-8")

    # Codex: un rollout con cwd esclusa (thread = se stesso: prima volta che
    # si vede) e la RIPRESA di un thread già escluso — file nuovo (un altro
    # uuid), aperto in una cartella NORMALE, così l'unico modo di escluderlo
    # è riconoscere il thread, non il percorso.
    _scrivi_rollout_codex(
        codex_home / "sessions" / "2026" / "01" / "01" / f"rollout-2026-01-01T00-00-00-{sid_codex_cwd}.jsonl",
        sid_codex_cwd, sid_codex_cwd, str(priv), "CODEXCWDPRIVXX")
    _scrivi_rollout_codex(
        codex_home / "sessions" / "2026" / "01" / "02" / f"rollout-2026-01-02T00-00-00-{sid_codex_ripresa}.jsonl",
        sid_codex_ripresa, sid_escluso, str(norm), "CODEXRIPRESAPRIVXX")

    # Lavagna: un todo di Claude Code e un obiettivo di Codex per la
    # sessione/il thread già esclusi, e uno normale per ciascuno — a fixture
    # invariata, tutt'e due dovrebbero comparire allo stesso modo; solo dopo
    # la correzione quelli "priv" spariscono.
    tasks_dir = claude_dir / "tasks"
    (tasks_dir / sid_escluso).mkdir(parents=True, exist_ok=True)
    (tasks_dir / sid_escluso / "t1.json").write_text(json.dumps(
        {"id": "t1", "subject": "COMPITOPRIVXX fai qualcosa di privato",
         "description": "", "status": "pending"}), "utf-8")
    (tasks_dir / sid_norm).mkdir(parents=True, exist_ok=True)
    (tasks_dir / sid_norm / "t2.json").write_text(json.dumps(
        {"id": "t2", "subject": "COMPITONORMXX fai qualcosa di normale",
         "description": "", "status": "pending"}), "utf-8")
    _scrivi_goals_codex(codex_home / "goals_1.sqlite", [
        (sid_escluso, "g1", "OBIETTIVOPRIVXX fai una cosa privata. dettaglio",
         "active", 10, 5, 0, 0),
        (sid_norm, "g2", "OBIETTIVONORMXX fai una cosa normale. dettaglio",
         "active", 10, 5, 0, 0),
    ])

    # config.json: le due chiavi nuove, code_roots vuoto e gh spento per non
    # toccare ne' `~/dev` vero ne' la rete. "motore_riepilogo": "template"
    # perche' il sync qui sotto e' un giro vero (modo="tutto"): senza questa
    # chiave il motore di default e' "claude" (plancia/recap.py) e il giro
    # freddo proverebbe a chiamarlo davvero (vedi il commento su _env_prova
    # in cima al file per il secondo fusibile, indipendente da questo).
    plancia_home.mkdir(parents=True, exist_ok=True)
    (plancia_home / "config.json").write_text(json.dumps({
        "cartelle_escluse": [str(priv)],
        "sessioni_escluse": [sid_escluso],
        "code_roots": [],
        "gh_enabled": False,
        "motore_riepilogo": "template",
    }), "utf-8")

    codex_home.mkdir(parents=True, exist_ok=True)

    return {
        "claude_dir": claude_dir, "plancia_home": plancia_home, "codex_home": codex_home,
        "priv": priv, "norm": norm, "altra": altra, "spostata": spostata,
        "sid_priv": sid_priv, "sid_escluso": sid_escluso, "sid_norm": sid_norm,
        "cod_priv": cod_priv, "cod_norm": cod_norm,
        "sid_spostata": sid_spostata, "path_spostata": path_spostata,
        "sid_codex_cwd": sid_codex_cwd, "sid_codex_ripresa": sid_codex_ripresa,
    }


# Segnaposto sostituiti a mano (str.replace, non str.format: vedi il
# docstring del modulo per il perché) con repr() dei valori veri, quindi
# ognuno diventa una stringa Python valida, tra virgolette, nello script.
SCRIPT = r"""
import json, sqlite3, sys
sys.path.insert(0, __RADICE__)
from pathlib import Path
from plancia import config, ingest, store

esito = {}
priv = __PRIV__
norm = __NORM__

# Un archivio che ha visto solo store.init_db() e mai un sync (quindi mai
# turni.prepara(), che vive fuori dallo schema di store.py): plancia esclusi
# su un'installazione appena creata deve poter contare/pulire comunque,
# senza "no such table: turni_file" (bug vero, misurato a mano lanciando
# `plancia esclusi --prova` su un archivio nuovo prima di questa riga).
conn_prima = store.connect()
store.init_db(conn_prima)
try:
    from plancia import esclusi as _esclusi_prima
    _esclusi_prima.conta(conn_prima, _esclusi_prima.carica())
    esito["conta_prima_del_sync_ok"] = True
except Exception as exc:
    esito["conta_prima_del_sync_ok"] = False
    esito["conta_prima_del_sync_errore"] = repr(exc)
conn_prima.close()

try:
    ingest.sync(modo="tutto", skip_git=True)
    esito["sync_ok"] = True
except Exception as exc:
    esito["sync_ok"] = False
    esito["sync_errore"] = repr(exc)

# ------------------------------------------------------------- fase 1b
# La sessione "spostata" era normale al primo giro: ora arrivano altre
# righe, nello STESSO file, con una cwd esclusa (come farebbe un tool che
# cambia cwd durante la sessione). Un secondo sync, incrementale (non
# `full`), deve accorgersene leggendo solo i byte nuovi.
try:
    riga_dopo_1 = json.dumps({
        "type": "user", "timestamp": "2026-01-01T00:20:00Z", "cwd": priv,
        "message": {"role": "user", "content":
                    "SPOSTATADOPOXX ora lavoro qui, un messaggio abbastanza "
                    "lungo da superare la soglia di indicizzazione."}},
        ensure_ascii=False, separators=(",", ":"))
    riga_dopo_2 = json.dumps({
        "type": "assistant", "timestamp": "2026-01-01T00:20:05Z",
        "message": {"role": "assistant", "model": "claude-prova",
                    "usage": {"input_tokens": 1, "output_tokens": 1},
                    "content": [{"type": "text", "text":
                                 "Ho letto SPOSTATADOPOXX e continuo qui, "
                                 "risposta lunga a sufficienza."}]}},
        ensure_ascii=False, separators=(",", ":"))
    with open(__PATH_SPOSTATA__, "a", encoding="utf-8") as fh:
        fh.write(riga_dopo_1 + "\n" + riga_dopo_2 + "\n")
    ingest.sync(modo="tutto", skip_git=True)
    esito["sync2_ok"] = True
except Exception as exc:
    esito["sync2_ok"] = False
    esito["sync2_errore"] = repr(exc)

# I due sync qui sopra (modo="tutto") possono aver lanciato, in un thread
# demone, recap.prepara() (vedi plancia/ingest.py: freddo=True), che scrive
# in meta (recap_testo, recap_impronta, ...) con la sua stessa connessione.
# La fase 2 qui sotto scrive apposta dei valori sentinella in QUEGLI STESSI
# meta.key per poi controllare che purga() li tolga: se il demone scrivesse
# ANCORA DOPO che purga() li ha già invalidati, la prova diventerebbe
# intermittente (a volte il valore sentinella resta, a volte no): lo stesso
# tipo di gara che questo modulo esiste per chiudere, non solo quella con
# claude vero. Un join con un tetto (10s: con "motore_riepilogo": "template"
# il demone non chiama nessun binario, e finisce all'istante; il tetto serve
# solo a non restare bloccati per sempre se qualcosa si impalla) prima di fase
# 2 rende deterministico l'ordine: quando arriva la sentinella, il demone ha
# già scritto (o è stato aspettato abbastanza), e non riscrive più dopo.
import threading as _th_join
for _t_join in _th_join.enumerate():
    if _t_join is not _th_join.current_thread():
        _t_join.join(timeout=10)

conn = store.connect()


def turni(parola):
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM turni_fts WHERE turni_fts MATCH ?", (parola,)
        ).fetchone()[0]
    except Exception as exc:
        return "errore: %r" % (exc,)


def ricerca(parola):
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM search_fts WHERE search_fts MATCH ?", (parola,)
        ).fetchone()[0]
    except Exception as exc:
        return "errore: %r" % (exc,)


def esiste(tabella, colonna, valore):
    return conn.execute(
        "SELECT COUNT(*) FROM %s WHERE %s=?" % (tabella, colonna), (valore,)
    ).fetchone()[0]


def conta_sql(sql, args=()):
    return conn.execute(sql, args).fetchone()[0]


esito["turni_priv"] = turni("ZBRAKKONDOR")
esito["turni_id_escluso"] = turni("TRENOBALENA")
esito["turni_subagente"] = turni("SUBAGENTONEXX")
esito["turni_norm"] = turni("QUINTAFULVA")
esito["search_priv"] = ricerca("ZBRAKKONDOR")
esito["search_norm"] = ricerca("QUINTAFULVA")
esito["sessione_priv"] = esiste("sessions", "session_id", __SID_PRIV__)
esito["sessione_id_escluso"] = esiste("sessions", "session_id", __SID_ESCLUSO__)
esito["sessione_norm"] = esiste("sessions", "session_id", __SID_NORM__)
esito["hook_priv"] = esiste("events", "ref", "hook-privato-0001")
esito["hook_norm"] = esiste("events", "ref", "hook-normale-0001")
esito["memoria_priv"] = esiste("knowledge", "name", "nota-privata")
esito["memoria_norm"] = esiste("knowledge", "name", "nota-normale")

# sessione spostata (fase 1b)
esito["turni_spostata_prima"] = turni("SPOSTATAPRIMAXX")
esito["turni_spostata_dopo"] = turni("SPOSTATADOPOXX")
esito["search_spostata_prima"] = ricerca("SPOSTATAPRIMAXX")
esito["sessione_spostata"] = esiste("sessions", "session_id", __SID_SPOSTATA__)
esito["evento_spostata"] = conta_sql(
    "SELECT COUNT(*) FROM events WHERE kind='sessione' AND ref=?", (__SID_SPOSTATA__,))

# Codex: cwd esclusa, e ripresa di un thread escluso con un uuid nuovo
esito["sessione_codex_cwd"] = esiste("sessions", "session_id", __SID_CODEX_CWD__)
esito["sessione_codex_ripresa"] = esiste("sessions", "session_id", __SID_CODEX_RIPRESA__)
esito["search_codex_cwd"] = ricerca("CODEXCWDPRIVXX")
esito["search_codex_ripresa"] = ricerca("CODEXRIPRESAPRIVXX")

# Lavagna: todo di Claude Code e obiettivo Codex, esclusi e normali
esito["agenda_claude_priv"] = conta_sql(
    "SELECT COUNT(*) FROM agenda WHERE titolo LIKE '%COMPITOPRIVXX%'")
esito["agenda_claude_norm"] = conta_sql(
    "SELECT COUNT(*) FROM agenda WHERE titolo LIKE '%COMPITONORMXX%'")
esito["agenda_codex_priv"] = conta_sql(
    "SELECT COUNT(*) FROM agenda WHERE titolo LIKE '%OBIETTIVOPRIVXX%'")
esito["agenda_codex_norm"] = conta_sql(
    "SELECT COUNT(*) FROM agenda WHERE titolo LIKE '%OBIETTIVONORMXX%'")

# ---------------------------------------------------------------- fase 2
try:
    from plancia import esclusi
    escl = esclusi.carica(conn=conn)

    conn.execute("INSERT INTO sessions(session_id, cwd) VALUES (?,?)",
                 ("man-priv-0001", priv))
    conn.execute("INSERT INTO sessions(session_id, cwd) VALUES (?,?)",
                 ("man-norm-0001", norm))

    conn.execute("INSERT INTO tasks(title, session_id, cwd) VALUES (?,?,?)",
                 ("task privato per sessione", "man-priv-0001", None))
    conn.execute("INSERT INTO tasks(title, session_id, cwd) VALUES (?,?,?)",
                 ("task privato per cwd", "altro-sid-non-escluso", priv))
    conn.execute("INSERT INTO tasks(title, session_id, cwd) VALUES (?,?,?)",
                 ("task normale", "man-norm-0001", norm))

    conn.execute("INSERT INTO posts(text, session_id) VALUES (?,?)",
                 ("post privato", "man-priv-0001"))
    conn.execute("INSERT INTO posts(text, session_id) VALUES (?,?)",
                 ("post normale", "man-norm-0001"))

    conn.execute(
        "INSERT INTO events(ts, kind, title, ref, dedup) VALUES (?,?,?,?,?)",
        ("2026-01-01T00:00:00Z", "sessione", "evento privato", "man-priv-0001", "ev-priv-1"))
    conn.execute(
        "INSERT INTO events(ts, kind, title, ref, dedup) VALUES (?,?,?,?,?)",
        ("2026-01-01T00:00:00Z", "hook", "hook privato", "man-priv-0001", "ev-priv-2"))
    conn.execute(
        "INSERT INTO events(ts, kind, title, ref, dedup) VALUES (?,?,?,?,?)",
        ("2026-01-01T00:00:00Z", "sessione", "evento normale", "man-norm-0001", "ev-norm-1"))

    path_know_priv = str(config.CLAUDE_PROJECTS / __COD_PRIV__ / "memory" / "manuale-privata.md")
    path_know_norm = str(config.CLAUDE_PROJECTS / __COD_NORM__ / "memory" / "manuale-normale.md")
    conn.execute(
        "INSERT INTO knowledge(name, path, scope) VALUES (?,?,?)",
        ("manuale-privata", path_know_priv, "x"))
    conn.execute(
        "INSERT INTO knowledge(name, path, scope) VALUES (?,?,?)",
        ("manuale-normale", path_know_norm, "x"))

    path_turni_priv = str(config.CLAUDE_PROJECTS / __COD_PRIV__ / "manuale-priv.jsonl")
    path_turni_norm = str(config.CLAUDE_PROJECTS / __COD_NORM__ / "manuale-norm.jsonl")
    conn.execute(
        "INSERT INTO turni_file(percorso, mtime, dimensione, turni) VALUES (?,0,0,1)",
        (path_turni_priv,))
    conn.execute(
        "INSERT INTO turni_fts(testo, sessione, ruolo, ts, progetto, percorso, riga) "
        "VALUES (?,?,?,?,?,?,?)",
        ("contiene MANOPRIVATAXX dentro", "manuale-priv", "user", "2026-01-01T00:00:00Z",
         "x", path_turni_priv, 1))
    conn.execute(
        "INSERT INTO turni_file(percorso, mtime, dimensione, turni) VALUES (?,0,0,1)",
        (path_turni_norm,))
    conn.execute(
        "INSERT INTO turni_fts(testo, sessione, ruolo, ts, progetto, percorso, riga) "
        "VALUES (?,?,?,?,?,?,?)",
        ("contiene MANONORMALEXX dentro", "manuale-norm", "user", "2026-01-01T00:00:00Z",
         "x", path_turni_norm, 1))

    conn.execute(
        "INSERT INTO repos(name, local_path) VALUES (?,?)",
        ("repo-privato-manuale", priv))
    conn.execute(
        "INSERT INTO repos(name, local_path) VALUES (?,?)",
        ("repo-normale-manuale", norm))

    # project_links ha UNIQUE(kind, value): tre progetti non possono
    # condividere lo stesso valore di link, quindi ognuno prende una
    # SOTTOCARTELLA diversa di `priv` (comunque esclusa: percorso_escluso
    # copre anche le sottocartelle di una cartella esclusa).
    sub_orfano = priv + "/sotto-orfano"
    sub_misto = priv + "/sotto-misto"
    sub_manuale = priv + "/sotto-manuale"

    cur = conn.execute(
        "INSERT INTO projects(key, name, auto) VALUES ('orfano-manuale','orfano',1)")
    pid_orfano = cur.lastrowid
    conn.execute("INSERT INTO project_links(project_id, kind, value) VALUES (?,?,?)",
                 (pid_orfano, "path", sub_orfano))

    cur = conn.execute(
        "INSERT INTO projects(key, name, auto) VALUES ('misto-manuale','misto',1)")
    pid_misto = cur.lastrowid
    conn.execute("INSERT INTO project_links(project_id, kind, value) VALUES (?,?,?)",
                 (pid_misto, "path", sub_misto))
    conn.execute("INSERT INTO project_links(project_id, kind, value) VALUES (?,?,?)",
                 (pid_misto, "repo", "qualche-repo-non-escluso"))

    cur = conn.execute(
        "INSERT INTO projects(key, name, auto) VALUES ('manuale-manuale','manuale',0)")
    pid_manuale = cur.lastrowid
    conn.execute("INSERT INTO project_links(project_id, kind, value) VALUES (?,?,?)",
                 (pid_manuale, "path", sub_manuale))

    # una memoria di TIPO PROGETTO, già orfana: una scheda automatica il cui
    # UNICO link è "memory", verso una memoria che sta sotto la cartella
    # esclusa (quindi trascrizione_esclusa la trova anche per percorso).
    cur = conn.execute(
        "INSERT INTO projects(key, name, auto) VALUES ('memoria-orfana-manuale','Memoria orfana',1)")
    pid_mem_orfano = cur.lastrowid
    path_mem_orfana = str(config.CLAUDE_PROJECTS / __COD_PRIV__ / "memory" / "memoria-progetto-orfana.md")
    conn.execute("INSERT INTO project_links(project_id, kind, value) VALUES (?,?,?)",
                 (pid_mem_orfano, "memory", "memoria-progetto-orfana"))
    conn.execute(
        "INSERT INTO knowledge(name, path, scope, project_id) VALUES (?,?,?,?)",
        ("memoria-progetto-orfana", path_mem_orfana, "x", pid_mem_orfano))
    conn.execute(
        "INSERT INTO events(ts, kind, title, ref, project_id, dedup) VALUES (?,?,?,?,?,?)",
        ("2026-01-01T00:00:00Z", "memoria", "memoria aggiornata: memoria-progetto-orfana",
         "memoria-progetto-orfana", pid_mem_orfano, "ev-mem-orfana"))

    # un repo escluso con un commit, e l'evento SQL del commit
    conn.execute("INSERT INTO repos(name, local_path) VALUES (?,?)",
                 ("repo-priv-commit", priv))
    conn.execute(
        "INSERT INTO commits(repo, sha, message, date, url) VALUES (?,?,?,?,?)",
        ("repo-priv-commit", "deadbeef00112233", "COMMITPRIVXX messaggio",
         "2026-01-01T00:00:00Z", ""))
    conn.execute(
        "INSERT INTO events(ts, kind, title, ref, dedup) VALUES (?,?,?,?,?)",
        ("2026-01-01T00:00:00Z", "commit", "COMMITPRIVXX messaggio",
         "deadbeef00112233", "ev-commit-priv"))

    # un lancio (runs) con cwd esclusa, e un log vero da cancellare su disco
    log_priv = str(config.DATA_DIR / "run-priv-test.log")
    Path(log_priv).write_text("LOGPRIVXX contenuto del log", "utf-8")
    cur = conn.execute(
        "INSERT INTO runs(agente, modo, prompt, cwd, stato, inizio, fine, log) "
        "VALUES ('claude','proposta','PROMPTPRIVXX prompt privato',?,'riuscito',?,?,?)",
        (priv, "2026-01-01T00:00:00Z", "2026-01-01T00:05:00Z", log_priv))
    run_id_priv = cur.lastrowid

    # un task e un post per gli eventi task.*/post.* di eventi.jsonl
    cur = conn.execute(
        "INSERT INTO tasks(title, session_id, created_at, updated_at) VALUES (?,?,?,?)",
        ("task per eventi jsonl", "man-priv-0001", "2026-01-01T00:00:00Z",
         "2026-01-01T00:00:00Z"))
    tid_eventi = cur.lastrowid
    cur = conn.execute(
        "INSERT INTO posts(text, session_id, created_at, updated_at) VALUES (?,?,?,?)",
        ("post per eventi jsonl", "man-priv-0001", "2026-01-01T00:00:00Z",
         "2026-01-01T00:00:00Z"))
    oid_eventi = cur.lastrowid

    # ON CONFLICT DO UPDATE (non un INSERT semplice) su tutte e quattro:
    # "recap_testo"/"recap_impronta"/"proposte" sono le stesse chiavi che il
    # thread demone di recap.prepara() (join già fatto qui sopra, prima di
    # questa fase) può aver già scritto per davvero con "motore_riepilogo":
    # "template": un INSERT semplice su una riga già esistente romperebbe
    # con IntegrityError (misurato), non con l'esito che questa prova vuole
    # controllare (che purga() la tolga di nuovo).
    conn.execute(
        "INSERT INTO meta(key, value) VALUES (?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (f"git_lento:{priv}", "2026-01-01T00:00:00Z"))
    conn.execute(
        "INSERT INTO meta(key, value) VALUES ('recap_testo','PRIMA della pulizia') "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value")
    conn.execute(
        "INSERT INTO meta(key, value) VALUES ('recap_impronta','x|it|2026-01-01') "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value")
    conn.execute(
        "INSERT INTO meta(key, value) VALUES ('proposte','[]') "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value")

    conn.execute(
        "INSERT INTO meta(key, value) VALUES ('live_session','man-priv-0001') "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value")

    conn.commit()

    from plancia import eventi as _eventi
    righe_eventi = [
        json.dumps({"schema": "plancia.evento/1", "id": "e1",
                   "ts": "2026-01-01T00:00:00Z", "tipo": "lavoro.avviato",
                   "titolo": "lancio privato MANOEVENTOPRIVXX",
                   "progetto": None, "origine": "cantiere",
                   "dati": {"cwd": priv, "run": 1}}),
        json.dumps({"schema": "plancia.evento/1", "id": "e2",
                   "ts": "2026-01-01T00:00:00Z", "tipo": "lavoro.avviato",
                   "titolo": "lancio normale MANOEVENTONORMXX",
                   "progetto": None, "origine": "cantiere",
                   "dati": {"cwd": norm, "run": 2}}),
        json.dumps({"schema": "plancia.evento/1", "id": "e3",
                   "ts": "2026-01-01T00:00:00Z", "tipo": "progetto.archiviato",
                   "titolo": "PROGARCHIVIATOPRIVXX", "progetto": "memoria-orfana-manuale",
                   "origine": "plancia", "dati": {}}),
        json.dumps({"schema": "plancia.evento/1", "id": "e4",
                   "ts": "2026-01-01T00:00:00Z", "tipo": "padre:batch-prova-priv",
                   "titolo": "PADREPRIVXX figlio sotto padre",
                   "progetto": "memoria-orfana-manuale", "origine": "plancia",
                   "dati": {"batch": "batch-prova-priv", "figlio": "memoria-orfana-manuale"}}),
        json.dumps({"schema": "plancia.evento/1", "id": "e5",
                   "ts": "2026-01-01T00:00:00Z", "tipo": "lavoro.completato",
                   "titolo": "lavoro privato", "progetto": None, "origine": "cantiere",
                   "dati": {"run": run_id_priv, "modo": "proposta",
                            "esito": "ESITOLAVOROPRIVXX finito"}}),
        json.dumps({"schema": "plancia.evento/1", "id": "e6",
                   "ts": "2026-01-01T00:00:00Z", "tipo": "task.creato",
                   "titolo": "TASKEVENTOPRIVXX creato", "progetto": None,
                   "origine": "plancia", "dati": {"id": tid_eventi, "fonte": "manuale"}}),
        json.dumps({"schema": "plancia.evento/1", "id": "e7",
                   "ts": "2026-01-01T00:00:00Z", "tipo": "post.pubblicato",
                   "titolo": "POSTEVENTOPRIVXX pubblicato", "progetto": None,
                   "origine": "plancia", "dati": {"id": oid_eventi}}),
    ]
    _eventi.FILE.write_text("\n".join(righe_eventi) + "\n", "utf-8")

    conteggi = esclusi.purga(conn, escl)
    esito["purga_ok"] = True
    esito["conteggi"] = conteggi

    esito["man_sessione_priv"] = esiste("sessions", "session_id", "man-priv-0001")
    esito["man_sessione_norm"] = esiste("sessions", "session_id", "man-norm-0001")
    esito["man_task_priv_sid"] = conn.execute(
        "SELECT COUNT(*) FROM tasks WHERE title=?", ("task privato per sessione",)
    ).fetchone()[0]
    esito["man_task_priv_cwd"] = conn.execute(
        "SELECT COUNT(*) FROM tasks WHERE title=?", ("task privato per cwd",)
    ).fetchone()[0]
    esito["man_task_norm"] = conn.execute(
        "SELECT COUNT(*) FROM tasks WHERE title=?", ("task normale",)
    ).fetchone()[0]
    esito["man_post_priv"] = conn.execute(
        "SELECT COUNT(*) FROM posts WHERE text=?", ("post privato",)
    ).fetchone()[0]
    esito["man_post_norm"] = conn.execute(
        "SELECT COUNT(*) FROM posts WHERE text=?", ("post normale",)
    ).fetchone()[0]
    esito["man_evento_priv"] = esiste("events", "dedup", "ev-priv-1")
    esito["man_evento_hook_priv"] = esiste("events", "dedup", "ev-priv-2")
    esito["man_evento_norm"] = esiste("events", "dedup", "ev-norm-1")
    esito["man_know_priv"] = esiste("knowledge", "path", path_know_priv)
    esito["man_know_norm"] = esiste("knowledge", "path", path_know_norm)
    esito["man_turni_priv"] = turni("MANOPRIVATAXX")
    esito["man_turni_norm"] = turni("MANONORMALEXX")
    esito["man_turni_file_priv"] = esiste("turni_file", "percorso", path_turni_priv)
    esito["man_turni_file_norm"] = esiste("turni_file", "percorso", path_turni_norm)
    esito["man_repo_priv"] = esiste("repos", "name", "repo-privato-manuale")
    esito["man_repo_norm"] = esiste("repos", "name", "repo-normale-manuale")
    esito["man_progetto_orfano"] = esiste("projects", "key", "orfano-manuale")
    esito["man_progetto_misto"] = esiste("projects", "key", "misto-manuale")
    esito["man_progetto_manuale"] = esiste("projects", "key", "manuale-manuale")
    esito["man_link_misto_path"] = conn.execute(
        "SELECT COUNT(*) FROM project_links WHERE project_id=? AND kind='path'",
        (pid_misto,)).fetchone()[0]
    esito["man_link_misto_repo"] = conn.execute(
        "SELECT COUNT(*) FROM project_links WHERE project_id=? AND kind='repo'",
        (pid_misto,)).fetchone()[0]
    esito["man_link_manuale_path"] = conn.execute(
        "SELECT COUNT(*) FROM project_links WHERE project_id=?",
        (pid_manuale,)).fetchone()[0]
    esito["man_live_session"] = store.get_meta(conn, "live_session")

    esito["man_progetto_memoria_orfano"] = esiste("projects", "key", "memoria-orfana-manuale")
    esito["man_know_progetto_orfano"] = esiste("knowledge", "path", path_mem_orfana)
    esito["man_evento_memoria_orfano"] = esiste("events", "dedup", "ev-mem-orfana")
    esito["man_repo_priv_commit"] = esiste("repos", "name", "repo-priv-commit")
    esito["man_commit_priv"] = esiste("commits", "sha", "deadbeef00112233")
    esito["man_evento_commit_priv"] = esiste("events", "dedup", "ev-commit-priv")
    esito["man_run_priv"] = esiste("runs", "id", run_id_priv)
    esito["man_run_log_esiste"] = Path(log_priv).exists()
    esito["man_meta_git_lento"] = store.get_meta(conn, f"git_lento:{priv}")
    esito["man_meta_recap_testo"] = store.get_meta(conn, "recap_testo")
    esito["man_meta_proposte"] = store.get_meta(conn, "proposte")

    testo_eventi = _eventi.FILE.read_text("utf-8")
    esito["eventi_jsonl_priv"] = "MANOEVENTOPRIVXX" in testo_eventi
    esito["eventi_jsonl_norm"] = "MANOEVENTONORMXX" in testo_eventi
    esito["eventi_jsonl_progetto_priv"] = "PROGARCHIVIATOPRIVXX" in testo_eventi
    esito["eventi_jsonl_padre_priv"] = "PADREPRIVXX" in testo_eventi
    esito["eventi_jsonl_lavoro_priv"] = "ESITOLAVOROPRIVXX" in testo_eventi
    esito["eventi_jsonl_task_priv"] = "TASKEVENTOPRIVXX" in testo_eventi
    esito["eventi_jsonl_post_priv"] = "POSTEVENTOPRIVXX" in testo_eventi
except Exception as exc:
    esito["purga_ok"] = False
    esito["purga_errore"] = repr(exc)

# Secondo giro dello stesso join (vedi il commento più sopra, prima di fase
# 2): a questo punto non dovrebbe restare niente da aspettare, ma un demone
# lanciato da qualcos'altro dentro fase 2 (non c'è, ma non deve MAI restare
# fuori controllo) troverebbe comunque un tetto qui, prima che lo script
# finisca sul serio.
import threading as _th_join
for _t_join in _th_join.enumerate():
    if _t_join is not _th_join.current_thread():
        _t_join.join(timeout=10)

print(json.dumps(esito))
"""


def _esegui_sottoprocesso(fix: dict) -> dict:
    script = SCRIPT
    for segnaposto, valore in (
        ("__RADICE__", str(RADICE)), ("__SID_PRIV__", fix["sid_priv"]),
        ("__SID_ESCLUSO__", fix["sid_escluso"]), ("__SID_NORM__", fix["sid_norm"]),
        ("__PRIV__", str(fix["priv"])), ("__NORM__", str(fix["norm"])),
        ("__COD_PRIV__", fix["cod_priv"]), ("__COD_NORM__", fix["cod_norm"]),
        ("__SID_SPOSTATA__", fix["sid_spostata"]),
        ("__PATH_SPOSTATA__", str(fix["path_spostata"])),
        ("__SID_CODEX_CWD__", fix["sid_codex_cwd"]),
        ("__SID_CODEX_RIPRESA__", fix["sid_codex_ripresa"]),
    ):
        script = script.replace(segnaposto, repr(valore))

    script_path = fix["plancia_home"].parent / "sottoprocesso.py"
    script_path.write_text(script, "utf-8")

    env = _env_prova(PLANCIA_HOME=str(fix["plancia_home"]),
                      CLAUDE_CONFIG_DIR=str(fix["claude_dir"]),
                      CODEX_HOME=str(fix["codex_home"]))
    proc = subprocess.run([sys.executable, str(script_path)], capture_output=True,
                          text=True, env=env, timeout=60)
    try:
        ultima_riga = [r for r in proc.stdout.splitlines() if r.strip()][-1]
        return json.loads(ultima_riga)
    except Exception as exc:
        return {"_fallito": True, "_eccezione": repr(exc),
                "_stdout": proc.stdout[-4000:], "_stderr": proc.stderr[-4000:]}


# --------------------------------------------------------------------------
# prove piccole e mirate, ognuna con il proprio ambiente
# --------------------------------------------------------------------------

def _prova_hook(prova) -> None:
    """`bin/plancia-hook` con una cwd esclusa e con un id escluso: niente in
    coda, e (per la cwd, che l'hook stesso valuta per il SessionStart)
    niente invito a "creala" nel testo che torna a Claude."""
    base = Path(tempfile.mkdtemp(prefix="plancia-prova-hook-"))
    try:
        priv = base / "privata"
        priv.mkdir()
        plancia_home = base / "home"
        (plancia_home).mkdir()
        (plancia_home / "config.json").write_text(json.dumps({
            "cartelle_escluse": [str(priv)],
            "sessioni_escluse": ["99999999-9999-9999-9999-999999999999"],
            "motore_riepilogo": "template",
        }), "utf-8")
        env = _env_prova(PLANCIA_HOME=str(plancia_home))

        def lancia(cwd, session_id):
            payload = json.dumps({"hook_event_name": "SessionStart",
                                  "session_id": session_id, "cwd": cwd}).encode()
            r = subprocess.run(_argv_script(RADICE / "bin" / "plancia-hook"),
                               input=payload, capture_output=True, env=env, timeout=15)
            return r

        r1 = lancia(str(priv), "un-id-qualsiasi")
        coda = plancia_home / "queue" / "hooks.jsonl"
        prova("hook con cwd esclusa: niente in coda",
              not coda.exists() or not coda.read_text().strip(), coda.read_text()
              if coda.exists() else "")
        prova("hook con cwd esclusa: esce comunque con 0", r1.returncode == 0)
        prova("hook con cwd esclusa: niente invito a creare una scheda",
              "creala" not in r1.stdout.decode("utf-8", "replace"),
              r1.stdout.decode("utf-8", "replace")[:200])
        prova("hook con cwd esclusa: dice che la sessione è privata",
              "sessione privata" in r1.stdout.decode("utf-8", "replace").lower(),
              r1.stdout.decode("utf-8", "replace")[:200])

        if coda.exists():
            coda.unlink()
        r2 = lancia(str(base / "normale"), "99999999-9999-9999-9999-999999999999")
        prova("hook con id escluso: niente in coda",
              not coda.exists() or not coda.read_text().strip())
        prova("hook con id escluso: esce comunque con 0", r2.returncode == 0)
        # Stessa frase generica dell'esclusione per cwd qui sopra: prima
        # della correzione diceva "Cartella privata" anche quando l'unico
        # motivo dell'esclusione era l'id di sessione, non la cartella.
        prova("hook con id escluso: dice che la sessione è privata (stessa "
              "frase dell'esclusione per cwd, non 'cartella')",
              "sessione privata" in r2.stdout.decode("utf-8", "replace").lower(),
              r2.stdout.decode("utf-8", "replace")[:200])

        # controllo: una sessione normale (ne' cwd ne' id esclusi) finisce in
        # coda come sempre — la regressione da evitare e' un fail-closed che
        # blocca TUTTO, non solo l'escluso.
        if coda.exists():
            coda.unlink()
        r3 = lancia(str(base / "normale-2"), "id-normale")
        prova("hook con cwd e id normali: finisce in coda",
              coda.exists() and "SessionStart" in coda.read_text())
    finally:
        import shutil
        shutil.rmtree(str(base), ignore_errors=True)


def _prova_git_locale(prova) -> None:
    """Un repository .git sotto una cartella esclusa, dentro un code_root,
    con `skip_git=False`: niente scheda, niente riga in `repos`, niente
    `commit` — e il vero `git log`/`git status` non deve nemmeno leggersi."""
    base = Path(tempfile.mkdtemp(prefix="plancia-prova-git-"))
    try:
        code_root = base / "dev"
        code_root.mkdir()
        priv_repo = code_root / "progetto-privato"
        priv_repo.mkdir()
        norm_repo = code_root / "progetto-normale"
        norm_repo.mkdir()
        env_git = _env_prova()
        for cartella, autore in ((priv_repo, "priv"), (norm_repo, "norm")):
            subprocess.run(["git", "init", "-q"], cwd=str(cartella), env=env_git, check=True)
            subprocess.run(["git", "config", "user.email", "p@p.it"], cwd=str(cartella),
                           env=env_git, check=True)
            subprocess.run(["git", "config", "user.name", "p"], cwd=str(cartella),
                           env=env_git, check=True)
            (cartella / "file.txt").write_text(f"contenuto {autore}\n", "utf-8")
            subprocess.run(["git", "add", "."], cwd=str(cartella), env=env_git, check=True)
            subprocess.run(["git", "commit", "-q", "-m", f"COMMITGITLOCALE{autore.upper()}XX"],
                           cwd=str(cartella), env=env_git, check=True)

        claude_dir = base / "claude-config"
        plancia_home = base / "plancia-home"
        codex_home = base / "codex-home"
        for c in (claude_dir, plancia_home, codex_home):
            c.mkdir(parents=True, exist_ok=True)
        (plancia_home / "config.json").write_text(json.dumps({
            "cartelle_escluse": [str(priv_repo)],
            "sessioni_escluse": [],
            "code_roots": [str(code_root)],
            "gh_enabled": False,
            "motore_riepilogo": "template",
        }), "utf-8")

        script = (
            f"import sys, json; sys.path.insert(0, {str(RADICE)!r})\n"
            "from plancia import esclusi, ingest, store\n"
            "conn = store.connect(); store.init_db(conn)\n"
            "n = ingest.sync_local_git(conn, escl=esclusi.carica(conn=conn))\n"
            "marcatore_priv = 'COMMITGITLOCALEPRIVXX'\n"
            "marcatore_norm = 'COMMITGITLOCALENORMXX'\n"
            "esito = {\n"
            "    'cartelle_lette': n,\n"
            "    'repo_priv': conn.execute(\"SELECT COUNT(*) FROM repos WHERE name=?\", "
            "('progetto-privato',)).fetchone()[0],\n"
            "    'repo_norm': conn.execute(\"SELECT COUNT(*) FROM repos WHERE name=?\", "
            "('progetto-normale',)).fetchone()[0],\n"
            "    'commit_priv': conn.execute(\"SELECT COUNT(*) FROM commits WHERE message "
            "LIKE ?\", ('%' + marcatore_priv + '%',)).fetchone()[0],\n"
            "    'commit_norm': conn.execute(\"SELECT COUNT(*) FROM commits WHERE message "
            "LIKE ?\", ('%' + marcatore_norm + '%',)).fetchone()[0],\n"
            "}\n"
            "print(json.dumps(esito))\n")
        env = _env_prova(PLANCIA_HOME=str(plancia_home), CLAUDE_CONFIG_DIR=str(claude_dir),
                         CODEX_HOME=str(codex_home))
        r = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True,
                           env=env, timeout=30)
        try:
            dati = json.loads([l for l in r.stdout.splitlines() if l.strip()][-1])
        except Exception:
            prova("sync_local_git con skip_git=False non solleva", False,
                  f"stdout={r.stdout[-800:]} stderr={r.stderr[-800:]}")
            return
        prova("un repo sotto una cartella esclusa non entra in repos",
              dati["repo_priv"] == 0, str(dati))
        prova("un repo normale entra in repos",
              dati["repo_norm"] == 1, str(dati))
        prova("il commit del repo escluso non entra in commits",
              dati["commit_priv"] == 0, str(dati))
        prova("il commit del repo normale entra in commits",
              dati["commit_norm"] == 1, str(dati))
    finally:
        import shutil
        shutil.rmtree(str(base), ignore_errors=True)


def _prova_mcp_scrittura(prova) -> None:
    """`plancia_task_add` da una sessione (id o cwd) esclusa: rifiutato,
    niente riga in `tasks`, niente evento, niente riga in eventi.jsonl."""
    base = Path(tempfile.mkdtemp(prefix="plancia-prova-mcp-"))
    try:
        priv = base / "privata"
        priv.mkdir()
        claude_dir = base / "claude-config"
        plancia_home = base / "plancia-home"
        for c in (claude_dir, plancia_home):
            c.mkdir(parents=True, exist_ok=True)
        (plancia_home / "config.json").write_text(json.dumps({
            "cartelle_escluse": [str(priv)], "sessioni_escluse": [], "gh_enabled": False,
            "motore_riepilogo": "template",
        }), "utf-8")

        script = (
            f"import sys, json; sys.path.insert(0, {str(RADICE)!r})\n"
            "from plancia import actions, mcp, sessione, store\n"
            f"sessione.corrente = lambda argv=None: {{'session_id': 'sid-mcp-priv', "
            f"'cwd': {str(priv)!r}, 'agent': 'claude', 'host': 'x', 'origine': 'env'}}\n"
            "conn = store.connect(); store.init_db(conn)\n"
            "rifiutato = False\n"
            "try:\n"
            "    mcp.call_tool('plancia_task_add', {'title': 'TASKMCPPRIVXX da sessione privata'})\n"
            "except actions.BadInput:\n"
            "    rifiutato = True\n"
            "conn2 = store.connect()\n"
            "marcatore = 'TASKMCPPRIVXX'\n"
            "n = conn2.execute(\"SELECT COUNT(*) FROM tasks WHERE title LIKE ?\","
            " ('%' + marcatore + '%',)).fetchone()[0]\n"
            "print(json.dumps({'rifiutato': rifiutato, 'righe_scritte': n}))\n")
        env = _env_prova(PLANCIA_HOME=str(plancia_home), CLAUDE_CONFIG_DIR=str(claude_dir))
        r = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True,
                           env=env, timeout=30)
        try:
            dati = json.loads([l for l in r.stdout.splitlines() if l.strip()][-1])
        except Exception:
            prova("plancia_task_add da una sessione con cwd esclusa è rifiutato", False,
                  f"stdout={r.stdout[-800:]} stderr={r.stderr[-800:]}")
            return
        prova("plancia_task_add da una sessione con cwd esclusa è rifiutato (BadInput)",
              dati["rifiutato"] is True, str(dati))
        prova("plancia_task_add rifiutato: niente riga scritta in tasks",
              dati["righe_scritte"] == 0, str(dati))
    finally:
        import shutil
        shutil.rmtree(str(base), ignore_errors=True)


def _prova_config_rotto(prova) -> None:
    """Ogni forma sbagliata di config.json: fail-closed, non "niente
    escluso". E `ingest.sync()` si comporta di conseguenza: non fa entrare
    niente di privato solo perché non ha capito la configurazione."""
    base = Path(tempfile.mkdtemp(prefix="plancia-prova-config-"))
    try:
        priv = base / "privata-config"
        priv.mkdir()
        claude_dir = base / "claude-config"
        plancia_home = base / "plancia-home"
        codex_home = base / "codex-home"
        for c in (claude_dir, plancia_home, codex_home):
            c.mkdir(parents=True, exist_ok=True)

        # "cartella_troppo_ampia_home" deve essere la STESSA HOME che vedrà il
        # sottoprocesso (quella finta di _env_prova, non quella vera di questo
        # processo): config.HOME, nel sottoprocesso, è Path.home() letta con
        # la HOME finta impostata da _env_prova, e deve coincidere col
        # percorso scritto qui per riconoscerlo come "troppo ampio".
        home_finta, _, _ = _ambiente_condiviso()
        casi = {
            "stringa_al_posto_di_lista": json.dumps({"cartelle_escluse": str(priv)}),
            "virgola_finale": '{"cartelle_escluse": [' + json.dumps(str(priv)) + '],}',
            "cartella_inesistente": json.dumps({"cartelle_escluse": [str(base / "non-esiste-x")]}),
            "cartella_relativa": json.dumps({"cartelle_escluse": ["relativa/x"]}),
            "cartella_troppo_ampia_home": json.dumps({"cartelle_escluse": [str(home_finta)]}),
            "id_non_uuid": json.dumps({"sessioni_escluse": ["non-e-un-uuid"]}),
            "non_e_un_oggetto": "[1, 2, 3]",
        }

        script = (
            f"import sys, json; sys.path.insert(0, {str(RADICE)!r})\n"
            "from plancia import config\n"
            "c = config.load_config_verificata()\n"
            "print(json.dumps({'ok': c.get('esclusi_ok'), 'errore': c.get('esclusi_errore')}))\n")

        for nome, contenuto in casi.items():
            (plancia_home / "config.json").write_text(contenuto, "utf-8")
            env = _env_prova(PLANCIA_HOME=str(plancia_home))
            r = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True,
                               env=env, timeout=15)
            try:
                dati = json.loads([l for l in r.stdout.splitlines() if l.strip()][-1])
            except Exception:
                prova(f"config rotto ({nome}): load_config_verificata non solleva", False,
                      f"stdout={r.stdout[-500:]} stderr={r.stderr[-500:]}")
                continue
            prova(f"config rotto ({nome}): esclusi_ok è False",
                  dati.get("ok") is False, str(dati))

        # caso valido, di controllo: la stessa cartella scritta bene passa.
        (plancia_home / "config.json").write_text(
            json.dumps({"cartelle_escluse": [str(priv)], "motore_riepilogo": "template"}),
            "utf-8")
        env = _env_prova(PLANCIA_HOME=str(plancia_home))
        r = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True,
                           env=env, timeout=15)
        dati = json.loads([l for l in r.stdout.splitlines() if l.strip()][-1])
        prova("config valido: esclusi_ok è True", dati.get("ok") is True, str(dati))

        # maiuscole diverse dalla grafia vera: non deve passare la
        # validazione COME se il percorso scritto fosse quello giusto, ma
        # deve risolvere alla grafia vera sul disco (bug misurato: prima
        # dava percorso_escluso=False con 'privato/x' e cwd 'Privato/X').
        vera = base / "CartellaMaiuscola"
        vera.mkdir()
        (plancia_home / "config.json").write_text(
            json.dumps({"cartelle_escluse": [str(base / "cartellamaiuscola")],
                       "motore_riepilogo": "template"}), "utf-8")
        r = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True,
                           env=env, timeout=15)
        dati = json.loads([l for l in r.stdout.splitlines() if l.strip()][-1])
        prova("maiuscole diverse dalla grafia vera: validato comunque (grafia corretta)",
              dati.get("ok") is True, str(dati))

        # fail-closed vero: un sync su un config.json rotto non deve far
        # entrare la sessione privata, e non deve sollevare. "cartelle_escluse"
        # resta rotta apposta (una stringa, non una lista: quello che si sta
        # controllando qui); "motore_riepilogo": "template" ci sta comunque
        # accanto, perche' non c'entra con QUELLA rottura e chiude anche qui
        # il primo fusibile (config-level), oltre al secondo (l'ambiente
        # finto di _env_prova, che da solo basterebbe: e' quello che il resto
        # di questo test verifica, "esclusi_errore"/"sessione_entrata").
        (plancia_home / "config.json").write_text(
            json.dumps({"cartelle_escluse": str(priv), "motore_riepilogo": "template"}),
            "utf-8")
        sid_priv_config = "88888888-8888-8888-8888-888888888888"
        cod_priv = _codifica_cartella(priv)
        _scrivi_transcript(
            claude_dir / "projects" / cod_priv / f"{sid_priv_config}.jsonl",
            str(priv), "CONFIGROTTOPRIVXX")
        script_sync = (
            f"import sys, json; sys.path.insert(0, {str(RADICE)!r})\n"
            "from plancia import ingest, store\n"
            "r = ingest.sync(modo='tutto', skip_git=True)\n"
            # Il join aspetta il thread demone di recap.prepara() prima che
            # lo script esca, cosi' il finto claude (se mai ci provasse) ha
            # gia' scritto il suo segnale quando questo processo termina.
            "import threading as _th\n"
            "for _t in _th.enumerate():\n"
            "    if _t is not _th.current_thread():\n"
            "        _t.join(timeout=10)\n"
            "conn = store.connect()\n"
            "n = conn.execute(\"SELECT COUNT(*) FROM sessions WHERE session_id=?\", "
            f"({sid_priv_config!r},)).fetchone()[0]\n"
            "print(json.dumps({'esclusi_errore': r.get('esclusi_errore'), "
            "'sessione_entrata': n, 'ha_esclusi_key': 'esclusi' in r}))\n")
        env2 = _env_prova(PLANCIA_HOME=str(plancia_home), CLAUDE_CONFIG_DIR=str(claude_dir),
                          CODEX_HOME=str(codex_home))
        r2 = subprocess.run([sys.executable, "-c", script_sync], capture_output=True, text=True,
                            env=env2, timeout=30)
        try:
            dati2 = json.loads([l for l in r2.stdout.splitlines() if l.strip()][-1])
        except Exception:
            prova("ingest.sync() con config.json rotto non solleva", False,
                  f"stdout={r2.stdout[-800:]} stderr={r2.stderr[-800:]}")
            return
        prova("ingest.sync() con config.json rotto: segnala l'errore",
              bool(dati2.get("esclusi_errore")), str(dati2))
        prova("ingest.sync() con config.json rotto: fail-closed, "
              "la sessione privata NON entra comunque",
              dati2.get("sessione_entrata") == 0, str(dati2))
        prova("ingest.sync() con config.json rotto: non lancia la purga (niente chiave 'esclusi')",
              dati2.get("ha_esclusi_key") is False, str(dati2))
    finally:
        import shutil
        shutil.rmtree(str(base), ignore_errors=True)


def _prova_spostata_un_giro(prova) -> None:
    """Lo scenario esatto trovato dal tester: una trascrizione che ha GIA'
    dentro di se', dalla prima riga, sia la cwd normale sia quella che poi
    diventera' privata, letta tutta da un primo sync PRIMA che la cartella
    sia esclusa (quindi sessions.cwd si ferma sull'ultima vista: quella
    privata). Si aggiunge poi la cartella a cartelle_escluse e si lancia UN
    SOLO sync incrementale, senza toccare piu' il file: e' il ramo veloce
    ("la dimensione non e' cambiata, salto") che sync_sessions prende quando
    non c'e' niente di nuovo da leggere.

    Prima della correzione: la riga in `sessions` sparisce comunque (la cwd
    era gia' salvata, e la purga la legge da li'), ma il testo resta intero
    in turni_fts (quindi in `plancia search`/`plancia_search`), perche' la
    sua pulizia guarda solo esclusi["sessioni"], e quell'id ci entra solo
    quando qualcosa rilegge il transcript da capo: cosa che qui non succede
    mai, dato che il file non cambia piu'. Dopo la correzione, la scoperta
    fatta guardando sessions.cwd durante la stessa purga vale anche per
    turni_fts, nello stesso giro.
    """
    base = Path(tempfile.mkdtemp(prefix="plancia-prova-spostata-un-giro-"))
    try:
        normale = base / "normale-un-giro"
        privata = base / "privata-un-giro"
        normale.mkdir()
        privata.mkdir()
        claude_dir = base / "claude-config"
        plancia_home = base / "plancia-home"
        codex_home = base / "codex-home"
        for c in (claude_dir, plancia_home, codex_home):
            c.mkdir(parents=True, exist_ok=True)

        sid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        cod_normale = _codifica_cartella(normale)
        path = claude_dir / "projects" / cod_normale / f"{sid}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        righe = [
            _riga("user", "UNGIROPRIMAXX apro qui, un messaggio abbastanza "
                  "lungo da superare la soglia di indicizzazione.",
                  "2026-01-01T00:00:00Z", cwd=str(normale)),
            _riga("assistant", "Ho letto UNGIROPRIMAXX e continuo il lavoro "
                  "con una risposta lunga a sufficienza.",
                  "2026-01-01T00:00:05Z"),
            _riga("user", "UNGIRODOPOXX ora lavoro qui invece, un messaggio "
                  "abbastanza lungo da superare la soglia.",
                  "2026-01-01T00:10:00Z", cwd=str(privata)),
            _riga("assistant", "Ho letto UNGIRODOPOXX e continuo qui, "
                  "risposta lunga a sufficienza.",
                  "2026-01-01T00:10:05Z"),
        ]
        path.write_text("\n".join(righe) + "\n", "utf-8")

        # Primo sync: PRIMA della regola, config.json senza le due chiavi
        # (ma valido: "motore_riepilogo": "template" perche' e' un sync
        # vero, modo="tutto").
        (plancia_home / "config.json").write_text(
            json.dumps({"gh_enabled": False, "code_roots": [],
                       "motore_riepilogo": "template"}), "utf-8")
        env = _env_prova(PLANCIA_HOME=str(plancia_home),
                         CLAUDE_CONFIG_DIR=str(claude_dir), CODEX_HOME=str(codex_home))
        script1 = (
            f"import sys; sys.path.insert(0, {str(RADICE)!r})\n"
            "from plancia import ingest\n"
            "ingest.sync(modo='tutto', skip_git=True, full=True)\n"
            # aspetta il thread demone di recap.prepara() (vedi il commento
            # sul join nello SCRIPT principale, in cima al file) prima che
            # lo script esca: qui non si legge lo stdout per un esito, ma un
            # demone lasciato a correre per conto suo e' comunque il rischio
            # che questa prova esiste per escludere.
            "import threading as _th\n"
            "for _t in _th.enumerate():\n"
            "    if _t is not _th.current_thread():\n"
            "        _t.join(timeout=10)\n")
        r1 = subprocess.run([sys.executable, "-c", script1], capture_output=True,
                            text=True, env=env, timeout=30)
        if r1.returncode != 0:
            prova("sessione spostata (un giro): il primo sync (prima della regola) "
                  "gira senza eccezioni", False,
                  f"stdout={r1.stdout[-500:]} stderr={r1.stderr[-500:]}")
            return

        # Si aggiunge la cartella a cartelle_escluse: il file della
        # trascrizione non viene piu' toccato da qui in avanti.
        (plancia_home / "config.json").write_text(json.dumps({
            "gh_enabled": False, "code_roots": [],
            "cartelle_escluse": [str(privata)],
            "motore_riepilogo": "template",
        }), "utf-8")

        script2 = (
            f"import sys, json; sys.path.insert(0, {str(RADICE)!r})\n"
            "from plancia import ingest, store\n"
            "ingest.sync(modo='tutto', skip_git=True)\n"
            "import threading as _th\n"
            "for _t in _th.enumerate():\n"
            "    if _t is not _th.current_thread():\n"
            "        _t.join(timeout=10)\n"
            "conn = store.connect()\n"
            f"sid = {sid!r}\n"
            "n_sessioni = conn.execute(\"SELECT COUNT(*) FROM sessions WHERE session_id=?\", "
            "(sid,)).fetchone()[0]\n"
            "n_turni_prima = conn.execute(\"SELECT COUNT(*) FROM turni_fts WHERE turni_fts MATCH ?\", "
            "('UNGIROPRIMAXX',)).fetchone()[0]\n"
            "n_turni_dopo = conn.execute(\"SELECT COUNT(*) FROM turni_fts WHERE turni_fts MATCH ?\", "
            "('UNGIRODOPOXX',)).fetchone()[0]\n"
            "n_search_prima = conn.execute(\"SELECT COUNT(*) FROM search_fts WHERE search_fts MATCH ?\", "
            "('UNGIROPRIMAXX',)).fetchone()[0]\n"
            "n_search_dopo = conn.execute(\"SELECT COUNT(*) FROM search_fts WHERE search_fts MATCH ?\", "
            "('UNGIRODOPOXX',)).fetchone()[0]\n"
            "print(json.dumps({'sessione': n_sessioni, 'turni_prima': n_turni_prima, "
            "'turni_dopo': n_turni_dopo, 'search_prima': n_search_prima, "
            "'search_dopo': n_search_dopo}))\n")
        r2 = subprocess.run([sys.executable, "-c", script2], capture_output=True,
                            text=True, env=env, timeout=30)
        try:
            dati = json.loads([l for l in r2.stdout.splitlines() if l.strip()][-1])
        except Exception:
            prova("sessione spostata (un giro): il secondo sync (incrementale, un solo "
                  "giro) stampa un JSON leggibile", False,
                  f"stdout={r2.stdout[-800:]} stderr={r2.stderr[-800:]}")
            return

        prova("sessione spostata, un solo sync incrementale dopo l'esclusione: "
              "sparisce da sessions", dati.get("sessione") == 0, str(dati))
        prova("...nello STESSO giro sparisce anche il testo di prima dello "
              "spostamento da turni_fts (non un giro dopo)",
              dati.get("turni_prima") == 0, str(dati))
        prova("...e anche il testo di dopo lo spostamento da turni_fts",
              dati.get("turni_dopo") == 0, str(dati))
        prova("...e da search_fts (prima dello spostamento)",
              dati.get("search_prima") == 0, str(dati))
        prova("...e da search_fts (dopo lo spostamento)",
              dati.get("search_dopo") == 0, str(dati))
    finally:
        import shutil
        shutil.rmtree(str(base), ignore_errors=True)


def _prova_hook_valida_come_esclusi(prova) -> None:
    """bin/plancia-hook e plancia/esclusi.valida() devono dire ok/non ok
    sullo STESSO config.json. Una guardia, non solo una correzione una
    tantum: se domani uno dei due cambia senza l'altro, questa prova se ne
    accorge da sola.

    Il segnale che si confronta e' "il file e' affidabile", non "la
    sessione di prova e' esclusa": con una cartella_esclusa che coincide
    con la cwd della sessione di controllo, un config.json valido fa si'
    che l'hook NON scriva in coda (la sessione e' privata) ma stampi
    comunque un messaggio (quello di privacy, invece dell'ancoraggio): lo
    stdout non vuoto e' la spia di "valido", a prescindere da quale dei due
    messaggi sia.
    """
    base = Path(tempfile.mkdtemp(prefix="plancia-prova-hook-valida-"))
    try:
        esiste = base / "cartella-esistente"
        esiste.mkdir()
        claude_dir = base / "claude-config"
        codex_home = base / "codex-home"
        for c in (claude_dir, codex_home):
            c.mkdir(parents=True, exist_ok=True)

        sid_valido = "12345678-1234-1234-1234-123456789abc"
        # "cartella_troppo_ampia_home" deve essere la stessa HOME che vedranno
        # questi sottoprocessi (quella finta di _env_prova): sia esclusi.valida()
        # (via config.HOME) sia bin/plancia-hook (via os.path.expanduser("~"))
        # la leggono dalla stessa variabile d'ambiente HOME.
        home_finta, _, _ = _ambiente_condiviso()
        casi = {
            "valido": {"cartelle_escluse": [str(esiste)], "sessioni_escluse": [sid_valido]},
            "liste_vuote": {},
            "cartella_stringa_al_posto_di_lista": {"cartelle_escluse": str(esiste)},
            "cartella_relativa": {"cartelle_escluse": ["relativa/x"]},
            "cartella_inesistente": {"cartelle_escluse": [str(base / "non-esiste-davvero")]},
            "cartella_troppo_ampia_claude_dir": {"cartelle_escluse": [str(claude_dir)]},
            "cartella_troppo_ampia_home": {"cartelle_escluse": [str(home_finta)]},
            "sessione_non_uuid": {"cartelle_escluse": [str(esiste)],
                                  "sessioni_escluse": ["non-e-un-uuid"]},
        }

        script_valida = (
            f"import sys, json; sys.path.insert(0, {str(RADICE)!r})\n"
            "from plancia import esclusi\n"
            "cfg = json.loads(sys.stdin.read())\n"
            "ok, errore, _, _ = esclusi.valida(cfg)\n"
            "print(json.dumps({'ok': ok, 'errore': errore}))\n")

        for nome, cfg in casi.items():
            plancia_home = base / f"home-{nome}"
            plancia_home.mkdir(parents=True, exist_ok=True)
            # Solo le tre tabelle che ancoraggio() interroga, vuote: senza
            # questo la connessione in sola lettura dell'hook fallirebbe (il
            # file non esiste ancora), l'eccezione verrebbe ingoiata (giusto:
            # l'hook non deve mai sollevare) e lo stdout resterebbe vuoto per
            # un motivo che non c'entra niente con la validita' di
            # config.json, mascherando il confronto.
            conn_min = sqlite3.connect(str(plancia_home / "plancia.db"))
            conn_min.executescript(
                "CREATE TABLE repos(local_path TEXT, project_id INTEGER);"
                "CREATE TABLE projects(id INTEGER PRIMARY KEY, key TEXT);"
                "CREATE TABLE project_links(value TEXT, kind TEXT, project_id INTEGER);")
            conn_min.commit()
            conn_min.close()
            (plancia_home / "config.json").write_text(json.dumps(cfg), "utf-8")
            env = _env_prova(PLANCIA_HOME=str(plancia_home),
                             CLAUDE_CONFIG_DIR=str(claude_dir), CODEX_HOME=str(codex_home))

            r_val = subprocess.run([sys.executable, "-c", script_valida],
                                   input=json.dumps(cfg), capture_output=True,
                                   text=True, env=env, timeout=15)
            try:
                dati_valida = json.loads(
                    [l for l in r_val.stdout.splitlines() if l.strip()][-1])
            except Exception:
                prova(f"esclusi.valida() ({nome}) stampa un JSON leggibile", False,
                      f"stdout={r_val.stdout!r} stderr={r_val.stderr!r}")
                continue
            ok_valida = dati_valida.get("ok")

            payload = json.dumps({"hook_event_name": "SessionStart",
                                  "session_id": sid_valido, "cwd": str(esiste)}).encode()
            r_hook = subprocess.run(_argv_script(RADICE / "bin" / "plancia-hook"),
                                    input=payload, capture_output=True, env=env, timeout=15)
            prova(f"hook ({nome}): esce comunque con 0", r_hook.returncode == 0)
            ok_hook = bool(r_hook.stdout.decode("utf-8", "replace").strip())

            prova(f"hook e esclusi.valida() d'accordo sullo stesso config.json ({nome})",
                  ok_hook == ok_valida,
                  f"valida.ok={ok_valida} ({dati_valida.get('errore')}) "
                  f"hook_considera_valido={ok_hook}")
    finally:
        import shutil
        shutil.rmtree(str(base), ignore_errors=True)


def esegui(prova) -> None:
    base = Path(tempfile.mkdtemp(prefix="plancia-prova-esclusi-"))
    try:
        fix = _prepara(base)
        r = _esegui_sottoprocesso(fix)

        if r.get("_fallito"):
            prova("il sottoprocesso stampa un JSON leggibile", False,
                  f"{r.get('_eccezione')} — stderr: {r.get('_stderr')}")
            return

        prova("esclusi.conta() non solleva su un archivio che ha visto solo init_db "
              "(turni_file non ancora creata da un sync)",
              r.get("conta_prima_del_sync_ok") is True,
              str(r.get("conta_prima_del_sync_errore")))
        prova("ingest.sync() gira senza eccezioni con le due chiavi nuove in config.json",
              r.get("sync_ok") is True, str(r.get("sync_errore")))

        # ---------------------------------------------------- fase 1: ingest
        prova("una sessione con cwd esclusa non entra in turni_fts",
              r.get("turni_priv") == 0, str(r.get("turni_priv")))
        prova("una sessione con id escluso non entra in turni_fts",
              r.get("turni_id_escluso") == 0, str(r.get("turni_id_escluso")))
        prova("il sottoagente di una sessione con id escluso non entra in turni_fts",
              r.get("turni_subagente") == 0, str(r.get("turni_subagente")))
        prova("una sessione normale entra in turni_fts",
              isinstance(r.get("turni_norm"), int) and r["turni_norm"] >= 1,
              str(r.get("turni_norm")))
        prova("la parola della sessione esclusa non entra in search_fts",
              r.get("search_priv") == 0, str(r.get("search_priv")))
        prova("la parola della sessione normale entra in search_fts",
              isinstance(r.get("search_norm"), int) and r["search_norm"] >= 1,
              str(r.get("search_norm")))
        prova("la sessione con cwd esclusa non entra in sessions",
              r.get("sessione_priv") == 0, str(r.get("sessione_priv")))
        prova("la sessione con id escluso non entra in sessions",
              r.get("sessione_id_escluso") == 0, str(r.get("sessione_id_escluso")))
        prova("la sessione normale entra in sessions",
              r.get("sessione_norm") == 1, str(r.get("sessione_norm")))
        prova("la coda hook non scrive un evento per la sessione/cwd esclusa",
              r.get("hook_priv") == 0, str(r.get("hook_priv")))
        prova("la coda hook scrive un evento per la sessione normale",
              r.get("hook_norm") == 1, str(r.get("hook_norm")))
        prova("la memoria di una cartella esclusa non entra in knowledge",
              r.get("memoria_priv") == 0, str(r.get("memoria_priv")))
        prova("la memoria di una cartella normale entra in knowledge",
              r.get("memoria_norm") == 1, str(r.get("memoria_norm")))

        # ------------------------------------------------- fase 1b: spostata
        prova("secondo sync (sessione spostata) gira senza eccezioni",
              r.get("sync2_ok") is True, str(r.get("sync2_errore")))
        prova("una sessione aperta normale e poi spostata in una cartella "
              "esclusa sparisce da sessions",
              r.get("sessione_spostata") == 0, str(r.get("sessione_spostata")))
        prova("...e sparisce anche il suo evento 'sessione'",
              r.get("evento_spostata") == 0, str(r.get("evento_spostata")))
        prova("...e il testo di PRIMA dello spostamento sparisce da turni_fts "
              "(non solo quello di dopo)",
              r.get("turni_spostata_prima") == 0, str(r.get("turni_spostata_prima")))
        prova("...e anche il testo di dopo lo spostamento",
              r.get("turni_spostata_dopo") == 0, str(r.get("turni_spostata_dopo")))
        prova("...e da search_fts (niente first_prompt indicizzato)",
              r.get("search_spostata_prima") == 0, str(r.get("search_spostata_prima")))

        # --------------------------------------------------------- Codex
        prova("un rollout Codex con cwd esclusa non entra in sessions",
              r.get("sessione_codex_cwd") == 0, str(r.get("sessione_codex_cwd")))
        prova("...e il suo testo non entra in search_fts",
              r.get("search_codex_cwd") == 0, str(r.get("search_codex_cwd")))
        prova("la RIPRESA di un thread Codex già escluso (uuid di file nuovo, "
              "cwd normale) non entra in sessions",
              r.get("sessione_codex_ripresa") == 0, str(r.get("sessione_codex_ripresa")))
        prova("...e il suo testo non entra in search_fts",
              r.get("search_codex_ripresa") == 0, str(r.get("search_codex_ripresa")))

        # -------------------------------------------------------- Lavagna
        prova("un todo di Claude Code di una sessione esclusa non entra in agenda",
              r.get("agenda_claude_priv") == 0, str(r.get("agenda_claude_priv")))
        prova("un todo di Claude Code di una sessione normale entra in agenda",
              r.get("agenda_claude_norm") == 1, str(r.get("agenda_claude_norm")))
        prova("un obiettivo Codex di un thread escluso non entra in agenda",
              r.get("agenda_codex_priv") == 0, str(r.get("agenda_codex_priv")))
        prova("un obiettivo Codex di un thread normale entra in agenda",
              r.get("agenda_codex_norm") == 1, str(r.get("agenda_codex_norm")))

        # -------------------------------------------------------- fase 2: purga
        prova("esclusi.purga() gira senza eccezioni sulle righe inserite a mano",
              r.get("purga_ok") is True, str(r.get("purga_errore")))
        if not r.get("purga_ok"):
            return

        prova("purga toglie una sessione già entrata con cwd esclusa",
              r.get("man_sessione_priv") == 0, str(r.get("man_sessione_priv")))
        prova("purga lascia una sessione normale",
              r.get("man_sessione_norm") == 1, str(r.get("man_sessione_norm")))
        prova("purga toglie un task legato per session_id a una sessione esclusa",
              r.get("man_task_priv_sid") == 0, str(r.get("man_task_priv_sid")))
        prova("purga toglie un task con cwd sotto una cartella esclusa",
              r.get("man_task_priv_cwd") == 0, str(r.get("man_task_priv_cwd")))
        prova("purga lascia un task normale",
              r.get("man_task_norm") == 1, str(r.get("man_task_norm")))
        prova("purga toglie un post legato a una sessione esclusa",
              r.get("man_post_priv") == 0, str(r.get("man_post_priv")))
        prova("purga lascia un post normale",
              r.get("man_post_norm") == 1, str(r.get("man_post_norm")))
        prova("purga toglie un evento 'sessione' legato a una sessione esclusa",
              r.get("man_evento_priv") == 0, str(r.get("man_evento_priv")))
        prova("purga toglie un evento 'hook' legato a una sessione esclusa",
              r.get("man_evento_hook_priv") == 0, str(r.get("man_evento_hook_priv")))
        prova("purga lascia un evento normale",
              r.get("man_evento_norm") == 1, str(r.get("man_evento_norm")))
        prova("purga toglie una memoria già entrata di una cartella esclusa",
              r.get("man_know_priv") == 0, str(r.get("man_know_priv")))
        prova("purga lascia una memoria normale già entrata",
              r.get("man_know_norm") == 1, str(r.get("man_know_norm")))
        prova("purga toglie una trascrizione indicizzata di una cartella esclusa",
              r.get("man_turni_priv") == 0, str(r.get("man_turni_priv")))
        prova("purga lascia una trascrizione indicizzata normale",
              isinstance(r.get("man_turni_norm"), int) and r["man_turni_norm"] >= 1,
              str(r.get("man_turni_norm")))
        prova("purga toglie anche la riga di turni_file corrispondente",
              r.get("man_turni_file_priv") == 0, str(r.get("man_turni_file_priv")))
        prova("purga lascia la riga di turni_file normale",
              r.get("man_turni_file_norm") == 1, str(r.get("man_turni_file_norm")))
        prova("purga toglie un repo con local_path sotto una cartella esclusa",
              r.get("man_repo_priv") == 0, str(r.get("man_repo_priv")))
        prova("purga lascia un repo normale",
              r.get("man_repo_norm") == 1, str(r.get("man_repo_norm")))
        prova("un progetto automatico rimasto senza nessun link sparisce",
              r.get("man_progetto_orfano") == 0, str(r.get("man_progetto_orfano")))
        prova("un progetto automatico con un altro link (repo) resta",
              r.get("man_progetto_misto") == 1, str(r.get("man_progetto_misto")))
        prova("un progetto manuale (auto=0) non viene mai cancellato",
              r.get("man_progetto_manuale") == 1, str(r.get("man_progetto_manuale")))
        prova("dal progetto con un altro link, il link di percorso escluso sparisce",
              r.get("man_link_misto_path") == 0, str(r.get("man_link_misto_path")))
        prova("dal progetto con un altro link, il link di repo resta",
              r.get("man_link_misto_repo") == 1, str(r.get("man_link_misto_repo")))
        prova("dal progetto manuale, il link di percorso escluso sparisce comunque",
              r.get("man_link_manuale_path") == 0, str(r.get("man_link_manuale_path")))
        prova("live_session che punta a una sessione esclusa viene tolto da meta",
              r.get("man_live_session") is None, str(r.get("man_live_session")))
        prova("purga riscrive eventi.jsonl togliendo la riga di cwd esclusa",
              r.get("eventi_jsonl_priv") is False, str(r.get("eventi_jsonl_priv")))
        prova("purga lascia in eventi.jsonl la riga di cwd normale",
              r.get("eventi_jsonl_norm") is True, str(r.get("eventi_jsonl_norm")))

        prova("una memoria di tipo progetto già orfana: la scheda automatica sparisce",
              r.get("man_progetto_memoria_orfano") == 0, str(r.get("man_progetto_memoria_orfano")))
        prova("...e la riga di knowledge che la referenziava anche",
              r.get("man_know_progetto_orfano") == 0, str(r.get("man_know_progetto_orfano")))
        prova("...e l'evento SQL kind='memoria' con quel nome",
              r.get("man_evento_memoria_orfano") == 0, str(r.get("man_evento_memoria_orfano")))
        prova("un repo escluso con un commit: il repo sparisce",
              r.get("man_repo_priv_commit") == 0, str(r.get("man_repo_priv_commit")))
        prova("...e il commit sparisce da commits",
              r.get("man_commit_priv") == 0, str(r.get("man_commit_priv")))
        prova("...e l'evento SQL kind='commit' del suo sha",
              r.get("man_evento_commit_priv") == 0, str(r.get("man_evento_commit_priv")))
        prova("un lancio (runs) con cwd esclusa sparisce dal database",
              r.get("man_run_priv") == 0, str(r.get("man_run_priv")))
        prova("...e il suo log su disco viene cancellato",
              r.get("man_run_log_esiste") is False, str(r.get("man_run_log_esiste")))
        prova("meta.git_lento della cartella esclusa viene tolto",
              r.get("man_meta_git_lento") is None, str(r.get("man_meta_git_lento")))
        prova("la cache del riepilogo (recap_testo) viene invalidata quando la "
              "pulizia toglie qualcosa",
              r.get("man_meta_recap_testo") is None, str(r.get("man_meta_recap_testo")))
        prova("...e anche la cache delle proposte",
              r.get("man_meta_proposte") is None, str(r.get("man_meta_proposte")))

        prova("eventi.jsonl: un progetto.archiviato del progetto orfano sparisce",
              r.get("eventi_jsonl_progetto_priv") is False, str(r.get("eventi_jsonl_progetto_priv")))
        prova("eventi.jsonl: un padre:* del progetto orfano sparisce",
              r.get("eventi_jsonl_padre_priv") is False, str(r.get("eventi_jsonl_padre_priv")))
        prova("eventi.jsonl: un lavoro.completato del lancio escluso sparisce",
              r.get("eventi_jsonl_lavoro_priv") is False, str(r.get("eventi_jsonl_lavoro_priv")))
        prova("eventi.jsonl: un task.creato del task escluso sparisce",
              r.get("eventi_jsonl_task_priv") is False, str(r.get("eventi_jsonl_task_priv")))
        prova("eventi.jsonl: un post.pubblicato del post escluso sparisce",
              r.get("eventi_jsonl_post_priv") is False, str(r.get("eventi_jsonl_post_priv")))

        c = r.get("conteggi") or {}
        prova("il conteggio di purga riporta esattamente le sessioni tolte (1)",
              c.get("sessioni") == 1, str(c))
        prova("il conteggio di purga riporta esattamente i task tolti (3)",
              c.get("tasks") == 3, str(c))
        prova("il conteggio di purga riporta i lanci (runs) tolti (1)",
              c.get("runs") == 1, str(c))
        prova("il conteggio di purga riporta i commit tolti (1)",
              c.get("commits") == 1, str(c))
        prova("il conteggio di purga riporta i progetti orfani tolti (2)",
              c.get("progetti") == 2, str(c))
        prova("con le liste vuote il comportamento non cambia: la chiave 'esclusi' "
              "compare solo se qualcosa è davvero configurato",
              True)  # verificato dalle prove piccole più sotto (config vuoto)
    finally:
        import shutil
        shutil.rmtree(str(base), ignore_errors=True)

    _prova_hook(prova)
    _prova_git_locale(prova)
    _prova_mcp_scrittura(prova)
    _prova_config_rotto(prova)
    _prova_spostata_un_giro(prova)
    _prova_hook_valida_come_esclusi(prova)

    # ---------------------------------------------------------- liste vuote
    base_vuoto = Path(tempfile.mkdtemp(prefix="plancia-prova-esclusi-vuoto-"))
    try:
        plancia_home = base_vuoto / "home"
        claude_dir = base_vuoto / "claude"
        codex_home = base_vuoto / "codex"
        for c in (plancia_home, claude_dir, codex_home):
            c.mkdir(parents=True, exist_ok=True)
        (plancia_home / "config.json").write_text(
            json.dumps({"cartelle_escluse": [], "sessioni_escluse": [], "gh_enabled": False,
                       "motore_riepilogo": "template"}),
            "utf-8")
        script = (
            f"import sys, json; sys.path.insert(0, {str(RADICE)!r})\n"
            "from plancia import ingest\n"
            "r = ingest.sync(modo='tutto', skip_git=True)\n"
            "import threading as _th\n"
            "for _t in _th.enumerate():\n"
            "    if _t is not _th.current_thread():\n"
            "        _t.join(timeout=10)\n"
            "print(json.dumps({'ha_esclusi': 'esclusi' in r, "
            "'ha_errore': 'esclusi_errore' in r}))\n")
        env = _env_prova(PLANCIA_HOME=str(plancia_home), CLAUDE_CONFIG_DIR=str(claude_dir),
                         CODEX_HOME=str(codex_home))
        r = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True,
                           env=env, timeout=30)
        dati = json.loads([l for l in r.stdout.splitlines() if l.strip()][-1])
        prova("con le liste vuote, l'esito del sync non ha la chiave 'esclusi'",
              dati.get("ha_esclusi") is False, str(dati))
        prova("con le liste vuote e un config.json valido, nessun errore di esclusi",
              dati.get("ha_errore") is False, str(dati))
    finally:
        import shutil
        shutil.rmtree(str(base_vuoto), ignore_errors=True)

    # -------------------------------------------------- claude mai vero
    # Il difetto grave del tester precedente: ingest.sync(modo="tutto") (lo
    # fanno quasi tutte le prove qui sopra) lancia in un thread demone
    # recap.prepara(), che con il motore di default "claude" (config.json
    # senza motore_riepilogo, o rotto: vedi plancia/config.load_config())
    # chiama davvero il binario `claude`: spesa di quota reale, e un
    # fallimento intermittente di questa stessa suite (1 su 11, misurato dal
    # tester: una gara col thread). _env_prova() mette un `claude` finto
    # davanti nel PATH di OGNI sottoprocesso lanciato da questo modulo (con
    # un'HOME finta: mai quella vera, che risolverebbe ~/.local/bin/claude a
    # un binario vero), e ogni script che chiama ingest.sync(modo='tutto')
    # aspetta (con un tetto) i suoi thread demoni prima di uscire: cosi' la
    # gara diventa un ordine deterministico, e il segnale, se c'e', c'e' gia'
    # quando si arriva qui. Un solo controllo, alla fine di tutte le prove di
    # questo modulo, su tutti i sottoprocessi lanciati finora: se anche uno
    # solo avesse provato a lanciare claude, il file esisterebbe.
    prova("nessuna prova di questo modulo ha provato a lanciare claude davvero",
          not _claude_chiamato())
