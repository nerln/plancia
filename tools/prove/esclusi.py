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

Le trascrizioni finte, la memoria finta e la coda degli hook le scrive
questo modulo (il genitore), prima di lanciare il sottoprocesso: è testo e
cartelle, non serve importare plancia per costruirli. Il calcolo di come
Claude Code codifica una cwd in nome di cartella (`_codifica_cartella` qui
sotto) è fatto apposta SENZA importare `plancia.esclusi`, che sul commit di
base non esiste ancora: la prova deve poter costruire le stesse fixture su
entrambi i commit.

Lo script che gira nel sottoprocesso è un testo con segnaposto (`__NOME__`),
sostituiti con `str.replace()` e mai con `str.format()`: lo script contiene
lui stesso dizionari e f-string, pieni di `{`/`}` veri, e farli convivere con
le graffe di sostituzione di `.format()` è un modo sicuro per sbagliare un
conteggio di graffe senza accorgersene.

Fase 1 (dentro il sottoprocesso): un sync vero (`ingest.sync`) su tre
sessioni Claude Code (una con cwd esclusa, una con id escluso e un
sottoagente sotto di lei, una normale), una memoria esclusa e una normale,
una riga di coda hook esclusa e una normale. Si controlla che le escluse non
compaiano in NESSUNA tabella (cercando anche una parola rara scritta apposta
nel testo, dentro turni_fts e search_fts) e che le normali sì.

Fase 2 (stesso sottoprocesso, di seguito): righe inserite A MANO in ogni
tabella che `esclusi.purga()` deve ripulire, come se ci fossero entrate
prima che la cartella/sessione fosse esclusa. Si chiama `purga()` e si
controlla che tolga le une e lasci le altre, coprendo anche i tre casi dei
progetti automatici (orfano da cancellare, con un altro link da tenere,
manuale da non toccare mai) ed `eventi.jsonl`.

Il sottoprocesso stampa un solo oggetto JSON, sull'ultima riga di stdout,
con tutto l'esito: qui si legge quello, non si prova a leggere lo stderr per
capire cos'è successo.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent.parent


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


def _prepara(base: Path) -> dict:
    """Cartelle e file finti, tutti sotto `base`. Torna i percorsi e gli id
    che il sottoprocesso userà per le verifiche."""
    priv = base / "cartella-privata"
    norm = base / "cartella-normale"
    altra = base / "cartella-altra"
    for c in (priv, norm, altra):
        c.mkdir(parents=True, exist_ok=True)

    claude_dir = base / "claude-config"
    plancia_home = base / "plancia-home"
    codex_home = base / "codex-home"
    projects = claude_dir / "projects"

    cod_priv = _codifica_cartella(priv)
    cod_norm = _codifica_cartella(norm)
    cod_altra = _codifica_cartella(altra)

    sid_priv = "11111111-1111-1111-1111-111111111111"
    sid_escluso = "22222222-2222-2222-2222-222222222222"
    sid_norm = "33333333-3333-3333-3333-333333333333"
    sub_uuid = "44444444-4444-4444-4444-444444444444"

    # 1. sessione con cwd esclusa
    _scrivi_transcript(projects / cod_priv / f"{sid_priv}.jsonl", str(priv), "ZBRAKKONDOR")
    # 2. sessione con id escluso, in una cartella NORMALE, con un sottoagente
    _scrivi_transcript(projects / cod_altra / f"{sid_escluso}.jsonl", str(altra), "TRENOBALENA")
    _scrivi_transcript(
        projects / cod_altra / sid_escluso / "subagents" / "workflows" / f"{sub_uuid}.jsonl",
        str(altra), "SUBAGENTONEXX")
    # 3. sessione normale
    _scrivi_transcript(projects / cod_norm / f"{sid_norm}.jsonl", str(norm), "QUINTAFULVA")

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

    # config.json: le due chiavi nuove, code_roots vuoto e gh spento per non
    # toccare ne' `~/dev` vero ne' la rete.
    plancia_home.mkdir(parents=True, exist_ok=True)
    (plancia_home / "config.json").write_text(json.dumps({
        "cartelle_escluse": [str(priv)],
        "sessioni_escluse": [sid_escluso],
        "code_roots": [],
        "gh_enabled": False,
    }), "utf-8")

    codex_home.mkdir(parents=True, exist_ok=True)

    return {
        "claude_dir": claude_dir, "plancia_home": plancia_home, "codex_home": codex_home,
        "priv": priv, "norm": norm, "altra": altra,
        "sid_priv": sid_priv, "sid_escluso": sid_escluso, "sid_norm": sid_norm,
        "cod_priv": cod_priv, "cod_norm": cod_norm,
    }


