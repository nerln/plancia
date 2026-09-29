"""Prove per E1-PLANCIA: Plancia mostra a ogni sessione solo il suo compartimento.

Tutto in un ambiente isolato, come tools/prove/esclusi.py e guardiano.py:
PLANCIA_HOME, CLAUDE_CONFIG_DIR e HOME sono cartelle temporanee (mai ~/.plancia,
~/.claude o la home vera), e il PATH mette per primi strumenti finti e inerti
(launchctl, osascript, schtasks, systemctl, crontab, claude, codex: escono 1 e
non fanno niente, `claude` in piu' lascia un segnale se qualcuno lo lancia).
Ogni parte di Plancia si prova COME LA USA CHI LA USA: l'hook `bin/plancia-hook`
(SessionStart) e `bin/plancia-richiamo` (UserPromptSubmit) come sottoprocessi con
il JSON su stdin, il server MCP `bin/plancia-mcp` lanciato con la cwd dentro un
compartimento e `CLAUDE_CODE_SESSION_ID` finto, la dashboard `plancia serve` su
una porta libera. Niente si importa da `plancia.compartimenti_viste`: la prova
deve poter girare (e fallire) sul commit di base, dove quel modulo non c'e'. Tutti
i sottoprocessi girano con `/usr/bin/python3` (3.9) quando c'e': e' anche la
prova che il codice nuovo regge la versione piu' vecchia.

I compartimenti sono finti: `alfa` e `beta` (nominati, con una cartella ciascuno) e
il predefinito, che non ha cartelle. Ogni oggetto porta nel nome una parola
marcatore (QUERCIA per alfa, SALICE per beta, FAGGIO per il predefinito) cosi'
"non contiene niente dell'altro" e' un confronto su testo, sul corpo intero di
ogni risposta e non su un campo scelto.

Le parti:

- senza config e con la sola voce `predefinito`: tutto come prima (hook,
  richiamo, MCP, dashboard vedono tutto) e `/api/compartimenti` dice che non c'e'
  niente da scegliere;
- briefing (SessionStart): la sessione di alfa vede solo alfa, quella del
  predefinito solo il predefinito, e l'avviso di una sessione aperta in una
  cartella contenitore non elenca i progetti degli altri (prova 4 della
  specifica);
- richiamo (UserPromptSubmit): il caso vero del 29/09, cioe' la memoria
  automatica di un nominato (`<claude>/projects/<codifica della sua cartella>/
  memory/`) richiamata da una sessione del predefinito, e il contrario;
- MCP: ricerca, progetti, task, post, sessioni, memoria, eventi, lavagna,
  briefing filtrati nei due sensi; scritture incrociate rifiutate con un messaggio
  chiaro (`plancia_task_add`, `plancia_project_update`, `plancia_task_update`,
  `plancia_post_update`, `plancia_log`, `plancia_manda`); una sessione che ha
  segnali di due nominati non vede niente;
- dashboard: con `?compartimento=alfa` ogni rotta di lettura torna solo alfa,
  senza parametro il predefinito, un nome sconosciuto e' un errore, un task nato
  nella vista di alfa e' di alfa;
- config rotta: si usa l'ultima copia valida;
- il filtro su un archivio grande, con il tempo che costa.
"""

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent.parent
PYTHON = "/usr/bin/python3" if os.path.exists("/usr/bin/python3") else sys.executable

MARCHI = {"alfa": "QUERCIA", "beta": "SALICE", "predefinito": "FAGGIO"}
PAROLA_ALFA_1 = "zafferano mongolfiera"      # memoria di alfa, specchio della radice
PAROLA_ALFA_2 = "peperoncino tamarindo"      # memoria di alfa, specchio di una discendente
PAROLA_PRED = "cardamomo lampone"            # memoria del predefinito
PAROLA_ALFA_3 = "rabarbaro genziana"         # memoria di alfa con uno `scope` che non dice niente


def _codifica(p) -> str:
    return re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(str(p)))


# --------------------------------------------------------------------------
# ambiente isolato
# --------------------------------------------------------------------------

def _ambiente(base: Path) -> dict:
    home = base / "home"
    bin_finto = base / "bin"
    segnale = base / "claude-chiamato"
    home.mkdir(parents=True, exist_ok=True)
    bin_finto.mkdir(parents=True, exist_ok=True)
    for nome in ("launchctl", "osascript", "schtasks", "systemctl", "crontab",
                 "claude", "codex"):
        f = bin_finto / nome
        f.write_text("#!/bin/sh\necho \"$0 $@\" >> '%s'\nexit 1\n" % segnale, "utf-8")
        f.chmod(0o755)
    env = dict(os.environ)
    env.update({
        "HOME": str(home),
        "PATH": "%s:/usr/bin:/bin:/usr/sbin:/sbin" % bin_finto,
        "PLANCIA_HOME": str(base / "dati"),
        "CLAUDE_CONFIG_DIR": str(base / "claude"),
        "CODEX_HOME": str(base / "codex"),
    })
    for k in ("CLAUDE_CODE_SESSION_ID", "CLAUDE_PID"):
        env.pop(k, None)
    (base / "dati").mkdir(parents=True, exist_ok=True)
    return env


def _scrivi_config(env: dict, extra: dict = None, comp=None) -> None:
    cfg = {"motore_riepilogo": "template", "contenitori": [env["_CONTENITORE"]]
           if "_CONTENITORE" in env else []}
    if comp is not None:
        cfg["compartimenti"] = comp
    if extra:
        cfg.update(extra)
    Path(env["PLANCIA_HOME"], "config.json").write_text(json.dumps(cfg), "utf-8")


def _env_sub(env: dict) -> dict:
    """L'ambiente che si passa ai sottoprocessi (senza le chiavi interne)."""
    return {k: v for k, v in env.items() if not k.startswith("_")}


def _config_comp(w: Path, sessioni_beta=None) -> dict:
    return {
        "alfa": {"cartelle": [str(w / "alfa")]},
        "beta": {"cartelle": [str(w / "beta")], "sessioni": sessioni_beta or []},
        "predefinito": {},
    }


# --------------------------------------------------------------------------
# l'archivio finto
# --------------------------------------------------------------------------

_SCRIPT_FIXTURE = r'''
import json, os, sys
sys.path.insert(0, "__RADICE__")
from plancia import actions, store, turni
spec = json.loads(os.environ["FIX"])
conn = store.connect(); store.init_db(conn)
ts = "2026-09-20T09:00:00Z"

def prog(key, name, path, passo):
    pid = store.upsert_project(conn, key, name, next_action=passo, auto=0,
                               last_activity=ts, summary=name + " riassunto")
    store.link_project(conn, pid, "path", path)
    return pid

P = {}
for c, d in spec["progetti"].items():
    P[c] = prog(d["key"], d["nome"], d["path"], d["passo"])
# il progetto di alfa e' figlio di un'area del predefinito: chi guarda alfa non
# vede il padre, e il figlio deve restare nell'albero
conn.execute("UPDATE projects SET parent_id=? WHERE id=?", (P["predefinito"], P["alfa"]))
conn.commit()

def ses(sid, pid, cwd, file, title):
    conn.execute(
        "INSERT INTO sessions(session_id, project_id, file, cwd, title, first_prompt, "
        "started_at, ended_at, n_user, n_assistant, n_tools, agent) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,'claude')",
        (sid, pid, file, cwd, title, "primo prompt " + title, ts, ts, 3, 3, 1))
    store.add_event(conn, ts, "sessione", title, "3 messaggi", pid, sid, "claude",
                    dedup="sessione:" + sid)

for c, s in spec["sessioni"].items():
    ses(s["id"], P[c], s["cwd"], s["file"], s["titolo"])
conn.commit()

for t in spec["task"]:
    actions.task_add(conn, t["titolo"], "", t.get("progetto"), 2, None, "", "claude",
                     session_id=t.get("sessione"), cwd=t.get("cwd"))
for p in spec["post"]:
    actions.post_add(conn, p["testo"], "x", "bozza", p.get("progetto"))
for e in spec["eventi"]:
    actions.log_event(conn, e["titolo"], "nota", "", e.get("progetto"))
conn.commit()

for k in spec["memorie"]:
    conn.execute(
        "INSERT INTO knowledge(name, path, scope, description, type, body, links, "
        "project_id, updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
        (k["nome"], k["path"], k["scope"], k["descrizione"], "feedback", k["corpo"],
         "[]", None, ts))
conn.commit()

# tasks fermi da giorni (alimentano le proposte), lanci falliti, la lavagna, i
# repository con modifiche, le skill: una vista vuota non proverebbe niente
for c, d in spec["extra"].items():
    conn.execute("UPDATE tasks SET status='in corso', updated_at=? WHERE title=?",
                 ("2026-09-0%d" % d["giorno"] + "T00:00:00Z", d["task_fermo"]))
    conn.execute(
        "INSERT INTO runs(agente, modo, prompt, cwd, stato, inizio, fine, esito) "
        "VALUES('claude','proposta',?,?,'fallito',?,?,?)",
        (d["marchio"] + " lancio fallito\nsecondo rigo", d["cwd"], store.now(), store.now(),
         "esito " + d["marchio"]))
    conn.execute(
        "INSERT INTO agenda(fonte, chiave, titolo, dettaglio, stato, stato_origine, agente, "
        "sessione, project_id, creato_at, aggiornato_at, visto_at) "
        "VALUES('claude', ?, ?, '', 'aperto', 'pending', 'claude', ?, ?, ?, ?, ?)",
        ("voce-" + c, "voce lavagna " + d["marchio"], d["sessione"], P[c], ts, ts, ts))
    conn.execute(
        "INSERT INTO repos(name, description, local_path, project_id, dirty, updated_at) "
        "VALUES(?,?,?,?,?,?)",
        ("repo-" + d["marchio"].lower(), "repo " + d["marchio"], d["cwd"], P[c], d["dirty"], ts))
    conn.execute(
        "INSERT INTO commits(repo, sha, message, date, session_id) VALUES(?,?,?,?,?)",
        ("repo-" + d["marchio"].lower(), "sha" + c, "commit " + d["marchio"], ts, d["sessione"]))
    store.add_event(conn, ts, "commit", "commit " + d["marchio"], "repo-" + d["marchio"].lower(),
                    P[c], "sha" + c, "github", dedup="commit:" + c)
    conn.execute(
        "INSERT INTO capabilities(name, kind, description, path, meta, updated_at, body) "
        "VALUES(?,?,?,?,?,?,?)",
        ("skill-" + d["marchio"].lower(), "skill", "skill " + d["marchio"],
         d["cwd"] + "/.claude/skills/x/SKILL.md", "{}", ts, "corpo " + d["marchio"]))
conn.commit()

turni.prepara(conn)
for t in spec["turni"]:
    conn.execute(
        "INSERT INTO turni_fts(testo, sessione, ruolo, ts, progetto, percorso, riga) "
        "VALUES(?,?,?,?,?,?,?)",
        (t["testo"], t["sessione"], "user", ts, "etichetta", t["percorso"], 1))
conn.commit()
store.rebuild_search(conn)
conn.commit()
print(json.dumps({"ok": True}))
'''


