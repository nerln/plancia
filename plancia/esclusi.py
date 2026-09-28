"""Cartelle e sessioni private: un posto solo per dire a Plancia di non
vederle.

Due modi, pensati per usarsi insieme:

- `cartelle_escluse`: percorsi assoluti. Tutto quello che sta in una di quelle
  cartelle, o sotto, è privato: le sue sessioni, la sua memoria, il suo repo.
- `sessioni_escluse`: id di sessione singoli (Claude Code o Codex), per una
  sessione aperta FUORI da una cartella esclusa che però ha lavorato su una
  cosa privata.

Ogni punto d'ingresso di ingest.py (e i suoi vicini: codex.py, turni.py,
bin/plancia-hook) chiama i predicati di qui PRIMA di scrivere nel database.
`purga()` toglie quello che era già entrato prima che la regola esistesse, o
che un punto d'ingresso non ha visto in tempo (vedi il commento su `sync()` in
ingest.py: un giro di ritardo è il prezzo accettato, non un bug).

Tutto qui dentro è generico apposta: nessuna di queste funzioni sa, né deve
sapere, quale cartella o sessione le viene passata. Lo decide chi chiama, non
chi implementa il controllo.
"""

import json
import os
import re
from pathlib import Path

from . import config, store


def _norm(path) -> str:
    """Un percorso assoluto, risolto fino in fondo.

    `os.path.realpath` funziona anche su un percorso che non esiste più
    (risolve solo i pezzi iniziali che esistono davvero), quindi va bene
    anche per una cartella esclusa e poi cancellata. Risolvere è necessario
    perché su questa macchina `/tmp` è un symlink a `/private/tmp`: una
    cartella esclusa scritta con l'uno deve riconoscere anche l'altro, o metà
    delle sessioni temporanee sfuggirebbe al controllo.
    """
    if not path:
        return ""
    p = os.path.realpath(os.path.expanduser(str(path)))
    return p.rstrip(os.sep) or os.sep


def _codifica(path_normalizzato: str) -> str:
    """Come Claude Code trasforma una cartella nel nome che le dà sotto
    `~/.claude/projects`: ogni carattere che non è `[A-Za-z0-9]` diventa un
    trattino, uno per uno, senza comprimere le sequenze.

    Misurato il 28/09/2026 sui nomi veri di `~/.claude/projects` di questa
    macchina (solo nomi, in sola lettura): una cartella `.claude-worktrees`
    dentro un progetto produce un trattino doppio nel nome codificato (il `/`
    che la precede e il `.` iniziale del suo nome, due caratteri non
    alfanumerici di fila, restano due trattini distinti — non uno). E il
    percorso del Drive (che ha già un trattino vero dentro il nome della
    cartella `GoogleDrive-<email>`) produce lo stesso numero di trattini dei
    caratteri non alfanumerici dell'originale. Comprimere le sequenze di
    trattini avrebbe fatto collassare quel doppio trattino in uno solo,
    smentito dal nome vero.
    """
    return re.sub(r"[^A-Za-z0-9]", "-", path_normalizzato)


def carica(cfg: dict = None) -> dict:
    """Le cartelle e le sessioni escluse, già pronte all'uso.

    Da calcolare una volta per sync (o per comando) e passare in giro, invece
    di rileggere config.json e ripetere `realpath()`/regex per ogni file: con
    centinaia di trascrizioni è la differenza fra un conto e un migliaio.
    """
    cfg = cfg if cfg is not None else config.load_config()
    cartelle = []
    for c in cfg.get("cartelle_escluse") or []:
        n = _norm(c)
        if n:
            cartelle.append(n)
    return {
        "cartelle": cartelle,
        "codifiche": [_codifica(c) for c in cartelle],
        "sessioni": {s for s in (cfg.get("sessioni_escluse") or []) if s},
    }


def configurato(esclusi: dict) -> bool:
    return bool(esclusi["cartelle"] or esclusi["sessioni"])


