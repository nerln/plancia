"""Server locale: API REST e dashboard.

Ascolta solo su 127.0.0.1. Le scritture chiedono il token in ~/.plancia/token,
così un'altra pagina aperta nel browser non può toccare i dati.
"""

import json
import mimetypes
import os
import re
import threading
import traceback
import urllib.parse
from pathlib import Path
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import (actions, agente, briefing, cantiere, compartimenti_viste as viste,
               config, eventi, ingest, jarvis, lavagna, recap, riprendi, slot, store,
               voice)

SYNC_LOCK = threading.Lock()
SYNC_STATE = {"running": False, "message": "", "started": None, "result": None}

# LOTTO-L3-RITOCCO punto 4: `serve()` la imposta a True quando il processo è
# partito con `--no-sync` (`sync_first=False`): nessun sync deve mai partire
# per tutta la vita del processo (vedi il commento su `serve`, più sotto), e
# `/api/sync` deve dirlo invece di far finta di aver avviato qualcosa che poi
# il ticker (mai partito) non farebbe mai davvero. Un modulo-livello invece di
# un parametro passato in giro perché `jarvis._esegui`, che risponde alla
# stessa domanda a voce, la legge da qui (import locale, per non creare un
# ciclo: vedi jarvis.py).
_NO_SYNC_ATTIVO = False


def _sync_worker(full=False, modo="tutto"):
    with SYNC_LOCK:
        SYNC_STATE.update(running=True, message="avvio", started=store.now(), result=None)
        try:
            res = ingest.sync(full=full, modo=modo,
                              progress=lambda m: SYNC_STATE.update(message=m))
            SYNC_STATE.update(result=res, message="fatto")
        except Exception as exc:
            SYNC_STATE.update(message=f"errore: {exc}")
            traceback.print_exc()
        finally:
            SYNC_STATE.update(running=False)


def start_sync(full=False, modo="tutto") -> bool:
    if SYNC_STATE["running"]:
        return False
    threading.Thread(target=_sync_worker, args=(full, modo), daemon=True).start()
    return True


# --------------------------------------------------------------------------
# letture aggregate
# --------------------------------------------------------------------------

def overview(conn, lang=None) -> dict:
    week = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    month = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    one = lambda sql, p=(): conn.execute(sql, p).fetchone()[0]

    stats = {
        "progetti_attivi": one("SELECT COUNT(*) FROM projects WHERE status='attivo' AND hidden=0"),
        "task_aperti": one("SELECT COUNT(*) FROM tasks WHERE status IN ('aperto','in corso','bloccato')"),
        "task_scaduti": one("SELECT COUNT(*) FROM tasks WHERE status IN ('aperto','in corso','bloccato') "
                            "AND due IS NOT NULL AND due < date('now')"),
        "sessioni_totali": one(f"SELECT COUNT(*) FROM sessions s WHERE {store.visibile()}"),
        "sessioni_settimana": one(f"SELECT COUNT(*) FROM sessions s WHERE started_at > ? AND {store.visibile()}", (week,)),
        "commit_mese": one("SELECT COUNT(*) FROM commits WHERE date > ?", (month,)),
        "post_pubblicati": one("SELECT COUNT(*) FROM posts WHERE status='pubblicato'"),
        "post_in_coda": one("SELECT COUNT(*) FROM posts WHERE status IN ('idea','bozza','approvato','programmato')"),
        "memorie": one("SELECT COUNT(*) FROM knowledge"),
        "scambi": one(f"SELECT COUNT(*) FROM sessions s WHERE scambi > 0 AND {store.visibile()}"),
        "token_out_mese": one(f"SELECT COALESCE(SUM(out_tokens),0) FROM sessions s WHERE started_at > ? AND {store.visibile()}", (month,)),
    }

    projects = [dict(r) for r in conn.execute(
        "SELECT p.*, "
        "(SELECT COUNT(*) FROM tasks t WHERE t.project_id=p.id AND t.status IN ('aperto','in corso','bloccato')) AS task_aperti, "
        "(SELECT COUNT(*) FROM sessions s WHERE s.project_id=p.id) AS sessioni, "
        "(SELECT COALESCE(SUM(s.out_tokens),0) FROM sessions s WHERE s.project_id=p.id "
        " AND s.started_at > ?) AS token_30g, "
        "(SELECT GROUP_CONCAT(r.name) FROM repos r WHERE r.project_id=p.id) AS repos "
        "FROM projects p WHERE p.hidden=0 "
        "ORDER BY p.pinned DESC, CASE p.status WHEN 'attivo' THEN 0 WHEN 'idea' THEN 1 "
        "WHEN 'in pausa' THEN 2 ELSE 3 END, p.priority ASC, p.last_activity DESC",
        (month,)
    ).fetchall()]

    events = [dict(r) for r in conn.execute(
        "SELECT e.*, p.name AS progetto, p.key AS project_key FROM events e "
        f"LEFT JOIN projects p ON p.id=e.project_id WHERE {store.visibile('e')} "
        "AND e.kind <> 'hook' ORDER BY e.ts DESC LIMIT 60"
    ).fetchall()]

    # attività per giorno, ultimi 30, separata per agente
    vuoto = {"claude": 0, "codex": 0, "commit": 0}
    activity = {}
    for row in conn.execute(
            f"SELECT substr(started_at,1,10) AS d, COALESCE(agent,'claude') AS a, "
            f"COUNT(*) AS n FROM sessions s WHERE started_at > ? AND {store.visibile()} "
            f"GROUP BY d, a", (month,)):
        activity.setdefault(row["d"], dict(vuoto))[row["a"]] = row["n"]
    for row in conn.execute(
            "SELECT substr(date,1,10) AS d, COUNT(*) AS n FROM commits WHERE date > ? GROUP BY d",
            (month,)):
        activity.setdefault(row["d"], dict(vuoto))["commit"] = row["n"]
    days = []
    for i in range(29, -1, -1):
        day = (datetime.now(timezone.utc) - timedelta(days=i)).strftime("%Y-%m-%d")
        cell = activity.get(day, dict(vuoto))
        days.append({"giorno": day, "sessioni": cell["claude"] + cell["codex"], **cell})

    agenti = [dict(r) for r in conn.execute(
        f"SELECT COALESCE(agent,'claude') AS agente, COUNT(*) AS sessioni, "
        f"COALESCE(SUM(out_tokens),0) AS token, COALESCE(SUM(n_tools),0) AS tool, "
        f"COALESCE(SUM(n_user),0) AS scambi_tuoi, MAX(started_at) AS ultimo "
        f"FROM sessions s WHERE {store.visibile()} GROUP BY agente ORDER BY token DESC"
    ).fetchall()]

    try:
        from . import proposte as _p
        stats["fuga"] = _p._fuga(conn)
    except Exception:
        stats["fuga"] = None

    try:
        from . import lavagna as _lav
        stats["lavagna_aperti"] = sum(
            v.get("aperti", 0) for v in _lav.conteggi(conn).values())
    except Exception:
        pass

    # Quanto e' grande l'indice dei turni: e' il numero che dice se cercare qui
    # ha senso, e la guida lo mostra invece di prometterlo.
    try:
        from . import turni as _turni
        stats["indice"] = _turni.stato(conn)
    except Exception:
        pass

    from . import proposte as _prop
    try:
        prop = _prop.calcola(conn, lang or config.load_config().get("lingua", "it"))
        # Si salvano quelle che si stanno mostrando: se poi dici "fallo", deve
        # partire quella che hai davanti agli occhi, non una calcolata prima.
        _prop.salva(conn, prop)
    except Exception:
        prop = []

    return {
        "stats": stats,
        "proposte": prop,
        "benvenuto": store.get_meta(conn, "onboarding_fatto") != "1",
        "agenti": agenti,
        "progetti": projects,
        "task": actions.tasks_list(conn, "aperti", limit=20),
        "post": actions.posts_list(conn, limit=40),
        "eventi": events,
        "attivita": days,
        "sessioni_recenti": [dict(r) for r in conn.execute(
            "SELECT s.session_id, s.title, substr(s.first_prompt,1,180) AS prompt, "
            "s.started_at, s.ended_at, s.n_user, s.n_tools, s.out_tokens, s.cwd, "
            "s.dedotto_da, s.dir_dedotta, "
            "p.name AS progetto, p.key AS project_key FROM sessions s "
            f"LEFT JOIN projects p ON p.id=s.project_id WHERE {store.visibile()} "
            "ORDER BY s.started_at DESC LIMIT 12"
        ).fetchall()],
        "ultimo_sync": store.get_meta(conn, "last_sync_end"),
        "sync": dict(SYNC_STATE),
    }