def _memoria(nome, argomento, marchio, cartella_specchio, claude: Path) -> dict:
    """Una memoria che il richiamo puo' trovare: descrizione + corpo oltre la
    soglia di sostanza (200 caratteri), l'argomento ripetuto. Sta nello
    specchio (`<claude>/projects/<codifica>/memory/`) della cartella data."""
    scope = _codifica(cartella_specchio)
    path = claude / "projects" / scope / "memory" / (nome + ".md")
    path.parent.mkdir(parents=True, exist_ok=True)
    corpo = ("%s: %s. Quando si parla di %s conviene ricordare che %s e' la "
             "regola di questo lavoro: %s, sempre %s, senza eccezioni, e "
             "%s va controllato ogni volta prima di andare avanti."
             % (marchio, argomento, argomento, argomento, argomento, argomento,
                argomento))
    path.write_text("---\nname: %s\n---\n%s\n" % (nome, corpo), "utf-8")
    return {"nome": nome, "path": str(path), "scope": scope,
            "descrizione": "%s nota su %s" % (marchio, argomento), "corpo": corpo}


def _prepara(base: Path) -> dict:
    """Le cartelle, le trascrizioni vuote, e lo `spec` per lo script della
    base di dati. Torna tutto quello che serve alle prove."""
    env = _ambiente(base)
    w = Path(os.path.realpath(base / "w"))
    claude = Path(os.path.realpath(base / "claude"))
    dirs = {"alfa": w / "alfa" / "quercia", "beta": w / "beta" / "salice",
            "predefinito": w / "pred" / "faggio"}
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)
    (w / "alfa" / "altra").mkdir(parents=True, exist_ok=True)
    env["_CONTENITORE"] = str(w)

    ids = {"alfa": "aaaaaaaa-0000-4000-8000-00000000000a",
           "beta": "bbbbbbbb-0000-4000-8000-00000000000b",
           "predefinito": "pppppppp-0000-4000-8000-00000000000c"}
    file = {}
    for c, d in dirs.items():
        f = claude / "projects" / _codifica(d) / (ids[c] + ".jsonl")
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("", "utf-8")
        file[c] = str(f)

    spec = {
        "progetti": {
            "alfa": {"key": "quercia", "nome": "QUERCIA progetto", "path": str(dirs["alfa"]),
                     "passo": "passo QUERCIA"},
            "beta": {"key": "salice", "nome": "SALICE progetto", "path": str(dirs["beta"]),
                     "passo": "passo SALICE"},
            "predefinito": {"key": "faggio", "nome": "FAGGIO progetto",
                            "path": str(dirs["predefinito"]), "passo": "passo FAGGIO"},
        },
        "sessioni": {c: {"id": ids[c], "cwd": str(dirs[c]), "file": file[c],
                         "titolo": "sessione %s" % MARCHI[c]} for c in dirs},
        "task": [
            {"titolo": "task QUERCIA con progetto", "progetto": "quercia",
             "sessione": ids["alfa"], "cwd": str(dirs["alfa"])},
            # senza progetto: il compartimento lo dice solo la sessione
            {"titolo": "task QUERCIA solo sessione", "sessione": ids["alfa"]},
            # senza sessione e senza cwd: lo dice solo il progetto
            {"titolo": "task QUERCIA solo progetto", "progetto": "quercia"},
            {"titolo": "task FAGGIO con progetto", "progetto": "faggio",
             "sessione": ids["predefinito"], "cwd": str(dirs["predefinito"])},
            {"titolo": "task FAGGIO solo progetto", "progetto": "faggio"},
            {"titolo": "task FAGGIO libero"},
            {"titolo": "task SALICE con progetto", "progetto": "salice",
             "sessione": ids["beta"], "cwd": str(dirs["beta"])},
        ],
        "post": [{"testo": "post QUERCIA bozza", "progetto": "quercia"},
                 {"testo": "post FAGGIO bozza", "progetto": "faggio"},
                 {"testo": "post SALICE bozza", "progetto": "salice"}],
        "eventi": [{"titolo": "nota QUERCIA", "progetto": "quercia"},
                   {"titolo": "nota FAGGIO", "progetto": "faggio"},
                   {"titolo": "nota SALICE", "progetto": "salice"}],
        "memorie": [
            # il caso del 29/09: la memoria automatica di alfa sta nello specchio
            # della sua cartella, e non e' sotto nessuna sua `cartella`
            _memoria("quercia-ricetta", PAROLA_ALFA_1, "QUERCIA", w / "alfa", claude),
            _memoria("quercia-spezie", PAROLA_ALFA_2, "QUERCIA", w / "alfa" / "altra", claude),
            _memoria("faggio-dolci", PAROLA_PRED, "FAGGIO", dirs["predefinito"], claude),
        ],
        "extra": {
            "alfa": {"marchio": "QUERCIA", "task_fermo": "task QUERCIA con progetto",
                     "giorno": 1, "dirty": 9, "cwd": str(dirs["alfa"]), "sessione": ids["alfa"]},
            "predefinito": {"marchio": "FAGGIO", "task_fermo": "task FAGGIO con progetto",
                            "giorno": 2, "dirty": 5, "cwd": str(dirs["predefinito"]),
                            "sessione": ids["predefinito"]},
            "beta": {"marchio": "SALICE", "task_fermo": "task SALICE con progetto",
                     "giorno": 3, "dirty": 3, "cwd": str(dirs["beta"]), "sessione": ids["beta"]},
        },
        "turni": [
            {"testo": "QUERCIA parlava del ciliegio in fiore di primavera oggi",
             "sessione": ids["alfa"], "percorso": file["alfa"]},
            {"testo": "FAGGIO parlava del ciliegio in fiore di primavera oggi",
             "sessione": ids["predefinito"], "percorso": file["predefinito"]},
            {"testo": "SALICE parlava del ciliegio in fiore di primavera oggi",
             "sessione": ids["beta"], "percorso": file["beta"]},
        ],
    }
    # una memoria nello specchio di alfa ma con uno `scope` che non c'entra: il
    # percorso del file basta a dire di chi e'
    strana = _memoria("quercia-strana", PAROLA_ALFA_3, "QUERCIA", w / "alfa", claude)
    strana["scope"] = "scope-strano"
    spec["memorie"].append(strana)
    # memorie di riempimento del predefinito: rendono il bm25 del richiamo
    # realistico (un indice con tre righe non discrimina)
    riempi = ["rosmarino origano basilico", "mandorla nocciola pistacchio",
              "ginepro alloro salvia", "sedano carota cipolla", "melograno cachi fico",
              "zenzero curcuma cannella", "vaniglia cacao caffe", "aceto senape rafano",
              "lenticchie ceci fagioli", "orzo farro segale"]
    for i, arg in enumerate(riempi):
        spec["memorie"].append(_memoria("riempimento-%d" % i, arg, "FAGGIO",
                                        dirs["predefinito"], claude))
    r = subprocess.run([PYTHON, "-c", _SCRIPT_FIXTURE.replace("__RADICE__", str(RADICE))],
                       env=dict(_env_sub(env), FIX=json.dumps(spec)),
                       capture_output=True, text=True, timeout=180)
    return {"env": env, "w": w, "claude": claude, "dirs": dirs, "ids": ids, "file": file,
            "spec": spec, "fixture_ok": r.returncode == 0 and '"ok": true' in r.stdout,
            "fixture_err": (r.stderr or r.stdout)[-1500:]}


# --------------------------------------------------------------------------
# i sottoprocessi
# --------------------------------------------------------------------------

def _hook(fix, comp: str, cwd=None, evento="SessionStart") -> dict:
    """L'uscita di `bin/plancia-hook` per una sessione del compartimento
    `comp`: `{"testo": additionalContext o "", "uscita": stdout}`."""
    payload = {"hook_event_name": evento, "session_id": fix["ids"][comp],
               "transcript_path": fix["file"][comp],
               "cwd": str(cwd or fix["dirs"][comp]), "source": "startup"}
    return _hook_payload(fix, payload)


def _hook_payload(fix, payload) -> dict:
    p = subprocess.run([PYTHON, str(RADICE / "bin" / "plancia-hook")],
                       input=json.dumps(payload), capture_output=True, text=True,
                       env=_env_sub(fix["env"]), timeout=60)
    testo = ""
    try:
        testo = json.loads(p.stdout)["hookSpecificOutput"]["additionalContext"]
    except Exception:  # noqa: BLE001
        pass
    return {"testo": testo, "uscita": p.stdout, "codice": p.returncode, "err": p.stderr}