def percorso_escluso(path, esclusi: dict) -> bool:
    """Un percorso vero (una cwd, il `local_path` di un repo) sotto una
    cartella esclusa, o uguale a lei.

    Il confronto è sul percorso intero seguito da un separatore, non su un
    prefisso di stringa nudo: `/foo/bar` non deve escludere `/foo/barba`.
    """
    if not path or not esclusi["cartelle"]:
        return False
    p = _norm(path)
    return any(p == c or p.startswith(c + os.sep) for c in esclusi["cartelle"])


def progetto_escluso(nome_cartella: str, esclusi: dict) -> bool:
    """Il nome di una cartella di `~/.claude/projects` (già codificata con i
    trattini) è escluso se è la codifica esatta di una cartella esclusa, o
    comincia con quella codifica seguita da un trattino (una sua
    sottocartella). Escludere un po' di più, qui, è il verso giusto: è lo
    stesso principio con cui `esclusi.py` viene chiamato ovunque, non solo
    dove il progetto ha già un nome.
    """
    if not nome_cartella or not esclusi["codifiche"]:
        return False
    return any(nome_cartella == c or nome_cartella.startswith(c + "-")
               for c in esclusi["codifiche"])


def _componenti_progetti(percorso, radice=None):
    """`percorso` (dentro la radice di `~/.claude/projects`) spezzato in
    componenti: il primo è il nome della cartella di progetto codificata, gli
    altri sono le sottocartelle, e l'ultimo ha l'estensione tolta (lo stem del
    file, non il nome intero: così un confronto con un id di sessione non
    fallisce per colpa di `.jsonl`).

    `radice` di norma è `None` e allora si ricalcola `config.CLAUDE_DIR /
    "projects"` a ogni chiamata invece di usare la costante di modulo
    `config.CLAUDE_PROJECTS`: una prova che sposta `config.CLAUDE_DIR` per
    isolarsi (come fa più di una in tools/prove/) non tocca quella costante,
    già congelata al primo import (stesso motivo per cui turni.py fa lo
    stesso calcolo invece di usare la costante). Chi ha già un'altra radice in
    mano (turni.indicizza, che la riceve da chi lo chiama) la passa qui.

    Torna `None` se `percorso` non sta sotto quella radice.
    """
    radice = radice if radice is not None else (config.CLAUDE_DIR / "projects")
    try:
        parti = Path(percorso).relative_to(radice).parts
    except ValueError:
        return None
    if not parti:
        return None
    return parti[:-1] + (Path(parti[-1]).stem,)


def trascrizione_esclusa(percorso, esclusi: dict, radice=None) -> bool:
    """Un file sotto `~/.claude/projects` (una trascrizione o una memoria) da
    non toccare: o la sua cartella di progetto è esclusa, o uno qualunque dei
    suoi componenti di percorso (la cartella della sessione, `subagents`,
    `workflows`, o lo stem del file) è un id in `sessioni_escluse`.

    Il secondo caso è quello che fa cadere anche un sottoagente in
    `<id-escluso>/subagents/workflows/<altro-id>.jsonl`: l'id della sessione
    padre compare come componente di percorso anche lì, non solo come nome
    del file principale.
    """
    if not configurato(esclusi):
        return False
    componenti = _componenti_progetti(percorso, radice)
    if componenti is None:
        return False
    if progetto_escluso(componenti[0], esclusi):
        return True
    return bool(esclusi["sessioni"]) and any(c in esclusi["sessioni"] for c in componenti)


def sessione_esclusa(session_id, cwd, esclusi: dict) -> bool:
    """Una sessione (Claude Code o Codex) da non vedere: per il suo id
    esplicito, o perché la cartella da cui è partita è esclusa."""
    if session_id and esclusi["sessioni"] and session_id in esclusi["sessioni"]:
        return True
    return percorso_escluso(cwd, esclusi)


# --------------------------------------------------------------------------
# eventi.jsonl: stesso principio, un file invece di una tabella
# --------------------------------------------------------------------------

