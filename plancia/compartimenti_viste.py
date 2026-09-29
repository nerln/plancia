"""Compartimenti, lato viste (E1): a chi Plancia fa vedere cosa.

`plancia/compartimenti.py` (E3) sa DIRE di che compartimento e' un percorso o
una sessione, e lo usa il guardiano per negare. Qui si usa la stessa regola per
FILTRARE quello che Plancia mostra: il briefing di SessionStart, il richiamo di
UserPromptSubmit, il server MCP e la dashboard. Le regole di appartenenza non si
riscrivono: si importano da E3 (`Ambito`, `chiamante`, la
regola dello specchio in `<claude>/projects`, gli annidati: vince il piu'
specifico).

Il modello in una riga: ogni oggetto ha un insieme di NOMI di compartimenti
nominati, ricavato dai dati che ha gia' (niente colonna obbligatoria); l'insieme
vuoto e' il `predefinito`.

- una sessione: il suo id in `sessioni` di X, la sua cwd o la cartella in cui ha
  davvero lavorato (`dir_dedotta`) dentro le cartelle di X, il suo transcript
  sotto `<claude>/projects/<codifica di una cartella di X>`;
- un progetto: i suoi percorsi (`project_links` di tipo path, `repos.local_path`)
  e le sue memorie collegate; solo se non ha nessuna di queste prove, le
  sessioni che lo toccano; piu' la colonna `compartimento` se una persona lo ha
  assegnato a mano dalla dashboard;
- un task: la sessione che lo ha creato, la sua cwd e il suo progetto;
- un post, un lancio, una voce dell'agenda: la sessione e/o il progetto;
- una memoria: il percorso del file (una memoria automatica sta nello specchio
  della cartella di X, quindi e' di X: e' il caso da cui e' partito E1) e il suo
  progetto;
- un evento: il progetto, la sessione o l'oggetto a cui punta `ref`.

Un oggetto toccato da piu' nominati (o dal nominato e da un altro percorso) non
e' del predefinito: la regola e' la prudenza di E3, "un segnale di X basta". Chi
ha segnali di due nominati (una sessione incerta) non vede niente.

Chi guarda e' di due tipi:

- un AGENTE (briefing, richiamo, MCP): vede solo gli oggetti il cui insieme e'
  esattamente il suo. Il predefinito vede quelli con l'insieme vuoto, e quindi
  niente dei nominati; un nominato vede solo i suoi.
- la DASHBOARD, che e' la vista di una persona e non di un agente: mostra tutto
  ma SEPARATO. Sceglie un compartimento e vede tutto quello che lo riguarda (un
  oggetto di due nominati compare in tutti e due, mai nel predefinito).

Il filtro si applica con viste TEMPORANEE di SQLite (`CREATE TEMP VIEW projects
AS SELECT ... WHERE id IN (...)`): nella connessione che le crea, ogni nome di
tabella senza schema si risolve prima sullo schema temporaneo, quindi TUTTE le
query che passano da quella connessione (briefing, slot, proposte, recap,
lavagna, lanci, mappa...) vedono solo il compartimento, senza toccare una per
una. Sono viste: in scrittura la connessione fallisce ("cannot modify tasks
because it is a view"). E' voluto: chi scrive usa una connessione normale, dopo
aver controllato a mano di che compartimento e' l'oggetto (vedi `mcp.py`). Le
due cose che le viste non coprono si trattano a parte: le tabelle virtuali FTS
(`search_fts`, `turni_fts`: `cerca_schede` e `cerca_turni` mettono il filtro
DENTRO la query, prima del taglio per rango, cosi' chi ha pochi oggetti in un
archivio grande li trova) e la tabella `meta`, dove stanno le cache del riepilogo e delle proposte (una
cache condivisa fra compartimenti sarebbe una fuga: vedi `_ombra_meta`).

Limiti da dire chiari:

- Non e' un confine di sicurezza, come E3: ferma il comportamento ordinario,
  non un agente che va a leggere il database o i file da solo (E3 nega gia'
  quelli, in `bloccante`).
- L'appartenenza si calcola a ogni richiesta dai dati di adesso (nessuna colonna
  da tenere allineata quando la config cambia). Costa una lettura delle tabelle
  e qualche `realpath` (memorizzati per percorso): misurato in
  `tools/prove/compartimenti-plancia.py`.
- Config assente o senza nominati: `attivo()` torna None e Plancia fa
  esattamente quello di prima. Config rotta: si usa l'ultima copia valida
  (`compartimenti.e1-ultima-valida.json`, scritta da qui, indipendente da quella
  del guardiano perche' quella si svuota quando il guardiano e' `spento`); senza
  nemmeno quella e' come non averla (dedotto: non si sa quali siano i nominati).
- Il riepilogo e le proposte hanno una cache per compartimento (`meta` con la
  chiave `<chiave>@<compartimento>`): la cache non separata che scrive un sync
  (`recap.prepara`) non si legge piu' quando i compartimenti sono attivi.
- Non filtrati: `jarvis` (l'assistente vocale della dashboard: la rotta gli
  passa la connessione non separata) e il comando `plancia` da terminale, che
  sono la vista di chi usa Plancia; `esporta.py`.
- Percorsi POSIX soltanto (`/...`, `~/...`): `nomi_percorso` non riconosce un
  percorso Windows con la lettera del disco, che risulta del predefinito.
"""

from __future__ import annotations

import json
import os
import re

from . import compartimenti as C
from . import piattaforma

PREDEFINITO = C.PREDEFINITO
#: chi ha segnali di piu' nominati: non e' un nome valido di compartimento
INCERTO = "\x00incerto"

VUOTO = frozenset()

#: le tabelle con un `id` intero che si filtrano una per una
TABELLE = ("projects", "sessions", "tasks", "posts", "repos", "commits",
           "knowledge", "capabilities", "agenda", "runs", "events")

