"""Prove per la RIPARAZIONE-SERVER della seconda passata di Plancia 2.0.

Il tester aveva trovato, sul server, difetti che le prove dei lotti non vedevano
perche' provavano ognuno il suo pezzo e mai l'incontro fra due pezzi:

- un lancio fallito perdeva la sessione che doveva riprendere (`runs.sessione`
  sovrascritta con NULL), quindi "Rilancia" ripartiva da una sessione nuova;
- "la quarta" (il pulsante della quarta proposta) non era una frase che Jarvis
  riconosce;
- il Terminale riprendeva con `--resume` una sessione chiusa la cui cartella non
  c'e' piu', mentre il lavoro in background la dava per persa: due percorsi che
  si contraddicevano;
- il piano mostrava la cartella del task ma l'agente partiva da un'altra;
- dopo un lancio Codex di Plancia il pulsante di stato diceva "viva" per dieci
  minuti (lo stato e il piano usavano due regole diverse);
- `plancia manda --task N` senza `--attendi` non lanciava mai l'agente (il
  thread moriva con il comando);
- `plancia riordina` con un file scritto male usciva con un traceback, con codice
  0 anche a righe rifiutate; un inglobamento in un progetto automatico veniva
  rifiutato per intero; riapplicare una riga di solo padre contava "applicata".

Come le altre prove del server: nessun agente vero (un `claude` e un `codex`
FINTI che registrano cosa hanno ricevuto), nessun archivio vero (una PLANCIA_HOME
di prova, con HOME, CLAUDE_CONFIG_DIR e CODEX_HOME finti), un server di prova su
una porta libera scelta al momento, un lanciatore di terminale finto
(PLANCIA_TERMINALE). Si riusa il "mondo" di riprendi-stessa-sessione.py.
"""

import importlib.util
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent.parent
if str(RADICE) not in sys.path:
    sys.path.insert(0, str(RADICE))


def _carica(nome_file, nome_modulo):
    if nome_modulo in sys.modules:
        return sys.modules[nome_modulo]
    spec = importlib.util.spec_from_file_location(
        nome_modulo, Path(__file__).resolve().parent / nome_file)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[nome_modulo] = modulo
    spec.loader.exec_module(modulo)
    return modulo


def _porta_libera():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    porta = s.getsockname()[1]
    s.close()
    return porta


# --------------------------------------------------------------------------
# i programmi finti
# --------------------------------------------------------------------------

# Un claude finto che sa anche fallire (modo "fallisce": esce 1 senza scrivere
# niente, come un lancio che muore subito).
_CLAUDE = r'''
import json, os, sys
registro = %(registro)r
modo_file = %(modo)r
argv = sys.argv[1:]
if argv[:1] == ["agents"]:
    print("[]")
    sys.exit(0)
stdin = sys.stdin.read() if "-p" in argv else ""
sid = argv[argv.index("--resume") + 1] if "--resume" in argv else None
if "--fork-session" in argv or not sid:
    sid = "nuova-%%d" %% os.getpid()
modo = open(modo_file).read().strip() if os.path.exists(modo_file) else "ok"
with open(registro, "a") as f:
    f.write(json.dumps({"bin": "claude", "argv": argv, "cwd": os.getcwd(),
                        "stdin": stdin, "sid": sid, "modo": modo}) + "\n")
if modo == "fallisce":
    sys.stderr.write("No conversation found\n")
    sys.exit(1)
print(json.dumps({"type": "system", "session_id": sid}))
print(json.dumps({"type": "result", "result": "fatto", "session_id": sid,
                  "usage": {"output_tokens": 1}, "total_cost_usd": 0, "is_error": False}))
'''

# Un codex finto che, come quello vero, tocca il rollout della sessione che
# riprende (e sa fare il conflitto del thread tenuto dall'app).
_CODEX = r'''
import glob, json, os, sys
registro = %(registro)r
modo_file = %(modo)r
codex_home = %(codex_home)r
argv = sys.argv[1:]
stdin = sys.stdin.read() if argv and argv[-1] == "-" else ""
modo = open(modo_file).read().strip() if os.path.exists(modo_file) else "ok"
with open(registro, "a") as f:
    f.write(json.dumps({"bin": "codex", "argv": argv, "cwd": os.getcwd(),
                        "stdin": stdin, "modo": modo}) + "\n")
if modo == "conflitto":
    sys.stderr.write("Error: thread-store conflict: thread already has an active writer\n")
    sys.exit(1)
sid = argv[argv.index("resume") + 1] if "resume" in argv else "0199aaaa-0000-0000-0000-0000000000ff"
for p in glob.glob(os.path.join(codex_home, "sessions", "*", "*", "*", "rollout-*-" + sid + ".jsonl")):
    os.utime(p, None)
print("session id: " + sid)
print("fatto")
'''

