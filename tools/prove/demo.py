"""Prove per LOTTO-L2-DEMO: `tools/demo-data.py` (aree, i tre stati di
"Riprendi", più di 7 progetti attivi, nessun nome reale).

`demo-data.py` gira qui in una `PLANCIA_HOME` **propria e isolata**, aperta
in un sottoprocesso invece che riassegnando `os.environ["PLANCIA_HOME"]` (vedi
`tools/prove/README.md`): al momento in cui `tools/prova.py` chiama
`esegui()`, quella condivisa (`CASA`) ha già passato duecento altre prove che
scrivono e cancellano righe nelle stesse tabelle, quindi contare progetti o
task lì darebbe un numero che non è più quello di `demo-data.py`.
"""

import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent.parent

NOMI_VIETATI_FILE = "nomi-vietati.txt"
NOMI_VIETATI_ENV = "PLANCIA_NOMI_VIETATI"

# Il repo è pubblico: cognomi veri e nomi di progetti privati non possono
# stare nel codice (erano qui, elencati per nome - LOTTO-L2-DEMO punto 2).
# Senza un file locale o una variabile d'ambiente (vedi _nomi_vietati più
# sotto), la prova usa solo questa lista generica, che non svela niente.
VIETATE_GENERICO = ()


def _isola():
    """`demo-data.py` in una `PLANCIA_HOME` temporanea; torna `(conn, casa)`."""
    casa = Path(tempfile.mkdtemp(prefix="plancia-prova-demo-"))
    ambiente = dict(os.environ, PLANCIA_HOME=str(casa))
    esito = subprocess.run([sys.executable, str(RADICE / "tools" / "demo-data.py")],
                           capture_output=True, env=ambiente, text=True)
    if esito.returncode != 0:
        raise RuntimeError(esito.stderr[-800:] or esito.stdout[-800:])
    conn = sqlite3.connect(str(casa / "plancia.db"))
    conn.row_factory = sqlite3.Row
    return conn, casa


def _nomi_vietati():
    """Nomi vietati nei dati demo: file locale, variabile d'ambiente, o
    (senza nessuno dei due) `VIETATE_GENERICO`; torna `(nomi, dettaglio)`.

    Il file sta in `config.DATA_DIR` (~/.plancia di norma, o dove punta
    `PLANCIA_HOME`) apposta fuori da questo repo pubblico, uno per riga:
    così sulla propria macchina si può continuare a controllare cognomi
    veri e nomi di progetti privati senza scriverli nel codice.
    """
    from plancia import config

    percorso = config.DATA_DIR / NOMI_VIETATI_FILE
    if percorso.exists():
        nomi = [r.strip().lower() for r in percorso.read_text("utf-8").splitlines()
                if r.strip()]
        return nomi, f"elenco locale: {percorso}"

    da_ambiente = os.environ.get(NOMI_VIETATI_ENV, "")
    if da_ambiente.strip():
        nomi = [n.strip().lower() for n in da_ambiente.split(",") if n.strip()]
        return nomi, f"elenco da {NOMI_VIETATI_ENV}"

    return list(VIETATE_GENERICO), "nessun elenco locale di nomi vietati: controllo generico"