def _riga_evento_esclusa(evento: dict, esclusi: dict) -> bool:
    """Una riga di `~/.plancia/eventi.jsonl` (plancia/eventi.py) da non
    tenere.

    Oggi l'unico campo che arriva popolato in modo affidabile è `dati.cwd`,
    scritto da cantiere.py per un lancio (`lavoro.avviato/completato/
    fallito`). Gli altri tipi di evento che passano da qui (task, post,
    progetto) non portano né una cwd né un id di sessione dentro il loro
    `dati` di oggi: restano fuori da questo controllo. È un limite noto,
    scritto nel rapporto del lotto, non un'omissione silenziosa.
    """
    dati = evento.get("dati")
    if not isinstance(dati, dict):
        return False
    if percorso_escluso(dati.get("cwd"), esclusi):
        return True
    if esclusi["sessioni"]:
        for chiave in ("session_id", "sessione"):
            valore = dati.get(chiave)
            if valore and valore in esclusi["sessioni"]:
                return True
    return False


def _file_eventi():
    from . import eventi
    return eventi.FILE, eventi.FILE.with_suffix(".1.jsonl")


def conta_eventi_jsonl(esclusi: dict) -> int:
    """Quante righe di eventi.jsonl (attivo + ruotato) `pulisci_eventi_jsonl`
    toglierebbe. Sola lettura: usata da `conta()` per `--prova`."""
    if not configurato(esclusi):
        return 0
    n = 0
    for percorso in _file_eventi():
        if not percorso.exists():
            continue
        try:
            testo = percorso.read_text("utf-8")
        except OSError:
            continue
        for riga in testo.splitlines():
            if not riga.strip():
                continue
            try:
                evento = json.loads(riga)
            except Exception:
                continue
            if _riga_evento_esclusa(evento, esclusi):
                n += 1
    return n


def pulisci_eventi_jsonl(esclusi: dict) -> int:
    """Riscrive eventi.jsonl (e il suo file ruotato, se c'è) senza le righe
    di sessioni o cartelle escluse.

    Riscrittura atomica: si scrive un file temporaneo nella stessa cartella e
    si rinomina sopra (`os.replace`, atomico sullo stesso filesystem), così
    chi legge il file tenendo un segnalibro (`eventi.leggi`) non lo trova mai
    a metà.
    """
    if not configurato(esclusi):
        return 0
    tolte = 0
    for percorso in _file_eventi():
        if not percorso.exists():
            continue
        try:
            testo = percorso.read_text("utf-8")
        except OSError:
            continue
        righe_nuove, cambiato = [], False
        for riga in testo.splitlines():
            if not riga.strip():
                continue
            try:
                evento = json.loads(riga)
            except Exception:
                righe_nuove.append(riga)
                continue
            if _riga_evento_esclusa(evento, esclusi):
                tolte += 1
                cambiato = True
                continue
            righe_nuove.append(riga)
        if cambiato:
            tmp = percorso.with_name(percorso.name + ".tmp")
            corpo = "\n".join(righe_nuove)
            tmp.write_text(corpo + "\n" if corpo else "", "utf-8")
            os.replace(tmp, percorso)
    return tolte


# --------------------------------------------------------------------------
# la pulizia del database: quello che era già entrato prima della regola
# --------------------------------------------------------------------------

def _in(valori) -> str:
    return ",".join("?" * len(valori))