#: le chiavi di `meta` che non appartengono a nessuna vista: si tolgono a chi
#: guarda da dentro un compartimento (una sessione viva, un giro di voce...)
_META_PRIVATE = ("recap_", "proposte", "ultima_", "live_", "git_lento:")
#: quelle che invece hanno una copia per compartimento (`<chiave>@<nome>`)
_META_PER_COMP = ("recap_", "proposte", "ultima_risposta")

_CONFIG_COPIA = "compartimenti.e1-ultima-valida.json"


# --------------------------------------------------------------------------
# config e ambito
# --------------------------------------------------------------------------

def _copia_percorso(data_dir):
    return os.path.join(data_dir, _CONFIG_COPIA)


def _leggi_copia(data_dir):
    try:
        with open(_copia_percorso(data_dir), "r", encoding="utf-8") as f:
            return C.valida_compartimenti(json.load(f))
    except (OSError, ValueError, UnicodeDecodeError, RecursionError):
        return None


def _salva_copia(data_dir, comp):
    """La copia dei compartimenti dell'ultima config valida, solo se cambia.
    Se non c'e' nessun NOMINATO (anche con la sola voce `predefinito`) e la copia
    non esiste non si crea niente: chi non usa i compartimenti non trova un file
    in piu'. Se la copia c'e' gia' si aggiorna anche a "nessun nominato": una
    config che poi si rompe non deve far rivivere dei compartimenti spenti."""
    nuovo = json.dumps(comp, indent=2, sort_keys=True, ensure_ascii=False)
    dest = _copia_percorso(data_dir)
    try:
        with open(dest, "r", encoding="utf-8") as f:
            if f.read() == nuovo:
                return
    except OSError:
        if not any(k != PREDEFINITO for k in comp):
            return
    try:
        os.makedirs(data_dir, exist_ok=True)
        tmp = "%s.%d.tmp" % (dest, os.getpid())
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(nuovo)
        os.replace(tmp, dest)
    except OSError:
        pass


def attivo(data_dir=None, home=None, claude_dir=None):
    """L'`Ambito` dei compartimenti, o None se non ce ne sono di nominati.

    None vuol dire "Plancia si comporta come sempre": config assente, senza la
    chiave, o con la sola voce `predefinito`. Non dipende dalla modalita' del
    guardiano (`spento`, `solo-registro`, `bloccante`): quella dice se E3 nega,
    questa se Plancia separa cio' che mostra, e basta che i nominati esistano.
    """
    if not piattaforma.compartimenti_supportati():
        # Windows: i compartimenti ragionano su percorsi POSIX, sono spenti (vedi
        # `piattaforma.compartimenti_supportati`). Prima di leggere la config: non
        # si scrive nemmeno la copia dell'ultima config valida.
        return None
    data_dir = data_dir or C.percorso_dati()
    c = C.leggi_config(data_dir)
    if c["stato"] == "ok":
        comp = c["compartimenti"]
        _salva_copia(data_dir, comp)
    elif c["stato"] == "rotta":
        comp = _leggi_copia(data_dir)
        if not comp:
            return None
    else:
        return None
    ambito = C.Ambito(comp, [], home=home, data_dir=data_dir, claude_dir=claude_dir)
    return ambito if ambito.nominati else None


def elenco(ambito):
    """I compartimenti fra cui scegliere: il predefinito e poi i nominati."""
    return [PREDEFINITO] + sorted(ambito.nominati)


def etichetta(nomi):
    """Da un elenco di nomi di nominati all'etichetta di chi guarda: vuoto e'
    il predefinito, uno e' lui, due o piu' e' incerto."""
    nomi = sorted(set(nomi))
    if not nomi:
        return PREDEFINITO
    if len(nomi) == 1:
        return nomi[0]
    return INCERTO


def visibile(nomi, visore, dashboard=False):
    """Un oggetto con questo insieme di nomi si mostra a `visore`?"""
    if dashboard:
        if visore == PREDEFINITO:
            return not nomi
        return visore in nomi
    if visore == INCERTO:
        return False
    if visore == PREDEFINITO:
        return not nomi
    return set(nomi) == {visore}


# --------------------------------------------------------------------------
# chi guarda
# --------------------------------------------------------------------------

def visore_da_payload(ambito, payload):
    """L'etichetta della sessione che manda un hook (SessionStart,
    UserPromptSubmit): stessa `chiamante` del guardiano, cioe' id, cartella di
    apertura (dal transcript) e cwd; ne basta un segnale."""
    if not isinstance(payload, dict):
        payload = {}
    return etichetta(C.chiamante(payload, ambito)["nomi"])


_RX_SID = re.compile(r"^[0-9A-Za-z_-]{1,80}$")


def trascrizione_di(ambito, sid):
    """Il file `<claude>/projects/<cartella>/<sid>.jsonl`, o "". Il server MCP
    non riceve il transcript_path dell'hook: lo cerca dall'id."""
    if not isinstance(sid, str) or not _RX_SID.match(sid) or not ambito.progetti:
        return ""
    try:
        with os.scandir(ambito.progetti) as it:
            for d in it:
                p = os.path.join(d.path, sid + ".jsonl")
                if os.path.isfile(p):
                    return p
    except OSError:
        pass
    return ""


def visore_mcp(ambito, sess):
    """L'etichetta della sessione che ha lanciato il server MCP.

    `sess` e' quello che torna `sessione.corrente()`: l'id e la cwd di
    PARTENZA del processo. Il segnale dell'id e quello della cartella di
    apertura (trovata cercando il transcript) non si muovono; la cwd puo' solo
    aggiungere un'appartenenza. Se non c'e' nessun segnale di un nominato la
    sessione e' del predefinito (la stessa prudenza di E3)."""
    sess = sess or {}
    sid = sess.get("session_id") or ""
    payload = {"session_id": sid, "cwd": sess.get("cwd") or ""}
    tp = trascrizione_di(ambito, sid)
    if tp:
        payload["transcript_path"] = tp
    return visore_da_payload(ambito, payload)