def project_detail(conn, ident) -> dict:
    row = store.get_project(conn, ident)
    if not row:
        return None
    pid = row["id"]
    return {
        "progetto": dict(row),
        "link": [dict(r) for r in conn.execute(
            "SELECT kind, value FROM project_links WHERE project_id=?", (pid,)).fetchall()],
        "task": actions.tasks_list(conn, "tutti", pid, limit=100),
        "post": [dict(r) for r in conn.execute(
            "SELECT * FROM posts WHERE project_id=? ORDER BY updated_at DESC", (pid,)).fetchall()],
        "sessioni": [dict(r) for r in conn.execute(
            "SELECT session_id, title, substr(first_prompt,1,200) AS prompt, started_at, "
            "n_user, n_tools, out_tokens, models, dedotto_da, dir_dedotta "
            "FROM sessions WHERE project_id=? "
            "ORDER BY started_at DESC LIMIT 40", (pid,)).fetchall()],
        "memoria": [dict(r) for r in conn.execute(
            "SELECT id, name, description, type, updated_at FROM knowledge WHERE project_id=? "
            "ORDER BY updated_at DESC", (pid,)).fetchall()],
        "repo": [dict(r) for r in conn.execute(
            "SELECT * FROM repos WHERE project_id=?", (pid,)).fetchall()],
        "commit": [dict(r) for r in conn.execute(
            "SELECT c.*, s.title AS sessione_titolo FROM commits c "
            "JOIN repos r ON r.name=c.repo "
            "LEFT JOIN sessions s ON s.session_id = c.session_id WHERE r.project_id=? "
            "ORDER BY c.date DESC LIMIT 30", (pid,)).fetchall()],
        "eventi": [dict(r) for r in conn.execute(
            "SELECT * FROM events WHERE project_id=? ORDER BY ts DESC LIMIT 60", (pid,)).fetchall()],
    }