def _bersagli(conn, esclusi: dict) -> dict:
    """Cosa la pulizia toglierebbe dal database, calcolato una volta sola.

    `conta()` (per `--prova`) e `purga()` condividono questa funzione: così
    il conto mostrato e quello che succede davvero non possono mai
    divergere, sono lo stesso codice.
    """
    # turni_fts/turni_file non sono nello schema di store.py: le crea
    # turni.prepara() (CREATE TABLE IF NOT EXISTS, quindi innocuo se
    # esistono già). Un'installazione che non ha ancora fatto un sync
    # arriva qui senza quelle tabelle (misurato lanciando `plancia esclusi`
    # su un archivio appena creato, prima di questa riga: "no such table:
    # turni_file"). Import qui dentro, non in cima al file: turni.py importa
    # esclusi, e in cima sarebbe un giro (turni -> esclusi -> turni).
    from . import turni
    turni.prepara(conn)

    righe_sessioni = conn.execute("SELECT session_id, cwd FROM sessions").fetchall()
    sid_esclusi = [r["session_id"] for r in righe_sessioni
                   if sessione_esclusa(r["session_id"], r["cwd"], esclusi)]
    sid_set = set(sid_esclusi)

    tasks = [r["id"] for r in conn.execute(
        "SELECT id, session_id, cwd FROM tasks").fetchall()
        if r["session_id"] in sid_set or percorso_escluso(r["cwd"], esclusi)]

    posts = ([r["id"] for r in conn.execute(
        "SELECT id, session_id FROM posts").fetchall() if r["session_id"] in sid_set]
        if sid_set else [])

    eventi_db = ([r["id"] for r in conn.execute(
        "SELECT id, ref FROM events WHERE kind IN ('sessione','hook','scambio')").fetchall()
        if r["ref"] in sid_set] if sid_set else [])

    # Nome diverso dal modulo `turni` importato qui sopra: un'assegnazione
    # locale con lo stesso nome lo ombreggerebbe per il resto della funzione,
    # e una chiamata futura a `turni.qualcosa()` più sotto fallirebbe con un
    # AttributeError su una lista invece che sul modulo.
    turni_percorsi = [r["percorso"] for r in conn.execute("SELECT percorso FROM turni_file").fetchall()
                     if trascrizione_esclusa(r["percorso"], esclusi)]

    memorie = [r["path"] for r in conn.execute("SELECT path FROM knowledge").fetchall()
               if trascrizione_esclusa(r["path"], esclusi)]

    repos = [r["id"] for r in conn.execute(
        "SELECT id, local_path FROM repos WHERE local_path IS NOT NULL AND local_path <> ''"
    ).fetchall() if percorso_escluso(r["local_path"], esclusi)]

    link_percorso = [(r["id"], r["project_id"]) for r in conn.execute(
        "SELECT id, project_id, value FROM project_links WHERE kind='path'").fetchall()
        if percorso_escluso(r["value"], esclusi)]

    live = store.get_meta(conn, "live_session")
    live_da_pulire = bool(live) and live in sid_set

    return {
        "sessioni": sid_esclusi, "tasks": tasks, "posts": posts, "eventi": eventi_db,
        "turni": turni_percorsi, "memorie": memorie, "repos": repos,
        "link_percorso": link_percorso, "live_session": live_da_pulire,
    }


def _progetti_orfani(conn, link_percorso, applica: bool) -> int:
    """Fra i progetti automatici che perdono un link di percorso, quanti non
    ne conservano nessun altro.

    Senza più niente che li identifichi, la scheda sparisce anche lei: è
    nata SOLO perché l'ingest ha visto quella cartella (progetto_per_cartella,
    auto=1), e quella cartella è ora esclusa. `project_links` ha
    `ON DELETE CASCADE` sul progetto: cancellare la scheda toglie da sola i
    link di percorso residui, che a quel punto sono solo quelli appena
    contati (altrimenti il progetto non sarebbe risultato orfano). Non si
    tocca mai un progetto con `auto=0`: quello lo ha dichiarato una persona,
    e un link di troppo si toglie, la scheda no.
    """
    per_progetto = {}
    for _, pid in link_percorso:
        per_progetto[pid] = per_progetto.get(pid, 0) + 1
    orfani = []
    for pid, tolti in per_progetto.items():
        riga = conn.execute("SELECT auto FROM projects WHERE id=?", (pid,)).fetchone()
        if not riga or not riga["auto"]:
            continue
        totali = conn.execute(
            "SELECT COUNT(*) FROM project_links WHERE project_id=?", (pid,)).fetchone()[0]
        if totali <= tolti:
            orfani.append(pid)
    if applica and orfani:
        conn.execute(f"DELETE FROM projects WHERE id IN ({_in(orfani)})", orfani)
    return len(orfani)