def visore_cli(ambito, sess=None):
    """L'etichetta di chi lancia il comando `plancia` da un terminale.

    Le stesse regole del server MCP (`visore_mcp`): l'id di sessione e la cwd
    dell'ambiente del processo (`CLAUDE_CODE_SESSION_ID`, la cartella in cui si
    e' lanciato il comando), piu' la cartella in cui la sessione e' stata
    aperta se il suo transcript si trova. Un comando lanciato da una sessione di
    un nominato vede il nominato. Un terminale umano, senza id di sessione e con
    la cwd fuori da ogni nominato, e' il predefinito (e vede il predefinito: e'
    dichiarato nei README); con la cwd dentro un nominato vede quel nominato.
    `sess` e' per le prove: quello che tornerebbe `sessione.corrente()`."""
    if sess is None:
        try:
            from . import sessione
            sess = sessione.corrente(argv=[])
        except Exception:  # noqa: BLE001 - nessun segnale: come un terminale umano
            sess = {}
    return visore_mcp(ambito, sess)


def file_compartimento(data_dir, prefisso, nome, estensione="md"):
    """Il file `<prefisso>.<nome>.<estensione>` di un compartimento. Il nome del
    compartimento puo' avere qualunque carattere: si riduce a uno sicuro e, se e'
    cambiato, si aggiunge un pezzo di hash perche' due nomi diversi non finiscano
    nello stesso file."""
    pulito = re.sub(r"[^A-Za-z0-9_-]", "_", nome)[:40]
    if pulito != nome:
        import hashlib
        pulito += "-" + hashlib.sha1(nome.encode("utf-8")).hexdigest()[:6]
    return os.path.join(data_dir, "%s.%s.%s" % (prefisso, pulito, estensione))


def file_briefing(data_dir, nome):
    """Il file del briefing di un compartimento (`briefing.<nome>.md`)."""
    return file_compartimento(data_dir, "briefing", nome)


# --------------------------------------------------------------------------
# a che compartimento appartiene ogni cosa
# --------------------------------------------------------------------------

def _specchio(a, n):
    """Tutti i nominati (col criterio del piu' specifico) a cui appartiene un
    percorso risolto `n` come specchio di una loro cartella sotto
    `<claude>/projects`: la stessa regola di `Ambito.proprietario_specchio`, ma
    con la lista dei nomi (un nome solo dice troppo poco a chi deve dire se
    un oggetto e' incerto)."""
    if not n or not a.progetti or not C._dentro(n, a.progetti):
        return []
    resto = n[len(a.progetti):].strip("/")
    if not resto:
        return []
    return a.proprietari_codifica(resto.split("/")[0])


def _righe(conn, tabella, colonne):
    """Le righe di una tabella con le colonne che ci sono (quelle che mancano
    valgono None): una base di dati non migrata non deve far cadere un filtro."""
    try:
        presenti = {r[1] for r in conn.execute("PRAGMA main.table_info(%s)" % tabella)}
    except Exception:  # noqa: BLE001
        return []
    if not presenti:
        return []
    sel = ", ".join(c if c in presenti else "NULL AS %s" % c for c in colonne)
    try:
        cur = conn.execute("SELECT %s FROM main.%s" % (sel, tabella))
        chiavi = [d[0] for d in cur.description]
        return [dict(zip(chiavi, r)) for r in cur.fetchall()]
    except Exception:  # noqa: BLE001
        return []


def nomi_percorso(ambito, p):
    """I nominati che possiedono un percorso: le loro cartelle (il piu'
    specifico) e lo specchio in `<claude>/projects`. Vuoto: nessuno."""
    if not isinstance(p, str) or not p.strip() or not p.startswith(("/", "~")):
        return VUOTO
    n = C._norm(p)
    if not n:
        return VUOTO
    s = set(ambito.proprietari_percorso(n))
    s.update(_specchio(ambito, n))
    return frozenset(s)


def percorso_visibile(ambito, visore, p):
    """Un percorso (un progetto legato a una cartella) si mostra a `visore`?
    Per l'ancoraggio di SessionStart, che non ha la base di dati sotto mano."""
    return visibile(nomi_percorso(ambito, p), visore)