def _richiamo(fix, comp: str, prompt: str, cwd=None) -> str:
    """Il testo che `bin/plancia-richiamo` porterebbe in contesto ("" se tace)."""
    payload = {"hook_event_name": "UserPromptSubmit", "session_id": fix["ids"][comp] + "-r",
               "transcript_path": fix["file"][comp], "prompt": prompt,
               "cwd": str(cwd or fix["dirs"][comp])}
    # il session_id del richiamo deve essere quello della sessione (e' un segnale
    # di appartenenza): il file `richiamo-<id>.json` di "gia' detto" e' per id,
    # quindi si cancella fra una chiamata e l'altra
    payload["session_id"] = fix["ids"][comp]
    coda = Path(fix["env"]["PLANCIA_HOME"]) / "queue"
    if coda.is_dir():
        for f in coda.glob("richiamo-*.json"):
            f.unlink()
    p = subprocess.run([PYTHON, str(RADICE / "bin" / "plancia-richiamo")],
                       input=json.dumps(payload), capture_output=True, text=True,
                       env=_env_sub(fix["env"]), timeout=60)
    try:
        return json.loads(p.stdout)["hookSpecificOutput"]["additionalContext"]
    except Exception:  # noqa: BLE001
        return ""


def _mcp(fix, comp: str, chiamate, cwd=None, sid=None):
    """Le risposte del server MCP lanciato con la cwd dentro `comp` e
    `CLAUDE_CODE_SESSION_ID` finto, una per chiamata: `(isError, testo)`."""
    righe = [{"jsonrpc": "2.0", "id": 0, "method": "initialize",
              "params": {"protocolVersion": "2025-06-18"}}]
    for i, (nome, args) in enumerate(chiamate, 1):
        righe.append({"jsonrpc": "2.0", "id": i, "method": "tools/call",
                      "params": {"name": nome, "arguments": args}})
    env = dict(_env_sub(fix["env"]), CLAUDE_CODE_SESSION_ID=sid or fix["ids"][comp])
    p = subprocess.run([PYTHON, str(RADICE / "bin" / "plancia-mcp")],
                       input="\n".join(json.dumps(r) for r in righe) + "\n",
                       capture_output=True, text=True, timeout=180,
                       cwd=str(cwd or fix["dirs"][comp]), env=env)
    risposte = {}
    for linea in p.stdout.splitlines():
        try:
            d = json.loads(linea)
        except ValueError:
            continue
        risposte[d.get("id")] = d
    fuori = []
    for i in range(1, len(chiamate) + 1):
        try:
            res = risposte[i]["result"]
            fuori.append((bool(res.get("isError")), res["content"][0]["text"]))
        except Exception:  # noqa: BLE001
            fuori.append((True, "<nessuna risposta> " + (p.stderr or "")[-400:]))
    return fuori


class _Server:
    """`plancia serve --no-sync` su una porta libera, con l'ambiente isolato."""

    def __init__(self, fix):
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        self.porta = s.getsockname()[1]
        s.close()
        self.fix = fix
        self.p = subprocess.Popen(
            [PYTHON, str(RADICE / "bin" / "plancia"), "serve", "--port", str(self.porta),
             "--no-sync"], env=_env_sub(fix["env"]), stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE)
        self.pronto = False
        for _ in range(100):
            try:
                self.get("/api/status")
                self.pronto = True
                break
            except Exception:  # noqa: BLE001
                time.sleep(0.2)
        # il token nasce alla prima pagina servita
        try:
            self.get("/", testo=True)
            self.token = Path(fix["env"]["PLANCIA_HOME"], "token").read_text().strip()
        except Exception:  # noqa: BLE001
            self.token = ""

    def get(self, path, testo=False):
        """`(codice, corpo)`: il corpo e' il testo grezzo (i confronti si fanno
        su tutto il corpo), o il JSON con `testo=False`."""
        try:
            with urllib.request.urlopen("http://127.0.0.1:%d%s" % (self.porta, path),
                                        timeout=60) as r:
                corpo, codice = r.read().decode("utf-8"), r.status
        except urllib.error.HTTPError as e:
            corpo, codice = e.read().decode("utf-8"), e.code
        return codice, (corpo if testo else json.loads(corpo))

    def scrivi(self, metodo, path, body):
        req = urllib.request.Request(
            "http://127.0.0.1:%d%s" % (self.porta, path),
            data=json.dumps(body).encode("utf-8"), method=metodo,
            headers={"Content-Type": "application/json", "X-Plancia-Token": self.token})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.status, json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode("utf-8") or "{}")

    def chiudi(self):
        self.p.terminate()
        try:
            self.p.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.p.kill()


def _senza(testo: str, altri) -> bool:
    """`testo` non nomina nessuno dei marcatori di `altri` (senza distinzione di
    maiuscole: vale anche per i percorsi e le chiavi)."""
    t = testo.lower()
    return not any(MARCHI[a].lower() in t for a in altri)


def _rifiuto(esito) -> bool:
    err, testo = esito
    return err and "compartimento" in testo.lower()


# --------------------------------------------------------------------------
# le prove
# --------------------------------------------------------------------------