def conta(conn, esclusi: dict = None) -> dict:
    """Quel che `purga()` toglierebbe, senza toccare niente (`--prova`)."""
    esclusi = esclusi if esclusi is not None else carica()
    if not configurato(esclusi):
        return {}
    b = _bersagli(conn, esclusi)
    return {
        "sessioni": len(b["sessioni"]), "eventi": len(b["eventi"]),
        "tasks": len(b["tasks"]), "posts": len(b["posts"]),
        "turni": len(b["turni"]), "memorie": len(b["memorie"]),
        "repos": len(b["repos"]), "link_percorso": len(b["link_percorso"]),
        "progetti": _progetti_orfani(conn, b["link_percorso"], applica=False),
        "eventi_jsonl": conta_eventi_jsonl(esclusi),
    }


def purga(conn, esclusi: dict = None) -> dict:
    """La pulizia vera: toglie dal database e da eventi.jsonl quello che è
    già entrato prima che una cartella o una sessione fosse esclusa, o che un
    punto d'ingresso non ha visto in tempo.

    Con le liste vuote è un no-op immediato (un `load_config()` e due `.get`,
    nessuna query): chi non usa la funzione non ne paga il costo. Va chiamata
    a ogni sync — se qualcosa sfugge a un punto d'ingresso, esce ripulito al
    giro dopo.
    """
    esclusi = esclusi if esclusi is not None else carica()
    if not configurato(esclusi):
        return {}
    b = _bersagli(conn, esclusi)
    conteggi = {}

    def _cancella(tabella, colonna, valori):
        if not valori:
            return 0
        return conn.execute(
            f"DELETE FROM {tabella} WHERE {colonna} IN ({_in(valori)})", valori).rowcount

    conteggi["sessioni"] = _cancella("sessions", "session_id", b["sessioni"])
    conteggi["eventi"] = _cancella("events", "id", b["eventi"])
    conteggi["tasks"] = _cancella("tasks", "id", b["tasks"])
    conteggi["posts"] = _cancella("posts", "id", b["posts"])
    conteggi["turni"] = _cancella("turni_fts", "percorso", b["turni"])
    _cancella("turni_file", "percorso", b["turni"])
    conteggi["memorie"] = _cancella("knowledge", "path", b["memorie"])
    conteggi["repos"] = _cancella("repos", "id", b["repos"])

    # I progetti orfani vanno tolti PRIMA di guardare quali link sono
    # sopravvissuti: cancellare la scheda porta via da sola (CASCADE) i suoi
    # link di percorso, che altrimenti proveremmo a cancellare una seconda
    # volta (innocuo: DELETE su una riga già sparita non fa niente, ma il
    # conto qui sotto li conterebbe due volte se non distinguessimo i due
    # gruppi).
    conteggi["progetti"] = _progetti_orfani(conn, b["link_percorso"], applica=True)
    pid_sopravvissuti = {pid for _, pid in b["link_percorso"]
                         if conn.execute("SELECT 1 FROM projects WHERE id=?",
                                        (pid,)).fetchone() is not None}
    residui = [link_id for link_id, pid in b["link_percorso"] if pid in pid_sopravvissuti]
    if residui:
        conn.execute(f"DELETE FROM project_links WHERE id IN ({_in(residui)})", residui)
    conteggi["link_percorso"] = len(b["link_percorso"])

    if b["live_session"]:
        conn.execute("DELETE FROM meta WHERE key IN ('live_session','live_since')")

    conteggi["eventi_jsonl"] = pulisci_eventi_jsonl(esclusi)

    conn.commit()
    if any(conteggi.values()):
        store.rebuild_search(conn)
        conn.commit()
    return conteggi
