"""Il plugin per Claude Code e le cause delle cadute del server MCP (novembre 2026).

- il plugin: manifest, marketplace e hook si leggono e puntano a cose che ci sono;
- la sentinella (bin/plancia-plugin mcp), contro un server finto: risponde
  subito, rifa' da sola una lettura rimasta a meta' quando il server cade, non
  rifa' una scrittura, riavvia un server bloccato, si ferma un attimo se il
  server non parte e lo dice;
- `store.init_db` non scrive se lo schema e' gia' aggiornato (prima scriveva a
  ogni chiamata, e il server moriva all'avvio con "database is locked");
- `turni.indicizza` riprende un file cresciuto in coda invece di rileggerlo, e
  lo rilegge da capo se e' stato riscritto;
- `actions.collega` non lega mai un contenitore e propone i progetti probabili.
"""

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent.parent
PLUGIN = RADICE / "bin" / "plancia-plugin"

# Un server MCP finto, per provare la sentinella senza il database: risponde a
# initialize e tools/list, e i tool fanno quello che dice il nome.
_FINTO = r'''
import json, os, sys, time
segno = os.path.join(os.environ["FINTO_DIR"], "caduto-una-volta")
if os.environ.get("FINTO_NON_PARTE"):
    sys.stderr.write("ImportError: il pacchetto finto non parte\n"); sys.exit(1)
for riga in sys.stdin:
    m = json.loads(riga)
    if "id" not in m:
        continue
    def rispondi(r):
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": m["id"], "result": r}) + "\n")
        sys.stdout.flush()
    if m["method"] == "initialize":
        rispondi({"protocolVersion": "2025-06-18", "capabilities": {"tools": {}},
                  "serverInfo": {"name": "plancia", "version": "finto"},
                  "instructions": "finto"})
    elif m["method"] == "tools/list":
        rispondi({"tools": [{"name": "plancia_search", "inputSchema": {"type": "object"}}]})
    elif m["method"] == "tools/call":
        nome = m["params"]["name"]
        q = (m["params"].get("arguments") or {}).get("query", "")
        if q == "cadi-una-volta" and not os.path.exists(segno):
            open(segno, "w").close(); os._exit(3)
        if q == "cadi":
            os._exit(3)
        if q == "dormi":
            time.sleep(60)
        rispondi({"content": [{"type": "text", "text": f"{nome} {q} pid {os.getpid()}"}],
                  "isError": False})
'''


class _Sessione:
    """Una sentinella vera davanti al server finto, parlata come la parla Claude Code."""

    def __init__(self, radice_finta, dati, extra_env=None):
        env = dict(os.environ, PLANCIA_ROOT=str(radice_finta), PLANCIA_HOME=str(dati),
                   FINTO_DIR=str(dati), PLANCIA_MCP_ATTESA="2")
        env.update(extra_env or {})
        self.p = subprocess.Popen([sys.executable, str(PLUGIN), "mcp"], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env)
        self.risposte = {}
        self.cv = threading.Condition()
        threading.Thread(target=self._leggi, daemon=True).start()

    def _leggi(self):
        for riga in self.p.stdout:
            m = json.loads(riga)
            with self.cv:
                self.risposte[m.get("id")] = m
                self.cv.notify_all()

    def chiedi(self, id_, metodo, params=None, attesa=20):
        msg = {"jsonrpc": "2.0", "id": id_, "method": metodo}
        if params is not None:
            msg["params"] = params
        self.p.stdin.write((json.dumps(msg) + "\n").encode())
        self.p.stdin.flush()
        with self.cv:
            self.cv.wait_for(lambda: id_ in self.risposte, timeout=attesa)
        return self.risposte.get(id_)

    def chiama(self, id_, nome, query, attesa=20):
        r = self.chiedi(id_, "tools/call", {"name": nome, "arguments": {"query": query}},
                        attesa=attesa)
        if r is None:
            return None, "nessuna risposta"
        res = r.get("result") or {}
        return res.get("isError"), (res.get("content") or [{}])[0].get("text", "")

    def chiudi(self):
        try:
            self.p.stdin.close()
            self.p.wait(timeout=10)
        except Exception:
            self.p.kill()
        return self.p.returncode