# Il lanciatore del Terminale finto: scrive nel registro la riga che riceverebbe.
_TERMINALE = r'''
import json, sys
open(%(registro)r, "a").write(json.dumps({"bin": "terminale", "riga": sys.argv[1]}) + "\n")
'''

_SEME = r'''
import json, os, socket, sys, time
sys.path.insert(0, %(radice)r)
from plancia import actions, richiamo, store
cfg = json.loads(%(cfg)r)
conn = store.connect(); store.init_db(conn)
host = socket.gethostname()
out = {}

def cartella(nome):
    p = os.path.join(cfg["lavoro"], nome); os.makedirs(p, exist_ok=True); return p

def trascrizione(cwd, sid):
    d = os.path.join(cfg["claude"], "projects", richiamo.cartella_sessione(cwd))
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, sid + ".jsonl"), "w").write('{"type":"summary"}\n')

def rollout(sid):
    d = os.path.join(cfg["codex"], "sessions", "2026", "09", "01"); os.makedirs(d, exist_ok=True)
    f = os.path.join(d, "rollout-2026-09-01T10-00-00-" + sid + ".jsonl")
    open(f, "w").write('{}\n')
    t = time.time() - 7200; os.utime(f, (t, t))

def task(titolo, sid, cwd, agente="claude"):
    t = actions.task_add(conn, titolo, session_id=sid, cwd=cwd, agent=agente, host=host)
    return t["id"]

# sessione chiusa il cui lancio fallira'
c = cartella("fallito"); trascrizione(c, "sid-fallito-0001")
out["t_fallito"] = task("task il cui lancio fallisce", "sid-fallito-0001", c)

# sessione chiusa la cui cartella poi sparisce
c = cartella("sparita"); trascrizione(c, "sid-sparita-0002")
out["t_sparita"] = task("task con la cartella sparita", "sid-sparita-0002", c)
out["cartella_sparita"] = c

# sessione persa (nessuna trascrizione) ma con una cartella che c'e'
c = cartella("persa-con-cartella")
out["t_persa"] = task("task perso con la sua cartella", "sid-persa-0003", c)
out["cartella_persa"] = c

# codex chiuso, lanciato due volte e in conflitto
c = cartella("codex"); rollout(%(sid_codex)r)
out["t_codex"] = task("task codex chiuso", %(sid_codex)r, c, "codex")
c = cartella("codex-conflitto"); rollout(%(sid_codex_c)r)
out["t_codex_conflitto"] = task("task codex occupato", %(sid_codex_c)r, c, "codex")

# per il comando `manda --task`
c = cartella("manda"); trascrizione(c, "sid-manda-0004")
out["t_manda"] = task("task per manda", "sid-manda-0004", c)

# per i progetti del riordino via riga di comando
for chiave, auto in (("manuale-uno", 0), ("auto-uno", 1), ("auto-due", 1), ("auto-tre", 1)):
    store.upsert_project(conn, chiave, chiave, auto=auto, _force=True)
conn.commit()
print(json.dumps(out))
'''

_SID_CODEX = "0199aaaa-0000-0000-0000-00000000d001"
_SID_CODEX_C = "0199aaaa-0000-0000-0000-00000000d002"


def _mondo_riparazione(base, riprendi_mod):
    """Il mondo di riprendi-stessa-sessione, con i programmi finti di questo file."""
    riprendi_mod.PORTA = _porta_libera()
    m = riprendi_mod._Mondo(base)
    finti = riprendi_mod._finti
    m.modo_claude = m.finti / "modo-claude.txt"
    m.terminale_registro = m.finti / "terminale.jsonl"
    claude = finti.crea_finto(m.finti, "claude-finto-2", _CLAUDE % {
        "registro": str(m.registro), "modo": str(m.modo_claude)})
    codex = finti.crea_finto(m.finti, "codex-finto-2", _CODEX % {
        "registro": str(m.registro), "modo": str(m.modo_codex), "codex_home": str(m.codex)})
    (m.home / "config.json").write_text(
        json.dumps({"claude_bin": claude, "codex_bin": codex}), "utf-8")
    m.terminale = finti.crea_finto(m.finti, "terminale-finto", _TERMINALE % {
        "registro": str(m.terminale_registro)})
    env_base = m.env

    def env():
        e = env_base()
        e["PLANCIA_TERMINALE"] = m.terminale
        return e
    m.env = env
    return m