class Appartenenze:
    """I nomi di compartimento di ogni oggetto, calcolati una volta.

    `nomi[tabella][id]` e' un frozenset di nomi di nominati; vuoto = predefinito.
    Si legge la base SENZA le viste del filtro (`main.<tabella>`)."""

    def __init__(self, conn, ambito, solo=None):
        """`solo`: le tabelle che servono (un insieme di nomi); quelle che non
        servono non si calcolano (il richiamo, che gira a ogni messaggio, vuole
        solo `knowledge`: contare anche i 9000 eventi sarebbe tempo perso).
        Sessioni, progetti, memorie e repository si calcolano sempre, perche'
        le altre ne dipendono."""
        self.solo = set(solo) if solo else None
        self.a = ambito
        self._memo = {}
        self.nomi = {t: {} for t in TABELLE}
        #: session_id -> nomi, e chiave di progetto -> nomi, per chi cerca da fuori
        self.sessioni = {}
        self.chiavi_progetto = {}
        self.progetto_di = lambda cwd: VUOTO
        self._calcola(conn)

    # -- pezzi ------------------------------------------------------------
    def perc(self, p):
        """I nominati che possiedono un percorso (cartelle e specchio)."""
        if not isinstance(p, str) or not p.strip():
            return VUOTO
        if p not in self._memo:
            self._memo[p] = nomi_percorso(self.a, p)
        return self._memo[p]

    def per_id(self, sid):
        """I nominati che elencano questo id di sessione."""
        if not sid:
            return VUOTO
        return frozenset(n for n, c in self.a.nominati.items() if sid in c["sessioni"])

    def _tag(self, valore):
        v = (valore or "").strip() if isinstance(valore, str) else ""
        return frozenset([v]) if v in self.a.nominati else VUOTO

    def sessione(self, sid):
        """I nomi di una sessione per id: quelli della tabella, e l'id da solo
        se la tabella non la conosce."""
        return self.sessioni.get(sid) or self.per_id(sid)

    def _vuole(self, *tabelle):
        return self.solo is None or bool(self.solo.intersection(tabelle))

    # -- calcolo ----------------------------------------------------------
    def _calcola(self, conn):
        nomi = self.nomi
        perc, tag = self.perc, self._tag

        # L'assegnazione a mano di un progetto (la colonna `compartimento`) e'
        # una decisione di una persona: si estende alle sessioni che gli sono
        # legate. I percorsi di un progetto invece NON passano alle sue sessioni
        # (una sessione ha i suoi segnali: l'attribuzione a un progetto puo'
        # essere sbagliata, e non deve portarsi dietro il compartimento del
        # progetto sbagliato).
        tag_prj = {r["id"]: tag(r["compartimento"])
                   for r in _righe(conn, "projects", ("id", "compartimento"))}

        for r in _righe(conn, "sessions",
                        ("id", "session_id", "cwd", "dir_dedotta", "file", "project_id")):
            s = set(self.per_id(r["session_id"]))
            s |= perc(r["cwd"]) | perc(r["dir_dedotta"]) | perc(r["file"])
            s |= tag_prj.get(r["project_id"], VUOTO)
            nomi["sessions"][r["id"]] = frozenset(s)
            if r["session_id"]:
                self.sessioni[r["session_id"]] = nomi["sessions"][r["id"]]

        kn_per_nome = {}
        for r in _righe(conn, "knowledge", ("id", "name", "path", "scope", "project_id")):
            s = set(perc(r["path"]))
            if r["scope"]:
                s.update(self.a.proprietari_codifica(r["scope"]))
            nomi["knowledge"][r["id"]] = frozenset(s)
            kn_per_nome.setdefault(r["name"], set()).update(s)

        repo_perc = {}
        for r in _righe(conn, "repos", ("id", "local_path")):
            repo_perc[r["id"]] = perc(r["local_path"])

        # progetti: le prove dei percorsi e delle memorie; solo se non ce ne
        # sono, le sessioni che li toccano (vedi il docstring del modulo)
        prove = {}
        for r in _righe(conn, "project_links", ("project_id", "kind", "value")):
            if r["kind"] == "path":
                p = prove.setdefault(r["project_id"], [False, set()])
                p[0] = True
                p[1] |= perc(r["value"])
            elif r["kind"] == "memory":
                p = prove.setdefault(r["project_id"], [False, set()])
                if r["value"] in kn_per_nome:
                    p[0] = True
                    p[1] |= kn_per_nome[r["value"]]
        for r in _righe(conn, "repos", ("id", "project_id", "local_path")):
            if r["project_id"] and (r["local_path"] or "").strip():
                p = prove.setdefault(r["project_id"], [False, set()])
                p[0] = True
                p[1] |= repo_perc[r["id"]]
        da_sessioni = {}
        for r in _righe(conn, "sessions", ("id", "project_id")):
            if r["project_id"]:
                da_sessioni.setdefault(r["project_id"], set()).update(
                    nomi["sessions"].get(r["id"], VUOTO))
        for r in _righe(conn, "projects", ("id", "key", "compartimento")):
            ha, s = prove.get(r["id"], (False, set()))
            s = set(s)
            if not ha:
                s |= da_sessioni.get(r["id"], set())
            s |= tag(r["compartimento"])
            nomi["projects"][r["id"]] = frozenset(s)
            self.chiavi_progetto[r["key"]] = nomi["projects"][r["id"]]
        prj = nomi["projects"]

        for r in _righe(conn, "knowledge", ("id", "project_id")):
            if r["project_id"]:
                nomi["knowledge"][r["id"]] = nomi["knowledge"][r["id"]] | prj.get(
                    r["project_id"], VUOTO)

        for r in _righe(conn, "repos", ("id", "project_id")):
            nomi["repos"][r["id"]] = repo_perc.get(r["id"], VUOTO) | prj.get(
                r["project_id"], VUOTO)
        repo_per_nome = {}
        for r in _righe(conn, "repos", ("id", "name")):
            repo_per_nome[r["name"]] = nomi["repos"][r["id"]]

        # da una cartella al progetto che la possiede (il collegamento piu'
        # specifico): un lancio parte in una cartella, non ha un progetto
        legami = []
        for r in _righe(conn, "project_links", ("project_id", "kind", "value")):
            if r["kind"] == "path" and isinstance(r["value"], str) and r["value"]:
                n = C._norm(r["value"]) if r["value"].startswith(("/", "~")) else ""
                if n:
                    legami.append((n, r["project_id"]))
        legami.sort(key=lambda x: -len(x[0]))
        memo_cwd = {}

        def progetto_di(cwd):
            if not isinstance(cwd, str) or not cwd.startswith(("/", "~")):
                return VUOTO
            if cwd not in memo_cwd:
                n = C._norm(cwd)
                memo_cwd[cwd] = VUOTO
                for base, pid in legami:
                    if C._dentro(n, base):
                        memo_cwd[cwd] = prj.get(pid, VUOTO)
                        break
            return memo_cwd[cwd]
        self.progetto_di = progetto_di

        if not self._vuole("tasks", "posts", "commits", "capabilities", "agenda",
                           "runs", "events"):
            return
        for r in _righe(conn, "tasks", ("id", "session_id", "cwd", "project_id",
                                        "compartimento")):
            nomi["tasks"][r["id"]] = frozenset(
                self.sessione(r["session_id"]) | perc(r["cwd"])
                | prj.get(r["project_id"], VUOTO) | tag(r["compartimento"]))
        tsk = nomi["tasks"]

        for r in _righe(conn, "posts", ("id", "session_id", "project_id",
                                        "compartimento")):
            nomi["posts"][r["id"]] = frozenset(
                self.sessione(r["session_id"]) | prj.get(r["project_id"], VUOTO)
                | tag(r["compartimento"]))
        pst = nomi["posts"]

        commit_per_sha = {}
        for r in _righe(conn, "commits", ("id", "repo", "sha", "session_id")):
            nomi["commits"][r["id"]] = frozenset(
                repo_per_nome.get(r["repo"], VUOTO) | self.sessione(r["session_id"]))
            commit_per_sha[r["sha"]] = nomi["commits"][r["id"]]

        for r in _righe(conn, "capabilities", ("id", "path")):
            nomi["capabilities"][r["id"]] = perc(r["path"])

        for r in _righe(conn, "agenda", ("id", "project_id", "task_id", "sessione")):
            nomi["agenda"][r["id"]] = frozenset(
                prj.get(r["project_id"], VUOTO) | tsk.get(r["task_id"], VUOTO)
                | self.sessione(r["sessione"]))

        # un lancio parte spesso da una cartella qualunque (la HOME, se il
        # progetto non ha un percorso): il compartimento di chi lo ha lanciato
        # dalla sua vista o dalla sua sessione sta nella colonna `compartimento`
        # (`cantiere.avvia`), e si SOMMA al task, alla cartella e alla sessione
        for r in _righe(conn, "runs", ("id", "task_id", "cwd", "sessione",
                                       "compartimento")):
            nomi["runs"][r["id"]] = frozenset(
                tsk.get(r["task_id"], VUOTO) | perc(r["cwd"]) | progetto_di(r["cwd"])
                | self.sessione(r["sessione"]) | tag(r["compartimento"]))

        for r in _righe(conn, "events", ("id", "kind", "project_id", "ref",
                                         "compartimento")):
            s = set(prj.get(r["project_id"], VUOTO)) | tag(r["compartimento"])
            ref = r["ref"] or ""
            if r["kind"] in ("sessione", "hook", "scambio"):
                s |= self.sessione(ref)
            elif r["kind"] == "memoria":
                s |= kn_per_nome.get(ref, set())
            elif r["kind"] == "commit":
                s |= commit_per_sha.get(ref, VUOTO)
            m = re.match(r"^(task|post):(\d+)$", ref)
            if m:
                tab = tsk if m.group(1) == "task" else pst
                s |= tab.get(int(m.group(2)), VUOTO)
            nomi["events"][r["id"]] = frozenset(s)

    # -- oggetti che stanno fuori dal database ----------------------------
    def nomi_evento_jsonl(self, e):
        """I nomi di una riga di `eventi.jsonl`: la chiave del progetto, la
        cwd o il lancio nei dati, l'id di un task o di un post."""
        s = set()
        if isinstance(e.get("progetto"), str):
            s |= self.chiavi_progetto.get(e["progetto"], VUOTO)
        d = e.get("dati") if isinstance(e.get("dati"), dict) else {}
        s |= self.perc(d.get("cwd")) | self.progetto_di(d.get("cwd"))
        s |= self.sessione(d.get("sessione")) if isinstance(d.get("sessione"), str) else VUOTO
        tipo = e.get("tipo") or ""
        if isinstance(d.get("run"), int):
            s |= self.nomi["runs"].get(d["run"], VUOTO)
        if isinstance(d.get("id"), int):
            if tipo.startswith("task."):
                s |= self.nomi["tasks"].get(d["id"], VUOTO)
            elif tipo.startswith("post."):
                s |= self.nomi["posts"].get(d["id"], VUOTO)
        return frozenset(s)