def esegui(prova) -> None:
    base = Path(tempfile.mkdtemp(prefix="plancia-prova-comp-"))
    server = None
    try:
        fix = _prepara(base)
        if not fix["fixture_ok"]:
            prova("l'archivio finto si costruisce", False, fix["fixture_err"])
            return
        env, w = fix["env"], fix["w"]

        def altri(c):
            return [x for x in MARCHI if x != c]

        # ---- senza config: tutto come prima ---------------------------------
        _scrivi_config(env)
        subprocess.run([PYTHON, str(RADICE / "bin" / "plancia"), "briefing"],
                       env=_env_sub(env), capture_output=True, timeout=120)
        h = _hook(fix, "predefinito")
        prova("senza compartimenti il briefing di SessionStart e' quello di sempre "
              "(vede tutti i progetti)",
              "QUERCIA" in h["testo"] and "FAGGIO" in h["testo"] and "SALICE" in h["testo"],
              h["testo"][:300])
        prova("senza compartimenti l'hook non lascia nessun file di briefing per compartimento",
              not list(Path(env["PLANCIA_HOME"]).glob("briefing.*.md")))
        r = _richiamo(fix, "predefinito", "come si prepara il risotto allo %s" % PAROLA_ALFA_1)
        prova("senza compartimenti il richiamo e' quello di sempre (trova la memoria "
              "scritta in un'altra cartella)", "QUERCIA" in r, r[:200])
        mcp = _mcp(fix, "predefinito", [("plancia_projects", {})])
        prova("senza compartimenti l'MCP vede tutti i progetti",
              all(m in mcp[0][1] for m in ("QUERCIA", "FAGGIO", "SALICE")), mcp[0][1][:200])
        srv = _Server(fix)
        server = srv
        prova("il server della dashboard parte", srv.pronto)
        c, d = srv.get("/api/compartimenti")
        prova("senza compartimenti /api/compartimenti dice che non c'e' niente da scegliere",
              c == 200 and d.get("attivo") is False and d.get("elenco") == [], str((c, d)))
        c, corpo = srv.get("/api/projects", testo=True)
        prova("senza compartimenti la dashboard mostra tutti i progetti",
              c == 200 and all(m in corpo for m in ("QUERCIA", "FAGGIO", "SALICE")), corpo[:200])
        c, corpo = srv.get("/api/projects?compartimento=alfa", testo=True)
        prova("senza compartimenti `?compartimento=` non cambia niente",
              c == 200 and "FAGGIO" in corpo and "QUERCIA" in corpo, corpo[:200])
        _scrivi_config(env, comp={"predefinito": {}})
        c, d = srv.get("/api/compartimenti")
        prova("con la sola voce `predefinito` non ci sono compartimenti da scegliere",
              c == 200 and d.get("attivo") is False, str((c, d)))
        c, corpo = srv.get("/api/projects", testo=True)
        prova("con la sola voce `predefinito` la dashboard mostra tutto",
              "QUERCIA" in corpo and "FAGGIO" in corpo and "SALICE" in corpo)

        # ---- compartimenti configurati (guardiano spento: E1 non dipende da E3)
        _scrivi_config(env, comp=_config_comp(w))
        subprocess.run([PYTHON, str(RADICE / "bin" / "plancia"), "briefing"],
                       env=_env_sub(env), capture_output=True, timeout=120)

        # briefing
        for comp in ("alfa", "predefinito", "beta"):
            h = _hook(fix, comp)
            prova("briefing: la sessione di %s vede il proprio lavoro" % comp,
                  MARCHI[comp] in h["testo"], h["testo"][:300] or h["err"][-300:])
            prova("briefing: la sessione di %s non vede niente degli altri compartimenti"
                  % comp, _senza(h["testo"], altri(comp)), h["testo"][:400])
        h = _hook(fix, "predefinito", cwd=w)
        prova("briefing: una sessione del predefinito aperta nel contenitore vede il "
              "proprio progetto nell'avviso", "faggio" in h["testo"].lower(),
              h["testo"][-400:])
        prova("briefing: l'avviso del contenitore non nomina i progetti dei nominati",
              _senza(h["testo"], ["alfa", "beta"]), h["testo"][-400:])
        h = _hook(fix, "alfa", cwd=w)
        prova("briefing: una sessione di alfa aperta nel contenitore vede il suo progetto "
              "e non quelli degli altri",
              "quercia" in h["testo"].lower() and _senza(h["testo"], ["beta", "predefinito"]),
              h["testo"][-400:])
        stale = Path(env["PLANCIA_HOME"]) / "briefing.md"
        vecchio = stale.read_text("utf-8")
        stale.write_text("VECCHIO QUERCIA FAGGIO SALICE\n", "utf-8")
        Path(env["PLANCIA_HOME"], "briefing.predefinito.md").unlink(missing_ok=True)
        h = _hook(fix, "predefinito")
        prova("briefing: con i compartimenti attivi l'hook non legge mai il "
              "briefing.md non separato (un file rimasto da prima non passa)",
              "VECCHIO" not in h["testo"], h["testo"][:200])
        stale.write_text(vecchio, "utf-8")
        subprocess.run([PYTHON, str(RADICE / "bin" / "plancia"), "briefing"],
                       env=_env_sub(env), capture_output=True, timeout=120)
        prova("briefing: il file del predefinito e' anche briefing.md, senza i nominati",
              _senza(stale.read_text("utf-8"), ["alfa", "beta"]))
        h = _hook(fix, "alfa", evento="SessionEnd")
        prova("briefing: l'hook di chiusura non stampa niente", h["uscita"].strip() == "",
              h["uscita"][:100])

        # richiamo (il caso del 29/09)
        r = _richiamo(fix, "predefinito", "come si prepara il risotto allo %s" % PAROLA_ALFA_1)
        prova("richiamo: una sessione del predefinito NON riceve la memoria automatica "
              "di alfa (specchio della cartella di alfa)", "QUERCIA" not in r, r[:300])
        r = _richiamo(fix, "predefinito", "come si usa il %s nelle ricette" % PAROLA_ALFA_2)
        prova("richiamo: ne' quella dello specchio di una cartella discendente di alfa",
              "QUERCIA" not in r, r[:300])
        r = _richiamo(fix, "predefinito", "come si usa il %s nelle ricette" % PAROLA_ALFA_3)
        prova("richiamo: la memoria nello specchio di alfa e' di alfa anche se il suo scope "
              "non lo dice (conta il percorso del file)", "QUERCIA" not in r, r[:300])
        r = _richiamo(fix, "predefinito", "come si usa il %s nei dolci" % PAROLA_PRED,
                      cwd=fix["w"] / "pred")
        prova("richiamo: la sessione del predefinito riceve ancora le memorie del "
              "predefinito", "FAGGIO" in r and "cardamomo" in r, r[:300])
        r = _richiamo(fix, "alfa", "come si usa il %s nei dolci" % PAROLA_PRED)
        prova("richiamo: una sessione di alfa NON riceve le memorie del predefinito",
              "FAGGIO" not in r, r[:300])
        r = _richiamo(fix, "alfa", "come si usa il %s nelle ricette" % PAROLA_ALFA_2)
        prova("richiamo: una sessione di alfa riceve le proprie memorie scritte in altre "
              "cartelle di alfa", "QUERCIA" in r and "peperoncino" in r, r[:300])
        r = _richiamo(fix, "beta", "come si usa il %s nelle ricette" % PAROLA_ALFA_2)
        prova("richiamo: una sessione di beta NON riceve le memorie di alfa",
              "QUERCIA" not in r, r[:300])
        r = _richiamo(fix, "alfa", "come si prepara il risotto allo %s" % PAROLA_ALFA_1,
                      cwd=fix["w"] / "alfa")
        prova("richiamo: la memoria della cartella in cui la sessione e' aperta non si "
              "ripete (la carica gia' Claude Code)", "zafferano" not in r, r[:300])

        # MCP
        s_alfa = _mcp(fix, "alfa", [
            ("plancia_projects", {}),
            ("plancia_tasks", {"status": "tutti"}),
            ("plancia_search", {"query": "ciliegio"}),
            ("plancia", {"azione": "sessions"}),
            ("plancia", {"azione": "memory", "query": "regola"}),
            ("plancia", {"azione": "briefing"}),
            ("plancia_briefing", {}),
            ("plancia", {"azione": "posts"}),
            ("plancia", {"azione": "eventi"}),
            ("plancia", {"azione": "lavagna"}),
            ("plancia", {"azione": "recap"}),
            ("plancia_search", {"query": "QUERCIA"}),
            ("plancia_search", {"query": "FAGGIO"}),
            ("plancia", {"azione": "lanci"}),
        ])
        nomi_call = ["projects", "tasks", "search ciliegio", "sessions", "memory",
                     "briefing", "plancia_briefing", "posts", "eventi", "lavagna", "recap",
                     "search QUERCIA", "search FAGGIO", "lanci"]
        for (err, testo), n in zip(s_alfa, nomi_call):
            prova("MCP alfa: %s non contiene niente degli altri compartimenti" % n,
                  _senza(testo, altri("alfa")), testo[:300])
        prova("MCP alfa: i progetti sono solo quelli di alfa",
              "QUERCIA" in s_alfa[0][1], s_alfa[0][1][:200])
        prova("MCP alfa: i task sono quelli di alfa (con progetto, solo sessione, solo "
              "progetto)", all(x in s_alfa[1][1] for x in (
                  "task QUERCIA con progetto", "task QUERCIA solo sessione",
                  "task QUERCIA solo progetto")), s_alfa[1][1][:300])
        prova("MCP alfa: la ricerca nei turni trova il turno di alfa",
              "QUERCIA parlava" in s_alfa[2][1], s_alfa[2][1][:300])
        prova("MCP alfa: la ricerca di una parola degli altri non trova niente",
              s_alfa[12][1].strip() in ("nessun risultato",) or _senza(s_alfa[12][1], ["predefinito"]),
              s_alfa[12][1][:200])
        prova("MCP alfa: il briefing esteso e' quello di alfa",
              "QUERCIA" in s_alfa[6][1], s_alfa[6][1][:200])
        prova("MCP alfa: la lavagna e i lanci mostrano quelli di alfa",
              "voce lavagna QUERCIA" in s_alfa[9][1] and "QUERCIA lancio fallito" in s_alfa[13][1],
              s_alfa[9][1][:150] + s_alfa[13][1][:150])
        prova("MCP alfa: la ricerca delle schede trova le schede di alfa (task e memoria)",
              "task QUERCIA" in s_alfa[11][1], s_alfa[11][1][:200])

        s_pred = _mcp(fix, "predefinito", [
            ("plancia_projects", {}),
            ("plancia_tasks", {"status": "tutti"}),
            ("plancia_search", {"query": "ciliegio"}),
            ("plancia", {"azione": "sessions"}),
            ("plancia", {"azione": "memory", "query": "regola"}),
            ("plancia_briefing", {}),
            ("plancia", {"azione": "posts"}),
            ("plancia", {"azione": "eventi"}),
            ("plancia", {"azione": "lavagna"}),
            ("plancia", {"azione": "recap"}),
            ("plancia", {"azione": "lanci"}),
        ])
        for (err, testo), n in zip(s_pred, ["projects", "tasks", "search", "sessions",
                                            "memory", "briefing", "posts", "eventi",
                                            "lavagna", "recap", "lanci"]):
            prova("MCP predefinito: %s non contiene niente dei nominati" % n,
                  _senza(testo, ["alfa", "beta"]), testo[:300])
        prova("MCP predefinito: vede il proprio lavoro (progetti, task senza sessione, "
              "task solo con progetto)",
              "FAGGIO" in s_pred[0][1] and "task FAGGIO libero" in s_pred[1][1]
              and "task FAGGIO solo progetto" in s_pred[1][1], s_pred[1][1][:300])
        prova("MCP predefinito: la ricerca nei turni trova il proprio turno",
              "FAGGIO parlava" in s_pred[2][1], s_pred[2][1][:300])
        prova("MCP predefinito: la lavagna e i lanci mostrano quelli del predefinito",
              "voce lavagna FAGGIO" in s_pred[8][1] and "FAGGIO lancio fallito" in s_pred[10][1],
              s_pred[8][1][:150] + s_pred[10][1][:150])

        # scritture incrociate
        idp = None
        for (err, testo) in _mcp(fix, "predefinito", [("plancia_tasks", {"status": "tutti"})]):
            try:
                idp = [t["id"] for t in json.loads(testo) if "FAGGIO con progetto" in t["title"]][0]
            except Exception:  # noqa: BLE001
                pass
        ida = None
        for (err, testo) in _mcp(fix, "alfa", [("plancia_tasks", {"status": "tutti"})]):
            try:
                ida = [t["id"] for t in json.loads(testo) if "QUERCIA con progetto" in t["title"]][0]
            except Exception:  # noqa: BLE001
                pass
        prova("gli id dei task di prova si trovano", idp is not None and ida is not None,
              str((idp, ida)))
        con = _apri(env)
        lanci_prima = con.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
        stato_prima = con.execute("SELECT status FROM tasks WHERE id=?", (idp,)).fetchone()[0]
        con.close()
        x = _mcp(fix, "alfa", [
            ("plancia_task_add", {"title": "task incrociato da alfa", "project": "faggio"}),
            ("plancia_project_update", {"project": "faggio", "next_action": "scritto da alfa"}),
            ("plancia_task_update", {"id": idp, "status": "fatto"}),
            ("plancia_log", {"title": "nota incrociata da alfa", "project": "faggio"}),
            ("plancia_post_add", {"text": "post incrociato da alfa", "project": "faggio"}),
            ("plancia_manda", {"titolo": "lavoro incrociato da alfa", "progetto": "faggio"}),
            ("plancia_manda", {"titolo": "lavoro senza progetto da alfa"}),
            ("plancia", {"azione": "riprendi", "id": idp}),
            ("plancia_project_update", {"project": "salice", "next_action": "da alfa a beta"}),
        ])
        for i, n in enumerate(["task_add", "project_update", "task_update", "log", "post_add",
                               "manda", "manda senza progetto", "riprendi", "project_update beta"]):
            prova("MCP alfa: %s su un oggetto di un altro compartimento e' rifiutato con un "
                  "messaggio chiaro" % n, _rifiuto(x[i]), str(x[i])[:250])
        y = _mcp(fix, "predefinito", [
            ("plancia_task_add", {"title": "task incrociato dal predefinito", "project": "quercia"}),
            ("plancia_project_update", {"project": "quercia", "next_action": "scritto dal predefinito"}),
            ("plancia_task_update", {"id": ida, "status": "fatto"}),
            ("plancia", {"azione": "tasks"}),
        ])
        for i, n in enumerate(["task_add", "project_update", "task_update"]):
            prova("MCP predefinito: %s su un oggetto di alfa e' rifiutato con un messaggio "
                  "chiaro" % n, _rifiuto(y[i]), str(y[i])[:250])
        prova("MCP predefinito: una scrittura rifiutata non lascia traccia in lettura",
              "incrociato" not in y[3][1] and "scritto dal" not in y[3][1], y[3][1][:200])
        # a scritture fatte, lo stato vero: niente e' cambiato
        con = _apri(env)
        prova("le scritture rifiutate non hanno toccato l'archivio (task, progetto, "
              "note, lanci)",
              con.execute("SELECT COUNT(*) FROM tasks WHERE title LIKE '%incrociato%'").fetchone()[0] == 0
              and con.execute("SELECT next_action FROM projects WHERE key='faggio'").fetchone()[0] == "passo FAGGIO"
              and con.execute("SELECT status FROM tasks WHERE id=?", (idp,)).fetchone()[0] == stato_prima
              and con.execute("SELECT COUNT(*) FROM events WHERE title LIKE '%incrociata%'").fetchone()[0] == 0
              and con.execute("SELECT COUNT(*) FROM posts WHERE text LIKE '%incrociato%'").fetchone()[0] == 0
              and con.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == lanci_prima)
        prova("nessun agente vero e' stato lanciato (il `claude` finto non e' stato chiamato)",
              not (base / "claude-chiamato").exists())
        con.close()
        # un lancio dal proprio compartimento riesce, e nel registro degli eventi
        # il progetto e' la chiave (non l'id)
        m = _mcp(fix, "predefinito", [("plancia_manda", {"titolo": "lavoro del predefinito",
                                                          "progetto": "faggio"})])
        prova("MCP predefinito: plancia_manda su un proprio progetto parte (torna l'id del "
              "lancio, nella cartella del progetto)",
              not m[0][0] and '"run"' in m[0][1] and "faggio" in m[0][1], str(m))
        try:
            ev = [json.loads(r) for r in (Path(env["PLANCIA_HOME"]) / "eventi.jsonl"
                                          ).read_text().splitlines()]
            avviato = [e for e in ev if e.get("tipo") == "lavoro.avviato"][-1]
        except Exception:  # noqa: BLE001
            avviato = {}
        prova("MCP predefinito: il lancio porta nel registro degli eventi la chiave del progetto",
              avviato.get("progetto") == "faggio", str(avviato)[:200])

        # scritture nel proprio compartimento: riescono e restano nel proprio
        z = _mcp(fix, "alfa", [
            ("plancia_task_add", {"title": "task nuovo QUERCIA da mcp", "project": "quercia"}),
            ("plancia_task_add", {"title": "task nuovo QUERCIA senza progetto"}),
            ("plancia_log", {"title": "nota nuova QUERCIA senza progetto"}),
            ("plancia_post_add", {"text": "post nuovo QUERCIA senza progetto"}),
            ("plancia_project_update", {"project": "quercia", "next_action": "nuovo passo QUERCIA"}),
        ])
        prova("MCP alfa: le scritture nel proprio compartimento riescono",
              all(not e for e, _ in z), str(z)[:300])
        pred_dopo = _mcp(fix, "predefinito", [
            ("plancia_tasks", {"status": "tutti"}), ("plancia", {"azione": "eventi"}),
            ("plancia", {"azione": "posts"}), ("plancia_projects", {}), ("plancia_briefing", {})])
        prova("cio' che alfa scrive (task, nota, post, progetto) non compare al predefinito",
              all(_senza(t, ["alfa"]) for _, t in pred_dopo),
              "; ".join(t[:120] for _, t in pred_dopo if not _senza(t, ["alfa"])))
        alfa_dopo = _mcp(fix, "alfa", [
            ("plancia_tasks", {"status": "tutti"}), ("plancia", {"azione": "eventi"}),
            ("plancia", {"azione": "posts"}), ("plancia_projects", {})])
        prova("cio' che alfa scrive compare ad alfa (anche senza progetto: la sessione "
              "lo dice)", "task nuovo QUERCIA senza progetto" in alfa_dopo[0][1]
              and "post nuovo QUERCIA senza progetto" in alfa_dopo[2][1]
              and "nuovo passo QUERCIA" in alfa_dopo[3][1], str(alfa_dopo)[:400])
        # la nota senza progetto sta nella tabella degli eventi, che l'MCP non
        # legge: si guarda dalla dashboard, che e' la vista di chi controlla
        _, ev_a = server.get("/api/events?compartimento=alfa", testo=True)
        _, ev_p = server.get("/api/events", testo=True)
        prova("la nota scritta da alfa senza progetto compare in alfa e non nel predefinito",
              "nota nuova QUERCIA senza progetto" in ev_a
              and "nota nuova QUERCIA senza progetto" not in ev_p, ev_a[:200])

        # una sessione con segnali di due nominati non vede niente
        _scrivi_config(env, comp=_config_comp(w, sessioni_beta=[fix["ids"]["alfa"]]))
        inc = _mcp(fix, "alfa", [("plancia_projects", {}), ("plancia_tasks", {}),
                                 ("plancia_task_add", {"title": "da una sessione incerta"})])
        prova("MCP: una sessione con segnali di due compartimenti non vede niente e non scrive",
              all(e and "compartimenti" in t for e, t in inc), str(inc)[:300])
        h = _hook(fix, "alfa")
        prova("briefing: una sessione con segnali di due compartimenti non riceve niente "
              "(ne' briefing ne' avviso)", h["testo"].strip() == "", h["testo"][:200])
        r = _richiamo(fix, "alfa", "come si usa il %s nelle ricette" % PAROLA_ALFA_2)
        prova("richiamo: una sessione con segnali di due compartimenti non riceve niente",
              r == "", r[:200])
        _scrivi_config(env, comp=_config_comp(w))

        # dashboard
        srv = server
        c, d = srv.get("/api/compartimenti")
        prova("dashboard: /api/compartimenti elenca il predefinito e i nominati della config, "
              "e il predefinito e' il default",
              d.get("attivo") is True and d.get("elenco") == ["predefinito", "alfa", "beta"]
              and d.get("scelto") == "predefinito", str(d))
        c, d = srv.get("/api/compartimenti?compartimento=beta")
        prova("dashboard: /api/compartimenti riporta la scelta", d.get("scelto") == "beta", str(d))
        rotte = ["/api/overview", "/api/projects", "/api/projects?albero=1",
                 "/api/tasks?status=tutti", "/api/posts", "/api/sessions", "/api/events",
                 "/api/knowledge", "/api/memoria/mappa", "/api/proposte", "/api/lavagna",
                 "/api/runs", "/api/eventi", "/api/agents", "/api/search?q=ciliegio",
                 "/api/search?q=QUERCIA", "/api/search?q=FAGGIO", "/api/prossimi",
                 "/api/briefing", "/api/capabilities", "/api/recap?solo_cache=1",
                 "/api/projects/quercia", "/api/projects/faggio", "/api/projects/salice",
                 "/api/status"]
        for comp in ("predefinito", "alfa", "beta"):
            sel = "" if comp == "predefinito" else "compartimento=%s" % comp
            for rotta in rotte:
                url = rotta + (("&" if "?" in rotta else "?") + sel if sel else "")
                c, corpo = srv.get(url, testo=True)
                if rotta.startswith("/api/projects/") and c == 404:
                    # il progetto di un altro non esiste per chi guarda
                    prova("dashboard %s: %s di un altro compartimento risponde 404" % (comp, rotta),
                          MARCHI[comp].lower() not in rotta.lower(), "%s %s" % (c, corpo[:100]))
                    continue
                prova("dashboard %s: %s non contiene niente degli altri compartimenti"
                      % (comp, rotta), c == 200 and _senza(corpo, altri(comp)),
                      "%s %s" % (c, corpo[:200]))
        for comp in ("predefinito", "alfa", "beta"):
            sel = "" if comp == "predefinito" else "?compartimento=%s" % comp
            for rotta, cosa in (("/api/runs", "lancio fallito"), ("/api/lavagna", "voce lavagna"),
                                ("/api/capabilities", "skill"), ("/api/proposte", ""),
                                ("/api/events", "commit"), ("/api/sessions", "sessione")):
                c, corpo = srv.get(rotta + sel, testo=True)
                prova("dashboard %s: %s mostra le cose di %s (non e' vuota)"
                      % (comp, rotta, comp), MARCHI[comp] in corpo, corpo[:200])
        c, corpo = srv.get("/api/projects?albero=1&compartimento=alfa", testo=True)
        prova("dashboard: un progetto di alfa figlio di un'area del predefinito resta "
              "nell'albero di alfa (e' un progetto senza padre per chi guarda alfa)",
              c == 200 and "QUERCIA progetto" in corpo and "FAGGIO" not in corpo, corpo[:300])
        c, corpo = srv.get("/api/prossimi?compartimento=alfa", testo=True)
        prova("dashboard: i prossimi di alfa non dicono l'area del predefinito",
              "QUERCIA" in corpo and "FAGGIO" not in corpo, corpo[:300])
        c, corpo = srv.get("/api/projects", testo=True)
        prova("dashboard: senza parametro e' il predefinito (FAGGIO si', QUERCIA no)",
              "FAGGIO" in corpo and "QUERCIA" not in corpo)
        c, corpo = srv.get("/api/projects?compartimento=alfa", testo=True)
        prova("dashboard: ?compartimento=alfa mostra alfa", "QUERCIA" in corpo, corpo[:200])
        c, corpo = srv.get("/api/tasks?status=tutti&compartimento=alfa", testo=True)
        prova("dashboard: i task di alfa sono tutti e tre quelli di alfa",
              all(x in corpo for x in ("solo sessione", "solo progetto", "con progetto")),
              corpo[:300])
        c, corpo = srv.get("/api/overview?compartimento=alfa", testo=True)
        ov = json.loads(corpo)
        prova("dashboard: l'overview di alfa conta solo le cose di alfa",
              ov["stats"]["progetti_attivi"] == 1 and len(ov["progetti"]) == 1
              and ov["stats"]["sessioni_totali"] == 1, str(ov["stats"])[:300])
        c, corpo = srv.get("/api/search?q=ciliegio&compartimento=alfa", testo=True)
        prova("dashboard: la ricerca nei turni di alfa trova il turno di alfa e basta",
              "QUERCIA parlava" in corpo and "FAGGIO" not in corpo and "SALICE" not in corpo,
              corpo[:300])
        c, corpo = srv.get("/api/projects?compartimento=inesistente", testo=True)
        prova("dashboard: un compartimento sconosciuto e' un errore, non il predefinito",
              c == 400, "%s %s" % (c, corpo[:100]))
        # la cache del riepilogo: un sync (recap.prepara) la scrive SENZA separare, e
        # con i compartimenti attivi non deve arrivare a nessuno; ogni vista ha la sua
        con = _apri(env)
        con.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('recap_testo', "
                    "'CACHE NON SEPARATA con QUERCIA e FAGGIO e SALICE')")
        con.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('recap_lingua', 'it')")
        con.commit()
        con.close()
        for comp in ("predefinito", "alfa", "beta"):
            sel = "" if comp == "predefinito" else "&compartimento=" + comp
            c, corpo = srv.get("/api/recap?solo_cache=1&lang=it" + sel, testo=True)
            prova("dashboard %s: la cache del riepilogo scritta senza separare non arriva" % comp,
                  c == 200 and "CACHE NON SEPARATA" not in corpo, corpo[:200])
        c, d = srv.scrivi("POST", "/api/recap?compartimento=alfa", {"voce": False, "lang": "it"})
        c2, corpo_a = srv.get("/api/recap?solo_cache=1&lang=it&compartimento=alfa", testo=True)
        c3, corpo_p = srv.get("/api/recap?solo_cache=1&lang=it", testo=True)
        prova("dashboard: il riepilogo di alfa si costruisce e resta nella cache di alfa",
              c == 200 and c2 == 200 and json.loads(corpo_a).get("testo")
              and _senza(corpo_a, ["predefinito", "beta"]), "%s %s" % (c, corpo_a[:200]))
        prova("dashboard: la cache del riepilogo di alfa non compare al predefinito",
              c3 == 200 and "QUERCIA" not in corpo_p, corpo_p[:200])
        con = _apri(env)
        chiavi = {r[0] for r in con.execute("SELECT key FROM meta")}
        con.close()
        prova("dashboard: le cache per compartimento stanno sotto la chiave `<chiave>@<nome>` "
              "e il server non riscrive quella non separata",
              "recap_testo@alfa" in chiavi, str(sorted(chiavi))[:300])
        c, corpo = srv.get("/api/proposte?compartimento=alfa", testo=True)
        con = _apri(env)
        chiavi = {r[0] for r in con.execute("SELECT key FROM meta")}
        raw = con.execute("SELECT value FROM meta WHERE key='recap_testo'").fetchone()
        con.close()
        prova("dashboard: le proposte di alfa stanno nella cache di alfa",
              "proposte@alfa" in chiavi, str(sorted(chiavi))[:300])
        prova("dashboard: il server non tocca la cache non separata del riepilogo",
              raw is not None and raw[0].startswith("CACHE NON SEPARATA"), str(raw))
        # cio' che nasce in una vista e' di quella vista
        c, d = srv.scrivi("POST", "/api/tasks?compartimento=alfa",
                          {"title": "task dalla vista di alfa NUOVOALFA"})
        c2, d2 = srv.scrivi("POST", "/api/posts?compartimento=alfa",
                            {"text": "post dalla vista di alfa NUOVOALFA"})
        c3, d3 = srv.scrivi("POST", "/api/projects?compartimento=alfa",
                            {"name": "progetto NUOVOALFA", "key": "nuovoalfa"})
        c4, d4 = srv.scrivi("POST", "/api/events?compartimento=alfa",
                            {"title": "nota dalla vista di alfa NUOVOALFA"})
        prova("dashboard: creare in una vista riesce", (c, c2, c3, c4) == (200, 200, 200, 200),
              str((c, c2, c3, c4, d, d2, d3, d4))[:300])
        for rotta in ("/api/tasks?status=tutti", "/api/posts", "/api/projects", "/api/events"):
            _, in_alfa = srv.get(rotta + "&compartimento=alfa" if "?" in rotta
                                 else rotta + "?compartimento=alfa", testo=True)
            _, in_pred = srv.get(rotta, testo=True)
            prova("dashboard: quello che nasce nella vista di alfa (%s) compare in alfa e non "
                  "nel predefinito" % rotta,
                  "NUOVOALFA" in in_alfa.replace("nuovoalfa", "NUOVOALFA")
                  and "NUOVOALFA" not in in_pred.replace("nuovoalfa", "NUOVOALFA"),
                  in_alfa[:200])
        c, d = srv.scrivi("POST", "/api/tasks?compartimento=inesistente", {"title": "x"})
        prova("dashboard: creare in un compartimento sconosciuto e' un errore", c == 400, str((c, d)))

        # config rotta: l'ultima copia valida
        cfg_path = Path(env["PLANCIA_HOME"], "config.json")
        valida = cfg_path.read_text("utf-8")
        cfg_path.write_text("{ questo non e' json", "utf-8")
        c, corpo = srv.get("/api/projects", testo=True)
        prova("config rotta: si usa l'ultima copia valida (il predefinito non vede alfa)",
              c == 200 and "FAGGIO" in corpo and "QUERCIA" not in corpo, corpo[:200])
        h = _hook(fix, "predefinito")
        prova("config rotta: anche l'hook usa l'ultima copia valida",
              "QUERCIA" not in h["testo"], h["testo"][:200])
        cfg_path.write_text(valida, "utf-8")

        # niente e' rimasto aperto senza motivo
        srv.chiudi()
        server = None

        # le guardie senza prova del primo giro e gli indici FTS grandi
        _prova_guardie(prova, base)

        # archivio grande: quanto costa filtrare
        _prova_archivio_grande(prova, base)

        segnale = base / "claude-chiamato"
        _prova_regole(prova)
        prova("nessuna prova ha lanciato un `claude` oltre a quello del lancio proprio "
              "(al piu' uno: il server MCP esce prima che il filo lo lanci)",
              not segnale.exists() or len(segnale.read_text().splitlines()) <= 1)
    finally:
        if server is not None:
            server.chiudi()
        shutil.rmtree(base, ignore_errors=True)