def _semina(m):
    cfg = {"lavoro": str(m.lavoro), "claude": str(m.claude), "codex": str(m.codex)}
    codice = _SEME % {"radice": str(RADICE), "cfg": json.dumps(cfg),
                      "sid_codex": _SID_CODEX, "sid_codex_c": _SID_CODEX_C}
    m.ids = json.loads(m.python(codice).strip().splitlines()[-1])
    m.token = m.python(
        "import sys; sys.path.insert(0, %r)\nfrom plancia import config\n"
        "print(config.get_token())" % str(RADICE)).strip()


def _righe(percorso):
    if not percorso.exists():
        return []
    return [json.loads(r) for r in percorso.read_text("utf-8").splitlines() if r.strip()]


def _uguali(a, b):
    return os.path.realpath(a or "") == os.path.realpath(b or "")


# --------------------------------------------------------------------------
# esegui
# --------------------------------------------------------------------------

def _stadio(prova, nome, funzione, *args):
    """Un gruppo che cade con un'eccezione e' una prova fallita col suo nome, e
    gli altri gruppi girano lo stesso."""
    try:
        funzione(prova, *args)
    except Exception as exc:  # noqa: BLE001 - un gruppo non affossa gli altri
        import traceback
        prova(f"{nome} gira senza eccezioni", False,
              "".join(traceback.format_exception_only(type(exc), exc)).strip()
              + " @ " + traceback.format_exc().strip().splitlines()[-3].strip())


def esegui(prova) -> None:
    _stadio(prova, "quarta", _quarta)
    _stadio(prova, "riordina senza processi", _riordina_puro)
    _stadio(prova, "avvisi", _avvisi)

    riprendi_mod = _carica("riprendi-stessa-sessione.py", "riprendi_stessa_sessione_p")
    base = Path(tempfile.mkdtemp(prefix="plancia-prova-riparazione-"))
    m = _mondo_riparazione(base, riprendi_mod)
    try:
        try:
            _semina(m)
        except Exception as exc:
            prova("l'archivio di prova della riparazione si semina", False, str(exc))
            return
        if not m.avvia_server():
            prova("il server di prova della riparazione parte", False, "nessuna risposta")
            return
        try:
            for nome, f in (("lancio fallito", _lancio_fallito),
                            ("codex conflitto", _codex_conflitto),
                            ("stato e piano", _stato_e_piano_coerenti),
                            ("cartella che parte", _cartella_che_parte),
                            ("terminale", _terminale_cartella_sparita),
                            ("cli manda", _cli_manda),
                            ("cli riordina", _cli_riordina),
                            ("lavagna subito", _lavagna_subito)):
                _stadio(prova, nome, f, m)
        finally:
            m.ferma()
    finally:
        shutil.rmtree(str(base), ignore_errors=True)


# --------------------------------------------------------------------------
# senza processi
# --------------------------------------------------------------------------

def _conn():
    from plancia import store
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    store.init_db(conn)
    return conn


def _quarta(prova):
    """Il quarto pulsante delle proposte manda 'la quarta': Jarvis deve capirla."""
    from plancia import jarvis, proposte
    prova("Jarvis riconosce 'la quarta' come la scelta di una proposta",
          jarvis.riconosci("la quarta") == ("fallo", "quarta"), str(jarvis.riconosci("la quarta")))
    prova("...e 'il quarto' allo stesso modo",
          jarvis.riconosci("il quarto") == ("fallo", "quarto"), str(jarvis.riconosci("il quarto")))
    conn = _conn()
    lista = [{"testo": t, "azione": {"tipo": "vai", "vista": "oggi"}}
             for t in ("proposta A", "proposta B", "proposta C", "proposta D")]
    proposte.salva(conn, lista)
    scelta = proposte.scegli(conn, "quarta")
    prova("proposte.scegli('quarta') torna la quarta proposta, non la prima",
          scelta is not None and scelta["testo"] == "proposta D", str(scelta))
    prova("...e la terza resta la terza",
          proposte.scegli(conn, "terza")["testo"] == "proposta C", "")
    # con solo tre proposte 'la quarta' non c'e': None, non una a caso
    proposte.salva(conn, lista[:3])
    prova("con tre proposte 'la quarta' non sceglie niente",
          proposte.scegli(conn, "quarta") is None, str(proposte.scegli(conn, "quarta")))