_CACHE = {}


def appartenenze(conn, ambito, solo=None):
    """`Appartenenze`, riusate se non e' cambiato niente da quando si sono
    calcolate: la firma e' il tempo e la dimensione della base di dati, del suo
    registro WAL (ogni scrittura lo cambia) e della config. Serve al server
    della dashboard, che a ogni apertura di vista riceve piu' richieste una
    dietro l'altra e non deve rifare il calcolo per ognuna. La firma si legge
    PRIMA dei dati: un dato piu' nuovo della firma fa solo rifare il calcolo
    alla richiesta dopo, mai il contrario."""
    d = ambito.data_dir
    firma = []
    for nome in ("plancia.db", "plancia.db-wal", "config.json", _CONFIG_COPIA):
        try:
            st = os.stat(os.path.join(d, nome))
            firma.append((st.st_mtime_ns, st.st_size))
        except OSError:
            firma.append(None)
    firma = (d, tuple(firma), tuple(sorted(solo or ())))
    dentro = _CACHE.get("ap")
    if dentro is not None and dentro[0] == firma:
        return dentro[1]
    ap = Appartenenze(conn, ambito, solo)
    _CACHE["ap"] = (firma, ap)
    return ap


# --------------------------------------------------------------------------
# le viste temporanee
# --------------------------------------------------------------------------