# Segnaposto sostituiti a mano (str.replace, non str.format: vedi il
# docstring del modulo per il perché) con repr() dei valori veri, quindi
# ognuno diventa una stringa Python valida, tra virgolette, nello script.
SCRIPT = r"""
import json, sys
sys.path.insert(0, __RADICE__)
from plancia import config, ingest, store

esito = {}

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

# ---------------------------------------------------------------- fase 2
try:
    from plancia import esclusi
    escl = esclusi.carica()
    priv = __PRIV__
    norm = __NORM__

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

    conn.execute(
        "INSERT INTO meta(key, value) VALUES ('live_session','man-priv-0001') "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value")

    conn.commit()

    from plancia import eventi as _eventi
    riga_priv = json.dumps({"schema": "plancia.evento/1", "id": "e1",
                            "ts": "2026-01-01T00:00:00Z", "tipo": "lavoro.avviato",
                            "titolo": "lancio privato MANOEVENTOPRIVXX",
                            "progetto": None, "origine": "cantiere",
                            "dati": {"cwd": priv, "run": 1}})
    riga_norm = json.dumps({"schema": "plancia.evento/1", "id": "e2",
                            "ts": "2026-01-01T00:00:00Z", "tipo": "lavoro.avviato",
                            "titolo": "lancio normale MANOEVENTONORMXX",
                            "progetto": None, "origine": "cantiere",
                            "dati": {"cwd": norm, "run": 2}})
    _eventi.FILE.write_text(riga_priv + "\n" + riga_norm + "\n", "utf-8")

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

    testo_eventi = _eventi.FILE.read_text("utf-8")
    esito["eventi_jsonl_priv"] = "MANOEVENTOPRIVXX" in testo_eventi
    esito["eventi_jsonl_norm"] = "MANOEVENTONORMXX" in testo_eventi
except Exception as exc:
    esito["purga_ok"] = False
    esito["purga_errore"] = repr(exc)

print(json.dumps(esito))
"""


def _esegui_sottoprocesso(fix: dict) -> dict:
    script = SCRIPT
    for segnaposto, valore in (
        ("__RADICE__", str(RADICE)), ("__SID_PRIV__", fix["sid_priv"]),
        ("__SID_ESCLUSO__", fix["sid_escluso"]), ("__SID_NORM__", fix["sid_norm"]),
        ("__PRIV__", str(fix["priv"])), ("__NORM__", str(fix["norm"])),
        ("__COD_PRIV__", fix["cod_priv"]), ("__COD_NORM__", fix["cod_norm"]),
    ):
        script = script.replace(segnaposto, repr(valore))

    script_path = fix["plancia_home"].parent / "sottoprocesso.py"
    script_path.write_text(script, "utf-8")

    env = dict(os.environ)
    env["PLANCIA_HOME"] = str(fix["plancia_home"])
    env["CLAUDE_CONFIG_DIR"] = str(fix["claude_dir"])
    env["CODEX_HOME"] = str(fix["codex_home"])
    proc = subprocess.run([sys.executable, str(script_path)], capture_output=True,
                          text=True, env=env, timeout=60)
    try:
        ultima_riga = [r for r in proc.stdout.splitlines() if r.strip()][-1]
        return json.loads(ultima_riga)
    except Exception as exc:
        return {"_fallito": True, "_eccezione": repr(exc),
                "_stdout": proc.stdout[-4000:], "_stderr": proc.stderr[-4000:]}


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

        c = r.get("conteggi") or {}
        prova("il conteggio di purga riporta esattamente le sessioni tolte (1)",
              c.get("sessioni") == 1, str(c))
        prova("il conteggio di purga riporta esattamente i task tolti (2)",
              c.get("tasks") == 2, str(c))
        prova("il conteggio di purga riporta esattamente i link di percorso tolti (3)",
              c.get("link_percorso") == 3, str(c))
        prova("il conteggio di purga riporta esattamente il progetto orfano tolto (1)",
              c.get("progetti") == 1, str(c))
    finally:
        import shutil
        shutil.rmtree(str(base), ignore_errors=True)