def _prova_regole(prova) -> None:
    """La regola di chi vede cosa, provata da sola (vale per il briefing, il
    richiamo, l'MCP e la dashboard). Importa il modulo nuovo: sul commit di base
    non esiste e la prova e' rossa."""
    try:
        from plancia import compartimenti_viste as v
    except ImportError as exc:
        prova("il modulo compartimenti_viste esiste", False, str(exc))
        return
    P, I = v.PREDEFINITO, v.INCERTO
    prova("regola agente: il predefinito vede solo cio' che non e' di nessuno",
          v.visibile(frozenset(), P) and not v.visibile(frozenset({"alfa"}), P)
          and not v.visibile(frozenset({"alfa", "beta"}), P))
    prova("regola agente: un nominato vede solo cio' che e' esattamente suo",
          v.visibile(frozenset({"alfa"}), "alfa") and not v.visibile(frozenset(), "alfa")
          and not v.visibile(frozenset({"alfa", "beta"}), "alfa")
          and not v.visibile(frozenset({"beta"}), "alfa"))
    prova("regola agente: chi e' incerto non vede niente, nemmeno cio' che non e' di nessuno",
          not v.visibile(frozenset(), I) and not v.visibile(frozenset({"alfa"}), I))
    prova("regola dashboard: un oggetto di due nominati compare in tutti e due e mai nel "
          "predefinito; il predefinito vede solo cio' che non e' di nessuno",
          v.visibile(frozenset({"alfa", "beta"}), "alfa", True)
          and v.visibile(frozenset({"alfa", "beta"}), "beta", True)
          and not v.visibile(frozenset({"alfa", "beta"}), P, True)
          and v.visibile(frozenset(), P, True) and not v.visibile(frozenset(), "alfa", True))
    prova("etichetta: nessun nome e' il predefinito, uno e' lui, due sono incerto",
          v.etichetta([]) == P and v.etichetta(["alfa"]) == "alfa"
          and v.etichetta(["alfa", "beta"]) == I and v.etichetta(["alfa", "alfa"]) == "alfa")
    a, b = v.file_briefing("/d", "alfa"), v.file_briefing("/d", "a/b")
    prova("il nome del file di briefing non esce dalla cartella e due nomi diversi non "
          "finiscono nello stesso file",
          a == "/d/briefing.alfa.md" and os.path.dirname(b) == "/d"
          and b != v.file_briefing("/d", "a_b") and "/" not in os.path.basename(b))