class Ombra:
    """Il filtro applicato a una connessione: chi guarda e quali id vede."""

    def __init__(self, ambito, appart, visore, dashboard):
        self.ambito, self.appart = ambito, appart
        self.visore, self.dashboard = visore, dashboard
        self.ok = {t: {i for i, n in appart.nomi[t].items()
                       if visibile(n, visore, dashboard)} for t in TABELLE}

    def vede(self, nomi):
        return visibile(nomi, self.visore, self.dashboard)

    def sessione_ok(self, sid, percorso=""):
        return self.vede(self.appart.sessione(sid) | self.appart.perc(percorso))

    def evento_jsonl_ok(self, e):
        return self.vede(self.appart.nomi_evento_jsonl(e))

    def filtra_eventi(self, lista):
        return [self.pulisci_evento(e) for e in lista
                if isinstance(e, dict) and self.evento_jsonl_ok(e)]

    def pulisci_evento(self, e):
        """L'evento com'e' per chi guarda. Un cambio di padre
        (`padre:<batch>`, titolo `<figlio> sotto <padre>`) di un progetto il cui
        padre e' di un altro compartimento non ne nomina il padre: il titolo dice
        solo del figlio e i dati non portano gli id del padre (l'evento e' del
        figlio, il padre no)."""
        tipo = e.get("tipo") or ""
        if not tipo.startswith("padre:"):
            return e
        d = e.get("dati") if isinstance(e.get("dati"), dict) else {}
        for chiave in ("dopo", "prima"):
            pid = d.get(chiave)
            if isinstance(pid, int) and pid not in self.ok["projects"]:
                break
        else:
            return e
        figlio = d.get("figlio") if isinstance(d.get("figlio"), str) else ""
        out = dict(e)
        out["titolo"] = "%s (cambio di padre)" % (figlio or "progetto")
        out["dati"] = {k: v for k, v in d.items() if k in ("batch", "figlio")}
        return out

    def leggi_eventi(self, dopo=None, tipo=None, limite=100):
        """`eventi.leggi` per chi guarda: il filtro sta DENTRO la lettura, prima
        del taglio agli ultimi `limite`, cosi' un compartimento con pochi eventi
        in un registro lungo li trova tutti (filtrare dopo il taglio da' una
        lista vuota)."""
        from . import eventi
        righe = eventi.leggi(dopo, tipo, limite,
                             filtro=lambda e: isinstance(e, dict) and self.evento_jsonl_ok(e))
        return [self.pulisci_evento(e) for e in righe]


def _esiste(conn, nome):
    return conn.execute("SELECT 1 FROM main.sqlite_master WHERE name=?",
                        (nome,)).fetchone() is not None


def _ombra_meta(conn, o):
    """`meta` temporanea: quello che non e' di nessuno si toglie, quello che ha
    una copia per compartimento si legge da `<chiave>@<nome>`. Le scritture
    (la cache del riepilogo, le proposte) vanno nella tabella temporanea e
    `chiudi()` le riporta sotto il nome giusto."""
    if not _esiste(conn, "meta"):
        return
    conn.execute("CREATE TEMP TABLE meta(key TEXT PRIMARY KEY, value TEXT)")
    for k, v in conn.execute("SELECT key, value FROM main.meta").fetchall():
        if "@" in k or k.startswith(_META_PRIVATE):
            continue
        conn.execute("INSERT OR REPLACE INTO temp.meta(key, value) VALUES(?,?)", (k, v))
    if o.visore == INCERTO:
        return
    suffisso = "@" + o.visore
    for k, v in conn.execute("SELECT key, value FROM main.meta").fetchall():
        if k.endswith(suffisso) and k[:-len(suffisso)].startswith(_META_PER_COMP):
            conn.execute("INSERT OR REPLACE INTO temp.meta(key, value) VALUES(?,?)",
                         (k[:-len(suffisso)], v))


def applica(conn, ambito, visore, dashboard=False, appart=None, solo=None):
    """Mette il filtro su `conn` (una connessione da usare in SOLA lettura) e
    torna l'`Ombra`. `visore` e' l'etichetta di chi guarda (PREDEFINITO, un
    nominato, INCERTO); con `dashboard` vale la regola della persona.
    Una connessione si filtra una volta sola. Con `solo` (un insieme di nomi di
    tabella) le altre non si calcolano e le loro viste sono VUOTE: non calcolato
    vuol dire invisibile, mai visibile."""
    ap = appart or Appartenenze(conn, ambito, solo)
    o = Ombra(ambito, ap, visore, dashboard)
    for tab in TABELLE:
        if not _esiste(conn, tab):
            continue
        conn.execute("CREATE TEMP TABLE _ok_%s(id INTEGER PRIMARY KEY)" % tab)
        conn.executemany("INSERT INTO temp._ok_%s(id) VALUES(?)" % tab,
                         [(i,) for i in sorted(o.ok[tab])])
        colonne = "*"
        if tab == "projects":
            # un progetto il cui padre (l'area) e' di un altro compartimento
            # non ha padre per chi guarda: senza questo l'albero dei progetti lo
            # perderebbe, figlio di un padre che non si vede
            colonne = ", ".join(
                "CASE WHEN parent_id IN (SELECT id FROM temp._ok_projects) "
                "THEN parent_id ELSE NULL END AS parent_id" if r[1] == "parent_id"
                else '"%s"' % r[1]
                for r in conn.execute("PRAGMA main.table_info(projects)"))
        conn.execute("CREATE TEMP VIEW %s AS SELECT %s FROM main.%s "
                     "WHERE id IN (SELECT id FROM temp._ok_%s)" % (tab, colonne, tab, tab))
    if _esiste(conn, "project_links"):
        conn.execute("CREATE TEMP VIEW project_links AS SELECT * FROM main.project_links "
                     "WHERE project_id IN (SELECT id FROM temp._ok_projects)")
    _ombra_meta(conn, o)
    # chiude la transazione aperta dalle scritture sulle tabelle temporanee: le
    # viste restano, ma la connessione non tiene ferma un'istantanea vecchia
    conn.commit()
    return o


