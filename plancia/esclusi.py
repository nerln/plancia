"""Cartelle e sessioni private: un posto solo per dire a Plancia di non
vederle.

Due modi, pensati per usarsi insieme:

- `cartelle_escluse`: percorsi assoluti. Tutto quello che sta in una di quelle
  cartelle, o sotto, è privato: le sue sessioni, la sua memoria, il suo repo.
- `sessioni_escluse`: id di sessione singoli (Claude Code o Codex), per una
  sessione aperta FUORI da una cartella esclusa che però ha lavorato su una
  cosa privata.

Ogni punto d'ingresso di ingest.py (e i suoi vicini: codex.py, turni.py,
lavagna.py, bin/plancia-hook, mcp.py) chiama i predicati di qui PRIMA di
scrivere nel database. `purga()` toglie quello che era già entrato prima che
la regola esistesse, o che un punto d'ingresso non ha visto in tempo (vedi il
commento su `sync()` in ingest.py: un giro di ritardo è il prezzo accettato,
non un bug).

Una sessione aperta in una cartella NORMALE e poi spostata (con un tool che
cambia la cwd, non un `cd` di shell) dentro una cartella privata è il caso che
non si vede guardando solo il percorso del file: il nome della cartella di
`~/.claude/projects` resta quello di dov'è stata APERTA, non di dove ha
lavorato. `sync_sessions`/`codex.sync` (ingest.py, codex.py) leggono anche il
contenuto e, quando lo scoprono, chiamano `segna_scoperto()`: da quel momento
l'id resta nell'insieme delle sessioni escluse — per questo stesso giro di
sync (l'oggetto `esclusi` passato in giro è mutato sul posto) e per tutti i
successivi (persistito in una tabella), così `turni.indicizza`, `lavagna.sync`
e il server MCP lo vedono senza dover rileggere il transcript ogni volta.

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


# --------------------------------------------------------------------------
# validazione di config.json: fail-closed, non "niente escluso" in silenzio
# --------------------------------------------------------------------------

# Gli id di sessione (Claude Code e Codex) sono uuid: un valore che non ha
# questa forma non può essere un id vero, ed è quasi sempre un refuso di chi
# ha scritto config.json a mano.
_ID_VALIDO = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def _grafia_vera(path_assoluto: str):
    """`path_assoluto`, con ogni componente ricondotta a come sta scritta
    davvero sul disco, o None se un componente qualunque non esiste.

    APFS (il filesystem di macOS, di default) non distingue le maiuscole ma
    le conserva: `os.path.realpath` risolve i symlink e i `..` ma NON
    corregge il maiuscolo/minuscolo, quindi una cartella esclusa scritta
    "privato/x" e una cwd vera "Privato/X" restano stringhe diverse anche se
    sono la stessa cartella (misurato: `percorso_escluso` dava False). Si
    cammina componente per componente con `os.scandir`, che la casing la
    conosce, e si prende quella.
    """
    risolto = os.path.realpath(path_assoluto)
    pezzi = [p for p in Path(risolto).parts if p not in (os.sep, "")]
    corrente = os.sep
    if not os.path.isdir(corrente):
        return None
    for pezzo in pezzi:
        try:
            trovato = next((e.name for e in os.scandir(corrente)
                            if e.name.lower() == pezzo.lower()), None)
        except OSError:
            return None
        if trovato is None:
            return None
        corrente = os.path.join(corrente, trovato)
    return corrente.rstrip(os.sep) or os.sep


def valida(cfg: dict):
    """La forma di `cartelle_escluse`/`sessioni_escluse` in `cfg`, controllata
    fino in fondo. Torna `(ok, errore, cartelle, sessioni)`.

    Fail-closed per costruzione: un problema qualunque (il tipo sbagliato, un
    percorso relativo, una cartella che non esiste, una cartella troppo
    ampia, un id che non è un uuid) rifiuta TUTTO il file, non solo la voce
    sbagliata. Misurato (config_rotta.py, in isolamento): con
    `"cartelle_escluse": "~/Privato/segreto"` (una stringa al posto di una
    lista) il vecchio codice la iterava carattere per carattere e otteneva
    dei singoli caratteri come "cartelle" — fra cui, per alcuni percorsi,
    l'equivalente di HOME o di `/`. Un errore di battitura non deve mai
    tradursi in «via libera a tutto»: da qui la scelta di rifiutare l'intero
    file piuttosto che provare a salvare la voce buona.
    """
    grezze_cartelle = cfg.get("cartelle_escluse") or []
    grezze_sessioni = cfg.get("sessioni_escluse") or []

    if not isinstance(grezze_cartelle, list) or not all(
            isinstance(c, str) for c in grezze_cartelle):
        return False, "cartelle_escluse deve essere una lista di stringhe", [], []
    if not isinstance(grezze_sessioni, list) or not all(
            isinstance(s, str) for s in grezze_sessioni):
        return False, "sessioni_escluse deve essere una lista di stringhe", [], []

    protette = [str(config.HOME), str(config.CLAUDE_DIR), str(config.DATA_DIR)]
    protette_norm = [os.path.realpath(p).rstrip(os.sep) or os.sep for p in protette]

    cartelle = []
    for grezza in grezze_cartelle:
        assoluto = os.path.expanduser(grezza)
        if not os.path.isabs(assoluto):
            return False, f"cartella_esclusa non assoluta: {grezza!r}", [], []
        vera = _grafia_vera(assoluto)
        if vera is None:
            return False, f"cartella_esclusa inesistente: {grezza!r}", [], []
        if vera == os.sep:
            return False, "cartella_esclusa non può essere '/'", [], []
        for p in protette_norm:
            if vera == p or p.startswith(vera + os.sep):
                return False, (f"cartella_esclusa troppo ampia (contiene una cartella "
                               f"di sistema di Plancia): {grezza!r}"), [], []
        cartelle.append(vera)

    sessioni = []
    for sid in grezze_sessioni:
        if not _ID_VALIDO.match(sid):
            return False, f"sessione_esclusa non ha la forma di un id valido: {sid!r}", [], []
        sessioni.append(sid)

    return True, None, cartelle, sessioni


# --------------------------------------------------------------------------
# id scoperti a runtime (sessione spostata, ripresa Codex di un thread escluso)
# --------------------------------------------------------------------------

_SCHEMA_SCOPERTI = (
    "CREATE TABLE IF NOT EXISTS esclusi_scoperti ("
    "session_id TEXT PRIMARY KEY, scoperto_at TEXT NOT NULL)"
)


def prepara_scoperti(conn) -> None:
    conn.execute(_SCHEMA_SCOPERTI)
    conn.commit()


def segna_scoperto(conn, session_id, esclusi: dict = None) -> None:
    """Ricorda `session_id` come escluso, scoperto guardando il contenuto
    (non il percorso) di una trascrizione o di un rollout Codex.

    Persiste nel database, cosi' il prossimo sync non deve rileggere il file
    da capo per riscoprirlo (l'offset incrementale, dopo il primo giro, non
    rivede più le righe dove la cwd era cambiata). Se `esclusi` è dato (lo
    stesso dizionario passato in giro in questo sync), lo aggiorna anche sul
    posto: cosi' turni.indicizza, lavagna.sync e la purga finale, più avanti
    nello STESSO giro, lo vedono subito, senza aspettare il giro dopo.
    """
    if not session_id:
        return
    prepara_scoperti(conn)
    conn.execute(
        "INSERT INTO esclusi_scoperti(session_id, scoperto_at) VALUES(?,?) "
        "ON CONFLICT(session_id) DO NOTHING", (session_id, store.now()))
    conn.commit()
    if esclusi is not None:
        esclusi["sessioni"].add(session_id)


def scoperti(conn) -> set:
    prepara_scoperti(conn)
    return {r[0] for r in conn.execute("SELECT session_id FROM esclusi_scoperti")}


# --------------------------------------------------------------------------
# i predicati
# --------------------------------------------------------------------------

def carica(cfg: dict = None, conn=None) -> dict:
    """Le cartelle e le sessioni escluse, già pronte all'uso.

    Da calcolare una volta per sync (o per comando) e passare in giro, invece
    di rileggere config.json e ripetere `realpath()`/regex per ogni file: con
    centinaia di trascrizioni è la differenza fra un conto e un migliaio.

    `conn`, se dato, aggiunge all'insieme delle sessioni gli id scoperti a
    runtime (vedi `segna_scoperto`): senza un database a disposizione (per
    esempio `bin/plancia-hook`, che non lo apre mai) si vedono solo gli id
    configurati a mano, e va bene così — quelli scoperti dopo il fatto sono
    appunto un giro di ritardo accettato.
    """
    cfg = cfg if cfg is not None else config.load_config()
    cartelle = []
    for c in cfg.get("cartelle_escluse") or []:
        n = _norm(c)
        if n:
            cartelle.append(n)
    sessioni = {s for s in (cfg.get("sessioni_escluse") or []) if s}
    if conn is not None:
        sessioni = sessioni | scoperti(conn)
    return {
        "cartelle": cartelle,
        "codifiche": [_codifica(c) for c in cartelle],
        "sessioni": sessioni,
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
    `workflows`, o lo stem del file) è un id in `sessioni_escluse` (che, dopo
    `carica(conn=...)`, include anche gli id scoperti a runtime).

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


def sessione_esclusa(session_id, cwd, esclusi: dict, thread=None) -> bool:
    """Una sessione (Claude Code o Codex) da non vedere: per il suo id
    esplicito, per il thread (Codex: una ripresa è un file nuovo con un id
    nuovo, ma il thread di partenza resta lo stesso — vedi codex.py), o
    perché la cartella da cui è partita è esclusa."""
    if session_id and esclusi["sessioni"] and session_id in esclusi["sessioni"]:
        return True
    if thread and esclusi["sessioni"] and thread in esclusi["sessioni"]:
        return True
    return percorso_escluso(cwd, esclusi)


# --------------------------------------------------------------------------
# eventi.jsonl: stesso principio, un file invece di una tabella
# --------------------------------------------------------------------------

def _riga_evento_esclusa(evento: dict, esclusi: dict, bersagli: dict = None) -> bool:
    """Una riga di `~/.plancia/eventi.jsonl` (plancia/eventi.py) da non
    tenere.

    Non ogni evento porta una cwd o un id di sessione dentro il suo `dati`:
    `lavoro.completato`/`lavoro.fallito` (cantiere.py) portano invece `run`
    (l'id della riga di `runs`), `task.*`/`post.*` portano `dati.id`,
    `progetto.*`/`padre:*` (slot.py) portano la CHIAVE del progetto nel campo
    di primo livello `progetto` (e `padre:*` anche in `dati.figlio`). Senza
    `bersagli` (il dizionario che `_bersagli()` calcola: run/task/post
    cancellati, chiavi dei progetti orfani cancellati) questi casi non si
    possono riconoscere: si controlla solo cwd e id di sessione, come prima.
    """
    tipo = evento.get("tipo") or ""
    dati = evento.get("dati")
    dati = dati if isinstance(dati, dict) else {}
    if percorso_escluso(dati.get("cwd"), esclusi):
        return True
    if esclusi["sessioni"]:
        for chiave in ("session_id", "sessione"):
            valore = dati.get(chiave)
            if valore and valore in esclusi["sessioni"]:
                return True
    b = bersagli or {}
    if dati.get("run") in (b.get("runs") or ()):
        return True
    if tipo.startswith("task.") and dati.get("id") in (b.get("tasks") or ()):
        return True
    if tipo.startswith("post.") and dati.get("id") in (b.get("posts") or ()):
        return True
    if tipo.startswith(("progetto.", "padre:")):
        chiavi_tolte = b.get("progetti_chiavi") or ()
        if evento.get("progetto") in chiavi_tolte or dati.get("figlio") in chiavi_tolte:
            return True
    return False


def _file_eventi():
    from . import eventi
    return eventi.FILE, eventi.FILE.with_suffix(".1.jsonl")


def conta_eventi_jsonl(esclusi: dict, bersagli: dict = None) -> int:
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
            if _riga_evento_esclusa(evento, esclusi, bersagli):
                n += 1
    return n


def pulisci_eventi_jsonl(esclusi: dict, bersagli: dict = None) -> int:
    """Riscrive eventi.jsonl (e il suo file ruotato, se c'è) senza le righe
    di sessioni, cartelle, lanci, task, post o progetti esclusi.

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
            if _riga_evento_esclusa(evento, esclusi, bersagli):
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


def _progetti_orfani_ids(conn, link_tolti) -> list:
    """Gli id dei progetti automatici che, tolti questi link (di percorso o
    di memoria), non ne conservano più nessuno. Sola lettura: non cancella
    niente, così lo stesso conto serve sia a `--prova` sia alla pulizia vera.

    Non si tocca mai un progetto con `auto=0`: quello lo ha dichiarato una
    persona, e un link di troppo si toglie, la scheda no.
    """
    per_progetto = {}
    for _, pid in link_tolti:
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
    return orfani


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

    # sid_set e' l'insieme ampio usato per filtrare TUTTO il resto (task,
    # post, agenda, eventi): oltre alle sessioni che risultano escluse fra
    # quelle gia' in `sessions`, include ANCHE gli id configurati o scoperti
    # a runtime che oggi non hanno (piu') una riga in sessions — una
    # sessione spostata, per esempio, viene cancellata da `sync_sessions`
    # nello stesso giro in cui la scopre, ma un task scritto da quella
    # sessione via MCP prima della scoperta resta, e va tolto lo stesso.
    righe_sessioni = conn.execute("SELECT session_id, cwd, thread FROM sessions").fetchall()
    sid_esclusi = [r["session_id"] for r in righe_sessioni
                   if sessione_esclusa(r["session_id"], r["cwd"], esclusi, r["thread"])]
    sid_set = set(sid_esclusi) | set(esclusi["sessioni"])

    # sid_esclusi include anche le sessioni scoperte solo qui, guardando la
    # cwd gia' salvata in sessions.cwd: una sessione aperta in una cartella
    # normale e poi spostata in una privata non ha la cartella di progetto
    # esclusa, quindi trascrizione_esclusa (usata sotto per turni_percorsi e
    # per le memorie) non la riconoscerebbe finche' esclusi["sessioni"] non
    # contiene anche il suo id. Senza questo, turni_fts di una sessione cosi'
    # resterebbe intatto e cercabile per un giro intero, anche se la sua riga
    # in sessions sparisce subito (misurato: e' esattamente il buco trovato
    # dal tester). Un dizionario NUOVO, non una mutazione sul posto: questa
    # funzione la usa anche conta() per --prova, che non deve scrivere ne'
    # persistere niente. purga(), qui sotto, chiama segna_scoperto() sui id
    # nuovi DOPO aver preso questi conteggi, cosi' esclusi_scoperti e
    # esclusi["sessioni"] restano aggiornati anche per chi guarda dopo, nello
    # stesso processo e nei sync successivi.
    esclusi_ampio = {**esclusi, "sessioni": sid_set}

    righe_repos = conn.execute(
        "SELECT id, name, local_path FROM repos "
        "WHERE local_path IS NOT NULL AND local_path <> ''").fetchall()
    repos = [r["id"] for r in righe_repos if percorso_escluso(r["local_path"], esclusi)]
    nomi_repos = {r["name"] for r in righe_repos if percorso_escluso(r["local_path"], esclusi)}

    righe_commits = conn.execute("SELECT id, repo, sha FROM commits").fetchall()
    commits = [r["id"] for r in righe_commits if r["repo"] in nomi_repos]
    shas_commits = {r["sha"] for r in righe_commits if r["repo"] in nomi_repos and r["sha"]}

    righe_memorie = conn.execute("SELECT path, name, project_id FROM knowledge").fetchall()
    memorie_escluse = {r["path"]: r["name"] for r in righe_memorie
                       if trascrizione_esclusa(r["path"], esclusi_ampio)}
    memorie = list(memorie_escluse)
    nomi_memorie = set(memorie_escluse.values())

    link_percorso = [(r["id"], r["project_id"]) for r in conn.execute(
        "SELECT id, project_id, value FROM project_links WHERE kind='path'").fetchall()
        if percorso_escluso(r["value"], esclusi)]
    link_memoria = [(r["id"], r["project_id"]) for r in conn.execute(
        "SELECT id, project_id, value FROM project_links WHERE kind='memory'").fetchall()
        if r["value"] in nomi_memorie]
    link_tolti = link_percorso + link_memoria

    orfani_ids = _progetti_orfani_ids(conn, link_tolti)
    chiavi_orfane = ({r["key"] for r in conn.execute(
        f"SELECT key FROM projects WHERE id IN ({_in(orfani_ids)})", orfani_ids).fetchall()}
        if orfani_ids else set())
    orfani_set = set(orfani_ids)

    # Aggiungere anche le righe di `knowledge` con `project_id` orfano, oltre
    # a quelle già trovate per percorso: una scheda che perde il suo unico
    # link non deve lasciare in giro memorie che la puntavano solo per id.
    memorie_extra = [r["path"] for r in righe_memorie
                     if r["project_id"] in orfani_set and r["path"] not in memorie_escluse]
    memorie = memorie + memorie_extra

    tasks = [r["id"] for r in conn.execute(
        "SELECT id, session_id, cwd, project_id FROM tasks").fetchall()
        if r["session_id"] in sid_set or percorso_escluso(r["cwd"], esclusi)
        or r["project_id"] in orfani_set]

    posts = [r["id"] for r in conn.execute(
        "SELECT id, session_id, project_id FROM posts").fetchall()
        if r["session_id"] in sid_set or r["project_id"] in orfani_set]

    tasks_set, posts_set = set(tasks), set(posts)
    agenda = [r["id"] for r in conn.execute(
        "SELECT id, sessione, task_id, project_id FROM agenda").fetchall()
        if (r["sessione"] and r["sessione"] in sid_set)
        or (r["task_id"] and r["task_id"] in tasks_set)
        or r["project_id"] in orfani_set]

    runs = [r["id"] for r in conn.execute(
        "SELECT id, cwd, task_id FROM runs").fetchall()
        if percorso_escluso(r["cwd"], esclusi) or (r["task_id"] and r["task_id"] in tasks_set)]

    ref_task = {f"task:{tid}" for tid in tasks_set}
    ref_post = {f"post:{pid}" for pid in posts_set}
    eventi_db = [r["id"] for r in conn.execute(
        "SELECT id, kind, ref, project_id FROM events").fetchall()
        if (r["kind"] in ("sessione", "hook", "scambio") and r["ref"] in sid_set)
        or (r["kind"] == "memoria" and r["ref"] in nomi_memorie)
        or (r["kind"] == "task" and r["ref"] in ref_task)
        or (r["kind"] == "post" and r["ref"] in ref_post)
        or (r["kind"] == "commit" and r["ref"] in shas_commits)
        or r["project_id"] in orfani_set]

    # Nome diverso dal modulo `turni` importato qui sopra: un'assegnazione
    # locale con lo stesso nome lo ombreggerebbe per il resto della funzione,
    # e una chiamata futura a `turni.qualcosa()` più sotto fallirebbe con un
    # AttributeError su una lista invece che sul modulo.
    turni_percorsi = [r["percorso"] for r in conn.execute("SELECT percorso FROM turni_file").fetchall()
                     if trascrizione_esclusa(r["percorso"], esclusi_ampio)]

    live = store.get_meta(conn, "live_session")
    live_da_pulire = bool(live) and live in sid_set

    meta_git_lento = [r["key"] for r in conn.execute(
        "SELECT key FROM meta WHERE key LIKE 'git_lento:%'").fetchall()
        if percorso_escluso(r["key"][len("git_lento:"):], esclusi)]

    return {
        "sessioni": sid_esclusi, "sid_set": sid_set, "tasks": tasks, "posts": posts,
        "agenda": agenda, "runs": runs, "eventi": eventi_db,
        "turni": turni_percorsi, "memorie": memorie, "repos": repos, "commits": commits,
        "link_tolti": link_tolti, "progetti_orfani_ids": orfani_ids,
        "progetti_orfani_chiavi": chiavi_orfane, "live_session": live_da_pulire,
        "meta_git_lento": meta_git_lento,
    }


def _bersagli_eventi_jsonl(b: dict) -> dict:
    """Il sottoinsieme di `_bersagli()` che serve a `pulisci_eventi_jsonl`."""
    return {"runs": set(b["runs"]), "tasks": set(b["tasks"]), "posts": set(b["posts"]),
            "progetti_chiavi": b["progetti_orfani_chiavi"]}


def conta(conn, esclusi: dict = None) -> dict:
    """Quel che `purga()` toglierebbe, senza toccare niente (`--prova`)."""
    esclusi = esclusi if esclusi is not None else carica(conn=conn)
    if not configurato(esclusi):
        return {}
    b = _bersagli(conn, esclusi)
    return {
        "sessioni": len(b["sessioni"]), "eventi": len(b["eventi"]),
        "tasks": len(b["tasks"]), "posts": len(b["posts"]), "agenda": len(b["agenda"]),
        "runs": len(b["runs"]), "turni": len(b["turni"]), "memorie": len(b["memorie"]),
        "repos": len(b["repos"]), "commits": len(b["commits"]),
        "link_percorso": len(b["link_tolti"]),
        "progetti": len(b["progetti_orfani_ids"]),
        "eventi_jsonl": conta_eventi_jsonl(esclusi, _bersagli_eventi_jsonl(b)),
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
    esclusi = esclusi if esclusi is not None else carica(conn=conn)
    if not configurato(esclusi):
        return {}
    b = _bersagli(conn, esclusi)

    # Persiste ORA, nello stesso giro, le sessioni che _bersagli() ha appena
    # scoperto guardando la cwd gia' salvata (non ancora in esclusi_scoperti
    # ne' in esclusi["sessioni"], altrimenti sarebbero gia' in
    # esclusi["sessioni"] e la differenza sarebbe vuota): senza questo, il
    # prossimo turni.indicizza o la prossima scrittura MCP tornerebbero a non
    # saperlo finche' qualcosa non rilegge il transcript da capo.
    for sid in set(b["sessioni"]) - set(esclusi["sessioni"]):
        segna_scoperto(conn, sid, esclusi)

    conteggi = {}

    def _cancella(tabella, colonna, valori):
        if not valori:
            return 0
        return conn.execute(
            f"DELETE FROM {tabella} WHERE {colonna} IN ({_in(valori)})", valori).rowcount

    conteggi["sessioni"] = _cancella("sessions", "session_id", b["sessioni"])
    # I lanci (runs) portano un log su disco: va tolto prima di perdere il
    # percorso insieme alla riga.
    if b["runs"]:
        for r in conn.execute(
                f"SELECT log FROM runs WHERE id IN ({_in(b['runs'])})", b["runs"]).fetchall():
            if r["log"]:
                try:
                    Path(r["log"]).unlink()
                except OSError:
                    pass
    conteggi["runs"] = _cancella("runs", "id", b["runs"])
    conteggi["eventi"] = _cancella("events", "id", b["eventi"])
    conteggi["tasks"] = _cancella("tasks", "id", b["tasks"])
    conteggi["posts"] = _cancella("posts", "id", b["posts"])
    conteggi["agenda"] = _cancella("agenda", "id", b["agenda"])
    conteggi["turni"] = _cancella("turni_fts", "percorso", b["turni"])
    _cancella("turni_file", "percorso", b["turni"])
    conteggi["memorie"] = _cancella("knowledge", "path", b["memorie"])
    conteggi["repos"] = _cancella("repos", "id", b["repos"])
    conteggi["commits"] = _cancella("commits", "id", b["commits"])

    # I progetti orfani vanno tolti PRIMA di guardare quali link sono
    # sopravvissuti: cancellare la scheda porta via da sola (CASCADE) i suoi
    # link residui, che altrimenti proveremmo a cancellare una seconda volta
    # (innocuo: DELETE su una riga già sparita non fa niente, ma il conto qui
    # sotto li conterebbe due volte se non distinguessimo i due gruppi).
    conteggi["progetti"] = _cancella("projects", "id", b["progetti_orfani_ids"])
    pid_sopravvissuti = {pid for _, pid in b["link_tolti"]
                         if conn.execute("SELECT 1 FROM projects WHERE id=?",
                                        (pid,)).fetchone() is not None}
    residui = [link_id for link_id, pid in b["link_tolti"] if pid in pid_sopravvissuti]
    if residui:
        conn.execute(f"DELETE FROM project_links WHERE id IN ({_in(residui)})", residui)
    conteggi["link_percorso"] = len(b["link_tolti"])

    if b["live_session"]:
        conn.execute("DELETE FROM meta WHERE key IN ('live_session','live_since')")
    if b["meta_git_lento"]:
        conn.execute(f"DELETE FROM meta WHERE key IN ({_in(b['meta_git_lento'])})",
                     b["meta_git_lento"])

    conteggi["eventi_jsonl"] = pulisci_eventi_jsonl(esclusi, _bersagli_eventi_jsonl(b))

    if any(conteggi.values()):
        # Il riepilogo e le proposte in cache possono aver letto, prima di
        # questa pulizia, esattamente il testo che qui viene tolto (misurato:
        # "Hai lavorato su segreto repo" restava nel riepilogo del giorno
        # dopo l'esclusione, perché la cache non sapeva di doversi
        # invalidare). Si toglie tutto il gruppo, non solo il testo: una
        # firma vecchia farebbe credere alla cache di essere ancora fresca.
        conn.execute(
            "DELETE FROM meta WHERE key IN ('recap_testo','recap_impronta',"
            "'recap_lingua','recap_fonte','recap_ts','proposte','proposte_ts')")

    conn.commit()
    if any(conteggi.values()):
        store.rebuild_search(conn)
        conn.commit()
    return conteggi