_SCRIPT_INDICI = r"""
import json, os, sys
sys.path.insert(0, "__RADICE__")
from plancia import store, turni
spec = json.loads(os.environ["FIX"])
conn = store.connect(); store.init_db(conn)
ts = "2026-09-20T09:00:00Z"
turni.prepara(conn)

def turno(testo, sid, percorso):
    conn.execute(
        "INSERT INTO turni_fts(testo, sessione, ruolo, ts, progetto, percorso, riga) "
        "VALUES(?,?,?,?,?,?,?)", (testo, sid, "user", ts, "etichetta", percorso, 1))

# 700 turni del predefinito che nominano la parola piu' volte, e uno solo di
# alfa che la nomina una volta in un testo lungo: per rango sta in fondo
for i in range(700):
    turno("FAGGIO ginestra ginestra ginestra ginestra numero %d" % i,
          spec["id_pred"], spec["file_pred"])
turno("QUERCIA una sola volta la ginestra in un testo " + "riempitivo " * 40,
      spec["id_alfa"], spec["file_alfa"])
# un turno di alfa la cui sessione l'archivio non conosce: lo dice solo il
# percorso del transcript (nello specchio della cartella di alfa)
turno("QUERCIA turno noto solo per percorso PERCORSOSPECCHIO",
      spec["id_ignoto"], spec["file_ignoto"])

# 200 task del predefinito e uno di alfa, stessa cosa per le schede
for i in range(200):
    conn.execute("INSERT INTO tasks(title, status, created_at, updated_at) "
                 "VALUES(?, 'aperto', ?, ?)",
                 ("FAGGIO ginestra ginestra ginestra idea %d" % i, ts, ts))
pid = conn.execute("SELECT id FROM projects WHERE key='quercia'").fetchone()[0]
conn.execute("INSERT INTO tasks(title, project_id, status, created_at, updated_at) "
             "VALUES(?,?, 'aperto', ?, ?)",
             ("QUERCIA unica ginestra tra molte altre parole di riempimento per "
              "abbassare il rango di questa scheda", pid, ts, ts))

# 80 memorie del predefinito e una di alfa
for k in spec["memorie"]:
    conn.execute(
        "INSERT INTO knowledge(name, path, scope, description, type, body, links, "
        "project_id, updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
        (k["nome"], k["path"], k["scope"], k["descrizione"], "feedback", k["corpo"],
         "[]", None, ts))
conn.commit()
store.rebuild_search(conn)
conn.commit()
print(json.dumps({"ok": True}))
"""