def _scrivi(righe, nome, testo=None):
    dest = Path(tempfile.mkdtemp(prefix="plancia-prova-riparazione-")) / f"{nome}.json"
    dest.write_text(testo if testo is not None else json.dumps(righe, ensure_ascii=False),
                    encoding="utf-8")
    return dest


def _progetto(conn, key, auto=0):
    from plancia import store
    pid = store.upsert_project(conn, key, key, auto=auto, _force=True)
    conn.commit()
    return pid


def _riordina_puro(prova):
    from plancia import riordina, slot

    # --- il file scritto male e' un errore detto, non un traceback ----------
    for nome, testo, atteso in (
            ("json rotto", "{ non e' json", "JSON"),
            ("oggetto invece di lista", '{"chiave": "a"}', "lista"),
    ):
        try:
            riordina.carica(_scrivi(None, "cattivo", testo))
            eccezione = None
        except getattr(riordina, "FileNonValido", ()) as exc:
            eccezione = str(exc)
        except Exception as exc:  # noqa: BLE001 - e' proprio il difetto da provare
            eccezione = "TRACEBACK " + type(exc).__name__
        prova(f"riordina.carica su un file «{nome}» alza FileNonValido col perche'",
              bool(eccezione) and not eccezione.startswith("TRACEBACK") and atteso in eccezione,
              str(eccezione))

    # --- righe che non sono oggetti, campi che non sono testo ---------------
    conn = _conn()
    _progetto(conn, "uno", auto=1)
    righe = ["stringa", {"chiave": "uno", "stato": "archiviato", "motivo": ["non", "testo"]}, 5]
    try:
        tab = riordina.tabella(righe)
        errore = None
    except Exception as exc:  # noqa: BLE001
        tab, errore = "", type(exc).__name__
    prova("--mostra: righe non-oggetto e un motivo non testuale non fanno cadere la tabella",
          errore is None and "DA CORREGGERE" in tab, f"{errore} {tab!r}")
    esito = riordina.applica(conn, _scrivi(righe, "righe-storte"))
    prova("--applica: le righe storte sono rifiutate con un motivo, nessuna eccezione",
          esito["rifiutate"] == 3 and esito["applicate"] == 0, str(esito))

    # --- un inglobamento in un progetto automatico non si perde -------------
    conn = _conn()
    _progetto(conn, "vecchio", auto=1)
    _progetto(conn, "gemello", auto=1)
    esito = riordina.applica(conn, _scrivi(
        [{"chiave": "vecchio", "inglobato_in": "gemello", "motivo": "il codice vive in gemello"}],
        "inglobo-auto"))
    riga = conn.execute("SELECT * FROM projects WHERE key='vecchio'").fetchone()
    prova("inglobare in un progetto AUTOMATICO archivia e mette la nota (prima: rifiutato per intero)",
          esito["rifiutate"] == 0 and esito["inglobati"] == 1
          and riga["status"] == "archiviato"
          and "Inglobato in gemello: il codice vive in gemello" in (riga["summary"] or ""),
          f"{esito} {dict(riga)}")
    prova("...senza scrivere il padre (un automatico non puo' fare da padre) e lo dice nell'esito",
          riga["parent_id"] is None and len(esito["inglobati_senza_padre"]) == 1
          and esito["inglobati_senza_padre"][0]["destinazione"] == "gemello", str(esito))
    dest = _scrivi([{"chiave": "vecchio", "inglobato_in": "gemello",
                     "motivo": "il codice vive in gemello"}], "inglobo-auto-bis")
    riordina.applica(conn, dest)
    esito2 = riordina.applica(conn, dest)
    riga2 = conn.execute("SELECT summary FROM projects WHERE key='vecchio'").fetchone()
    prova("...riapplicarlo non cambia niente e non ripete la nota",
          esito2["applicate"] == 0 and esito2["invariate"] == 1
          and (riga2["summary"] or "").count("Inglobato in gemello") == 1, str(esito2))

    # una riga con un PADRE esplicito (non un inglobamento) resta tutto o niente
    conn = _conn()
    _progetto(conn, "x", auto=1)
    _progetto(conn, "y", auto=1)
    esito = riordina.applica(conn, _scrivi(
        [{"chiave": "x", "padre": "y", "stato": "archiviato", "motivo": "prova"}], "padre-auto"))
    prova("un padre automatico esplicito resta rifiutato e lo stato non cambia",
          esito["rifiutate"] == 1
          and conn.execute("SELECT status FROM projects WHERE key='x'").fetchone()[0] != "archiviato",
          str(esito))
    prova("un inglobamento in un progetto che non esiste resta rifiutato",
          riordina.applica(conn, _scrivi(
              [{"chiave": "x", "inglobato_in": "non-esiste", "motivo": "m"}], "inglobo-vuoto")
          )["rifiutate"] == 1, "")

    # --- riapplicare una riga di solo padre non e' una modifica -------------
    conn = _conn()
    _progetto(conn, "tesi", auto=0)
    _progetto(conn, "tesi-a", auto=1)
    dest = _scrivi([{"chiave": "tesi-a", "padre": "tesi"}], "solo-padre")
    prima = riordina.applica(conn, dest)
    seconda = riordina.applica(conn, dest)
    prova("una riga di solo padre: la prima volta e' applicata",
          prima["applicate"] == 1 and prima["invariate"] == 0, str(prima))
    prova("...la seconda e' 'invariata', non 'applicata'",
          seconda["applicate"] == 0 and seconda["invariate"] == 1, str(seconda))
    esito = slot.set_parent(conn, "tesi-a", "tesi", "prova-idempotente")
    prova("slot.set_parent su un padre gia' scritto torna cambiato=False",
          esito["ok"] is True and esito.get("cambiato") is False, str(esito))