def prossimi_raggruppati(conn) -> dict:
    """`/api/prossimi`: le righe di `slot.prossimi()` raggruppate per area
    (il progetto padre), per il pannello "Prossimi" di Oggi (LOTTO-L2-VISTA,
    punto 1).

    Il gruppo si apre alla prima riga incontrata scorrendo `slot.prossimi()`
    nel suo ordine (già quello del verdetto: scadenza minore prima, poi
    ultima attività) e non si riordina più dopo: così la primissima riga del
    primo gruppo resta la primissima riga dell'ordine originale, e "la prima
    riga con scadenza ha la scadenza minore" (prova rossa del lotto) resta
    vero anche raggruppato. Stesso ragionamento di
    `briefing._blocco_prossimi`, che raggruppa la stessa lista per lo stesso
    motivo, ma per il testo del briefing invece che per questo JSON.

    Un padre attivo che ha anche lui una riga (un suo task o next_action) va
    nel gruppo con la propria chiave, non in "senza area": la sua chiave è
    già un'intestazione (compare come area di almeno un figlio), non serve
    un secondo gruppo solo per lui.
    """
    righe = slot.prossimi(conn)
    if not righe:
        return {"aree": [], "senza_area": []}

    chiavi_area = {r["area"] for r in righe if r["area"]}
    nomi_area = {}
    if chiavi_area:
        segnaposto = ",".join("?" for _ in chiavi_area)
        for r in conn.execute(
                f"SELECT key, name FROM projects WHERE key IN ({segnaposto})",
                list(chiavi_area)):
            nomi_area[r["key"]] = r["name"]

    gruppi, ordine, senza_area = {}, [], []
    for r in righe:
        chiave_gruppo = r["area"] or (r["key"] if r["key"] in chiavi_area else None)
        if chiave_gruppo is None:
            senza_area.append(r)
            continue
        if chiave_gruppo not in gruppi:
            gruppi[chiave_gruppo] = []
            ordine.append(chiave_gruppo)
        gruppi[chiave_gruppo].append(r)

    return {
        "aree": [{"key": k, "name": nomi_area.get(k, k), "righe": gruppi[k]} for k in ordine],
        "senza_area": senza_area,
    }


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------

def _sintesi_o_nota(testo, lang, *args, **kwargs):
    """`(info, None)` con il file audio, oppure `(None, nota)` quando su questa
    macchina non c'e' un motore vocale (Linux senza espeak-ng, Windows senza
    PowerShell). La voce e' un di piu': senza, la risposta con il testo parte lo
    stesso, e `nota` dice cosa installare."""
    try:
        return voice.sintesi(testo, lang, *args, **kwargs), None
    except voice.NessunMotoreVoce as exc:
        return None, str(exc)


def _senza_voce(risposta, nota) -> dict:
    """Il testo resta, la voce manca: `voce` a null e `nota_voce` col perche'."""
    risposta["voce"] = None
    risposta["nota_voce"] = nota
    return risposta


def compartimenti_info(scelto=None) -> dict:
    """`/api/compartimenti`: cosa sa la dashboard dei compartimenti.

    Senza compartimenti nominati in config.json: `attivo` falso e nessun
    elenco (il selettore non si disegna e tutto resta com'e' sempre). Con dei
    nominati: il predefinito e poi i nominati, con i nomi della config, e
    quello scelto (senza scelta o con un nome che non c'e', il predefinito).
    La dashboard e' la vista di una persona, non di un agente: mostra tutto,
    ma un compartimento alla volta."""
    ambito = viste.attivo()
    if ambito is None:
        return {"attivo": False, "elenco": [], "scelto": None,
                "predefinito": viste.PREDEFINITO}
    elenco = viste.elenco(ambito)
    return {"attivo": True, "elenco": elenco,
            "scelto": scelto if scelto in elenco else viste.PREDEFINITO,
            "predefinito": viste.PREDEFINITO}


def _connessione_separata(scelta):
    """`(conn, ombra)`: una connessione con le viste del compartimento scelto
    (`ombra` e' None senza compartimenti: e' la connessione di sempre). Una
    scelta sconosciuta e' un errore, non il predefinito in silenzio: chi ha
    scritto il nome sbagliato non deve credere di guardare il proprio."""
    conn = store.connect()
    try:
        ambito = viste.attivo()
        if ambito is None:
            return conn, None
        if scelta and scelta not in viste.elenco(ambito):
            raise actions.BadInput("compartimento sconosciuto: %s" % scelta)
        return conn, viste.applica(conn, ambito, scelta or viste.PREDEFINITO,
                                   dashboard=True,
                                   appart=viste.appartenenze(conn, ambito))
    except BaseException:
        conn.close()
        raise