def chiudi(conn, o):
    """Riporta sotto il nome del compartimento le cache scritte durante la
    richiesta (riepilogo, proposte). Non solleva mai: e' una comodita'."""
    if o is None or o.visore == INCERTO:
        return
    try:
        suffisso = "@" + o.visore
        for k, v in conn.execute("SELECT key, value FROM temp.meta").fetchall():
            if not k.startswith(_META_PER_COMP):
                continue
            conn.execute(
                "INSERT INTO main.meta(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (k + suffisso, v))
        conn.commit()
    except Exception:  # noqa: BLE001 - sola lettura o base bloccata: niente cache
        pass


def sessione_viva(conn, o):
    """La sessione che ingest ha visto per ultima come viva (`live_session` in
    `meta`), se e' visibile a chi guarda, altrimenti None. `live_` non passa
    nella `meta` temporanea (e' di nessuna vista): si legge da `main.meta` e si
    filtra per la visibilita' della sessione."""
    try:
        r = conn.execute("SELECT value FROM main.meta WHERE key='live_session'").fetchone()
    except Exception:  # noqa: BLE001
        return None
    sid = r[0] if r else None
    if not sid or not o.sessione_ok(sid):
        return None
    return sid


# --------------------------------------------------------------------------
# le ricerche che le viste non coprono
# --------------------------------------------------------------------------

_SCHEDE = {"task": "tasks", "memoria": "knowledge", "capacita": "capabilities",
           "sessione": "sessions", "post": "posts", "commit": "commits"}


def _ok_temp(conn):
    """Le tabelle `_ok_<tabella>` (gli id visibili) che `applica` ha creato."""
    return {r[0][4:] for r in conn.execute(
        "SELECT name FROM temp.sqlite_master WHERE type='table'")
        if r[0].startswith("_ok_")}


def cerca_schede(conn, o, q, limit=20):
    """`store.search` (l'indice FTS delle schede) senza le schede degli altri.

    L'indice e' una tabella virtuale e non si filtra con una vista. Filtrare
    DOPO il taglio per rango da' falsi negativi: chi ha poche schede in un
    archivio grande non trova niente, perche' le prime N per rango sono tutte
    degli altri. Quindi il filtro sta DENTRO la query: `kind` e `ref_id` devono
    stare fra gli id visibili (le tabelle `_ok_*` di `applica`), e il `LIMIT` si
    applica a quello che resta."""
    from . import store
    q = (q or "").strip()
    if not q:
        return []
    if store.has_fts(conn):
        expr = store._fts_query(q)
        presenti = _ok_temp(conn)
        cond = " OR ".join(
            "(kind='%s' AND ref_id IN (SELECT id FROM temp._ok_%s))" % (k, t)
            for k, t in _SCHEDE.items() if t in presenti)
        if expr and cond:
            try:
                righe = conn.execute(
                    "SELECT kind, ref_id, title, project, ts, "
                    "snippet(search_fts, 3, '«', '»', '…', 14) AS snip "
                    "FROM search_fts WHERE search_fts MATCH ? AND (%s) "
                    "ORDER BY rank LIMIT ?" % cond, (expr, limit)).fetchall()
                return [dict(r) for r in righe]
            except Exception:  # noqa: BLE001 - FTS rifiuta certe query: come store.search
                pass
    # senza indice, `store.search` cerca nei task, che nella connessione filtrata
    # sono gia' la vista; il controllo a valle e' una seconda cintura
    fuori = []
    for h in store.search(conn, q, limit):
        tab = _SCHEDE.get(h.get("kind"))
        if tab and h.get("ref_id") in o.ok[tab]:
            fuori.append(h)
    return fuori[:limit]


def cerca_turni(conn, o, q, limit=12, progetto=None):
    """`turni.cerca` senza i turni degli altri (per sessione e per percorso del
    transcript). Torna `(turni, gruppi)`.

    Come per le schede il filtro sta DENTRO la ricerca (`turni.ricerca` con un
    `Filtro` che dice se `(sessione, percorso)` e' visibile), prima del taglio per
    rango e del `LIMIT`: un compartimento con un turno solo in un indice di
    migliaia lo trova. Stesso ordine, stesso scarto dei doppioni; i gruppi contano
    per progetto sui soli turni visibili, su tutto l'indice.

    Le tabelle si leggono da `main`, non dalle viste temporanee di `applica`: la
    visibilita' di sessioni e progetti la decide il `Filtro` con gli stessi id, e
    una giuntura sulle viste faceva ripetere il controllo per ogni riga trovata."""
    from . import turni

    def vede(sessione, percorso):
        return o.sessione_ok(sessione, percorso or "")
    return turni.ricerca(conn, q, limit, progetto,
                         filtro=turni.Filtro(vede, o.ok["sessions"], o.ok["projects"]))


# --------------------------------------------------------------------------
# scritture da un agente: controllare prima di che compartimento e' l'oggetto
# --------------------------------------------------------------------------

MSG_ALTRO = ("%s non appartiene al tuo compartimento: da qui non si legge e non si "
             "tocca (e' di un altro compartimento).")


def progetto_esatto(conn, ident):
    """La riga del progetto che `ident` nomina ESATTAMENTE (id, chiave o nome),
    senza la ricerca per somiglianza di `store.get_project`, o None. Serve a
    dire "esiste ma e' di un altro" solo quando chi scrive lo ha nominato per
    davvero, non quando la somiglianza ha pescato a caso."""
    if ident in (None, "", 0):
        return None
    if isinstance(ident, int) or (isinstance(ident, str) and ident.isdigit()):
        r = conn.execute("SELECT id FROM projects WHERE id=?", (int(ident),)).fetchone()
        if r:
            return r
    r = conn.execute("SELECT id FROM projects WHERE key=? OR lower(name)=lower(?)",
                     (str(ident), str(ident))).fetchone()
    return r


def progetto_scrivibile(conn, lettura, ombra, ident, esiste=False, chiave=False):
    """Il progetto da usare in una scrittura, senza uscire dal compartimento.

    Senza compartimenti (`ombra` None) torna `ident` com'e' (comportamento di
    sempre). Con i compartimenti torna l'id (o la chiave, con `chiave`) del
    progetto SE chi scrive lo vede; se `ident` ne nomina esattamente uno di un
    altro compartimento rifiuta con un messaggio chiaro (non nomina il
    compartimento dell'altro: e' quello che non si deve sapere). Un progetto che
    non c'e' resta come prima (nessuna scheda, o 'inesistente' se `esiste` dice
    che ci deve essere): non si ripiega mai sulla ricerca per somiglianza
    sull'intero archivio, che potrebbe pescare un progetto altrui.

    `conn` e' la connessione di scrittura (vede tutto), `lettura` quella con le
    viste. Vale per l'MCP, per il comando da terminale e per la dashboard."""
    from . import actions, store
    if ombra is None:
        return ident
    if ident in (None, "", 0):
        if esiste:
            raise actions.BadInput("serve il progetto")
        return None
    riga = store.get_project(lettura, ident)
    if riga:
        return riga["key"] if chiave else riga["id"]
    if progetto_esatto(conn, ident):
        raise actions.BadInput(MSG_ALTRO % ("il progetto '%s'" % ident))
    if esiste:
        raise actions.BadInput("progetto '%s' inesistente" % ident)
    return None


def oggetto_scrivibile(conn, lettura, ombra, leggi, chiave, nome):
    """Rifiuta di toccare un task, un post o un lancio che chi scrive non vede:
    la lettura con le viste (`leggi(lettura, chiave)`) non lo trova, quella
    senza si'. Se non esiste in nessuno dei due la funzione che scrive dice da
    se' 'inesistente'."""
    from . import actions
    if ombra is None:
        return
    if leggi(lettura, chiave):
        return
    if leggi(conn, chiave):
        raise actions.BadInput(MSG_ALTRO % ("%s %s" % (nome, chiave)))


MSG_INCERTO = ("questa sessione ha segnali di piu' compartimenti: Plancia non "
               "mostra niente (e non scrive) finche' non e' chiaro di quale sia.")

MSG_AMMINISTRAZIONE = ("comando di amministrazione di tutta Plancia: da una sessione di "
                       "un compartimento nominato non si lancia.")


class Vista:
    """Cosa vede e cosa puo' scrivere chi lancia un comando: il comando `plancia`
    da terminale, l'assistente vocale (`jarvis`), la dashboard quando scrive.

    Due connessioni, come nel server MCP: `lettura` ha le viste temporanee che
    nascondono gli altri compartimenti (sola lettura, salvo le cache di `meta`
    che `chiudi` riporta sotto il nome giusto), `conn` e' quella di scrittura,
    da usare solo DOPO aver controllato di che compartimento e' l'oggetto
    (`progetto`, `oggetto`). Senza compartimenti nominati le due sono la stessa
    connessione, `ombra` e' None e non cambia niente."""

    def __init__(self, conn, lettura, ombra, visore):
        self.conn, self.lettura, self.ombra, self.visore = conn, lettura, ombra, visore

    @property
    def attiva(self):
        return self.ombra is not None

    @property
    def incerta(self):
        return self.attiva and self.visore == INCERTO

    @property
    def nominato(self):
        return self.attiva and self.visore not in (PREDEFINITO, INCERTO)

    @property
    def tag(self):
        """Cosa mettere nella colonna `compartimento` di quello che si crea: il
        nome, se chi scrive e' di un nominato (vale anche se la sessione non e'
        nota al database); vuoto per il predefinito e senza compartimenti."""
        return self.visore if self.nominato else ""

    def progetto(self, ident, esiste=False, chiave=False):
        return progetto_scrivibile(self.conn, self.lettura, self.ombra, ident,
                                   esiste=esiste, chiave=chiave)

    def oggetto(self, leggi, chiave, nome):
        oggetto_scrivibile(self.conn, self.lettura, self.ombra, leggi, chiave, nome)

    def chiudi(self):
        """Riporta le cache scritte durante il comando e chiude tutto. Non
        solleva mai."""
        try:
            if self.lettura is not self.conn:
                chiudi(self.lettura, self.ombra)
                self.lettura.close()
        except Exception:  # noqa: BLE001
            pass
        try:
            self.conn.close()
        except Exception:  # noqa: BLE001
            pass


def apri_vista(scelta=None, dashboard=False, sess=None):
    """La `Vista` di chi lancia un comando.

    Da un agente o da un terminale (`dashboard` falso): il compartimento e'
    quello di chi lancia (`visore_cli`). Dalla dashboard (`dashboard` vero) e'
    quello scelto (`scelta`, senza: il predefinito), con la regola della
    persona; una scelta sconosciuta e' un errore, non il predefinito in
    silenzio. Se la separazione non riesce (un'eccezione) il comando non parte:
    niente lettura senza filtro."""
    from . import actions, store
    conn = store.connect()
    lettura = None
    try:
        store.init_db(conn)
        ambito = attivo()
        if ambito is None:
            return Vista(conn, conn, None, None)
        lettura = store.connect()
        if dashboard:
            if scelta and scelta not in elenco(ambito):
                raise actions.BadInput("compartimento sconosciuto: %s" % scelta)
            visore = scelta or PREDEFINITO
            ombra = applica(lettura, ambito, visore, dashboard=True,
                            appart=appartenenze(lettura, ambito))
        else:
            visore = visore_cli(ambito, sess)
            ombra = applica(lettura, ambito, visore)
        return Vista(conn, lettura, ombra, visore)
    except BaseException:
        if lettura is not None:
            lettura.close()
        conn.close()
        raise