def _avvisi(prova):
    """L'avviso di una sessione aperta non ha piu' le parentesi doppie."""
    from plancia import riprendi
    ok = riprendi._AVVISI["niente"].format(sid="abcd1234", motivo="aperta in /x/y")
    prova("l'avviso 'niente' non ripete il motivo fra parentesi",
          "((" not in ok and "/x/y" not in ok and "abcd1234" in ok, ok)
    cx = riprendi._AVVISI["niente_codex"].format(sid="abcd1234", motivo="il rollout e' recente")
    prova("...per Codex dice 'sembra' aperta e da' il perche' (e' un'euristica)",
          "sembra aperta" in cx and "il rollout e' recente" in cx, cx)


# --------------------------------------------------------------------------
# con il server
# --------------------------------------------------------------------------

def _fine(m, run_id, secondi=25):
    return m.lancio_finito(run_id, secondi) if run_id else {}


def _lancio_fallito(prova, m):
    """Un lancio che fallisce non deve perdere la sessione che riprendeva."""
    ids = m.ids
    m.modo_claude.write_text("fallisce", "utf-8")
    try:
        r = m.http("/api/riprendi/%d" % ids["t_fallito"], "POST", {"background": True})
        d = _fine(m, r.get("run"))
        prova("un lancio che fallisce subito finisce 'fallito'",
              d.get("stato") == "fallito", str(d)[:200])
        prova("...e tiene l'id della sessione che riprendeva (runs.sessione non e' NULL)",
              d.get("sessione") == "sid-fallito-0001", str(d)[:300])
        a = m.http("/api/cantiere", "POST", {"run": r.get("run"), "anteprima": True})
        prova("...cosi' 'Rilancia' lo rimette nella STESSA sessione (piano riprendi, non nuova)",
              (a.get("piano") or {}).get("modo") == "riprendi"
              and (a.get("piano") or {}).get("origine") == "sid-fallito-0001", str(a)[:300])
        n = len(m.chiamate())
        rl = m.http("/api/cantiere", "POST", {"run": r.get("run")})
        m.modo_claude.write_text("ok", "utf-8")
        c = m.dopo(n)
        argv = (c[0] if c else {}).get("argv", [])
        prova("...e il rilancio parte davvero con --resume sulla sessione originale",
              "--resume" in argv and argv[argv.index("--resume") + 1] == "sid-fallito-0001"
              and "--fork-session" not in argv, str(argv))
    finally:
        m.modo_claude.write_text("ok", "utf-8")