def esegui(prova):
    try:
        conn, casa = _isola()
    except Exception as errore:  # noqa: BLE001 - un lotto non affossa gli altri
        prova("demo-data.py gira su una casa isolata senza errori", False, str(errore))
        return

    try:
        # ---------------------------------------------------------- le tre aree
        padri = conn.execute(
            "SELECT id, key FROM projects WHERE parent_id IS NULL AND auto=0"
        ).fetchall()
        figli_per_padre = {}
        for p in padri:
            n = conn.execute("SELECT COUNT(*) FROM projects WHERE parent_id=?",
                             (p["id"],)).fetchone()[0]
            if n:
                figli_per_padre[p["key"]] = n
        con_tre = {k: n for k, n in figli_per_padre.items() if n >= 3}
        prova("almeno 3 aree (padri manuali) con almeno 3 figli l'una",
              len(con_tre) >= 3, str(figli_per_padre))

        # ------------------------------------------------------- progetti attivi
        attivi = conn.execute(
            "SELECT COUNT(*) FROM projects WHERE status='attivo'").fetchone()[0]
        prova("più di 7 progetti attivi", attivi > 7, f"attivi: {attivi}")

        # ---------------------------------------- ultime attività scaglionate
        # Correzione del critico 18/09: senza questa prova, un progetto nuovo
        # con last_activity NULL passava lo stesso ("più di 7 attivi" non
        # guarda quella colonna) e finiva "never" nel pannello Prossimi.
        righe = conn.execute(
            "SELECT key, last_activity FROM projects WHERE status='attivo'").fetchall()
        senza_attivita = [r["key"] for r in righe if not r["last_activity"]]
        prova("ogni progetto attivo ha un'ultima attività (nessun 'never')",
              not senza_attivita, f"senza last_activity: {senza_attivita}")
        distinte = {r["last_activity"] for r in righe if r["last_activity"]}
        prova("le ultime attività sono scaglionate (almeno 3 valori distinti)",
              len(distinte) >= 3, f"valori distinti: {len(distinte)}")

        # ------------------------------------------------- progetti senza area
        senza_area = conn.execute(
            "SELECT COUNT(*) FROM projects p WHERE p.parent_id IS NULL "
            "AND NOT EXISTS (SELECT 1 FROM projects f WHERE f.parent_id=p.id)"
        ).fetchone()[0]
        prova("qualche progetto resta senza area (né padre né figlio)",
              senza_area >= 1, f"senza area: {senza_area}")

        # ---------------------------------------------------- i tre stati di ripresa
        from plancia import config, riprendi  # noqa: E402 - solo qui, dopo l'isolamento

        chiusa = conn.execute(
            "SELECT * FROM tasks WHERE session_id='demo-closed-01'").fetchone()
        altro_host = conn.execute(
            "SELECT * FROM tasks WHERE session_id='demo-otherhost-01'").fetchone()
        senza_sessione = conn.execute(
            "SELECT * FROM tasks WHERE status IN ('aperto','in corso','bloccato') "
            "AND (session_id IS NULL OR session_id='') LIMIT 1").fetchone()

        prova("un task rappresenta 'persa' (mai registrata)", senza_sessione is not None)
        if senza_sessione is not None:
            esito = riprendi.stato(conn, senza_sessione)
            prova("...e riprendi.stato lo dice: 'persa'",
                  esito["stato"] == "persa", str(esito))

        prova("un task rappresenta 'persa' (host diverso)", altro_host is not None)
        if altro_host is not None:
            esito = riprendi.stato(conn, altro_host)
            prova("...e riprendi.stato lo dice: 'persa', per l'host che non è questo",
                  esito["stato"] == "persa" and altro_host["host"] != socket.gethostname(),
                  str(esito))

        prova("un task rappresenta 'chiusa'", chiusa is not None)
        if chiusa is not None:
            # config.CLAUDE_DIR e PLANCIA_AGENTS_JSON spostati sulla casa finta
            # solo per questa chiamata (stesso schema di tools/prove/sessione.py):
            # mai il ~/.claude vero, e mai un sottoprocesso `claude agents --json`
            # vero (il file JSON finto, vuoto, lo sostituisce - vedi il
            # commento su riprendi._claude_vivo).
            vecchio_dir = config.CLAUDE_DIR
            vecchio_agents = os.environ.get("PLANCIA_AGENTS_JSON")
            finto_agenti = casa / "agenti-vuoti.json"
            finto_agenti.write_text("[]", encoding="utf-8")
            config.CLAUDE_DIR = casa / "claude-config"
            os.environ["PLANCIA_AGENTS_JSON"] = str(finto_agenti)
            try:
                esito = riprendi.stato(conn, chiusa)
            finally:
                config.CLAUDE_DIR = vecchio_dir
                if vecchio_agents is None:
                    os.environ.pop("PLANCIA_AGENTS_JSON", None)
                else:
                    os.environ["PLANCIA_AGENTS_JSON"] = vecchio_agents
            prova("...e riprendi.stato lo dice: 'chiusa' (trova la trascrizione finta)",
                  esito["stato"] == "chiusa", str(esito))

        # "viva" non ha una riga qui: non è simulabile senza un processo vero
        # (vedi il commento su TASK_RIPRESA in tools/demo-data.py).

        # -------------------------------------------------------- nessun nome vero
        # Solo il testo che questo file inventa (progetti, task, post, memorie,
        # lavagna, lanci, repo, commit): non le colonne che ripetono il
        # vocabolario fisso del programma vero, sempre uguale su qualunque
        # installazione, demo o no, e che quindi non "svela" niente:
        # - agenda.fonte/agente valgono letteralmente 'claude'/'codex'/'plancia'
        #   ovunque (plancia/lavagna.py:130 e la stringa scritta qui sotto,
        #   "i task di Plancia stanno sulla lavagna");
        # - capabilities: la skill che il demo elenca si chiama "plancia" perché
        #   quella è la skill vera che si installa (plancia/setup_claude.py:32,
        #   SKILL_DIR = .../skills/plancia), non un nome scelto da demo-data.py.
        #
        # I nomi vietati (cognomi, sigle di progetti privati) non sono più
        # elencati qui: il repo è pubblico, e quella lista li avrebbe
        # esposti. Vengono da un file locale o da una variabile d'ambiente
        # (`_nomi_vietati`, sopra); senza nessuno dei due il controllo resta
        # generico e non fallisce.
        COLONNE_TESTO = {
            "projects": ("key", "name", "summary", "next_action"),
            "tasks": ("title", "body"),
            "posts": ("text",),
            "knowledge": ("name", "description", "body"),
            "agenda": ("titolo", "dettaglio"),
            "sessions": ("title", "first_prompt"),
            "runs": ("prompt", "esito"),
            "repos": ("description",),
            "commits": ("message",),
        }
        pezzi = []
        for tabella, colonne in COLONNE_TESTO.items():
            for r in conn.execute(f"SELECT {', '.join(colonne)} FROM {tabella}"):
                pezzi.extend(v for v in tuple(r) if v)
        testo = " ".join(pezzi).lower()
        vietati, dettaglio_vietati = _nomi_vietati()
        trovate = [p for p in vietati if p in testo]
        prova(f"nessun nome reale nel testo inventato dal demo ({dettaglio_vietati})",
              not trovate, str(trovate))
    finally:
        conn.close()
        shutil.rmtree(casa, ignore_errors=True)