def _prove_manifest(prova):
    pj = json.loads((RADICE / ".claude-plugin" / "plugin.json").read_text("utf-8"))
    mk = json.loads((RADICE / ".claude-plugin" / "marketplace.json").read_text("utf-8"))
    prova("plugin.json e marketplace.json parlano dello stesso plugin",
          pj["name"] == "plancia" and [p["name"] for p in mk["plugins"]] == ["plancia"]
          and mk["plugins"][0]["source"] == "./", json.dumps(mk["plugins"]))
    srv = pj["mcpServers"]["plancia"]
    prova("il server MCP del plugin e' la sentinella",
          srv["args"] == ["${CLAUDE_PLUGIN_ROOT}/bin/plancia-plugin", "mcp"], json.dumps(srv))
    hooks = json.loads((RADICE / "hooks" / "hooks.json").read_text("utf-8"))["hooks"]
    comandi = [h["command"] for v in hooks.values() for e in v for h in e["hooks"]]
    sotto = {c.split("plancia-plugin\"")[-1].split()[0] for c in comandi}
    prova("gli hook del plugin chiamano sottocomandi che esistono",
          sotto <= {"hook", "avvio", "richiamo"} and set(hooks) ==
          {"SessionStart", "SessionEnd", "UserPromptSubmit"}, str(sotto))
    prova("il guardiano dei compartimenti resta fuori dal plugin (si spegnerebbe "
          "disattivando il plugin)", not any("guardiano" in c for c in comandi))
    for nome in ("briefing", "doctor"):
        prova(f"il comando /plancia:{nome} c'e'",
              (RADICE / "commands" / f"{nome}.md").read_text("utf-8").startswith("---"))
    prova("il plugin porta le skill plancia e riepilogo",
          all((RADICE / "skills" / s / "SKILL.md").exists() for s in ("plancia", "riepilogo")))


def _prove_sentinella(prova):
    radice = Path(tempfile.mkdtemp(prefix="plancia-sentinella-"))
    (radice / "bin").mkdir()
    (radice / "bin" / "plancia-mcp").write_text(_FINTO, "utf-8")
    dati = radice / "dati"
    dati.mkdir()
    try:
        s = _Sessione(radice, dati)
        t0 = time.monotonic()
        r = s.chiedi(1, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                        "clientInfo": {"name": "prova", "version": "1"}})
        prova("la sentinella risponde a initialize con il server vero dietro",
              r is not None and r["result"]["serverInfo"]["version"] == "finto",
              json.dumps(r)[:200])
        prova("e lo fa in pochi secondi", time.monotonic() - t0 < 10)
        r = s.chiedi(2, "tools/list")
        prova("tools/list passa", r and r["result"]["tools"][0]["name"] == "plancia_search")
        prova("e la lista resta in cache per quando il server non risponde",
              (dati / "cache" / "mcp-tools.json").exists())
        err, testo = s.chiama(3, "plancia_search", "cadi-una-volta")
        prova("una lettura a meta' quando il server cade si rifa' da sola",
              err is False and "cadi-una-volta" in testo, f"{err} {testo}")
        err, testo = s.chiama(4, "plancia_task_add", "cadi")
        prova("una scrittura a meta' non si rifa': errore che dice di controllare",
              err is True and "controlla" in testo.lower(), f"{err} {testo}")
        err, testo = s.chiama(5, "plancia_search", "ancora")
        prova("dopo una caduta la chiamata seguente trova un server nuovo",
              err is False and "ancora" in testo, f"{err} {testo}")
        t0 = time.monotonic()
        err, testo = s.chiama(6, "plancia_search", "dormi", attesa=30)
        prova("un server bloccato oltre l'attesa si riavvia e la chiamata lo dice",
              err is True and "superato" in testo and time.monotonic() - t0 < 15,
              f"{err} {testo} in {time.monotonic() - t0:.1f}s")
        err, testo = s.chiama(7, "plancia_search", "dopo-il-blocco")
        prova("e la chiamata dopo funziona", err is False, testo)
        r = s.chiedi(8, "ping")
        prova("ping risponde la sentinella", r == {"jsonrpc": "2.0", "id": 8, "result": {}})
        prova("la sentinella esce pulita quando Claude Code chiude", s.chiudi() == 0)
        log = [json.loads(x)["evento"] for x in
               (dati / "sentinella-mcp.log").read_text("utf-8").splitlines()]
        prova("il registro della sentinella dice cadute, blocchi e riavvii",
              {"avvio", "caduto", "bloccato", "riavviato"} <= set(log), str(log))

        # un server che non parte: niente attese infinite, l'ultimo errore detto
        s = _Sessione(radice, dati, {"FINTO_NON_PARTE": "1"})
        r = s.chiedi(1, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                        "clientInfo": {"name": "prova", "version": "1"}})
        prova("con il server che non parte, initialize risponde lo stesso",
              r is not None and "result" in r, json.dumps(r)[:200])
        r = s.chiedi(2, "tools/list")
        prova("e tools/list arriva dalla cache", r is not None and r.get("result", {}).get("tools"),
              json.dumps(r)[:200])
        ultimo = None
        for i in range(3, 9):
            err, ultimo = s.chiama(i, "plancia_search", "x")
        prova("una chiamata dice perche' non parte (l'ultima riga d'errore)",
              "non parte" in (ultimo or "") and "ImportError" in (ultimo or ""), ultimo)
        prova("e dopo qualche caduta di fila si ferma un attimo invece di girare a vuoto",
              "in-pausa" in (dati / "sentinella-mcp.log").read_text("utf-8"))
        s.chiudi()
    finally:
        shutil.rmtree(radice, ignore_errors=True)