ID_IGNOTO = "cccccccc-0000-4000-8000-0000000000aa"


def _prova_guardie(prova, base: Path) -> None:
    """Le guardie che il codice dichiara e nessuna prova esercitava (ognuna e'
    stata vista sopravvivere a una mutazione che la toglie), e i due difetti del
    secondo giro: la ricerca nell'indice FTS che filtra DOPO il taglio per rango
    (chi ha poche cose in un archivio grande non trova niente) e la risposta a
    voce che portava in contesto la ricerca non filtrata."""
    fix = _prepara(base / "guardie")
    if not fix["fixture_ok"]:
        prova("guardie: l'archivio finto si costruisce", False, fix["fixture_err"])
        return
    env, w, claude, ids, dirs = fix["env"], fix["w"], fix["claude"], fix["ids"], fix["dirs"]
    dati = Path(env["PLANCIA_HOME"])
    _scrivi_config(env, comp=_config_comp(w))

    # ---- la cache del riepilogo, scritta da chi chiama l'MCP, torna sotto il nome
    # del compartimento (`viste.chiudi`): due chiamate e la chiave `@alfa` c'e'
    _mcp(fix, "alfa", [("plancia", {"azione": "recap"})])
    con = _apri(env)
    chiavi = {r[0] for r in con.execute("SELECT key FROM meta")}
    con.close()
    prova("MCP: la cache del riepilogo di una sessione di alfa resta sotto `recap_*@alfa` "
          "dopo la prima chiamata (e non nella cache non separata)",
          any(k.startswith("recap_") and k.endswith("@alfa") for k in chiavi)
          and "recap_testo" not in chiavi, str(sorted(chiavi))[:300])

    # ---- il compartimento della sessione MCP si stabilisce anche dal transcript:
    # id sconosciuto ad alfa, cwd di partenza fuori da alfa, transcript nello specchio
    tr = claude / "projects" / _codifica(dirs["alfa"]) / (ID_IGNOTO + ".jsonl")
    tr.write_text("", "utf-8")
    m = _mcp(fix, "alfa", [("plancia_projects", {})], cwd=dirs["predefinito"], sid=ID_IGNOTO)
    prova("MCP: una sessione con id sconosciuto, cwd fuori da alfa e transcript sotto la "
          "codifica di alfa e' trattata da alfa (vede QUERCIA, non FAGGIO)",
          not m[0][0] and "QUERCIA" in m[0][1] and "FAGGIO" not in m[0][1], str(m)[:300])
    m = _mcp(fix, "predefinito", [("plancia_projects", {})], cwd=dirs["predefinito"],
             sid="dddddddd-0000-4000-8000-0000000000dd")
    prova("MCP: una sessione senza nessun segnale di un nominato e' del predefinito",
          not m[0][0] and "FAGGIO" in m[0][1] and "QUERCIA" not in m[0][1], str(m)[:300])

    # ---- l'hook, se il pacchetto non si carica, tace (niente lettura senza filtro)
    scr = base / "hook-rotto"
    (scr / "bin").mkdir(parents=True)
    (scr / "plancia").mkdir()
    shutil.copy(str(RADICE / "bin" / "plancia-hook"), str(scr / "bin" / "plancia-hook"))
    (scr / "plancia" / "__init__.py").write_text("raise ImportError('rotto apposta')\n", "utf-8")
    for nome in ("briefing.md", "briefing.predefinito.md", "briefing.alfa.md"):
        (dati / nome).write_text("BRIEFING DI PROVA FAGGIO QUERCIA\n", "utf-8")
    payload = {"hook_event_name": "SessionStart", "session_id": ids["predefinito"],
               "transcript_path": fix["file"]["predefinito"], "cwd": str(dirs["predefinito"]),
               "source": "startup"}
    p = subprocess.run([PYTHON, str(scr / "bin" / "plancia-hook")], input=json.dumps(payload),
                       capture_output=True, text=True, env=_env_sub(env), timeout=60)
    prova("hook: con dei compartimenti attivi e il pacchetto che non si carica non stampa "
          "niente (nemmeno il briefing non separato)",
          p.returncode == 0 and p.stdout.strip() == "", p.stdout[:200] + p.stderr[:200])
    for nome in ("briefing.md", "briefing.predefinito.md", "briefing.alfa.md"):
        (dati / nome).unlink()

    # ---- il briefing per compartimento che non c'e' ancora lo genera l'hook
    h = _hook(fix, "alfa")
    prova("hook: appena scritta la config, senza un briefing per compartimento, ne genera "
          "uno (la sessione di alfa vede il proprio lavoro e non quello degli altri)",
          "QUERCIA" in h["testo"] and "FAGGIO" not in h["testo"] and "SALICE" not in h["testo"],
          h["testo"][:300] + h["err"][:200])
    prova("hook: il briefing generato al volo lascia anche quello degli altri compartimenti",
          (dati / "briefing.predefinito.md").exists() and (dati / "briefing.beta.md").exists())

    # ---- i briefing dei compartimenti spenti spariscono, gli altri file no
    estraneo = dati / "briefing.v1.2.md"
    estraneo.write_text("un file di chi usa la cartella\n", "utf-8")
    _scrivi_config(env, comp={"beta": {"cartelle": [str(w / "beta")]}, "predefinito": {}})
    subprocess.run([PYTHON, str(RADICE / "bin" / "plancia"), "briefing"],
                   env=_env_sub(env), capture_output=True, timeout=120)
    prova("briefing: togliendo alfa dalla config il suo `briefing.alfa.md` sparisce, quello "
          "di beta resta",
          not (dati / "briefing.alfa.md").exists() and (dati / "briefing.beta.md").exists(),
          str(sorted(f.name for f in dati.glob("briefing*"))))
    prova("briefing: un file con un nome che Plancia non sa scrivere non si tocca",
          estraneo.exists())
    _scrivi_config(env, comp=_config_comp(w))

    # ---- chi non ha mai usato i compartimenti non perde un suo file
    senza = base / "senza-comp"
    env2 = _ambiente(senza)
    _scrivi_config(env2)
    suo = Path(env2["PLANCIA_HOME"]) / "briefing.mio.md"
    suo.write_text("mio\n", "utf-8")
    subprocess.run([PYTHON, str(RADICE / "bin" / "plancia"), "briefing"],
                   env=_env_sub(env2), capture_output=True, timeout=120)
    prova("briefing: senza compartimenti (mai usati) un file `briefing.<nome>.md` di chi usa "
          "la cartella resta dov'e'", suo.exists())
    _scrivi_config(env2, comp={"predefinito": {}})
    subprocess.run([PYTHON, str(RADICE / "bin" / "plancia"), "briefing"],
                   env=_env_sub(env2), capture_output=True, timeout=120)
    prova("config con la sola voce `predefinito`: nessuna copia di config in piu' nella "
          "cartella dei dati",
          not (Path(env2["PLANCIA_HOME"]) / "compartimenti.e1-ultima-valida.json").exists()
          and suo.exists())

    # ---- plancia_task_update con project="" svuota il progetto anche con i compartimenti
    z = _mcp(fix, "alfa", [("plancia_task_add", {"title": "task da svuotare QUERCIA",
                                                 "project": "quercia"})])
    try:
        tid = json.loads(z[0][1])["id"]
    except Exception:  # noqa: BLE001
        tid = None
    if tid is not None:
        u = _mcp(fix, "alfa", [("plancia_task_update", {"id": tid, "project": ""})])
        con = _apri(env)
        pid_dopo = con.execute("SELECT project_id FROM tasks WHERE id=?", (tid,)).fetchone()
        con.close()
        prova("MCP alfa: plancia_task_update con project vuoto svuota il progetto del task",
              not u[0][0] and pid_dopo is not None and pid_dopo[0] is None, str((u, pid_dopo)))
    else:
        prova("MCP alfa: task_add per la prova di project vuoto", False, str(z)[:200])

    # ---- gli indici FTS: chi ha una cosa sola in un archivio grande la trova
    memorie = []
    for i in range(80):
        memorie.append(_memoria("ibisco-cumino-%d" % i, "ibisco cumino", "FAGGIO",
                                w / "pred", claude))
    memorie.append(_memoria("quercia-ibisco-cumino-rara", "ibisco cumino", "QUERCIA",
                            w / "alfa", claude))
    ignoto = claude / "projects" / _codifica(dirs["alfa"]) / (ID_IGNOTO + ".jsonl")
    spec = {"id_pred": ids["predefinito"], "file_pred": fix["file"]["predefinito"],
            "id_alfa": ids["alfa"], "file_alfa": fix["file"]["alfa"],
            "id_ignoto": ID_IGNOTO, "file_ignoto": str(ignoto), "memorie": memorie}
    r = subprocess.run([PYTHON, "-c", _SCRIPT_INDICI.replace("__RADICE__", str(RADICE))],
                       env=dict(_env_sub(env), FIX=json.dumps(spec)),
                       capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        prova("guardie: gli indici grandi si costruiscono", False, (r.stderr or r.stdout)[-600:])
        return
    a = _mcp(fix, "alfa", [("plancia_search", {"query": "ginestra"}),
                           ("plancia_search", {"query": "PERCORSOSPECCHIO"})])
    prova("MCP alfa: un turno solo in un indice di 700 turni degli altri si trova "
          "(il filtro sta dentro la query, non dopo il taglio per rango)",
          "QUERCIA una sola volta" in a[0][1] and "FAGGIO" not in a[0][1], a[0][1][:300])
    prova("MCP alfa: una scheda sola fra 200 degli altri si trova",
          "QUERCIA unica ginestra" in a[0][1], a[0][1][:300])
    prova("MCP alfa: un turno di una sessione sconosciuta, il cui transcript sta nello "
          "specchio di alfa, e' di alfa (il percorso conta)",
          "PERCORSOSPECCHIO" in a[1][1] and "FAGGIO" not in a[1][1], a[1][1][:300])
    b = _mcp(fix, "predefinito", [("plancia_search", {"query": "PERCORSOSPECCHIO"}),
                                  ("plancia_search", {"query": "ginestra"})])
    prova("MCP predefinito: il turno noto per percorso di alfa non si vede",
          "PERCORSOSPECCHIO" not in b[0][1], b[0][1][:300])
    prova("MCP predefinito: la ricerca in un indice grande non porta niente di alfa",
          "QUERCIA" not in b[1][1] and "FAGGIO" in b[1][1], b[1][1][:300])
    r_alfa = _richiamo(fix, "alfa", "ibisco cumino")
    r_pred = _richiamo(fix, "predefinito", "ibisco cumino")
    prova("richiamo alfa: una memoria sola fra 80 del predefinito che rispondono meglio "
          "si trova (il filtro sta dentro la query, prima del LIMIT)",
          "QUERCIA" in r_alfa and "FAGGIO" not in r_alfa, r_alfa[:300])
    prova("richiamo predefinito: le 80 memorie del predefinito, e niente di alfa",
          "FAGGIO" in r_pred and "QUERCIA" not in r_pred, r_pred[:300])

    # ---- dashboard: la stessa ricerca, e lo stato della sessione viva
    srv = _Server(fix)
    try:
        c, corpo = srv.get("/api/search?q=ginestra&compartimento=alfa", testo=True)
        prova("dashboard alfa: la ricerca trova il turno e la scheda di alfa fra le "
              "migliaia degli altri", "QUERCIA una sola volta" in corpo
              and "QUERCIA unica ginestra" in corpo and "FAGGIO" not in corpo, corpo[:300])
        c, corpo = srv.get("/api/search?q=PERCORSOSPECCHIO&compartimento=alfa", testo=True)
        c2, corpo2 = srv.get("/api/search?q=PERCORSOSPECCHIO", testo=True)
        prova("dashboard: il turno noto per percorso e' visibile ad alfa e invisibile al "
              "predefinito", "PERCORSOSPECCHIO" in corpo and "PERCORSOSPECCHIO" not in corpo2,
              corpo[:200] + " | " + corpo2[:200])
        con = _apri(env)
        con.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('live_session', ?)",
                    (ids["alfa"],))
        con.commit()
        con.close()
        _, sa = srv.get("/api/status?compartimento=alfa")
        _, sp = srv.get("/api/status")
        _, sb = srv.get("/api/status?compartimento=beta")
        prova("dashboard: la sessione viva di alfa si vede in alfa e non nelle altre viste "
              "(il pallino 'live' non sparisce con i compartimenti attivi)",
              sa.get("sessione_viva") == ids["alfa"] and not sp.get("sessione_viva")
              and not sb.get("sessione_viva"), str((sa, sp, sb))[:300])

        # ---- la risposta a voce: la ricerca nell'archivio e' quella del compartimento
        segnale = base / "guardie" / "claude-chiamato"
        for comp in ("predefinito", "alfa", "beta"):
            if segnale.exists():
                segnale.unlink()
            sel = "" if comp == "predefinito" else "?compartimento=%s" % comp
            c, d = srv.scrivi("POST", "/api/voice/ask" + sel,
                              {"domanda": "task", "voce": False, "lang": "it"})
            passato = segnale.read_text("utf-8") if segnale.exists() else ""
            pezzo = ""
            if "Risultati di ricerca sul suo archivio:" in passato:
                pezzo = passato.split("Risultati di ricerca sul suo archivio:", 1)[1]
                pezzo = pezzo.split("Dati di oggi:", 1)[0]
            altri_ = [x for x in MARCHI if x != comp]
            prova("voce %s: la domanda arriva al modello (con il contesto)" % comp,
                  c == 200 and "Dati di oggi:" in passato, "%s %s" % (c, passato[:200]))
            prova("voce %s: i risultati di ricerca allegati non portano niente degli altri "
                  "compartimenti (ne' il prompt intero)" % comp,
                  _senza(passato, altri_),
                  passato[:400])
            prova("voce %s: i risultati di ricerca allegati ci sono e sono del compartimento"
                  % comp, MARCHI[comp] in pezzo, pezzo[:200])
    finally:
        srv.chiudi()