class Handler(BaseHTTPRequestHandler):
    server_version = "Plancia/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass  # niente rumore sul terminale

    # --- utilità ---------------------------------------------------------
    def _send(self, code, body=b"", ctype="application/json; charset=utf-8", extra=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for key, val in (extra or {}).items():
            self.send_header(key, val)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, data, code=200):
        self._send(code, json.dumps(data, ensure_ascii=False, default=str))

    def _error(self, code, msg):
        self._json({"errore": msg}, code)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    def _authorised(self) -> bool:
        return self.headers.get("X-Plancia-Token") == config.get_token()

    # --- rotte -----------------------------------------------------------
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)
        try:
            if path.startswith("/api/"):
                return self._api_get(path, query)
            return self._static(path)
        except BrokenPipeError:
            pass
        except Exception as exc:
            traceback.print_exc()
            self._error(500, str(exc))

    do_HEAD = do_GET

    def do_POST(self):
        self._write_request("POST")

    def do_PATCH(self):
        self._write_request("PATCH")

    def do_DELETE(self):
        self._write_request("DELETE")

    def _write_request(self, method):
        parsed = urllib.parse.urlparse(self.path)
        if not self._authorised():
            return self._error(403, "token mancante o non valido")
        try:
            q = urllib.parse.parse_qs(parsed.query)
            self._scelta = (q.get("compartimento") or [None])[0]
            self._api_write(method, parsed.path, self._body())
        except actions.BadInput as exc:
            self._error(400, str(exc))
        except BrokenPipeError:
            pass
        except Exception as exc:
            traceback.print_exc()
            self._error(500, str(exc))

    # --- API -------------------------------------------------------------
    def _api_get(self, path, query):
        first = lambda k, d=None: (query.get(k) or [d])[0]
        if path == "/api/compartimenti":
            return self._json(compartimenti_info(first("compartimento")))
        # I compartimenti (vedi plancia/compartimenti_viste.py): con dei nominati
        # in config ogni lettura passa da una connessione che vede solo il
        # compartimento scelto con `?compartimento=` (senza: il predefinito).
        try:
            conn, ombra = _connessione_separata(first("compartimento"))
        except actions.BadInput as exc:
            return self._error(400, str(exc))
        try:
            if path == "/api/overview":
                return self._json(overview(conn, first("lang")))
            if path == "/api/briefing":
                return self._send(200, briefing.build(conn, first("project")),
                                  "text/markdown; charset=utf-8")
            if path == "/api/projects":
                # ?albero=1 (LOTTO-L2-VISTA): la vista Progetti annidata legge
                # da qui, padri con i loro figli e i totali già sommati
                # (slot.albero, non toccato da questo lotto: solo instradato).
                # Il parametro conta per presenza/valore, non solo per
                # presenza: first(...) restituisce la stringa così com'è, e
                # "0" (falsy in Python, ma non un valore vuoto) non deve
                # disattivare l'albero come farebbe un `if first("albero"):`
                # nudo.
                if first("albero") not in (None, "", "0"):
                    return self._json(slot.albero(conn))
                return self._json([dict(r) for r in conn.execute(
                    "SELECT * FROM projects ORDER BY pinned DESC, priority, last_activity DESC"
                ).fetchall()])
            m = re.match(r"^/api/projects/([^/]+)$", path)
            if m:
                data = project_detail(conn, urllib.parse.unquote(m.group(1)))
                return self._json(data) if data else self._error(404, "progetto inesistente")
            if path == "/api/prossimi":
                return self._json(prossimi_raggruppati(conn))
            if path == "/api/tasks":
                progetto = first("project")
                if first("dopo") not in (None, "", "0") and progetto:
                    # Il cassetto "Dopo" nel drawer del progetto: gli stessi
                    # task aperti che slot.prossimi() userebbe come "cosa"
                    # per questo progetto (stesso ordine: _ORDINE_TASK di
                    # slot.py è copiato da qui, vedi il commento su quella
                    # costante), oltre al primo. Il drawer non ha una riga
                    # di Prossimi (quella sta nel pannello di Oggi): mostra
                    # già tutti i task del progetto nella sua sezione
                    # "Task", quindi il cassetto ripete apposta i task oltre
                    # il primo, così com'è nel lotto (vedi il dubbio
                    # nel rapporto sulla ridondanza con quella sezione).
                    aperti = actions.tasks_list(conn, "aperti", progetto, limit=100)
                    return self._json(aperti[1:])
                return self._json(actions.tasks_list(conn, first("status"), progetto,
                                                     int(first("limit", 200))))
            if path == "/api/posts":
                return self._json(actions.posts_list(conn, first("status"), first("platform")))
            if path == "/api/sessions":
                sql = ("SELECT s.*, p.name AS progetto, p.key AS project_key FROM sessions s "
                       "LEFT JOIN projects p ON p.id=s.project_id WHERE 1=1")
                params = []
                if first("agent"):
                    sql += " AND COALESCE(s.agent,'claude')=?"
                    params.append(first("agent"))
                if first("project"):
                    row = store.get_project(conn, first("project"))
                    sql += " AND s.project_id=?"
                    params.append(row["id"] if row else -1)
                if first("q"):
                    sql += " AND (s.first_prompt LIKE ? OR s.title LIKE ? OR s.cwd LIKE ?)"
                    params += [f"%{first('q')}%"] * 3
                sql += " ORDER BY s.started_at DESC LIMIT ?"
                params.append(int(first("limit", 200)))
                return self._json([dict(r) for r in conn.execute(sql, params).fetchall()])
            if path == "/api/events":
                sql = ("SELECT e.*, p.name AS progetto, p.key AS project_key FROM events e "
                       "LEFT JOIN projects p ON p.id=e.project_id WHERE 1=1")
                params = []
                if first("kind"):
                    sql += " AND e.kind=?"
                    params.append(first("kind"))
                sql += " ORDER BY e.ts DESC LIMIT ?"
                params.append(int(first("limit", 200)))
                return self._json([dict(r) for r in conn.execute(sql, params).fetchall()])
            if path == "/api/knowledge":
                if first("name"):
                    row = conn.execute("SELECT * FROM knowledge WHERE name=?",
                                       (first("name"),)).fetchone()
                    return self._json(dict(row)) if row else self._error(404, "non trovata")
                return self._json([dict(r) for r in conn.execute(
                    "SELECT k.id, k.name, k.description, k.type, k.updated_at, k.links, "
                    "p.name AS progetto, p.key AS project_key FROM knowledge k "
                    "LEFT JOIN projects p ON p.id=k.project_id ORDER BY k.updated_at DESC"
                ).fetchall()])
            if path == "/api/memoria/mappa":
                from . import mappa as _mappa
                return self._json(_mappa.mappa(conn))
            if path == "/api/memoria/prova":
                from . import mappa as _mappa
                return self._json(_mappa.prova(conn, first("q", "")))
            if path == "/api/proposte":
                from . import proposte as _prop
                lista = _prop.calcola(conn, recap.lang_or_default(first("lang")))
                _prop.salva(conn, lista)
                return self._json(lista)
            if path == "/api/lavagna":
                return self._json({
                    "voci": lavagna.elenco(conn, first("stato", "aperti"), first("fonte"),
                                           int(first("limite", 200))),
                    "conteggi": lavagna.conteggi(conn),
                    "in_corso": cantiere.in_corso(conn),
                })
            if path == "/api/runs":
                return self._json(cantiere.elenco(conn, int(first("limite", 20))))
            m = re.match(r"^/api/runs/(\d+)$", path)
            if m:
                d = cantiere.dettaglio(conn, int(m.group(1)))
                return self._json(d) if d else self._error(404, "lancio inesistente")
            if path == "/api/eventi":
                limite = int(first("limite", 100))
                if ombra is not None:
                    # il registro e' un file solo, di tutti: si toglie a valle (e
                    # `stato` non dice piu' quanti eventi ha in tutto)
                    righe = ombra.filtra_eventi(eventi.leggi(
                        first("dopo"), first("tipo"), max(limite * 20, 500)))[:limite]
                    return self._json({"eventi": righe, "stato": {
                        "schema": eventi.SCHEMA, "tipi": list(eventi.TIPI)}})
                return self._json({"eventi": eventi.leggi(first("dopo"), first("tipo"),
                                                          limite),
                                   "stato": eventi.stato()})
            if path == "/api/agents":
                mese = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
                totali = [dict(r) for r in conn.execute(
                    f"SELECT COALESCE(agent,'claude') AS agente, COUNT(*) AS sessioni, "
                    f"COALESCE(SUM(out_tokens),0) AS token, COALESCE(SUM(n_tools),0) AS tool, "
                    f"COALESCE(SUM(n_user),0) AS messaggi, COALESCE(SUM(scambi),0) AS scambi, "
                    f"MIN(started_at) AS primo, MAX(started_at) AS ultimo "
                    f"FROM sessions s WHERE {store.visibile()} GROUP BY agente").fetchall()]
                per_giorno = [dict(r) for r in conn.execute(
                    f"SELECT substr(started_at,1,10) AS giorno, COALESCE(agent,'claude') AS agente, "
                    f"COUNT(*) AS n FROM sessions s WHERE started_at > ? AND {store.visibile()} "
                    f"GROUP BY giorno, agente", (mese,)).fetchall()]
                per_progetto = [dict(r) for r in conn.execute(
                    f"SELECT p.name AS progetto, p.key AS chiave, "
                    f"SUM(CASE WHEN COALESCE(s.agent,'claude')='claude' THEN 1 ELSE 0 END) AS claude, "
                    f"SUM(CASE WHEN s.agent='codex' THEN 1 ELSE 0 END) AS codex "
                    f"FROM sessions s JOIN projects p ON p.id=s.project_id "
                    f"WHERE p.hidden=0 GROUP BY p.id HAVING claude+codex > 0 "
                    f"ORDER BY claude+codex DESC LIMIT 12").fetchall()]
                scambi = [dict(r) for r in conn.execute(
                    "SELECT e.ts, e.title, e.detail, p.name AS progetto FROM events e "
                    "LEFT JOIN projects p ON p.id=e.project_id WHERE e.kind='scambio' "
                    "ORDER BY e.ts DESC LIMIT 20").fetchall()]
                from . import codex as codex_mod
                return self._json({"totali": totali, "per_giorno": per_giorno,
                                   "per_progetto": per_progetto, "scambi": scambi,
                                   "codex": codex_mod.stato()})
            if path == "/api/capabilities":
                return self._json([dict(r) for r in conn.execute(
                    "SELECT * FROM capabilities ORDER BY kind, name").fetchall()])
            if path == "/api/search":
                # Due indici, e l'ordine dice quale conta. Nei turni c'e' quello
                # che e' stato detto davvero; nelle schede ci sono i titoli. Fino
                # al 9 agosto 2026 esisteva solo il secondo, che indicizzava lo
                # 0,08% del materiale, ed e' il motivo per cui questa ricerca non
                # trovava mai niente.
                from . import turni
                q = first("q", "")
                if ombra is not None:
                    # gli indici FTS non si filtrano con una vista: si toglie a valle
                    dai_turni, gruppi = viste.cerca_turni(
                        conn, ombra, q, int(first("limit", 30)), first("progetto") or None)
                    return self._json({
                        "turni": dai_turni, "progetti": gruppi,
                        "schede": viste.cerca_schede(conn, ombra, q, int(first("limit", 20))),
                    })
                return self._json({
                    "turni": turni.cerca(conn, q, int(first("limit", 30)),
                                         first("progetto") or None),
                    # Il conteggio è su tutto l'indice, non sulla pagina: dice se
                    # la cosa cercata sta in un progetto solo o è sparsa.
                    "progetti": turni.raggruppa(conn, q),
                    "schede": store.search(conn, q, int(first("limit", 20))),
                })
            if path == "/api/recap":
                if first("solo_cache"):
                    return self._json(recap.solo_cache(conn, first("lang")))
                data = recap.build(conn, first("day"), first("lang"), first("engine"))
                if first("compact"):
                    data.pop("dati", None)
                return self._json(data)
            if path == "/api/voice/status":
                return self._json(voice.stato())
            if path == "/api/status":
                return self._json({
                    "sync": dict(SYNC_STATE),
                    "ultimo_sync": store.get_meta(conn, "last_sync_end"),
                    "sessione_viva": store.get_meta(conn, "live_session"),
                    "ultima_voce": store.get_meta(conn, "ultima_voce"),
                    "ultima_voce_da": store.get_meta(conn, "ultima_voce_da"),
                })
            m = re.match(r"^/api/riprendi/(\d+)$", path)
            if m:
                # LOTTO-L3-RIPRENDI-UI, punto 1: i tre stati di un task
                # (plancia/riprendi.py, non toccato da questo lotto) piu' il
                # comando pronto e il messaggio, cosi' la dashboard mostra
                # UN pulsante con lo stato invece di dover ricalcolarlo lei.
                task = actions.task_get(conn, int(m.group(1)))
                if not task:
                    return self._error(404, "task inesistente")
                s = riprendi.stato(conn, task)
                argv = riprendi.comando(task, s, conn)
                # La data da mostrare in "sessione del <data>" (chiusa/codex):
                # riprendi.stato() non la porta (non le serve per decidere lo
                # stato), quindi si va a prenderla dalla sessione vera se
                # c'e', e solo se manca si ripiega sull'ultimo tocco del task.
                sessione_data = None
                if s.get("session_id"):
                    r = conn.execute("SELECT started_at FROM sessions WHERE session_id=?",
                                     (s["session_id"],)).fetchone()
                    sessione_data = r["started_at"] if r else None
                sessione_data = sessione_data or task.get("updated_at")
                return self._json({"riprendi": s, "comando": argv,
                                   "messaggio": riprendi.messaggio(task),
                                   "sessione_data": sessione_data})
            return self._error(404, "rotta inesistente")
        finally:
            viste.chiudi(conn, ombra)
            conn.close()

    def _api_write(self, method, path, body):
        # `?compartimento=` dice in che vista e' chi scrive: cio' che nasce li'
        # (un task, un post, un progetto, una nota) ne porta il compartimento
        scelta = getattr(self, "_scelta", None)
        if scelta:
            ambito = viste.attivo()
            if ambito is None:
                scelta = None
            elif scelta not in viste.elenco(ambito):
                raise actions.BadInput("compartimento sconosciuto: %s" % scelta)
        nuovo = scelta if scelta and scelta != viste.PREDEFINITO else ""
        conn = store.connect()
        try:
            if path.startswith("/api/voice/") or path == "/api/recap":
                # utile a capire da dove è partita la voce quando qualcosa non torna
                store.set_meta(conn, "ultima_voce", store.now())
                store.set_meta(conn, "ultima_voce_da",
                               (self.headers.get("User-Agent") or "?")[:80])
                conn.commit()
            if path == "/api/voice/speak" and method == "POST":
                testo = (body.get("testo") or "").strip()
                if not testo:
                    raise actions.BadInput("serve un testo")
                lang = recap.lang_or_default(body.get("lang"))
                info, nota = _sintesi_o_nota(testo, lang, body.get("motore"))
                if info is None:
                    return self._json(_senza_voce(
                        {"testo": testo, "lingua": lang}, nota))
                info["url"] = "/audio/" + Path(info["file"]).name
                if body.get("riproduci"):
                    try:
                        voice.riproduci(info["file"])
                    except voice.NessunMotoreVoce as exc:
                        # il file c'e' ma il server non ha un lettore audio
                        info["riprodotto"] = False
                        info["nota_voce"] = str(exc)
                return self._json(info)
            if path == "/api/voice/stop" and method == "POST":
                voice.ferma()
                return self._json({"fermato": True})
            if path == "/api/onboarding" and method == "POST":
                store.set_meta(conn, "onboarding_fatto", "1" if body.get("fatto", True) else "0")
                conn.commit()
                return self._json({"ok": True})
            if path == "/api/cantiere" and method == "POST":
                titolo = (body.get("titolo") or "").strip()
                if not titolo:
                    raise actions.BadInput("serve un titolo")
                # LOTTO-L3-RITOCCO punto 13: `scrive` (bool, dal nuovo
                # interruttore del front) invece di `modo` ("proposta"/
                # "esegui", il vecchio menu a tendina sparito col punto 2 di
                # LOTTO-L3-RIPRENDI-UI) - vedi cantiere.avvia/_scrive_da.
                #
                # L3-RIPRENDI-UI-4 (obbligatoria del critico): `sessione`
                # inoltrata a cantiere.avvia(), che già la accetta (--resume
                # --fork-session quando c'è) - prima il modulo "In
                # background" senza un task_id (righe della lavagna venute
                # da Claude/Codex, che una sessione la hanno già) partiva
                # sempre da zero, anche quando "Riprendi" prometteva il
                # contrario.
                return self._json(cantiere.avvia(
                    conn, titolo, body.get("dettaglio", ""), body.get("progetto"),
                    body.get("istruzioni", ""), body.get("agente", "claude"),
                    bool(body.get("scrive")), body.get("cwd"),
                    body.get("task_id"), recap.lang_or_default(body.get("lang")),
                    sessione=body.get("sessione") or None))
            if path == "/api/riprendi/backfill" and method == "POST":
                # Un nome di batch nuovo a ogni chiamata (mai virgole o spazi,
                # riprendi._batch_valido lo richiede): senza un batch tornato
                # al chiamante, un --annulla successivo non saprebbe quale
                # lotto di attribuzioni disfare.
                batch = "backfill-" + store.now()
                esito = riprendi.backfill(conn, batch, secco=bool(body.get("secco")))
                esito["batch"] = batch
                return self._json(esito)
            if path == "/api/riprendi/annulla" and method == "POST":
                batch = (body.get("batch") or "").strip()
                if not batch:
                    raise actions.BadInput("serve un batch")
                return self._json({"ripristinati": riprendi.annulla(conn, batch)})
            m = re.match(r"^/api/riprendi/(\d+)$", path)
            if m and method == "POST":
                task = actions.task_get(conn, int(m.group(1)))
                if not task:
                    # LOTTO-L3-RITOCCO punto 12: stesso codice e stesso corpo
                    # della GET qui sopra (404, {"errore": "task inesistente"}),
                    # non actions.BadInput -> 400: un id inesistente e' lo
                    # stesso "non trovato" sia che lo si legga sia che ci si
                    # scriva sopra.
                    return self._error(404, "task inesistente")
                if body.get("apri"):
                    return self._json(riprendi.apri(task, conn))
                if body.get("background"):
                    # Il fork (verdetto §B, "In background"): se il task ha
                    # gia' una sessione viva o chiusa, cantiere.avvia() la
                    # riprende (--resume/exec resume, con --fork-session per
                    # Claude: vedi plancia/cantiere.py._comando, non toccato
                    # da questo lotto) invece di ripartire da un prompt
                    # scritto a mano. "Persa" non ha niente da forkare:
                    # sessione resta None e componi_prompt() scrive il
                    # contesto lei.
                    s = riprendi.stato(conn, task)
                    sessione = riprendi.sessione_da_riprendere(s)
                    esito = cantiere.avvia(
                        conn, task.get("title") or "", "", task.get("project_key"),
                        body.get("istruzioni", ""), s.get("agent") or task.get("agent") or "claude",
                        bool(body.get("scrive")), None, task["id"],
                        recap.lang_or_default(body.get("lang")), sessione=sessione)
                    return self._json(esito)
                raise actions.BadInput("serve 'apri' o 'background'")
            m = re.match(r"^/api/runs/(\d+)/annulla$", path)
            if m and method == "POST":
                return self._json({"annullato": cantiere.annulla(conn, int(m.group(1)))})
            if path == "/api/jarvis/scalda" and method == "POST":
                agente.scalda(recap.lang_or_default(body.get("lang")))
                return self._json({"scaldato": True})
            if path == "/api/jarvis" and method == "POST":
                testo = (body.get("testo") or "").strip()
                if not testo:
                    raise actions.BadInput("serve una frase")
                lang = recap.lang_or_default(body.get("lang"))
                esito = jarvis.esegui(testo, lang, conn)
                esito["lingua"] = lang
                esito["detto"] = testo
                # Se la voce sarebbe comunque quella di sistema, la sintesi la
                # fa il chiamante: parlare parte subito invece di aspettare che
                # il server scriva un file e lo rimandi indietro.
                esito["motore"] = "voicebox" if voice.voicebox_vivo() else "say"
                # Quando a parlare è l'app con la voce di sistema, il testo da
                # dire è diverso da quello da leggere: niente indirizzi, niente
                # percorsi, niente sha.
                if esito.get("risposta"):
                    from .voce_testo import per_voce
                    esito["da_dire"] = per_voce(esito["risposta"], lang)

                nativa = body.get("voce_nativa") and esito["motore"] == "say"
                if not esito.get("muto") and body.get("voce", True) and \
                        esito.get("risposta") and not nativa:
                    info, nota = _sintesi_o_nota(esito["risposta"], lang, subito=True)
                    if info is None:
                        esito["motore"] = None
                        _senza_voce(esito, nota)
                    else:
                        esito["url"] = "/audio/" + Path(info["file"]).name
                        esito["file"] = info["file"]
                        esito["motore"] = info["motore"]
                return self._json(esito)
            if path == "/api/voice/ask" and method == "POST":
                domanda = (body.get("domanda") or "").strip()
                if not domanda:
                    raise actions.BadInput("serve una domanda")
                lang = recap.lang_or_default(body.get("lang"))
                # la risposta si costruisce dal compartimento scelto (l'assistente
                # vocale `jarvis`, che apre una connessione sua, non e' separato)
                conn_r, ombra_r = _connessione_separata(scelta)
                try:
                    risposta = recap.answer(domanda, lang, conn_r)
                finally:
                    viste.chiudi(conn_r, ombra_r)
                    conn_r.close()
                out = {"domanda": domanda, "risposta": risposta, "lingua": lang}
                if body.get("voce", True):
                    info, nota = _sintesi_o_nota(risposta, lang, subito=True)
                    if info is None:
                        _senza_voce(out, nota)
                    else:
                        out["url"] = "/audio/" + Path(info["file"]).name
                        out["file"] = info["file"]
                        out["motore"] = info["motore"]
                return self._json(out)
            if path == "/api/recap" and method == "POST":
                conn_r, ombra_r = _connessione_separata(scelta)
                try:
                    data = recap.build(conn_r, body.get("day"), body.get("lang"),
                                       body.get("engine"))
                finally:
                    viste.chiudi(conn_r, ombra_r)
                    conn_r.close()
                if body.get("voce", True):
                    info, nota = _sintesi_o_nota(data["testo"], data["lingua"], subito=True)
                    if info is None:
                        _senza_voce(data, nota)
                    else:
                        data["url"] = "/audio/" + Path(info["file"]).name
                        data["file"] = info["file"]
                        data["motore"] = info["motore"]
                data.pop("dati", None)
                return self._json(data)
            if path == "/api/sync" and method == "POST":
                if _NO_SYNC_ATTIVO:
                    return self._json({"avviato": False, "motivo": "--no-sync"})
                started = start_sync(bool(body.get("full")))
                return self._json({"avviato": started, "stato": SYNC_STATE})
            if path == "/api/tasks" and method == "POST":
                return self._json(actions.task_add(
                    conn, body.get("title"), body.get("body", ""), body.get("project"),
                    body.get("priority", 2), body.get("due"), body.get("tags", ""), "dashboard",
                    compartimento=nuovo))
            m = re.match(r"^/api/tasks/(\d+)$", path)
            if m and method == "PATCH":
                return self._json(actions.task_update(conn, int(m.group(1)), **body))
            if m and method == "DELETE":
                conn.execute("DELETE FROM tasks WHERE id=?", (int(m.group(1)),))
                conn.commit()
                return self._json({"eliminato": int(m.group(1))})
            if path == "/api/posts" and method == "POST":
                return self._json(actions.post_add(
                    conn, body.get("text"), body.get("platform", "x"),
                    body.get("status", "bozza"), body.get("project"), body.get("url"),
                    body.get("source_ref", ""), body.get("scheduled_for"),
                    media=body.get("media", ""), compartimento=nuovo))
            m = re.match(r"^/api/posts/(\d+)$", path)
            if m and method == "PATCH":
                return self._json(actions.post_update(conn, int(m.group(1)), **body))
            if m and method == "DELETE":
                conn.execute("DELETE FROM posts WHERE id=?", (int(m.group(1)),))
                conn.commit()
                return self._json({"eliminato": int(m.group(1))})
            if path == "/api/projects" and method == "POST":
                return self._json(actions.project_create(
                    conn, body.get("name"), body.get("key"), body.get("kind", "progetto"),
                    body.get("summary", ""), body.get("priority", 2), compartimento=nuovo))
            m = re.match(r"^/api/projects/([^/]+)$", path)
            if m and method == "PATCH":
                return self._json(actions.project_update(
                    conn, urllib.parse.unquote(m.group(1)), **body))
            if path == "/api/events" and method == "POST":
                return self._json(actions.log_event(
                    conn, body.get("title"), body.get("kind", "nota"), body.get("detail", ""),
                    body.get("project"), body.get("ref"), "dashboard", compartimento=nuovo))
            return self._error(404, "rotta inesistente")
        finally:
            conn.close()

    # --- file statici ----------------------------------------------------
    def _static(self, path):
        if path in ("/", "/index.html"):
            html = (config.WEB_DIR / "index.html").read_text("utf-8")
            html = html.replace("__PLANCIA_TOKEN__", config.get_token())
            # marca css, js e i font con la loro data: un aggiornamento non
            # lascia in giro la versione vecchia nella cache del browser. I
            # woff2 sono piatti in WEB_DIR (niente sottocartelle, vedi sotto),
            # quindi un glob basta a trovarli tutti senza elencarli per nome.
            marcati = ["style.css", "app.js"] + sorted(
                p.name for p in config.WEB_DIR.glob("*.woff2"))
            stamp = int(max((config.WEB_DIR / n).stat().st_mtime
                            for n in marcati))
            html = html.replace("__PLANCIA_V__", str(stamp))
            return self._send(200, html, "text/html; charset=utf-8")
        m = re.match(r"^/audio/([0-9a-f]{8,32}\.wav)$", path)
        if m:
            target = voice.AUDIO_DIR / m.group(1)
            if not target.is_file():
                return self._error(404, "audio non trovato")
            return self._send(200, target.read_bytes(), "audio/wav")
        name = path.lstrip("/")
        if "/" in name or name.startswith("."):
            return self._error(404, "non trovato")
        target = config.WEB_DIR / name
        if not target.is_file():
            return self._error(404, "non trovato")
        if name.endswith(".woff2"):
            # Python 3.9 non ha .woff2 nella sua tabella mime: senza questo
            # mimetypes.guess_type torna None e il font arriverebbe come
            # application/octet-stream, che alcuni browser rifiutano.
            ctype = "font/woff2"
        else:
            ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        return self._send(200, target.read_bytes(), ctype)