def _prove_schema(prova):
    from plancia import store
    conn = store.connect()
    store.init_db(conn)
    prova("lo schema dell'archivio di prova risulta aggiornato", store.schema_aggiornato(conn))
    altro = sqlite3.connect(str(store.config.DB_PATH), isolation_level=None, timeout=5)
    altro.execute("BEGIN IMMEDIATE")
    try:
        conn.execute("PRAGMA busy_timeout=0")
        try:
            store.init_db(conn)
            esito = None
        except sqlite3.OperationalError as exc:
            esito = str(exc)
        prova("init_db non chiede il blocco di scrittura se lo schema e' gia' aggiornato",
              esito is None, esito or "")
    finally:
        altro.execute("ROLLBACK")
        altro.close()
        conn.close()


def _riga(ruolo, testo, n):
    return json.dumps({"type": ruolo, "timestamp": f"2026-11-08T10:00:{n:02d}Z",
                       "message": {"role": ruolo, "content": testo}}) + "\n"


def _prove_turni(prova):
    from plancia import turni
    cartella = Path(tempfile.mkdtemp(prefix="plancia-turni-"))
    try:
        radice = cartella / "projects"
        (radice / "-tmp-progetto").mkdir(parents=True)
        f = radice / "-tmp-progetto" / "sessione-a.jsonl"
        lungo = "una frase abbastanza lunga da entrare nell'indice dei turni, numero %d"
        f.write_text(_riga("user", lungo % 1, 1) + _riga("assistant", lungo % 2, 2), "utf-8")
        conn = sqlite3.connect(str(cartella / "t.db"))
        esito = turni.indicizza(conn, radice=radice)
        prova("indice: il primo giro legge il file", esito["turni"] == 2, str(esito))
        # una riga intera e una ancora a meta' (Claude Code la sta scrivendo)
        with open(f, "a", encoding="utf-8") as fh:
            fh.write(_riga("user", lungo % 3, 3))
            fh.write(_riga("assistant", lungo % 4, 4)[:30])
        os.utime(f, None)
        esito = turni.indicizza(conn, radice=radice)
        prova("indice: un file cresciuto si legge solo nella coda",
              esito["file_in_coda"] == 1 and esito["turni"] == 1, str(esito))
        prova("indice: niente turni doppi",
              conn.execute("SELECT COUNT(*) FROM turni_fts").fetchone()[0] == 3)
        with open(f, "a", encoding="utf-8") as fh:
            fh.write(_riga("assistant", lungo % 4, 4)[30:])
        time.sleep(0.01)
        os.utime(f, None)
        esito = turni.indicizza(conn, radice=radice)
        righe = dict(conn.execute("SELECT testo, riga FROM turni_fts").fetchall())
        prova("indice: la riga che era a meta' entra quando e' finita, col suo numero",
              esito["turni"] == 1 and righe.get(lungo % 4) == 4, f"{esito} {righe}")
        prova("indice: la mappa dei rowid copre ancora tutto", turni.mappa(conn) is not None)
        # riscritto da capo (stessa lunghezza o no, altro contenuto): si rilegge
        f.write_text(_riga("user", lungo % 9, 1), "utf-8")
        os.utime(f, None)
        esito = turni.indicizza(conn, radice=radice)
        testi = [r[0] for r in conn.execute("SELECT testo FROM turni_fts")]
        prova("indice: un file riscritto si rilegge da capo e i turni vecchi spariscono",
              testi == [lungo % 9] and esito["file_in_coda"] == 0, f"{esito} {testi}")
        # un codice di prima che aggiorna la riga senza le colonne nuove
        conn.execute("UPDATE turni_file SET dimensione = dimensione + 1")
        conn.commit()
        with open(f, "a", encoding="utf-8") as fh:
            fh.write(_riga("assistant", lungo % 5, 2))
        os.utime(f, None)
        esito = turni.indicizza(conn, radice=radice)
        n = conn.execute("SELECT COUNT(*) FROM turni_fts").fetchone()[0]
        prova("indice: una riga toccata da un codice vecchio si rilegge, senza doppioni",
              n == 2 and esito["file_in_coda"] == 0, f"{esito} {n}")
        conn.close()
    finally:
        shutil.rmtree(cartella, ignore_errors=True)