def _codex_conflitto(prova, m):
    ids = m.ids
    m.modo_codex.write_text("conflitto", "utf-8")
    try:
        r = m.http("/api/riprendi/%d" % ids["t_codex_conflitto"], "POST", {"background": True})
        d = _fine(m, r.get("run"))
        prova("codex col thread tenuto dall'app: il lancio e' 'bloccato'",
              d.get("stato") == "bloccato", str(d)[:200])
        prova("...e tiene la sessione, cosi' si puo' riprovare dopo aver chiuso il thread",
              d.get("sessione") == _SID_CODEX_C, str(d)[:300])
        a = m.http("/api/cantiere", "POST", {"run": r.get("run"), "anteprima": True})
        prova("...il rilancio propone di riprenderla, non di ripartire da zero",
              (a.get("piano") or {}).get("modo") == "riprendi", str(a)[:300])
    finally:
        m.modo_codex.write_text("ok", "utf-8")


def _stato_e_piano_coerenti(prova, m):
    """Dopo un lancio Codex di Plancia, stato e piano dicono la stessa cosa."""
    ids = m.ids
    m.modo_codex.write_text("ok", "utf-8")
    r = m.http("/api/riprendi/%d" % ids["t_codex"], "POST", {"background": True})
    d = _fine(m, r.get("run"))
    prova("codex chiuso: il lancio riprende la sessione e finisce 'riuscito'",
          d.get("stato") == "riuscito" and d.get("sessione") == _SID_CODEX, str(d)[:300])
    time.sleep(1.2)  # il finto ha toccato il rollout: l'ultimo tocco e' del lancio
    g = m.http("/api/riprendi/%d" % ids["t_codex"])
    prova("subito dopo il lancio il pulsante NON dice 'viva' (l'ha chiusa Plancia)",
          (g.get("riprendi") or {}).get("stato") == "chiusa", str(g.get("riprendi")))
    prova("...ed e' lo stesso che dice il piano",
          (g.get("piano") or {}).get("stato") == (g.get("riprendi") or {}).get("stato")
          and (g.get("piano") or {}).get("modo") == "riprendi", str(g.get("piano")))


def _cartella_che_parte(prova, m):
    """La cartella che il piano mostra e' quella da cui l'agente parte davvero."""
    ids = m.ids
    n = len(m.chiamate())
    r = m.http("/api/riprendi/%d" % ids["t_persa"], "POST", {"background": True})
    c = m.dopo(n)
    partito = (c[0] if c else {}).get("cwd")
    prova("sessione persa con la cartella del task ancora li': il piano mostra quella cartella",
          _uguali((r.get("piano") or {}).get("cwd"), ids["cartella_persa"]), str(r.get("piano")))
    prova("...e l'agente parte proprio da quella (prima partiva dalla HOME)",
          _uguali(partito, ids["cartella_persa"]), str(partito))
    prova("...la cartella del lancio e quella del piano coincidono",
          _uguali(r.get("cwd"), (r.get("piano") or {}).get("cwd")), str(r)[:300])
    # senza cartella e senza progetto: e' la HOME, e il piano lo dice
    g = m.http("/api/riprendi/%d" % ids["t_sparita"])
    shutil.rmtree(ids["cartella_sparita"], ignore_errors=True)
    g = m.http("/api/riprendi/%d" % ids["t_sparita"])
    p = g.get("piano") or {}
    prova("cartella sparita: il piano e' 'nuova' e mostra una cartella che esiste",
          p.get("modo") == "nuova" and os.path.isdir(p.get("cwd") or ""), str(p))
    n = len(m.chiamate())
    r = m.http("/api/riprendi/%d" % ids["t_sparita"], "POST", {"background": True})
    c = m.dopo(n)
    prova("...e l'agente parte da quella stessa cartella",
          bool(c) and _uguali(c[0].get("cwd"), p.get("cwd")), str(c[:1]))


def _terminale_cartella_sparita(prova, m):
    """Il Terminale e il background dicono la stessa cosa su una cartella sparita."""
    ids = m.ids
    g = m.http("/api/riprendi/%d" % ids["t_sparita"])
    prova("cartella sparita: anche il pulsante di stato dice 'persa', non 'chiusa'",
          (g.get("riprendi") or {}).get("stato") == "persa"
          and "cartella" in (g.get("riprendi") or {}).get("motivo", ""), str(g.get("riprendi")))
    r = m.http("/api/riprendi/%d" % ids["t_sparita"], "POST", {"apri": True})
    righe = [x for x in _righe(m.terminale_registro) if x.get("bin") == "terminale"]
    riga = righe[-1]["riga"] if righe else ""
    prova("il Terminale NON lancia --resume in una cartella che non c'e' (sarebbe una sessione mai trovata)",
          bool(righe) and "--resume" not in riga, riga[:200])
    prova("...lancia una sessione nuova, e la risposta lo dice (stato persa)",
          r.get("stato") == "persa", str(r)[:200])