def serve(port=None, open_browser=False, sync_first=True) -> None:
    cfg = config.load_config()
    port = int(port or cfg.get("port", config.DEFAULT_PORT))
    conn = store.connect()
    store.init_db(conn)
    store.migrate(conn)
    # I lanci girano in un thread di questo processo: se il processo è stato
    # riavviato, quelli che risultano ancora in corso non stanno lavorando.
    try:
        from . import cantiere
        fermi = cantiere.riconcilia(conn)
        if fermi:
            print(f"lanci rimasti appesi e chiusi: {fermi}")
    except Exception:
        pass
    conn.close()
    # `sync_first` (da cli.py: `not args.no_sync`) non vuol dire solo "il primo
    # giro": e' l'interruttore di ogni sync di questo processo. Prima il
    # ticker partiva comunque, fuori da questo `if`: tre tester indipendenti
    # (residuo dell'ondata 2, 16/09/2026) hanno visto `plancia serve
    # --no-sync` riempire lo stesso i db di prova con progetti veri della
    # macchina due minuti dopo l'avvio, e `tools/scatti.sh` corre lo stesso
    # rischio (nomi veri negli screenshot del sito). Con `--no-sync` niente
    # sync all'avvio E niente ticker: nessun sync parte da solo per tutta la
    # vita del processo.
    global _NO_SYNC_ATTIVO
    _NO_SYNC_ATTIVO = not sync_first
    if sync_first:
        start_sync(False)

        # Due ritmi: il caldo costa un centesimo di secondo e tiene aggiornato
        # quello che stai facendo, il freddo costa un secondo e rilegge il resto.
        caldo = max(1, int(cfg.get("sync_caldo_minuti", 2)))
        freddo = max(5, int(cfg.get("sync_freddo_minuti", 30)))

        def ticker():
            import time
            passati = 0
            # PLANCIA_TICKER_SECONDI (solo per le prove: tools/prove/serve-no-sync.py):
            # forza il periodo del ticker a un numero di SECONDI invece dei
            # minuti veri, cosi' una prova puo' aspettare pochi secondi
            # invece di 2-30 minuti per vedere se il ticker parte.
            secondi_prova = os.environ.get("PLANCIA_TICKER_SECONDI")
            periodo = float(secondi_prova) if secondi_prova else caldo * 60
            while True:
                time.sleep(periodo)
                passati += caldo
                if passati >= freddo:
                    passati = 0
                    start_sync(False, "freddo")
                else:
                    start_sync(False, "caldo")
        threading.Thread(target=ticker, daemon=True).start()

    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}"
    print(f"Plancia in ascolto su {url}")
    print(f"Dati in {config.DB_PATH}")
    if open_browser:
        import webbrowser
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nchiuso")
        httpd.server_close()