def _apri(env):
    import sqlite3
    con = sqlite3.connect(os.path.join(env["PLANCIA_HOME"], "plancia.db"))
    return con


_SCRIPT_GRANDE = r'''
import json, os, sys, time, random
sys.path.insert(0, "__RADICE__")
from plancia import store
spec = json.loads(os.environ["FIX"])
conn = store.connect(); store.init_db(conn)
ts = "2026-09-20T09:00:00Z"
random.seed(3)
liberi = spec["liberi"]
nom = spec["nominati"]
for i in range(220):
    d = random.choice([liberi, nom])
    pid = store.upsert_project(conn, "p%d" % i, "progetto %d" % i, auto=0, last_activity=ts)
    store.link_project(conn, pid, "path", "%s/pr%d" % (d, i))
conn.commit()
for i in range(3000):
    d = random.choice([liberi, nom])
    conn.execute(
        "INSERT INTO sessions(session_id, project_id, file, cwd, title, first_prompt, started_at, "
        "n_user, agent) VALUES(?,?,?,?,?,?,?,?, 'claude')",
        ("s%d" % i, 1 + i % 220, "/nessun/file/s%d.jsonl" % i, "%s/pr%d" % (d, i % 220),
         "sessione %d" % i, "prompt", ts, 2))
for i in range(900):
    conn.execute("INSERT INTO tasks(title, project_id, session_id, cwd, status, created_at, updated_at) "
                 "VALUES(?,?,?,?, 'aperto', ?, ?)", ("task %d" % i, 1 + i % 220, "s%d" % (i * 3), "", ts, ts))
for i in range(9000):
    conn.execute("INSERT INTO events(ts, kind, title, project_id, ref, dedup) VALUES(?,?,?,?,?,?)",
                 (ts, "sessione", "evento %d" % i, 1 + i % 220, "s%d" % (i % 3000), "e%d" % i))
for i in range(400):
    conn.execute("INSERT INTO knowledge(name, path, scope, description, type, body, links, updated_at) "
                 "VALUES(?,?,?,?,?,?,?,?)", ("m%d" % i, "%s/m%d.md" % (liberi, i), "x", "d", "feedback", "b", "[]", ts))
conn.commit()
from plancia import compartimenti_viste as viste
amb = viste.attivo()
t0 = time.time()
ap = viste.Appartenenze(conn, amb)
t1 = time.time()
o = viste.applica(conn, amb, "alfa", appart=ap)
t2 = time.time()
n = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
print(json.dumps({"calcolo_ms": round((t1 - t0) * 1000), "viste_ms": round((t2 - t1) * 1000),
                  "visibili": n}))
'''


def _prova_archivio_grande(prova, base: Path) -> None:
    """Il filtro su un archivio di dimensioni vere (220 progetti, 3000 sessioni,
    900 task, 9000 eventi, 400 memorie): quanto costa calcolare l'appartenenza e
    montare le viste. Il tempo si riporta nel nome della prova."""
    grande = base / "grande"
    env = _ambiente(grande)
    liberi = os.path.realpath(grande / "w" / "libero")
    nominato = os.path.realpath(grande / "w" / "alfa")
    os.makedirs(liberi, exist_ok=True)
    os.makedirs(nominato, exist_ok=True)
    _scrivi_config(env, comp={"alfa": {"cartelle": [nominato]}, "predefinito": {}})
    r = subprocess.run([PYTHON, "-c", _SCRIPT_GRANDE.replace("__RADICE__", str(RADICE))],
                       env=dict(_env_sub(env), FIX=json.dumps({"liberi": liberi, "nominati": nominato})),
                       capture_output=True, text=True, timeout=300)
    try:
        d = json.loads(r.stdout.strip().splitlines()[-1])
    except Exception:  # noqa: BLE001
        prova("il filtro su un archivio grande gira", False, (r.stderr or r.stdout)[-600:])
        return
    prova("il filtro su un archivio grande (3000 sessioni, 9000 eventi) costa %d ms di calcolo e "
          "%d ms di viste, sotto i 3 secondi" % (d["calcolo_ms"], d["viste_ms"]),
          d["calcolo_ms"] + d["viste_ms"] < 3000, str(d))
    prova("il filtro su un archivio grande toglie davvero le sessioni dei nominati",
          0 < d["visibili"] < 3000, str(d))