def _cli(m, *args, timeout=90):
    r = subprocess.run([sys.executable, str(RADICE / "bin" / "plancia")] + list(args),
                       capture_output=True, text=True, env=m.env(), timeout=timeout,
                       stdin=subprocess.DEVNULL)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def _cli_manda(prova, m):
    """`plancia manda ... --task N` senza --attendi deve far girare il lavoro."""
    ids = m.ids
    n = len(m.chiamate())
    codice, uscita = _cli(m, "manda", "lavoro da fare", "--task", str(ids["t_manda"]))
    c = m.dopo(n, secondi=5)
    prova("manda --task N (senza --attendi) lancia davvero l'agente",
          codice == 0 and bool(c), f"{codice} {uscita[:300]}")
    runs = m.http("/api/runs?limite=10")
    ultimo = None
    if isinstance(runs, list):
        ultimo = next((r for r in runs if r.get("task_id") == ids["t_manda"]), None)
    prova("...e il lancio e' finito prima che il comando uscisse (non 'in coda' per sempre)",
          ultimo is not None and ultimo.get("stato") == "riuscito", str(ultimo)[:300])
    task = m.http("/api/tasks?limite=200")
    riga = None
    if isinstance(task, list):
        riga = next((t for t in task if t.get("id") == ids["t_manda"]), None)
    prova("...e il task non resta 'in corso' su un lancio morto",
          riga is None or riga.get("status") != "in corso", str(riga)[:200])


def _cli_riordina(prova, m):
    cattivo = _scrivi(None, "cli-json-rotto", "questo non e' json")
    codice, uscita = _cli(m, "riordina", "--mostra", str(cattivo))
    prova("riordina --mostra su un JSON rotto: un messaggio, niente traceback, uscita 1",
          codice == 1 and "Traceback" not in uscita and "non valido" in uscita,
          f"{codice} {uscita[:300]}")
    codice, uscita = _cli(m, "riordina", "--applica", str(cattivo))
    prova("riordina --applica su un JSON rotto: stesso, uscita 1",
          codice == 1 and "Traceback" not in uscita and "non valido" in uscita,
          f"{codice} {uscita[:300]}")
    storto = _scrivi([{"chiave": "auto-uno", "stato": "archiviato"}], "cli-senza-motivo")
    codice, uscita = _cli(m, "riordina", "--applica", str(storto))
    prova("riordina --applica con una riga rifiutata esce con 1 (prima 0)",
          codice == 1 and "rifiutata" in uscita, f"{codice} {uscita[:300]}")
    buono = _scrivi([{"chiave": "auto-due", "inglobato_in": "auto-tre",
                      "motivo": "il codice e' in auto-tre"}], "cli-inglobo-auto")
    codice, uscita = _cli(m, "riordina", "--applica", str(buono))
    prova("riordina --applica di un inglobamento in un automatico: esce 0 e dice 'senza padre'",
          codice == 0 and "senza padre" in uscita and "inglobati: 1" in uscita,
          f"{codice} {uscita[:300]}")


def _lavagna_subito(prova, m):
    """Un task scritto dalla dashboard compare in 'Tutti i task' senza aspettare un sync."""
    def voce(tid):
        voci = (m.http("/api/lavagna?stato=tutti&limite=500") or {}).get("voci", [])
        return next((v for v in voci if v.get("fonte") == "plancia" and v.get("task_id") == tid), None)

    t = m.http("/api/tasks", "POST", {"title": "task nato dalla dashboard"})
    tid = t.get("id")
    v = voce(tid)
    prova("un task creato dalla dashboard e' subito in 'Tutti i task' (nessun sync in mezzo)",
          v is not None and v.get("titolo") == "task nato dalla dashboard" and v.get("stato") == "aperto",
          str(v))
    m.http("/api/tasks/%d" % tid, "PATCH", {"status": "fatto"})
    v = voce(tid)
    prova("...chiuderlo lo aggiorna subito",
          v is not None and v.get("stato") == "fatto", str(v))
    m.http("/api/tasks/%d" % tid, "DELETE")
    prova("...cancellarlo lo toglie subito",
          voce(tid) is None, str(voce(tid)))