def _prove_collega(prova):
    from plancia import actions, config, store
    conn = store.connect()
    store.init_db(conn)
    try:
        try:
            actions.collega(conn, str(config.HOME / "dev"), "qualcosa")
            esito = "accettato"
        except actions.BadInput as exc:
            esito = str(exc)
        prova("collega: ~/dev e' un contenitore e non si lega", "contenitore" in esito, esito)
        cartella = Path(tempfile.mkdtemp(prefix="plancia-collega-"))
        repo = cartella / "progettofinto-copie" / "lavoro"
        repo.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(repo)], capture_output=True)
        subprocess.run(["git", "-C", str(repo), "remote", "add", "origin",
                        "https://github.com/nessuno/progettofinto.git"], capture_output=True)
        actions.project_create(conn, "Progettofinto", key="progettofinto")
        r = actions.collega(conn, str(repo))
        cand = [c["key"] for c in r.get("candidati") or []]
        prova("collega: una cartella mai vista propone il progetto del suo remote git",
              r["collegata"] is False and cand[:1] == ["progettofinto"], json.dumps(r)[:300])
        r = actions.collega(conn, str(repo), "progettofint")
        prova("collega: un nome non esatto non lega niente e propone i simili",
              r["collegata"] is False and r["simili"][:1] and
              r["simili"][0]["key"] == "progettofinto", json.dumps(r)[:300])
        r = actions.collega(conn, str(repo), "progettofinto")
        prova("collega: con il nome esatto la cartella si lega",
              r["collegata"] and r["progetto"] == "progettofinto" and not r["gia_legata"],
              json.dumps(r)[:300])
        r = actions.collega(conn, str(repo / "sotto"))
        prova("collega: una sottocartella risulta gia' del progetto, senza scrivere",
              r["collegata"] and r["gia_legata"] and r["progetto"] == "progettofinto",
              json.dumps(r)[:300])
        shutil.rmtree(cartella, ignore_errors=True)
    finally:
        conn.close()


def esegui(prova):
    _prove_manifest(prova)
    _prove_sentinella(prova)
    _prove_schema(prova)
    _prove_turni(prova)
    _prove_collega(prova)
