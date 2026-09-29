"""Prove per il lotto GUARDIANO: l'hook PreToolUse dei compartimenti
(`bin/plancia-guardiano`, logica in `plancia/compartimenti.py`).

Tutto in un ambiente isolato, come `tools/prove/esclusi.py`: HOME,
PLANCIA_HOME e CLAUDE_CONFIG_DIR sono cartelle temporanee, mai `~/.claude` o
`~/.plancia` veri. Il guardiano si lancia SEMPRE come sottoprocesso, con il
JSON dell'hook su stdin, con `/usr/bin/python3` quando c'e' (e' il Python 3.9
di sistema: la prova che l'hook regge la versione piu' vecchia che deve
reggere). Nessuna prova lancia `claude` o `codex`: il PATH del sottoprocesso
e' solo `/usr/bin:/bin`.

I compartimenti delle prove sono finti e generici: `alfa` e `beta` (nominati,
con cartelle temporanee) e il `predefinito`. Nessun nome vero.

Le prove seguono la specifica dei compartimenti: 1 (un nominato: fuori
negato, dentro ok), 2 (il predefinito verso le cartelle di un nominato), 3 (i
subagenti), 6 (strumenti di sessione incrociati, nei due sensi), 7
(change_directory), 8 (config malformata), piu' il manifesto dei divieti,
`comandi_vietati`, i symlink, le tre modalita', lo stdin rotto, il tempo per
chiamata, la rotazione del registro, il sottocomando `plancia guardiano` e
la compatibilita' con Python 3.9. Le prove 4 e 5 (briefing/richiamo e boa)
sono di altri lotti.

Il terzo giro aggiunge: lo specchio delle cartelle dei nominati sotto
`~/.claude/projects` (trascrizioni e memoria: `_prove_specchio`), l'autoprotezione
contro la CLI di Plancia e le altre vie di scrittura dei file del guardiano
(`_prove_autoprotezione_cli`), il controllo del valore di `plancia config
guardiano` (`_prove_cli_config`), i falsi positivi di Bash per un nominato e il
motivo del diniego per `/tmp` (`_prove_falsi_positivi_bash`) e la ricerca nelle
trascrizioni di tutte le sessioni (`_prove_ricerca_trascrizioni`).

Il quarto giro aggiunge: il testo di echo/printf e i corpi degli heredoc che
arrivano a un comando che li usa (`_prove_flusso_testo`, 58 idiomi), la cartella
e le variabili simulate lungo il comando (`_prove_cd_variabili`), il guardiano
che non parte (`_prove_non_parte`), la config illeggibile che non si riscrive
(`_prove_config_illeggibile`), settings.json (`_prove_settings`), gli
interpreti con il percorso costruito e le altre scritture nella cartella dei
dati (`_prove_interpreti_e_scritture`), le cartelle annidate, i nominati sulla
stessa cartella e la madre di un subagente (`_prove_annidati`) e i minori
(`_prove_minori`).

Il quinto giro aggiunge: i falsi positivi di un nominato per argomenti che cominciano
con `/` senza essere percorsi (`_prove_falsi_positivi_regex`, 75 comandi onesti), le
cartelle di codice condivise (`_prove_condivise`), i buchi di elenco del quarto tester
(`_prove_gravi_5`: here-string, sostituzione di processo, script scritto e lanciato,
`chmod` senza -R, `xargs`, cicli, graffe, interpreti; e i permessi tolti alla cartella
dei dati), i settings che neutralizzano il guardiano (`_prove_settings_5`) e i minori
(`_prove_minori_5`: ANSI-C, `cd` con graffe, il tetto dei percorsi, BaseException,
hang, PYTHONPATH).

Gli strumenti di sessione si provano con gli id che l'app manda davvero
(`local_<uuid>`, nomi, `self`, `main`), risolti da un registro dell'app finto
nella HOME temporanea (`claude-code-sessions/*/*/local_<uuid>.json`), con l'id
`local_` DIVERSO dal `cliSessionId`: e' cosi' anche nel registro vero, e una
prova con id uguali al `session_id` non proverebbe niente. Ogni controllo che
dice "non succede niente" (nessuna scrittura, nessuna uscita) e' legato, nello
stesso controllo, a una condizione positiva (uscita 0, esito atteso, o lo
stesso ambiente che altrove scrive davvero): senza il codice, che qui non
esiste, resterebbe verde per il motivo sbagliato.
"""

import ast
import importlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
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
GUARDIANO = RADICE / "bin" / "plancia-guardiano"
PYTHON = "/usr/bin/python3" if os.path.exists("/usr/bin/python3") else sys.executable

# Id di sessione finti (la forma di un uuid, ma inventati).
S_COMUNE = "c0c0c0c0-0000-4000-8000-000000000001"     # sessione del predefinito
S_ALFA = "a1a1a1a1-0000-4000-8000-000000000002"       # in alfa.sessioni
S_ALFA_LIBERA = "a1a1a1a1-0000-4000-8000-000000000003"  # alfa solo per cartella
S_BETA = "b2b2b2b2-0000-4000-8000-000000000004"       # in beta.sessioni
S_DB_ALFA = "d0d0d0d0-0000-4000-8000-000000000005"    # nella tabella, cwd in alfa
S_DB_COMUNE = "d0d0d0d0-0000-4000-8000-000000000006"  # nella tabella, cwd comune
S_IGNOTA = "e0e0e0e0-0000-4000-8000-000000000007"     # in nessun posto
S_MADRE = "f0f0f0f0-0000-4000-8000-000000000008"      # madre di un subagente

# Id dell'app (`local_...`) e `cliSessionId` DIVERSI, come nel registro vero.
L_ALFA = "local_aaaa0000-0000-4000-8000-00000000000a"
S_REG_ALFA = "a2a2a2a2-0000-4000-8000-00000000000b"
L_ALFA_ID = "local_aaaa0000-0000-4000-8000-00000000000c"   # cli = S_ALFA, cwd nel comune
L_COMUNE = "local_cccc0000-0000-4000-8000-00000000000d"    # cli = S_COMUNE
L_COMUNE2 = "local_cccc0000-0000-4000-8000-00000000000e"
S_REG_COMUNE2 = "c3c3c3c3-0000-4000-8000-00000000000f"
L_BETA = "local_bbbb0000-0000-4000-8000-000000000010"      # cli = S_BETA
L_IGNOTA = "local_eeee0000-0000-4000-8000-000000000011"    # non nel registro
L_CFG = "local_dddd0000-0000-4000-8000-000000000012"       # scritto in alfa.sessioni
S_CFG = "d1d1d1d1-0000-4000-8000-000000000013"             # il suo cliSessionId
L_DUP1 = "local_9999aaaa-0000-4000-8000-000000000014"
L_DUP2 = "local_9999aaaa-0000-4000-8000-000000000015"
S_DUP1 = "91919191-0000-4000-8000-000000000016"
S_DUP2 = "92929292-0000-4000-8000-000000000017"

RAMO = "ramo-condiviso-x"
ID_DRIVE_ALFA = "drive-alfa-1"
ID_DRIVE_BETA = "drive-beta-1"
ID_DRIVE_COMUNE = "drive-comune-1"


def _codifica(p) -> str:
    """Come Claude Code codifica una cartella (senza importare il pacchetto:
    la prova deve poter costruire le stesse fixture anche sul commit di
    base, dove `plancia.compartimenti` non esiste)."""
    return re.sub(r"[^A-Za-z0-9]", "-", str(p))


class Esito:
    def __init__(self, rc, out, err, secondi):
        self.rc, self.out, self.err, self.secondi = rc, out, err, secondi
        self.deny = None
        try:
            d = json.loads(out)
            self.deny = d["hookSpecificOutput"]
        except Exception:  # noqa: BLE001
            pass

    @property
    def negato(self) -> bool:
        return bool(self.deny and self.deny.get("permissionDecision") == "deny"
                    and self.rc == 0)

    @property
    def motivo(self) -> str:
        return (self.deny or {}).get("permissionDecisionReason", "")

    @property
    def ammesso(self) -> bool:
        return self.rc == 0 and self.out == "" and self.err == ""

    def __repr__(self):
        return f"rc={self.rc} out={self.out[:200]!r} err={self.err[:200]!r}"


class Ambiente:
    """Le cartelle finte e il modo di chiamare il guardiano."""

    def __init__(self):
        self.radice = Path(os.path.realpath(tempfile.mkdtemp(prefix="plancia-prova-guardiano-")))
        r = self.radice
        self.home, self.dati, self.claude = r / "home", r / "dati", r / "claude"
        self.alfa1, self.alfa2 = r / "alfa-uno", r / "alfa-due"
        self.beta1 = r / "beta-uno"
        # un albero che contiene una cartella di alfa e NIENTE del manifesto:
        # serve a provare da sola la regola "la ricerca include una cartella
        # di un nominato"
        self.albero = r / "albero"
        self.alfa3 = self.albero / "alfa-tre"
        self.comune = r / "comune"
        self.condiviso = self.comune / "condiviso"
        # due alberi isolati, ognuno con UN solo divieto di config (fuori dal
        # manifesto): uno letterale e uno con un glob. Servono a vedere rossi,
        # separatamente, i due rami "la ricerca include un percorso vietato".
        self.albero_lett = r / "albero-lett"
        self.albero_glob = r / "albero-glob"
        for d in (self.home, self.dati, self.claude / "projects", self.alfa1,
                  self.alfa2, self.alfa3, self.beta1, self.condiviso,
                  self.condiviso / "repo", self.albero_lett / "lett-vietato",
                  self.albero_glob):
            d.mkdir(parents=True, exist_ok=True)
        (self.condiviso / "repo" / "README").write_text("repo comune", "utf-8")
        (self.condiviso / "PR-7.md").write_text("pr comune", "utf-8")
        (self.albero_lett / "lett-vietato" / "f.txt").write_text("x", "utf-8")
        (self.albero_lett / "libero.txt").write_text("x", "utf-8")
        (self.albero_glob / "GLOB-uno.txt").write_text("x", "utf-8")
        (self.albero_glob / "libero.txt").write_text("x", "utf-8")
        (self.alfa1 / "segreto.txt").write_text("dentro alfa", "utf-8")
        (self.alfa1 / "sotto").mkdir()
        (self.alfa1 / "sotto" / "f.txt").write_text("x", "utf-8")
        (self.alfa2 / "due.txt").write_text("x", "utf-8")
        (self.beta1 / "b.txt").write_text("dentro beta", "utf-8")
        (self.comune / "nota.txt").write_text("nota comune", "utf-8")
        (self.condiviso / "libero.txt").write_text("non vietato", "utf-8")
        self.progetto = self.comune / "progetto"
        self.progetto.mkdir()
        (self.progetto / "p.txt").write_text("progetto comune", "utf-8")
        self.manifesto = r / "manifesto.txt"
        self.scrivi_manifesto(self.righe_manifesto())

    # -- manifesto e config ------------------------------------------------
    def righe_manifesto(self):
        c = self.condiviso
        return [f"{c}/repo", f"{c}/out-1", f"{c}/PR-*", f"{c}/NOTA-X.md",
                f"{c}/*TEAM*", "*.segreto"]

    def scrivi_manifesto(self, righe):
        self.manifesto.write_text(
            "# lavoro comune ancora nell'albero del predefinito\n\n"
            + "\n".join(righe) + "\n", "utf-8")

    def config(self, modo="bloccante", **extra):
        cfg = {"guardiano": modo, "compartimenti": {
            "alfa": {"cartelle": [str(self.alfa1), str(self.alfa2), str(self.alfa3)],
                     "sessioni": [S_ALFA], "drive_ids": [ID_DRIVE_ALFA]},
            "beta": {"cartelle": [str(self.beta1)], "sessioni": [S_BETA],
                     "drive_ids": [ID_DRIVE_BETA]},
            "predefinito": {"manifesto_divieti": str(self.manifesto),
                            "divieti": [str(self.comune / "riservato"),
                                        str(self.albero_lett / "lett-vietato"),
                                        str(self.albero_glob / "GLOB-*")],
                            "comandi_vietati": [RAMO]}}}
        cfg.update(extra)
        return cfg

    def scrivi_config(self, cfg):
        testo = cfg if isinstance(cfg, str) else json.dumps(cfg, indent=2)
        (self.dati / "config.json").write_text(testo, "utf-8")

    def togli_config(self):
        for f in ("config.json", "compartimenti.ultima-valida.json",
                  "guardiano.log", "guardiano.log.1",
                  "guardiano.config-illeggibile"):
            try:
                (self.dati / f).unlink()
            except OSError:
                pass

    # -- chiamare il guardiano --------------------------------------------
    def env(self):
        e = {"PLANCIA_HOME": str(self.dati),
             "CLAUDE_CONFIG_DIR": str(self.claude),
             "PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "C.UTF-8"}
        # su Windows la casa e' USERPROFILE, e un Python figlio senza SYSTEMROOT non
        # parte; su macOS e Linux queste due righe tornano `{"HOME": ...}` e basta
        _finti.casa_finta(e, self.home)
        if _finti.WIN:
            e["PATH"] = os.environ.get("PATH", "")
        _finti.variabili_di_sistema(e)
        return e

    def esegui_testo(self, testo, interprete=None, env=None):
        t0 = time.time()
        p = subprocess.run([interprete or PYTHON, str(GUARDIANO)],
                           input=testo, capture_output=True,
                           env=env if env is not None else self.env(),
                           timeout=60)
        return Esito(p.returncode, p.stdout.decode("utf-8", "replace"),
                     p.stderr.decode("utf-8", "replace"), time.time() - t0)

    def chiama(self, payload, env=None):
        return self.esegui_testo(json.dumps(payload).encode("utf-8"), env=env)

    def trascrizione(self, aperta_in, sid, madre=None, agente="a1", workflows=False):
        base = self.claude / "projects" / _codifica(aperta_in)
        if madre:
            sotto = base / madre / "subagents"
            if workflows:
                sotto = sotto / "workflows" / "w1"
            return str(sotto / f"agent-{agente}.jsonl")
        return str(base / f"{sid}.jsonl")

    def pl(self, tool, ti, sid=S_COMUNE, aperta_in=None, cwd=None, madre=None,
           workflows=False):
        """Il payload di un PreToolUse. `aperta_in`: la cartella in cui la
        sessione e' stata aperta (da cui il transcript_path); `cwd`: dove si
        trova adesso (di norma la stessa)."""
        aperta = aperta_in or self.comune
        tp = self.trascrizione(aperta, sid, madre, workflows=workflows)
        if madre:
            # il guardiano crede all'id della madre solo se il transcript del
            # subagente esiste davvero e la madre ha il suo: qui esistono
            Path(tp).parent.mkdir(parents=True, exist_ok=True)
            Path(tp).write_text("{}\n", "utf-8")
            mamma = self.claude / "projects" / _codifica(aperta) / f"{madre}.jsonl"
            mamma.parent.mkdir(parents=True, exist_ok=True)
            mamma.write_text("{}\n", "utf-8")
        return {"session_id": sid, "cwd": str(cwd or aperta),
                "transcript_path": tp,
                "hook_event_name": "PreToolUse", "tool_name": tool,
                "tool_input": ti}

    def registro(self):
        p = self.dati / "guardiano.log"
        if not p.exists():
            return []
        return [json.loads(x) for x in p.read_text("utf-8").splitlines() if x.strip()]

    def registra_app(self, local, cli, cwd, titolo, origine=None):
        """Una voce del registro dell'app, nella HOME temporanea."""
        d = (self.home / "Library" / "Application Support" / "Claude"
             / "claude-code-sessions" / "u1" / "u2")
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{local}.json").write_text(json.dumps({
            "sessionId": local, "cliSessionId": cli, "cwd": str(cwd),
            "originCwd": str(origine or cwd), "title": titolo}), "utf-8")

    def crea_db(self):
        """Il database di Plancia con lo schema VERO (lo crea `store`, in un
        sottoprocesso con PLANCIA_HOME finto) e le sessioni di prova."""
        righe = [
            (S_DB_ALFA, str(self.alfa1), "Sessione di alfa"),
            (S_DB_COMUNE, str(self.comune), "Sessione comune"),
        ]
        codice = (
            "from plancia import store\n"
            "c = store.connect(); store.init_db(c)\n"
            "for r in %r:\n"
            "    c.execute('INSERT INTO sessions(session_id, cwd, title) VALUES(?,?,?)', r)\n"
            "c.commit()\n" % (righe,))
        e = dict(self.env())
        e["PYTHONPATH"] = str(RADICE)
        p = subprocess.run([sys.executable, "-c", codice], env=e, cwd=str(RADICE),
                           capture_output=True, timeout=60)
        return p.returncode == 0

    def chiudi(self):
        shutil.rmtree(self.radice, ignore_errors=True)


def _testo(p: Path) -> str:
    """Il testo di un file, o "" se non c'e' (sul commit di base la copia
    dell'ultima config valida non esiste: la prova deve diventare rossa, non
    andare in errore)."""
    try:
        return p.read_text("utf-8")
    except OSError:
        return ""


def _mtime(p: Path) -> int:
    try:
        return p.stat().st_mtime_ns
    except OSError:
        return -1


def _crea_symlink(dest: Path, src: Path) -> bool:
    try:
        dest.symlink_to(src, target_is_directory=src.is_dir())
        return True
    except OSError:
        return False


def _percorsi_esempio(riga: str, base: Path):
    """Da una riga di manifesto, i percorsi concreti che devono risultare
    negati: il percorso stesso, e uno sotto (se non e' un nome con glob)."""
    riga = riga.strip()
    if "/" not in riga:  # un nome con glob: qualunque file che combacia
        nome = riga.replace("*", "dato")
        return [str(base / "qualsiasi" / nome)]
    concreto = riga.replace("*", "x")
    return [concreto, concreto + "/dentro/f.txt"]


def _non_negati_dal_manifesto(amb: Ambiente, righe):
    """I percorsi di esempio delle `righe` che il predefinito NON si vede
    negare. E' la verifica che le prove del manifesto usano: se compare un
    percorso della linea comune che il manifesto non elenca, sta qui."""
    aperti = []
    for riga in righe:
        for p in _percorsi_esempio(riga, amb.comune):
            r = amb.chiama(amb.pl("Read", {"file_path": p}))
            if not r.negato:
                aperti.append(p)
    return aperti


# --------------------------------------------------------------------------
# gruppi di prove
# --------------------------------------------------------------------------

def _prove_nominato(prova, a: Ambiente):
    """Prova 1: sessione di un nominato."""
    a.scrivi_config(a.config())
    dentro = str(a.alfa1 / "segreto.txt")
    fuori = str(a.comune / "nota.txt")

    def alfa(tool, ti, **kw):
        kw.setdefault("sid", S_ALFA_LIBERA)
        return a.chiama(a.pl(tool, ti, aperta_in=a.alfa1, **kw))

    r = alfa("Read", {"file_path": fuori})
    prova("1: alfa, Read fuori dalle sue cartelle: negato", r.negato, repr(r))
    prova("1: il motivo dice il compartimento e il percorso negato",
          "alfa" in r.motivo and fuori in r.motivo, r.motivo)
    r = alfa("Read", {"file_path": "/opt/altro/dato.txt"})
    prova("1: ...e per un percorso che non e' di un nominato ne' temporaneo dice che appartiene "
          "al predefinito", r.negato and "appartiene a predefinito" in r.motivo, r.motivo)
    r = alfa("Read", {"file_path": dentro})
    prova("1: alfa, Read dentro la sua cartella: ammesso", r.ammesso, repr(r))
    prova("1: alfa, Read nella seconda cartella di alfa: ammesso",
          alfa("Read", {"file_path": str(a.alfa2 / "due.txt")}).ammesso)
    prova("1: alfa, Read nella cartella di beta: negato, appartiene a beta",
          (lambda x: x.negato and "appartiene a beta" in x.motivo)(
              alfa("Read", {"file_path": str(a.beta1 / "b.txt")})))
    prova("1: alfa, Write fuori: negato",
          alfa("Write", {"file_path": fuori, "content": "x"}).negato)
    prova("1: alfa, Edit dentro: ammesso",
          alfa("Edit", {"file_path": dentro, "old_string": "a", "new_string": "b"}).ammesso)
    prova("1: alfa, NotebookEdit fuori (notebook_path): negato",
          alfa("NotebookEdit", {"notebook_path": str(a.comune / "n.ipynb")}).negato)
    prova("1: alfa, lista `files` con un percorso fuori: negata",
          alfa("SendUserFile", {"files": [dentro, fuori]}).negato)
    prova("1: alfa, lista `files` tutta dentro: ammessa",
          alfa("SendUserFile", {"files": [dentro]}).ammesso)
    prova("1: alfa, percorso relativo risolto sulla cwd: dentro ammesso",
          alfa("Read", {"file_path": "segreto.txt"}).ammesso)
    prova("1: alfa, percorso relativo con .. che esce: negato",
          alfa("Read", {"file_path": "../comune/nota.txt"}).negato)
    prova("1: alfa, ~ risolto sulla HOME (fuori dai permessi): negato",
          alfa("Read", {"file_path": "~/appunti.txt"}).negato)
    # Grep e Glob
    prova("1: alfa, Grep con path fuori: negato",
          alfa("Grep", {"pattern": "x", "path": str(a.comune)}).negato)
    prova("1: alfa, Grep senza path (cwd dentro alfa): ammesso",
          alfa("Grep", {"pattern": "x"}).ammesso)
    prova("1: alfa, Grep sull'antenato delle sue cartelle: negato",
          alfa("Grep", {"pattern": "x", "path": str(a.radice)}).negato)
    prova("1: alfa, Glob assoluto fuori: negato",
          alfa("Glob", {"pattern": f"{a.comune}/**/*.txt"}).negato)
    prova("1: alfa, Glob relativo dentro (path dentro): ammesso",
          alfa("Glob", {"pattern": "**/*.txt", "path": str(a.alfa1)}).ammesso)
    # l'elenco neutro
    prova("1: alfa, binari di sistema (/usr/bin/env): ammesso",
          alfa("Read", {"file_path": "/usr/bin/env"}).ammesso)
    prova("1: alfa, ~/.local/bin (neutro): ammesso",
          alfa("Read", {"file_path": "~/.local/bin/qualcosa"}).ammesso)
    prova("1: alfa, /tmp NON e' neutro (un posto per passarsi file): negato",
          alfa("Write", {"file_path": "/tmp/passaggio.txt", "content": "x"}).negato)
    # la cartella temporanea di Claude Code (`/private/tmp/claude-<uid>`) c'e' solo su
    # macOS e Linux: su Windows non esiste ne' `os.getuid` ne' quella cartella
    uid = os.getuid() if hasattr(os, "getuid") else None
    scratch = f"/private/tmp/claude-{uid}/{_codifica(a.alfa1)}/{S_ALFA_LIBERA}/scratchpad/x.txt"
    altro_scratch = f"/private/tmp/claude-{uid}/{_codifica(a.alfa1)}/{S_COMUNE}/scratchpad/x.txt"
    prova("1: alfa, la propria cartella di sessione in /private/tmp/claude-<uid>: ammessa",
          uid is None or alfa("Write", {"file_path": scratch, "content": "x"}).ammesso,
          "saltato: su Windows non c'e' ne' os.getuid ne' /private/tmp/claude-<uid>"
          if uid is None else "")
    prova("1: alfa, la cartella di sessione di un'ALTRA sessione: negata",
          uid is None or alfa("Write", {"file_path": altro_scratch, "content": "x"}).negato,
          "saltato: su Windows non c'e' ne' os.getuid ne' /private/tmp/claude-<uid>"
          if uid is None else "")
    proj = a.claude / "projects" / _codifica(a.alfa1)
    prova("1: alfa, la propria cartella in ~/.claude/projects (memoria): ammessa",
          alfa("Read", {"file_path": str(proj / "memory" / "MEMORY.md")}).ammesso)
    prova("1: alfa, la cartella di progetto di un'altra cartella: negata",
          alfa("Read", {"file_path": str(a.claude / "projects" / _codifica(a.comune) / "x.jsonl")}).negato)
    # Bash
    prova("1: alfa, Bash `cat` su un file fuori: negato",
          alfa("Bash", {"command": f"cat {fuori}"}).negato)
    prova("1: alfa, Bash `cat` su un file dentro: ammesso",
          alfa("Bash", {"command": f"cat {dentro}"}).ammesso)
    prova("1: alfa, Bash con 2>/dev/null e un percorso dentro: ammesso",
          alfa("Bash", {"command": f"ls -la {a.alfa1} 2>/dev/null | head"}).ammesso)
    prova("1: alfa, Bash con un URL (https://host/a/b): ammesso",
          alfa("Bash", {"command": "curl -s https://esempio.test/a/b/c"}).ammesso)
    prova("1: alfa, Bash con sed 's/a/b/' non scambia l'espressione per un percorso",
          alfa("Bash", {"command": f"sed -i 's/a/b/' {dentro}"}).ammesso)
    prova("1: alfa, Bash con il percorso fuori dentro python -c: negato",
          alfa("Bash", {"command": f"python3 -c \"print(open('{fuori}').read())\""}).negato)
    prova("1: alfa, Bash con il percorso dopo una pipe e un ';': negato",
          alfa("Bash", {"command": f"echo ok; ls {a.comune}"}).negato)
    prova("1: alfa, Bash con --opzione=/percorso fuori: negato",
          alfa("Bash", {"command": f"tar --directory={a.comune} -cf x.tar ."}).negato)
    prova("1: alfa, Bash `cd ..` (esce dalla cartella): negato",
          alfa("Bash", {"command": "cd .. && ls"}).negato)
    prova("1: alfa, Bash con virgolette che non tornano (ripiego su split): "
          "il percorso fuori si vede lo stesso",
          alfa("Bash", {"command": f"cat <<EOF\ndon't\nEOF\ncat {fuori}"}).negato)
    # Un nominato per id e' aperto FUORI dalle sue cartelle: la cwd fuori dai
    # permessi e' un percorso toccato da ogni comando (le parole senza barre,
    # `.` e i glob di shell leggono la cwd senza nominarla).
    for cmd in ("cat nota.txt", "ls", "grep -rn comune .", "head -5 *", "echo ciao && ls"):
        r = a.chiama(a.pl("Bash", {"command": cmd}, sid=S_ALFA, aperta_in=a.comune))
        prova(f"1: alfa con la cwd fuori dai permessi, Bash `{cmd}`: negato, "
              "con l'indicazione di change_directory",
              r.negato and "change_directory" in r.motivo and str(a.alfa1) in r.motivo, repr(r))
    for cmd in ("cat segreto.txt", "ls", "grep -rn x .", "head -5 segreto.txt"):
        r = alfa("Bash", {"command": cmd})
        prova(f"1: alfa con la cwd dentro le sue cartelle, Bash `{cmd}`: ammesso", r.ammesso, repr(r))
    r = a.chiama(a.pl("Bash", {"command": "cat due.txt"}, sid=S_ALFA, aperta_in=a.comune, cwd=a.alfa2))
    prova("1: alfa aperta fuori ma spostata con change_directory in una sua cartella: "
          "Bash ammesso", r.ammesso, repr(r))
    r = a.chiama(a.pl("mcp__ccd_directory__change_directory", {"path": str(a.alfa2)},
                      sid=S_ALFA, aperta_in=a.comune))
    prova("1: ...e change_directory verso una sua cartella da una cwd fuori: ammesso "
          "(la via per rientrare non e' bloccata)", r.ammesso, repr(r))
    prova("1: alfa, Bash senza percorsi: ammesso",
          alfa("Bash", {"command": "echo ciao && python3 --version"}).ammesso)
    # id di sessione dichiarato: alfa anche se aperta altrove
    r = a.chiama(a.pl("Read", {"file_path": fuori}, sid=S_ALFA, aperta_in=a.comune))
    prova("1: una sessione in alfa.sessioni aperta nella cartella del predefinito e' "
          "comunque alfa: Read del file comune negato", r.negato, repr(r))
    memoria = str(a.claude / "projects" / _codifica(a.comune) / "memory" / "MEMORY.md")
    r = a.chiama(a.pl("Read", {"file_path": memoria}, sid=S_ALFA, aperta_in=a.comune))
    prova("1: ...la `memory` della cartella che condivide con il predefinito NON e' sua: "
          "Read negata (canale 7: leggerebbe i ricordi del predefinito)", r.negato, repr(r))
    r = a.chiama(a.pl("Write", {"file_path": memoria, "content": "x"}, sid=S_ALFA, aperta_in=a.comune))
    prova("1: ...e Write in quella `memory` negata (un MEMORY.md che il predefinito "
          "caricherebbe da solo)", r.negato, repr(r))
    prova("1: ...la propria cartella di sessione (<sid>/subagents/...) resta ammessa",
          a.chiama(a.pl("Read", {"file_path": str(a.claude / "projects" / _codifica(a.comune)
                                                  / S_ALFA / "subagents" / "agent-q.jsonl")},
                        sid=S_ALFA, aperta_in=a.comune)).ammesso)
    prova("1: ...ma le trascrizioni delle ALTRE sessioni della stessa cartella no",
          a.chiama(a.pl("Read", {"file_path": str(a.claude / "projects" / _codifica(a.comune) / "altra.jsonl")},
                        sid=S_ALFA, aperta_in=a.comune)).negato)
    prova("1: ...la sua trascrizione si',",
          a.chiama(a.pl("Read", {"file_path": str(a.claude / "projects" / _codifica(a.comune) / f"{S_ALFA}.jsonl")},
                        sid=S_ALFA, aperta_in=a.comune)).ammesso)
    # il cwd da solo non libera un nominato (un cd lo sposta)
    r = a.chiama(a.pl("Read", {"file_path": fuori}, sid=S_ALFA_LIBERA,
                      aperta_in=a.alfa1, cwd=a.comune))
    prova("1: una sessione aperta in alfa con cwd spostato fuori (cd) resta alfa: negato",
          r.negato, repr(r))
    # ...e il cwd dentro alfa aggiunge l'appartenenza
    r = a.chiama(a.pl("Read", {"file_path": fuori}, sid=S_COMUNE,
                      aperta_in=a.comune, cwd=a.alfa1))
    prova("1: una sessione del predefinito con cwd dentro alfa e' trattata da alfa "
          "(prudenza): Read del file comune negato", r.negato, repr(r))
    # due compartimenti insieme: i permessi si intersecano
    ambi = a.pl("Read", {"file_path": dentro}, sid=S_ALFA, aperta_in=a.alfa1, cwd=a.beta1)
    prova("1: una sessione che sembra di alfa E di beta rispetta i permessi di entrambi: "
          "il file di alfa e' negato", a.chiama(ambi).negato)
    # cartella sorella con lo stesso prefisso: in dubbio si confina
    sorella = a.radice / "alfa-uno-sorella"
    sorella.mkdir()
    r = a.chiama(a.pl("Read", {"file_path": fuori}, sid="s-sorella", aperta_in=sorella))
    prova("1: una cartella sorella con lo stesso prefisso di alfa (la codifica perde la "
          "differenza) si confina per prudenza", r.negato, repr(r))


def _prove_predefinito(prova, a: Ambiente):
    """Prova 2: il predefinito verso le cartelle dei nominati."""
    a.scrivi_config(a.config())
    dentro_alfa = str(a.alfa1 / "segreto.txt")

    def pred(tool, ti, **kw):
        kw.setdefault("sid", S_COMUNE)
        return a.chiama(a.pl(tool, ti, **kw))

    r = pred("Read", {"file_path": dentro_alfa})
    prova("2: predefinito, Read in una cartella di alfa: negato", r.negato, repr(r))
    prova("2: il motivo nomina il compartimento della sessione e quello proprietario",
          "compartimento predefinito" in r.motivo and "appartiene a alfa" in r.motivo, r.motivo)
    prova("2: predefinito, Read in beta: negato",
          pred("Read", {"file_path": str(a.beta1 / "b.txt")}).negato)
    prova("2: predefinito, Read di un file comune normale: ammesso",
          pred("Read", {"file_path": str(a.comune / "nota.txt")}).ammesso)
    prova("2: predefinito, Read di un file vicino ma non vietato (condiviso/libero): ammesso",
          pred("Read", {"file_path": str(a.condiviso / "libero.txt")}).ammesso)
    prova("2: predefinito, Grep con path dentro alfa: negato",
          pred("Grep", {"pattern": "x", "path": str(a.alfa1)}).negato)
    prova("2: predefinito, Grep con path in una cartella comune senza divieti sotto: ammesso",
          pred("Grep", {"pattern": "x", "path": str(a.progetto)}).ammesso)
    r = pred("Grep", {"pattern": "x", "path": str(a.comune)})
    prova("2: predefinito, Grep sulla cartella comune che CONTIENE percorsi del manifesto: "
          "negato (la ricerca li include)", r.negato and "restringi" in r.motivo, repr(r))
    r = pred("Grep", {"pattern": "x", "path": str(a.radice)})
    prova("2: predefinito, Grep che parte da un antenato di alfa (la ricerca la include): "
          "negato, con l'indicazione di restringere", r.negato and "restringi" in r.motivo, repr(r))
    r = pred("Grep", {"pattern": "x", "path": str(a.albero)})
    prova("2: predefinito, Grep da un albero che contiene SOLO una cartella di alfa: negato "
          "(la ricerca include la cartella di un nominato)",
          r.negato and "include" in r.motivo and "alfa-tre" in r.motivo, repr(r))
    r = pred("Grep", {"pattern": "x", "path": str(a.albero_lett)})
    prova("2: predefinito, Grep da un albero con SOLO un divieto letterale (config `divieti`) "
          "sotto: negato (ramo letterale della regola)",
          r.negato and "restringi" in r.motivo, repr(r))
    r = pred("Grep", {"pattern": "x", "path": str(a.albero_glob)})
    prova("2: predefinito, Grep che parte proprio dal prefisso letterale di un divieto con glob "
          "(<albero>/GLOB-*): negato, include i file che combaciano (ramo dei glob)",
          r.negato and "restringi" in r.motivo, repr(r))
    prova("2: ...anche con `glob` di Grep: la ricerca in quella cartella e' negata",
          pred("Grep", {"pattern": "x", "path": str(a.albero_glob), "glob": "GLOB-*"}).negato)
    prova("2: ...e Glob che parte da quella cartella",
          pred("Glob", {"pattern": "*.txt", "path": str(a.albero_glob)}).negato)
    prova("2: ...ma Read di un file della stessa cartella che non combacia col modello: ammesso",
          pred("Read", {"file_path": str(a.albero_glob / "libero.txt")}).ammesso)
    prova("2: ...e Read di uno che combacia (GLOB-uno.txt): negato",
          pred("Read", {"file_path": str(a.albero_glob / "GLOB-uno.txt")}).negato)
    prova("2: predefinito, Read nell'albero con il divieto letterale, fuori dal divieto: ammesso",
          pred("Read", {"file_path": str(a.albero_lett / "libero.txt")}).ammesso)
    prova("2: predefinito, Glob relativo da quell'albero: negato",
          pred("Glob", {"pattern": "**/*.py", "path": str(a.albero)}).negato)
    prova("2: predefinito, Read di un file dell'albero fuori da alfa-tre: ammesso",
          pred("Read", {"file_path": str(a.albero / "altro.txt")}).ammesso)
    prova("2: predefinito, Grep SENZA path con cwd antenato di alfa: negato",
          pred("Grep", {"pattern": "x"}, aperta_in=a.comune, cwd=a.radice).negato)
    prova("2: predefinito, Grep SENZA path con cwd in una cartella senza divieti sotto: ammesso",
          pred("Grep", {"pattern": "x"}, aperta_in=a.progetto).ammesso)
    prova("2: predefinito, Glob assoluto in alfa: negato",
          pred("Glob", {"pattern": f"{a.alfa1}/**/*.txt"}).negato)
    prova("2: predefinito, Glob relativo in una cartella senza divieti sotto: ammesso",
          pred("Glob", {"pattern": "*.txt", "path": str(a.progetto)}).ammesso)
    prova("2: predefinito, Bash `cat` su un file di alfa: negato",
          pred("Bash", {"command": f"cat {dentro_alfa}"}).negato)
    prova("2: predefinito, Bash `cd <alfa> && ls`: negato",
          pred("Bash", {"command": f"cd {a.alfa1} && ls"}).negato)
    prova("2: predefinito, Bash con percorso relativo (cwd comune, ../alfa-uno): negato",
          pred("Bash", {"command": "git -C ../alfa-uno log"}).negato)
    prova("2: predefinito, Bash `cd alfa-uno` (nome senza barre) da una cwd che sta sopra: negato",
          pred("Bash", {"command": "cd alfa-uno && ls"}, aperta_in=a.comune, cwd=a.radice).negato)
    prova("2: predefinito, Bash `git -C alfa-uno log` da una cwd che sta sopra: negato",
          pred("Bash", {"command": "git -C alfa-uno log"}, aperta_in=a.comune, cwd=a.radice).negato)
    prova("2: predefinito, Bash `ls comune` da una cwd che sta sopra (non e' vietata, `ls` non e' ricorsivo): ammesso",
          pred("Bash", {"command": "ls comune"}, aperta_in=a.comune, cwd=a.radice).ammesso)
    # Bash ricorsivo: lo stesso incidente ordinario di Grep e Glob, dalla shell
    for cmd in ("grep -rn x .", "grep -R x", "rg x", "find . -name x", "ls -R", "tree",
                "tar -cf x.tar condiviso", "rsync -a condiviso/ dest/", "git grep x",
                "cp -r condiviso dest", "cd comune 2>/dev/null; grep -rn x ."):
        r = pred("Bash", {"command": cmd}, aperta_in=a.comune)
        prova(f"2: predefinito dalla cartella comune, Bash `{cmd}`: negato (la ricerca "
              "include un percorso vietato)", r.negato, repr(r))
    for cmd in ("cat condiviso/*", "head -3 condiviso/PR-*", "cat condiviso/repo/README"):
        r = pred("Bash", {"command": cmd}, aperta_in=a.comune)
        prova(f"2: predefinito, Bash `{cmd}` (il glob di shell si espande sul disco): negato",
              r.negato, repr(r))
    for cmd in ("cat nota.txt", "grep x nota.txt", "ls condiviso", "echo find tree",
                "grep -rn x progetto", "ls -R progetto", "find progetto -name x"):
        r = pred("Bash", {"command": cmd}, aperta_in=a.comune)
        prova(f"2: predefinito dalla cartella comune, Bash `{cmd}`: ammesso", r.ammesso, repr(r))
    for cmd in ("grep -rn x .", "rg x", "find . -name x", "ls -R", "cat *"):
        r = pred("Bash", {"command": cmd}, aperta_in=a.progetto)
        prova(f"2: predefinito da una cartella senza divieti sotto, Bash `{cmd}`: ammesso",
              r.ammesso, repr(r))
    prova("2: predefinito, Bash con un nome di file vietato da un modello di nome (dato.segreto): negato",
          pred("Bash", {"command": "cat dato.segreto"}, aperta_in=a.progetto).negato)
    prova("2: predefinito, Bash con python -c su un file di alfa: negato",
          pred("Bash", {"command": f"python3 -c \"open('{dentro_alfa}')\""}).negato)
    prova("2: predefinito, Bash sul comune con 2>/dev/null: ammesso",
          pred("Bash", {"command": f"cat {a.comune}/nota.txt 2>/dev/null"}).ammesso)
    prova("2: predefinito, Bash senza percorsi: ammesso",
          pred("Bash", {"command": "echo ciao"}).ammesso)
    prova("2: predefinito, Write in alfa: negato",
          pred("Write", {"file_path": dentro_alfa, "content": "x"}).negato)
    # la relazione e' simmetrica fra due nominati e verso il predefinito
    prova("2: beta verso alfa: negato",
          a.chiama(a.pl("Read", {"file_path": dentro_alfa}, sid=S_BETA, aperta_in=a.beta1)).negato)
    # canale 9: rami git condivisi
    r = pred("Bash", {"command": f"git log --all {RAMO}"})
    prova("comandi_vietati: il predefinito che nomina un ramo condiviso e' negato",
          r.negato and RAMO in r.motivo, repr(r))
    prova("comandi_vietati: anche dentro un percorso di git (origin/<ramo>:file)",
          pred("Bash", {"command": f"git show origin/{RAMO}:README"}).negato)
    prova("comandi_vietati: un comando git senza quel ramo passa",
          pred("Bash", {"command": "git log --oneline -5"}).ammesso)
    prova("comandi_vietati: valgono solo per il predefinito (un nominato non e' toccato)",
          a.chiama(a.pl("Bash", {"command": f"git log {RAMO}"}, sid=S_ALFA_LIBERA,
                        aperta_in=a.alfa1)).ammesso)


def _prove_subagenti(prova, a: Ambiente):
    """Prova 3: un subagente ha lo stesso esito della sua sessione madre."""
    a.scrivi_config(a.config())
    fuori = str(a.comune / "nota.txt")
    dentro = str(a.alfa1 / "segreto.txt")
    for etichetta, sid, wf in (("session_id = id madre", S_MADRE, False),
                               ("session_id = id del subagente", "agent-a1", False),
                               ("transcript in subagents/workflows/", "agent-a1", True)):
        r = a.chiama(a.pl("Read", {"file_path": fuori}, sid=sid, aperta_in=a.alfa1,
                          cwd=a.comune, madre=S_MADRE, workflows=wf))
        prova(f"3: subagente di una sessione alfa ({etichetta}): Read fuori negato",
              r.negato, repr(r))
        r = a.chiama(a.pl("Read", {"file_path": dentro}, sid=sid, aperta_in=a.alfa1,
                          cwd=a.comune, madre=S_MADRE, workflows=wf))
        prova(f"3: subagente di una sessione alfa ({etichetta}): Read dentro ammesso",
              r.ammesso, repr(r))
    # la madre e' alfa solo per id, aperta nella cartella del predefinito
    cfg = a.config()
    cfg["compartimenti"]["alfa"]["sessioni"].append(S_MADRE)
    a.scrivi_config(cfg)
    r = a.chiama(a.pl("Read", {"file_path": fuori}, sid="agent-b", aperta_in=a.comune,
                      madre=S_MADRE))
    prova("3: subagente la cui MADRE e' in alfa.sessioni (aperta altrove): Read fuori negato "
          "(l'id della madre si ricava dal transcript_path)", r.negato, repr(r))
    a.scrivi_config(a.config())
    r = a.chiama(a.pl("Read", {"file_path": dentro}, sid="agent-c", aperta_in=a.comune,
                      madre=S_COMUNE))
    prova("3: subagente di una sessione del predefinito: Read in alfa negato",
          r.negato, repr(r))
    r = a.chiama(a.pl("Read", {"file_path": fuori}, sid="agent-c", aperta_in=a.comune,
                      madre=S_COMUNE))
    prova("3: subagente di una sessione del predefinito: Read nel comune ammesso",
          r.ammesso, repr(r))


def _prove_sessioni_e_drive(prova, a: Ambiente):
    """Prova 6 (strumenti di sessione, nei due sensi) e strumenti del Drive."""
    ok_db = a.crea_db()
    prova("6: il database di prova (schema vero di store) si crea", ok_db)
    cfg = a.config()
    cfg["compartimenti"]["alfa"]["sessioni"].append(S_ALFA_LIBERA)
    a.scrivi_config(cfg)

    def pred(tool, ti):
        return a.chiama(a.pl(tool, ti, sid=S_COMUNE))

    def alfa(tool, ti):
        return a.chiama(a.pl(tool, ti, sid=S_ALFA, aperta_in=a.alfa1))

    ss = "mcp__ccd_session_mgmt__"
    r = pred(ss + "get_session", {"session_id": S_ALFA})
    prova("6: predefinito -> get_session di una sessione in alfa.sessioni: negato",
          r.negato and "appartiene a alfa" in r.motivo, repr(r))
    prova("6: predefinito -> list_events di una sessione alfa nota solo alla tabella (cwd in alfa): negato",
          pred(ss + "list_events", {"id": S_DB_ALFA}).negato)
    prova("6: predefinito -> send_message a una sessione alfa: negato",
          pred(ss + "send_message", {"sessionId": S_ALFA, "message": "x"}).negato)
    prova("6: predefinito -> export_transcript di una sessione alfa: negato",
          pred(ss + "export_transcript", {"session_id": S_DB_ALFA}).negato)
    prova("6: predefinito -> SendMessage (nome `to`) a una sessione alfa: negato",
          pred("SendMessage", {"to": S_ALFA, "message": "x"}).negato)
    prova("6: predefinito -> get_session di una sessione del predefinito: ammesso",
          pred(ss + "get_session", {"session_id": S_DB_COMUNE}).ammesso)
    prova("6: predefinito -> sessione sconosciuta: ammesso (come da specifica)",
          pred(ss + "get_session", {"session_id": S_IGNOTA}).ammesso)
    prova("6: predefinito -> ListAgents: ammesso", pred("ListAgents", {}).ammesso)
    prova("6: predefinito -> list_sessions senza bersaglio: ammesso (limite dichiarato)",
          pred(ss + "list_sessions", {}).ammesso)
    # nel verso opposto
    r = alfa(ss + "get_session", {"session_id": S_DB_COMUNE})
    prova("6: alfa -> get_session di una sessione del predefinito (dalla tabella): negato",
          r.negato and "appartiene a predefinito" in r.motivo, repr(r))
    prova("6: alfa -> list_events di una sessione sconosciuta: negato",
          alfa(ss + "list_events", {"session_id": S_IGNOTA}).negato)
    prova("6: alfa -> send_message alla sessione di beta: negato",
          alfa(ss + "send_message", {"session_id": S_BETA, "message": "x"}).negato)
    prova("6: alfa -> get_session della PROPRIA sessione: ammesso",
          alfa(ss + "get_session", {"session_id": S_ALFA}).ammesso)
    prova("6: alfa -> get_session di un'altra sessione di alfa (in sessioni): ammesso",
          alfa(ss + "get_session", {"session_id": S_ALFA_LIBERA}).ammesso)
    prova("6: alfa -> get_session di una sessione di alfa nota solo alla tabella: ammesso",
          alfa(ss + "get_session", {"session_id": S_DB_ALFA}).ammesso)
    prova("6: alfa -> ListAgents: negato (elenca sessioni altrui)",
          alfa("ListAgents", {}).negato)
    prova("6: alfa -> search_session_transcripts senza bersaglio: negato",
          alfa(ss + "search_session_transcripts", {"query": "x"}).negato)
    prova("6: alfa -> SendMessage a un nome non risolvibile: negato",
          alfa("SendMessage", {"to": "un-nome-qualsiasi", "message": "x"}).negato)
    # un nominato scrive ai propri subagenti
    sub = a.claude / "projects" / _codifica(a.alfa1) / S_ALFA / "subagents"
    sub.mkdir(parents=True, exist_ok=True)
    (sub / "agent-zzz.jsonl").write_text("{}", "utf-8")
    prova("6: alfa -> SendMessage a un proprio subagente (file agent-<id>.jsonl): ammesso",
          alfa("SendMessage", {"to": "zzz", "message": "x"}).ammesso)
    # Drive
    def drv(tool, ti, nominato=True):
        if nominato:
            return a.chiama(a.pl(tool, ti, sid=S_ALFA, aperta_in=a.alfa1))
        return a.chiama(a.pl(tool, ti, sid=S_COMUNE))

    letto = "mcp__uuid-finto__read_file_content"
    prova("drive: alfa, read_file_content su un id di alfa: ammesso",
          drv(letto, {"fileId": ID_DRIVE_ALFA}).ammesso)
    r = drv(letto, {"fileId": ID_DRIVE_COMUNE})
    prova("drive: alfa, read_file_content su un id NON ammesso: negato", r.negato, repr(r))
    prova("drive: alfa, su un id di beta: negato, appartiene a beta",
          (lambda x: x.negato and "appartiene a beta" in x.motivo)(drv(letto, {"fileId": ID_DRIVE_BETA})))
    prova("drive: alfa, search_files: negato (elenca tutto il Drive)",
          drv("mcp__uuid-finto__search_files", {"query": "x"}).negato)
    prova("drive: alfa, list_recent_files: negato",
          drv("mcp__uuid-finto__list_recent_files", {}).negato)
    prova("drive: alfa, create_file con parentId ammesso: ammesso",
          drv("mcp__uuid-finto__create_file", {"parentId": ID_DRIVE_ALFA, "title": "x"}).ammesso)
    prova("drive: alfa, create_file con parentId non ammesso: negato",
          drv("mcp__uuid-finto__create_file", {"parentId": ID_DRIVE_COMUNE}).negato)
    prova("drive: alfa, copy_file con un id ammesso e un parentId no: negato",
          drv("mcp__uuid-finto__copy_file", {"fileId": ID_DRIVE_ALFA, "parentId": ID_DRIVE_COMUNE}).negato)
    prova("drive: alfa, get_file_metadata senza alcun id: negato (non verificabile)",
          drv("mcp__uuid-finto__get_file_metadata", {}).negato)
    for nome in ("download_file_content", "get_file_permissions", "update_file",
                 "share_file", "trash_file"):
        prova(f"drive: alfa, {nome} su un id non ammesso: negato",
              drv(f"mcp__uuid-finto__{nome}", {"fileId": ID_DRIVE_COMUNE}).negato)
    prova("drive: predefinito, un id di alfa: negato",
          drv(letto, {"fileId": ID_DRIVE_ALFA}, nominato=False).negato)
    prova("drive: predefinito, un id qualunque non di un nominato: ammesso",
          drv(letto, {"fileId": ID_DRIVE_COMUNE}, nominato=False).ammesso)
    prova("drive: predefinito, search_files: ammesso (limite dichiarato)",
          drv("mcp__uuid-finto__search_files", {"query": "x"}, nominato=False).ammesso)
    prova("drive: uno strumento MCP che non e' del Drive non e' toccato (alfa)",
          drv("mcp__uuid-finto__altro_strumento", {"fileId": ID_DRIVE_COMUNE}).ammesso)
    a.scrivi_config(a.config(strumenti_drive=["sposta_file"]))
    prova("drive: `strumenti_drive` aggiunge un nome: alfa, sposta_file su id non ammesso: negato",
          drv("mcp__uuid-finto__sposta_file", {"fileId": ID_DRIVE_COMUNE}).negato)


def _prove_sessioni_app(prova, a: Ambiente):
    """Gli strumenti di sessione con gli id che l'app manda DAVVERO: `local_<uuid>`
    (diverso dal `cliSessionId`), nomi, `self` e `main`. Un registro dell'app
    finto nella HOME temporanea li risolve. Senza il registro tutti i bersagli
    risultano sconosciuti: e' quello che la prova 6 con id uguali al session_id
    non poteva vedere."""
    a.registra_app(L_ALFA, S_REG_ALFA, a.alfa1, "Lavoro alfa")
    a.registra_app(L_ALFA_ID, S_ALFA, a.comune, "Alfa per id")   # alfa solo per id
    a.registra_app(L_COMUNE, S_COMUNE, a.comune, "Principale")
    a.registra_app(L_COMUNE2, S_REG_COMUNE2, a.comune, "Altra comune")
    a.registra_app(L_BETA, S_BETA, a.beta1, "Lavoro beta")
    a.registra_app(L_CFG, S_CFG, a.comune, "Scritta in config")
    a.registra_app(L_DUP1, S_DUP1, a.alfa1, "Duplicato")
    a.registra_app(L_DUP2, S_DUP2, a.comune, "Duplicato")
    cfg = a.config()
    cfg["compartimenti"]["alfa"]["sessioni"] = [S_ALFA, L_CFG, "local_zzzz0000-0000-4000-8000-000000000099"]
    a.scrivi_config(cfg)
    ss = "mcp__ccd_session_mgmt__"

    def pred(tool, ti, **kw):
        return a.chiama(a.pl(tool, ti, sid=S_COMUNE, **kw))

    def alfa(tool, ti, **kw):
        return a.chiama(a.pl(tool, ti, sid=S_ALFA, aperta_in=a.alfa1, **kw))

    r = pred(ss + "get_session", {"session_id": L_ALFA})
    prova("6-app: predefinito -> get_session di un id `local_` di alfa (per cartella): negato",
          r.negato and "appartiene a alfa" in r.motivo, repr(r))
    prova("6-app: predefinito -> list_events di un id `local_` il cui cliSessionId e' in alfa.sessioni: negato",
          pred(ss + "list_events", {"id": L_ALFA_ID}).negato)
    prova("6-app: predefinito -> send_message a un id `local_` di beta: negato",
          pred(ss + "send_message", {"sessionId": L_BETA, "message": "x"}).negato)
    prova("6-app: predefinito -> export_transcript di un id `local_` di alfa: negato",
          pred(ss + "export_transcript", {"session_id": L_ALFA}).negato)
    prova("6-app: predefinito -> SendMessage a un NOME (il titolo) di una sessione di alfa: negato",
          pred("SendMessage", {"to": "Lavoro alfa", "message": "x"}).negato)
    prova("6-app: ...il titolo senza badare alle maiuscole",
          pred("SendMessage", {"to": "lavoro ALFA", "message": "x"}).negato)
    prova("6-app: predefinito -> get_session di un id `local_` del predefinito: ammesso",
          pred(ss + "get_session", {"session_id": L_COMUNE2}).ammesso)
    prova("6-app: predefinito -> SendMessage a un nome del predefinito: ammesso",
          pred("SendMessage", {"to": "Principale", "message": "x"}).ammesso)
    prova("6-app: predefinito -> id `local_` sconosciuto: ammesso (come da specifica)",
          pred(ss + "get_session", {"session_id": L_IGNOTA}).ammesso)
    prova("6-app: predefinito -> get_session `self`: ammesso",
          pred(ss + "get_session", {"session_id": "self"}).ammesso)
    r = alfa(ss + "get_session", {"session_id": L_COMUNE})
    prova("6-app: alfa -> get_session di un id `local_` del predefinito: negato, e dice che "
          "appartiene al predefinito (non che e' sconosciuto)",
          r.negato and "appartiene a predefinito" in r.motivo, repr(r))
    prova("6-app: alfa -> get_session `self`: ammesso",
          alfa(ss + "get_session", {"session_id": "self"}).ammesso)
    prova("6-app: alfa -> export_transcript `self`: ammesso",
          alfa(ss + "export_transcript", {"session_id": "self"}).ammesso)
    prova("6-app: alfa -> get_session di un altro id `local_` di alfa: ammesso",
          alfa(ss + "get_session", {"session_id": L_ALFA}).ammesso)
    prova("6-app: alfa -> get_session del PROPRIO id `local_` (il cui cliSessionId e' il suo session_id): ammesso",
          alfa(ss + "get_session", {"session_id": L_ALFA_ID}).ammesso)
    r = alfa(ss + "get_session", {"session_id": L_BETA})
    prova("6-app: alfa -> get_session di un id `local_` di beta: negato",
          r.negato and "beta" in r.motivo, repr(r))
    prova("6-app: alfa -> id `local_` sconosciuto: negato",
          alfa(ss + "list_events", {"session_id": L_IGNOTA}).negato)
    prova("6-app: alfa -> SendMessage a un nome di alfa: ammesso",
          alfa("SendMessage", {"to": "Lavoro alfa", "message": "x"}).ammesso)
    prova("6-app: alfa -> SendMessage a un nome del predefinito: negato",
          alfa("SendMessage", {"to": "Principale", "message": "x"}).negato)
    prova("6-app: alfa (sessione principale, non un subagente) -> SendMessage a `main`: "
          "nome sconosciuto, negato",
          alfa("SendMessage", {"to": "main", "message": "x"}).negato)
    sub = dict(sid="agent-x", madre=S_ALFA)
    prova("6-app: un SUBAGENTE di alfa -> SendMessage a `main` (il modo documentato di "
          "parlare alla madre): ammesso",
          a.chiama(a.pl("SendMessage", {"to": "main", "message": "x"}, aperta_in=a.alfa1, **sub)).ammesso)
    prova("6-app: un subagente di alfa -> get_session `self`: ammesso",
          a.chiama(a.pl(ss + "get_session", {"session_id": "self"}, aperta_in=a.alfa1, **sub)).ammesso)
    prova("6-app: un subagente di alfa -> SendMessage a un nome del predefinito: negato",
          a.chiama(a.pl("SendMessage", {"to": "Principale", "message": "x"}, aperta_in=a.alfa1, **sub)).negato)
    prova("6-app: un subagente del predefinito -> SendMessage a `main`: ammesso",
          a.chiama(a.pl("SendMessage", {"to": "main", "message": "x"}, aperta_in=a.comune,
                        sid="agent-y", madre=S_COMUNE)).ammesso)
    prova("6-app: titolo ripetuto (una sessione di alfa e una del predefinito): il predefinito "
          "e' negato (una delle due non e' sua)",
          pred("SendMessage", {"to": "Duplicato", "message": "x"}).negato)
    prova("6-app: ...e alfa e' negata (l'altra non e' sua)",
          alfa("SendMessage", {"to": "Duplicato", "message": "x"}).negato)
    # un id `local_` scritto in alfa.sessioni si traduce nel cliSessionId
    r = a.chiama(a.pl("Read", {"file_path": str(a.comune / "nota.txt")}, sid=S_CFG, aperta_in=a.comune))
    prova("6-app: un id `local_` in alfa.sessioni vale per la sessione che ha quel cliSessionId "
          "(Read del file comune negato)", r.negato, repr(r))
    prova("6-app: ...e un id `local_` in alfa.sessioni che il registro non conosce non rompe niente "
          "(il predefinito legge nel comune)",
          a.chiama(a.pl("Read", {"file_path": str(a.comune / "nota.txt")}, sid=S_COMUNE)).ammesso)
    r = pred(ss + "get_session", {"session_id": L_CFG})
    prova("6-app: predefinito -> get_session dell'id `local_` scritto in alfa.sessioni: negato",
          r.negato, repr(r))


def _prove_misura(prova, a: Ambiente):
    """Le chiamate senza bersaglio che il predefinito puo' fare (`list_sessions`,
    `ListAgents`) non si negano, ma in solo-registro lasciano una riga.
    `search_session_transcripts` invece cerca nel CONTENUTO di tutte le sessioni:
    si nega (vedi `_prove_ricerca_trascrizioni`); qui se ne controlla solo la riga."""
    ss = "mcp__ccd_session_mgmt__"
    chiamate = [(ss + "list_sessions", {}), (ss + "search_session_transcripts", {"query": "x"}),
                ("ListAgents", {})]
    a.togli_config()
    a.scrivi_config(a.config("solo-registro"))
    esiti = [a.chiama(a.pl(t, ti, sid=S_COMUNE)) for t, ti in chiamate]
    righe = a.registro()
    prova("misura: in solo-registro il predefinito che elenca/cerca fra tutte le sessioni e' "
          "ammesso e lascia una riga `avrebbe-negato` per strumento",
          all(e.ammesso for e in esiti) and len(righe) == 3
          and {x["strumento"] for x in righe} == {t for t, _ in chiamate}
          and all(x["esito"] == "avrebbe-negato" for x in righe), str(righe))
    a.chiama(a.pl(ss + "get_usage", {}, sid=S_COMUNE))
    prova("misura: get_usage (non guarda altre sessioni) non lascia righe", len(a.registro()) == 3)
    a.togli_config()
    a.scrivi_config(a.config("bloccante"))
    esiti = [a.chiama(a.pl(t, ti, sid=S_COMUNE)) for t, ti in chiamate]
    righe = a.registro()
    prova("misura: in bloccante list_sessions e ListAgents non si negano (limite dichiarato) e non "
          "scrivono niente; search_session_transcripts si nega e lascia la sua riga `negato`",
          esiti[0].ammesso and esiti[2].ammesso and esiti[1].negato
          and len(righe) == 1 and righe[0]["esito"] == "negato", repr(esiti) + str(righe))
    a.togli_config()
    cfg = a.config("solo-registro")
    cfg["compartimenti"] = {"predefinito": cfg["compartimenti"]["predefinito"]}
    a.scrivi_config(cfg)
    e = a.chiama(a.pl(ss + "list_sessions", {}, sid=S_COMUNE))
    prova("misura: senza compartimenti nominati non c'e' niente da misurare (nessuna riga)",
          e.ammesso and a.registro() == [], repr(e))
    a.togli_config()


def _prove_protezione(prova, a: Ambiente):
    """Un agente fermato dal guardiano non lo spegne da solo: i file del
    guardiano non si modificano da nessuna sessione. Leggerli resta ammesso."""
    a.togli_config()
    a.scrivi_config(a.config("bloccante"))
    a.chiama(a.pl("Read", {"file_path": str(a.comune / "nota.txt")}, sid=S_COMUNE))  # scrive la copia
    copia = a.dati / "compartimenti.ultima-valida.json"
    config = a.dati / "config.json"

    def pred(tool, ti):
        return a.chiama(a.pl(tool, ti, sid=S_COMUNE))

    prova("protezione: la copia dell'ultima valida esiste (il bloccante l'ha scritta)", copia.exists())
    for etichetta, percorso in (("config.json", config), ("la copia dell'ultima valida", copia),
                                ("il manifesto", a.manifesto), ("il registro", a.dati / "guardiano.log"),
                                ("bin/plancia-guardiano", GUARDIANO),
                                ("plancia/compartimenti.py", RADICE / "plancia" / "compartimenti.py")):
        r = pred("Edit", {"file_path": str(percorso), "old_string": "a", "new_string": "b"})
        prova(f"protezione: predefinito, Edit di {etichetta}: negato", r.negato and "guardiano" in r.motivo, repr(r))
    prova("protezione: predefinito, Write di config.json: negato",
          pred("Write", {"file_path": str(config), "content": "{}"}).negato)
    prova("protezione: ...anche con un percorso che passa da `..`",
          pred("Write", {"file_path": str(a.dati / "x" / ".." / "config.json"), "content": "{}"}).negato)
    prova("protezione: predefinito, Read di config.json: ammesso",
          pred("Read", {"file_path": str(config)}).ammesso)
    prova("protezione: predefinito, Write di un altro file della cartella dati: ammesso",
          pred("Write", {"file_path": str(a.dati / "altro.txt"), "content": "x"}).ammesso)
    for cmd in (f"echo '{{}}' > {config}", f"sed -i s/a/b/ {config}", f"rm {copia}",
                f"mv {a.manifesto} /dev/null", f"echo x | tee {config}"):
        r = pred("Bash", {"command": cmd})
        prova(f"protezione: predefinito, Bash `{cmd[:40]}...`: negato", r.negato, repr(r))
    for cmd in (f"cat {config}", f"cat {config} 2>/dev/null", f"grep guardiano {config} > /dev/null",
                f"python3 -c \"import json; json.load(open('{config}'))\"", f"echo x > {a.dati}/altro.txt"):
        r = pred("Bash", {"command": cmd})
        prova(f"protezione: predefinito, Bash `{cmd[:40]}...`: ammesso", r.ammesso, repr(r))
    # Artifact: `files` come mappa e `root`
    def art(ti, sid=S_ALFA_LIBERA, aperta=None, **kw):
        return a.chiama(a.pl("Artifact", ti, sid=sid, aperta_in=aperta or a.alfa1, **kw))

    fuori = str(a.comune / "nota.txt")
    dentro = str(a.alfa1 / "segreto.txt")
    prova("artifact: alfa, `files` come mappa con un sorgente fuori: negato",
          art({"file_path": dentro, "files": {"a.txt": fuori}}).negato)
    prova("artifact: alfa, `files` con {\"from\": fuori}: negato",
          art({"file_path": dentro, "files": {"a.txt": {"from": fuori}}}).negato)
    prova("artifact: alfa, `root` fuori: negato",
          art({"file_path": dentro, "root": str(a.comune), "files": {"a.txt": "nota.txt"}}).negato)
    r = art({"file_path": dentro, "files": {"a.txt": dentro, "b.txt": {"from": str(a.alfa2 / "due.txt")}}})
    prova("artifact: alfa, `files` tutti dentro le sue cartelle: ammesso", r.ammesso, repr(r))
    r = art({"file_path": dentro, "files": {"a.js": {"artifact": "https://esempio.test/a", "path": "x.js"}}})
    prova("artifact: alfa, un valore {artifact, path} copia da un altro artifact e non tocca il disco: ammesso",
          r.ammesso, repr(r))
    prova("artifact: predefinito, `files` con un sorgente dentro alfa: negato",
          a.chiama(a.pl("Artifact", {"file_path": fuori, "files": {"a.txt": dentro}}, sid=S_COMUNE)).negato)
    prova("artifact: predefinito, `files` nel comune: ammesso",
          a.chiama(a.pl("Artifact", {"file_path": fuori, "files": {"a.txt": fuori}}, sid=S_COMUNE)).ammesso)
    a.togli_config()


def _prove_relativi(prova, a: Ambiente):
    """Le righe con una barra ma non assolute si risolvono rispetto alla
    cartella del manifesto (le sue) e dei dati (`divieti`), non alla cwd
    dell'hook, che cambia da sessione a sessione."""
    a.togli_config()
    righe = a.righe_manifesto() + ["relativo/segreto", "relativo/*.tmp"]
    a.scrivi_manifesto(righe)
    cfg = a.config("bloccante")
    cfg["compartimenti"]["predefinito"]["divieti"].append("riserva-dati/x")
    a.scrivi_config(cfg)

    def leggi(p):
        return a.chiama(a.pl("Read", {"file_path": str(p)}, sid=S_COMUNE))

    prova("relativi: una riga del manifesto `relativo/segreto` vale rispetto alla cartella del manifesto",
          leggi(a.radice / "relativo" / "segreto" / "f").negato)
    prova("relativi: un modello del manifesto `relativo/*.tmp` con una barra vale allo stesso modo",
          leggi(a.radice / "relativo" / "dato.tmp").negato)
    prova("relativi: ...e un file vicino che non combacia e' ammesso",
          leggi(a.radice / "relativo" / "altro.txt").ammesso)
    prova("relativi: una riga relativa di `divieti` vale rispetto alla cartella dei dati",
          leggi(a.dati / "riserva-dati" / "x" / "f").negato)
    a.scrivi_manifesto(a.righe_manifesto())
    a.togli_config()


def _prove_change_directory(prova, a: Ambiente):
    """Prova 7."""
    a.scrivi_config(a.config())
    cd = "mcp__ccd_directory__change_directory"
    rd = "mcp__ccd_directory__request_directory"
    r = a.chiama(a.pl(cd, {"path": str(a.alfa1)}, sid=S_COMUNE))
    prova("7: predefinito, change_directory verso una cartella di alfa: negato",
          r.negato and "alfa" in r.motivo, repr(r))
    prova("7: predefinito, request_directory verso alfa: negato",
          a.chiama(a.pl(rd, {"path": str(a.alfa2)}, sid=S_COMUNE)).negato)
    prova("7: predefinito, change_directory verso beta (chiave `directory`): negato",
          a.chiama(a.pl(cd, {"directory": str(a.beta1)}, sid=S_COMUNE)).negato)
    prova("7: predefinito, change_directory verso una cartella del comune: ammesso",
          a.chiama(a.pl(cd, {"path": str(a.condiviso)}, sid=S_COMUNE)).ammesso)
    prova("7: predefinito, change_directory verso la cartella del predefinito vietata da manifesto: negato",
          a.chiama(a.pl(cd, {"path": str(a.condiviso / "repo")}, sid=S_COMUNE)).negato)
    prova("7: alfa, change_directory verso la propria seconda cartella: ammesso",
          a.chiama(a.pl(cd, {"path": str(a.alfa2)}, sid=S_ALFA, aperta_in=a.alfa1)).ammesso)
    prova("7: alfa, change_directory verso il comune: negato",
          a.chiama(a.pl(cd, {"path": str(a.comune)}, sid=S_ALFA, aperta_in=a.alfa1)).negato)
    prova("7: alfa, request_directory verso il comune (chiave `cwd`): negato",
          a.chiama(a.pl(rd, {"cwd": str(a.comune)}, sid=S_ALFA, aperta_in=a.alfa1)).negato)


def _prove_manifesto(prova, a: Ambiente):
    """Ogni riga del manifesto e' negata al predefinito, e la verifica sa
    accorgersi di un percorso non elencato."""
    a.scrivi_config(a.config())
    righe = a.righe_manifesto()
    aperti = _non_negati_dal_manifesto(a, righe)
    prova("manifesto: ogni riga (percorso, glob, nome con glob) e' negata al predefinito",
          aperti == [], f"non negati: {aperti}")
    # la verifica deve FALLIRE se un percorso della linea comune non e' nel manifesto
    a.scrivi_manifesto([x for x in righe if not x.endswith("/out-1")])
    aperti = _non_negati_dal_manifesto(a, righe)
    prova("manifesto: la verifica fallisce se manca una riga (percorso comune non elencato)",
          any(p.endswith("/out-1") or "/out-1/" in p for p in aperti) and len(aperti) == 2,
          f"non negati: {aperti}")
    a.scrivi_manifesto([x for x in righe if x != "*.segreto"])
    aperti = _non_negati_dal_manifesto(a, righe)
    prova("manifesto: la verifica fallisce se manca un modello di nome",
          len(aperti) == 1 and aperti[0].endswith("dato.segreto"), f"non negati: {aperti}")
    a.scrivi_manifesto(righe)
    prova("manifesto: un commento e una riga vuota non vietano niente",
          a.chiama(a.pl("Read", {"file_path": str(a.comune / "nota.txt")})).ammesso)
    prova("manifesto: `divieti` di config vale come il manifesto",
          a.chiama(a.pl("Read", {"file_path": str(a.comune / "riservato" / "f")})).negato)
    prova("manifesto: la Bash che nomina un percorso del manifesto e' negata",
          a.chiama(a.pl("Bash", {"command": f"cat {a.condiviso}/repo/README"})).negato)
    prova("manifesto: un nominato non ne e' condizionato (alfa legge dentro alfa)",
          a.chiama(a.pl("Read", {"file_path": str(a.alfa1 / "segreto.txt")},
                        sid=S_ALFA_LIBERA, aperta_in=a.alfa1)).ammesso)
    # il manifesto sparisce: il predefinito non si blocca, perde solo quelle righe
    a.manifesto.unlink()
    r = a.chiama(a.pl("Read", {"file_path": str(a.condiviso / "repo" / "f")}))
    prova("manifesto: se il file manca il predefinito non si rompe (perde quelle righe)",
          r.ammesso, repr(r))
    prova("manifesto: ...ma le cartelle dei nominati restano vietate",
          a.chiama(a.pl("Read", {"file_path": str(a.alfa1 / "segreto.txt")})).negato)
    a.scrivi_manifesto(righe)


def _prove_symlink(prova, a: Ambiente):
    a.scrivi_config(a.config())
    ponte = a.comune / "ponte-verso-alfa"
    if not _crea_symlink(ponte, a.alfa1):
        prova("symlink: creazione del symlink di prova", False, "non riuscita")
        return
    r = a.chiama(a.pl("Read", {"file_path": str(ponte / "segreto.txt")}))
    prova("symlink: il predefinito che legge attraverso un symlink verso alfa: negato",
          r.negato and "appartiene a alfa" in r.motivo, repr(r))
    prova("symlink: ...anche in un comando Bash",
          a.chiama(a.pl("Bash", {"command": f"cat {ponte}/segreto.txt"})).negato)
    prova("symlink: ...e una ricerca (Grep) che parte dal symlink",
          a.chiama(a.pl("Grep", {"pattern": "x", "path": str(ponte)})).negato)
    uscita = a.alfa1 / "uscita"
    _crea_symlink(uscita, a.comune)
    prova("symlink: alfa che esce con un symlink verso il comune: negato",
          a.chiama(a.pl("Read", {"file_path": str(uscita / "nota.txt")}, sid=S_ALFA_LIBERA,
                        aperta_in=a.alfa1)).negato)
    interno = a.alfa1 / "interno"
    _crea_symlink(interno, a.alfa1 / "sotto")
    prova("symlink: alfa con un symlink che resta dentro alfa: ammesso",
          a.chiama(a.pl("Read", {"file_path": str(interno / "f.txt")}, sid=S_ALFA_LIBERA,
                        aperta_in=a.alfa1)).ammesso)
    # /tmp e' un symlink a /private/tmp: un modello scritto con l'uno vale per l'altro
    a.scrivi_config(a.config())
    cfg = a.config()
    cfg["compartimenti"]["predefinito"]["divieti"] = ["/tmp/plancia-prova-guardiano-glob/*.riservato"]
    a.scrivi_config(cfg)
    r = a.chiama(a.pl("Read", {"file_path": "/private/tmp/plancia-prova-guardiano-glob/x.riservato"}))
    prova("symlink: un divieto scritto con /tmp vale per /private/tmp (prefisso risolto)",
          r.negato or not os.path.islink("/tmp"), repr(r))


def _prove_modi(prova, a: Ambiente):
    """Le tre modalita' e i guasti."""
    fuori = str(a.comune / "nota.txt")
    viola = a.pl("Read", {"file_path": fuori}, sid=S_ALFA_LIBERA, aperta_in=a.alfa1)
    ammessa = a.pl("Read", {"file_path": str(a.alfa1 / "segreto.txt")}, sid=S_ALFA_LIBERA,
                   aperta_in=a.alfa1)

    # spento
    a.togli_config()
    r = a.chiama(viola)
    prova("modi: senza config.json il guardiano e' spento (exit 0, nessuna uscita)",
          r.ammesso and not (a.dati / "guardiano.log").exists(), repr(r))
    a.scrivi_config(a.config("spento"))
    r = a.chiama(viola)
    prova("modi: `spento` esce 0 senza uscita e senza riga di registro",
          r.ammesso and a.registro() == [], repr(r))
    # La copia: nello stesso ambiente, subito prima, un bloccante la scrive; poi,
    # senza copia, uno spento non la crea.
    copia = a.dati / "compartimenti.ultima-valida.json"
    a.scrivi_config(a.config("bloccante"))
    rb = a.chiama(viola)
    scritta = copia.exists()
    a.togli_config()
    a.scrivi_config(a.config("spento"))
    rs = a.chiama(viola)
    prova("modi: `spento` non scrive la copia dell'ultima config valida (mentre un bloccante, "
          "nello stesso ambiente, la scrive)",
          rb.negato and scritta and rs.ammesso and not copia.exists(), f"{rb!r} {scritta} {rs!r}")
    # `spento` e' un interruttore stabile: una config rotta dopo lo spegnimento
    # non rimette in piedi il vecchio bloccante.
    a.togli_config()
    a.scrivi_config(a.config("bloccante"))
    r0 = a.chiama(viola)
    a.scrivi_config(a.config("spento"))
    r1 = a.chiama(viola)
    nota_pred = a.pl("Read", {"file_path": str(a.alfa1 / "segreto.txt")}, sid=S_COMUNE)
    a.scrivi_config("{ rotto")
    r2 = a.chiama(viola)
    r3 = a.chiama(nota_pred)
    prova("modi: bloccante, poi `spento`, poi config rotta: resta spento (ne' l'alfa ne' il "
          "predefinito vengono negati con le regole vecchie)",
          r0.negato and r1.ammesso and r2.ammesso and r3.ammesso and a.registro()[-1].get("esito") == "negato"
          and len(a.registro()) == 1, f"{r0!r} {r1!r} {r2!r} {r3!r}")
    prova("modi: ...e la copia dell'ultima valida e' diventata `spento`",
          _testo(copia) != "" and json.loads(_testo(copia)).get("guardiano") == "spento")
    a.togli_config()
    a.scrivi_config(a.config("bloccante"))
    prova("modi: ...riacceso a bloccante con una config valida, si torna a negare",
          a.chiama(viola).negato)
    a.togli_config()
    cfg = a.config("spento")
    cfg["compartimenti"] = ["rotto"]
    a.scrivi_config(cfg)
    r = a.chiama(viola)
    prova("modi: `spento` non guarda il resto (compartimenti scritti male: comunque spento, "
          "nessuna riga nemmeno di config illeggibile)",
          r.ammesso and a.registro() == [], repr(r))
    a.togli_config()

    # solo-registro
    a.scrivi_config(a.config("solo-registro"))
    r = a.chiama(viola)
    riga = (a.registro() or [{}])[-1]
    prova("modi: `solo-registro` non nega mai (stdout vuoto, exit 0)", r.ammesso, repr(r))
    prova("modi: `solo-registro` scrive una riga `avrebbe-negato` con tutti i campi",
          riga.get("esito") == "avrebbe-negato" and riga.get("modalita") == "solo-registro"
          and riga.get("compartimento") == "alfa" and riga.get("strumento") == "Read"
          and riga.get("bersaglio") == fuori and riga.get("sessione") == S_ALFA_LIBERA
          and "alfa" in riga.get("motivo", "") and riga.get("ts"), str(riga))
    n = len(a.registro())
    r = a.chiama(ammessa)
    prova("modi: una chiamata ammessa (uscita 0, nessun output) non scrive niente nel registro "
          "che, con la chiamata di prima, ha gia' una riga",
          r.ammesso and n >= 1 and len(a.registro()) == n, f"{r!r} {n}")
    # bloccante
    a.togli_config()
    a.scrivi_config(a.config("bloccante"))
    r = a.chiama(viola)
    riga = (a.registro() or [{}])[-1]
    prova("modi: `bloccante` nega con hookSpecificOutput/permissionDecision=deny, exit 0",
          r.negato and r.deny.get("hookEventName") == "PreToolUse" and r.rc == 0, repr(r))
    prova("modi: `bloccante` scrive la riga con esito `negato`",
          riga.get("esito") == "negato" and riga.get("modalita") == "bloccante", str(riga))
    prova("modi: `bloccante`, una chiamata ammessa non ha uscita",
          a.chiama(ammessa).ammesso)
    a.scrivi_config(a.config(" Bloccante "))
    prova("modi: `Bloccante` maiuscolo e con spazi vale come `bloccante`",
          a.chiama(viola).negato)
    a.scrivi_config(a.config("bloccante"))
    ev = dict(viola)
    ev["hook_event_name"] = "PostToolUse"
    prova("modi: un evento diverso da PreToolUse non e' toccato",
          a.chiama(ev).ammesso)

    # stdin rotto, in ogni modalita'
    righe_prima = len(a.registro())
    stdin_ok = []
    for modo in ("spento", "solo-registro", "bloccante"):
        a.scrivi_config(a.config(modo))
        for nome, dati in (("vuoto", b""), ("non JSON", b"non e' json {"),
                           ("JSON che non e' un oggetto", b"[1, 2]"),
                           ("byte non UTF-8", b"\xff\xfe\x00\xff"),
                           ("oggetto senza tool_name", b"{}"),
                           ("tool_input di tipo sbagliato",
                            b'{"tool_name":"Read","tool_input":["x"],"session_id":5}')):
            r = a.esegui_testo(dati)
            stdin_ok.append(r.ammesso)
            prova(f"modi: {modo}, stdin {nome}: exit 0 e nessuna uscita", r.ammesso, repr(r))
    prova("modi: gli stdin rotti (18 chiamate, tutte uscite 0 senza output) non hanno scritto "
          "niente nel registro, che aveva gia' delle righe",
          righe_prima >= 1 and len(stdin_ok) == 18 and all(stdin_ok)
          and len(a.registro()) == righe_prima, f"{righe_prima} {stdin_ok}")

    # rotazione
    a.togli_config()
    a.scrivi_config(a.config("solo-registro"))
    (a.dati / "guardiano.log").write_bytes(b"x" * (5 * 1024 * 1024 + 10))
    a.chiama(viola)
    vecchio = a.dati / "guardiano.log.1"
    prova("registro: oltre 5 MB il file diventa .1 e ne inizia uno nuovo",
          vecchio.exists() and vecchio.stat().st_size > 5 * 1024 * 1024
          and len(a.registro()) == 1, f"{[p.name for p in a.dati.iterdir()]}")
    a.togli_config()


def _prove_config_malformata(prova, a: Ambiente):
    """Prova 8: un nominato resta confinato se la config si rompe."""
    fuori = str(a.comune / "nota.txt")
    dentro = str(a.alfa1 / "segreto.txt")

    def alfa(p):
        return a.chiama(a.pl("Read", {"file_path": p}, sid=S_ALFA_LIBERA, aperta_in=a.alfa1))

    def comune(p):
        return a.chiama(a.pl("Read", {"file_path": p}, sid=S_COMUNE))

    guasti = {
        "JSON con virgola finale": json.dumps(a.config(), indent=2).replace(
            '"comandi_vietati": [\n        "%s"\n      ]' % RAMO,
            '"comandi_vietati": [\n        "%s",\n      ]' % RAMO),
        "`compartimenti` e' una lista": json.dumps({"guardiano": "bloccante", "compartimenti": ["x"]}),
        "`cartelle` e' una stringa": json.dumps({"guardiano": "bloccante", "compartimenti": {
            "alfa": {"cartelle": str(a.alfa1)}}}),
        "modo sconosciuto": json.dumps({"guardiano": "forse", "compartimenti": {}}),
        "file vuoto": "",
        "il file non e' un oggetto": "[1, 2, 3]",
    }
    for nome, testo in guasti.items():
        a.togli_config()
        a.scrivi_config(a.config("bloccante"))
        alfa(dentro)  # legge una config valida: scrive la copia
        copia_ok = (a.dati / "compartimenti.ultima-valida.json").exists()
        a.scrivi_config(testo)
        r = alfa(fuori)
        prova(f"8: config rotta ({nome}), con la copia: alfa resta confinato (Read fuori negato)",
              copia_ok and r.negato, repr(r))
        prova(f"8: config rotta ({nome}): alfa dentro le sue cartelle lavora ancora",
              alfa(dentro).ammesso)
        prova(f"8: config rotta ({nome}): il predefinito lavora nel comune",
              comune(str(a.comune / "nota.txt")).ammesso)
    # la copia non viene sovrascritta da una config rotta
    a.togli_config()
    a.scrivi_config(a.config("bloccante"))
    alfa(dentro)
    copia = _testo(a.dati / "compartimenti.ultima-valida.json")
    a.scrivi_config("{ rotto")
    alfa(fuori)
    prova("8: la copia dell'ultima valida non viene toccata da una config rotta",
          copia != "" and _testo(a.dati / "compartimenti.ultima-valida.json") == copia)
    prova("8: la copia e' una config valida con `alfa` dentro",
          copia != "" and "alfa" in json.loads(copia)["compartimenti"])
    # una config valida e diversa aggiorna la copia
    cfg = a.config("bloccante")
    cfg["compartimenti"]["alfa"]["cartelle"] = [str(a.alfa1)]
    a.scrivi_config(cfg)
    alfa(dentro)
    testo_nuova = _testo(a.dati / "compartimenti.ultima-valida.json")
    prova("8: una config valida e diversa riscrive la copia",
          testo_nuova != ""
          and json.loads(testo_nuova)["compartimenti"]["alfa"]["cartelle"] == [str(a.alfa1)])
    mt = _mtime(a.dati / "compartimenti.ultima-valida.json")
    time.sleep(0.02)
    alfa(dentro)
    prova("8: una config valida e uguale non riscrive la copia",
          mt != -1 and _mtime(a.dati / "compartimenti.ultima-valida.json") == mt)
    # config rotta e nessuna copia: solo-registro per tutti, una riga di nota
    a.togli_config()
    a.scrivi_config("{ rotto")
    r1 = alfa(fuori)
    r2 = comune(str(a.alfa1 / "segreto.txt"))
    righe = a.registro()
    prova("8: config rotta SENZA copia: nessuno viene negato (solo-registro per tutti)",
          r1.ammesso and r2.ammesso, f"{r1!r} {r2!r}")
    prova("8: ...e c'e' una sola riga `config illeggibile` (non una per strumento)",
          len(righe) == 1 and "config illeggibile" in righe[0].get("motivo", "")
          and righe[0].get("esito") == "nota", str(righe))
    # una copia che non e' piu' valida non si usa
    a.togli_config()
    a.scrivi_config("{ rotto")
    (a.dati / "compartimenti.ultima-valida.json").write_text('{"compartimenti": []}', "utf-8")
    prova("8: una copia non valida e' come nessuna copia (nessuno negato)",
          alfa(fuori).ammesso)
    # config illeggibile per permessi
    a.togli_config()
    a.scrivi_config(a.config("bloccante"))
    alfa(dentro)
    cfgp = a.dati / "config.json"
    try:
        os.chmod(cfgp, 0)
        se_root = os.access(cfgp, os.R_OK)
        r = alfa(fuori)
        prova("8: config.json illeggibile (permessi): con la copia alfa resta confinato",
              se_root or r.negato, repr(r))
    finally:
        os.chmod(cfgp, 0o644)
    a.togli_config()


def _prove_errore_interno(prova):
    """Un'eccezione dentro la decisione (in-process, con `valuta` sostituita):
    un nominato in `bloccante` viene negato, gli altri no."""
    try:
        cm = importlib.import_module("plancia.compartimenti")
    except ImportError as e:
        prova("errore interno: plancia.compartimenti si importa", False, str(e))
        return
    dati = Path(tempfile.mkdtemp(prefix="plancia-prova-guardiano-int-"))
    cartella = Path(os.path.realpath(tempfile.mkdtemp(prefix="plancia-prova-guardiano-cart-")))
    originale = cm.valuta
    try:
        def guasta(*args, **kw):
            raise RuntimeError("guasto simulato")
        cm.valuta = guasta
        payload = {"session_id": "s1", "cwd": str(cartella), "hook_event_name": "PreToolUse",
                   "transcript_path": str(dati / "p" / _codifica(cartella) / "s1.jsonl"),
                   "tool_name": "Read", "tool_input": {"file_path": "/etc/hosts"}}
        altro = dict(payload, cwd="/", transcript_path=str(dati / "p" / "-altra-cartella" / "s2.jsonl"),
                     session_id="s2")
        for modo, atteso_nominato in (("bloccante", True), ("solo-registro", False), ("spento", False)):
            (dati / "config.json").write_text(json.dumps({
                "guardiano": modo, "compartimenti": {
                    "alfa": {"cartelle": [str(cartella)]}}}), "utf-8")
            nom = cm.hook(json.dumps(payload), str(dati))
            if modo == "spento":
                attesa = nom == ""
                cosa = "ammesso, nessuna uscita"
            elif atteso_nominato:
                attesa = "errore interno" in nom and "deny" in nom
                cosa = "negato per prudenza"
            else:
                attesa = "errore interno" in nom and "systemMessage" in nom and "deny" not in nom
                cosa = "ammesso ma con il systemMessage"
            prova(f"errore interno: {modo}, nominato: {cosa}", attesa, nom[:150])
            pre = cm.hook(json.dumps(altro), str(dati))
            if modo == "spento":
                prova(f"errore interno: {modo}, predefinito: ammesso, nessuna uscita", pre == "",
                      pre[:150])
            else:
                prova(f"errore interno: {modo}, predefinito: ammesso ma con il systemMessage "
                      "(sesto giro: non piu' in silenzio)",
                      "systemMessage" in pre and "errore interno" in pre and "deny" not in pre,
                      pre[:150])
    finally:
        cm.valuta = originale
        shutil.rmtree(dati, ignore_errors=True)
        shutil.rmtree(cartella, ignore_errors=True)


def _prove_tempo(prova, a: Ambiente):
    a.togli_config()
    a.scrivi_config(a.config("bloccante"))
    bash = a.pl("Bash", {"command": f"cat {a.alfa1}/segreto.txt | head; ls {a.alfa2} 2>/dev/null"},
                sid=S_ALFA_LIBERA, aperta_in=a.alfa1)
    leggi = a.pl("Read", {"file_path": str(a.comune / "nota.txt")}, sid=S_COMUNE)
    nega = a.pl("Read", {"file_path": str(a.comune / "nota.txt")}, sid=S_ALFA_LIBERA,
                aperta_in=a.alfa1)
    for _ in range(3):  # riscalda i .pyc e la cache del disco
        a.chiama(bash)
    tempi, giuste, negate = [], True, 0
    for i in range(21):
        # Il tempo si misura solo se la chiamata ha l'esito che deve avere: un
        # Python che non trova il file esce in pochi ms con un errore, e
        # passerebbe qualunque soglia.
        quale = (bash, leggi, nega)[i % 3]
        r = a.chiama(quale)
        tempi.append(r.secondi * 1000)
        if quale is nega:
            negate += 1
            giuste = giuste and r.negato
        else:
            giuste = giuste and r.ammesso
    tempi.sort()
    med, mx = tempi[len(tempi) // 2], tempi[-1]
    t0 = time.time()
    subprocess.run([PYTHON, "-c", "pass"], env=a.env(), capture_output=True)
    base = (time.time() - t0) * 1000
    prova(f"tempo: per chiamata mediana {med:.0f} ms, massimo {mx:.0f} ms "
          f"(avvio di Python a vuoto {base:.0f} ms); soglia 150 ms; ogni chiamata misurata "
          f"ha l'esito atteso e {negate} sono negate",
          med < 150 and giuste and negate >= 1, f"mediana {med:.0f} ms, esiti giusti {giuste}")
    a.scrivi_config(a.config("spento"))
    for _ in range(3):
        a.chiama(bash)
    corse = [a.chiama(bash) for _ in range(11)]
    tempi = sorted(c.secondi * 1000 for c in corse)
    prova(f"tempo: `spento` mediana {tempi[5]:.0f} ms (ogni chiamata esce 0 senza output)",
          tempi[5] < 150 and all(c.ammesso for c in corse), f"{tempi[5]:.0f} ms")


def _prove_cli(prova, a: Ambiente):
    a.togli_config()
    a.scrivi_config(a.config("solo-registro"))
    a.chiama(a.pl("Read", {"file_path": str(a.comune / "nota.txt")}, sid=S_ALFA_LIBERA,
                  aperta_in=a.alfa1))
    a.chiama(a.pl("Read", {"file_path": str(a.alfa1 / "segreto.txt")}, sid=S_COMUNE))
    env = dict(a.env())
    env["PYTHONPATH"] = str(RADICE)

    codici = []

    def plancia(*args):
        p = subprocess.run([sys.executable, str(RADICE / "bin" / "plancia"), "guardiano", *args],
                           env=env, cwd=str(RADICE), capture_output=True, timeout=60)
        codici.append(p.returncode)
        return p.returncode, p.stdout.decode("utf-8", "replace") + p.stderr.decode("utf-8", "replace")

    rc, out = plancia("--stato")
    prova("cli: `plancia guardiano --stato` dice modalita', compartimenti e righe recenti",
          rc == 0 and "solo-registro" in out and "alfa: 3 cartelle" in out
          and "beta: 1 cartelle" in out and "predefinito:" in out
          and "2 righe" in out and "2 avrebbe-negato" in out, out)
    prova("cli: --stato (uscita 0, con l'elenco dei compartimenti) NON stampa i percorsi delle cartelle",
          rc == 0 and "alfa: 3 cartelle" in out and str(a.radice) not in out
          and "alfa-uno" not in out, out)
    rc, out = plancia("--registro", "50")
    prova("cli: `--registro 50` mostra le decisioni in chiaro (esito, compartimento, strumento, percorso)",
          rc == 0 and out.count("avrebbe-negato") == 2 and "[alfa] Read" in out
          and "[predefinito] Read" in out and str(a.comune / "nota.txt") in out, out)
    rc, out = plancia("--registro", "1")
    prova("cli: `--registro 1` mostra solo l'ultima", rc == 0 and len(out.strip().splitlines()) == 1, out)
    rc, out = plancia()
    prova("cli: senza opzioni mostra lo stato", rc == 0 and "modalita: solo-registro" in out, out)
    a.togli_config()
    rc, out = plancia("--registro")
    prova("cli: registro vuoto e config assente: nessun errore", rc == 0 and "vuoto" in out, out)
    rc, out = plancia("--stato")
    prova("cli: config assente: modalita' spento", rc == 0 and "modalita: spento" in out, out)
    a.scrivi_config("{ rotto")
    rc, out = plancia("--stato")
    prova("cli: config rotta e senza copia: lo dice", rc == 0 and "solo-registro" in out
          and "nessuna copia valida" in out, out)
    a.togli_config()
    # e non scrive niente: dopo aver girato in ogni stato (config valida, assente,
    # rotta, registro vuoto), tutte con uscita 0 e l'uscita attesa
    rc, out = plancia("--stato")
    prova("cli: il sottocomando non crea ne' scrive config.json, copia o registro "
          "(dopo 8 esecuzioni in tutti gli stati, tutte uscita 0)",
          len(codici) == 8 and all(c == 0 for c in codici) and "modalita: spento" in out
          and not any((a.dati / f).exists() for f in
                      ("config.json", "compartimenti.ultima-valida.json", "guardiano.log")),
          f"{codici}")


def _prove_specchio(prova, a: Ambiente):
    """Le trascrizioni e la memoria di un compartimento stanno sotto
    `<CLAUDE_CONFIG_DIR o ~/.claude>/projects/<cartella codificata>`: sono suo
    lavoro come le sue cartelle. Il predefinito non le legge, ne' le cerca."""
    a.togli_config()
    a.scrivi_config(a.config("bloccante"))
    proj = a.claude / "projects"
    enc_alfa, enc_beta, enc_com = _codifica(a.alfa1), _codifica(a.beta1), _codifica(a.comune)
    mem_alfa = proj / enc_alfa / "memory" / "MEMORY.md"
    trascr_alfa = proj / enc_alfa / f"{S_ALFA_LIBERA}.jsonl"
    sub_alfa = proj / enc_alfa / S_ALFA_LIBERA / "subagents" / "agent-q.jsonl"
    disc_alfa = proj / (enc_alfa + "-sotto") / "d.jsonl"       # aperta in alfa/sotto
    sorella = proj / (enc_alfa + "altro") / "s.jsonl"          # alfa-unoaltro: non e' di alfa
    mem_beta = proj / enc_beta / "memory" / "MEMORY.md"
    propria = proj / enc_com / "c.jsonl"
    mem_com = proj / enc_com / "memory" / "MEMORY.md"
    for f in (mem_alfa, trascr_alfa, sub_alfa, disc_alfa, sorella, mem_beta, propria, mem_com):
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("segreto-di-" + f.parent.name[-12:], "utf-8")

    def pred(tool, ti, **kw):
        kw.setdefault("aperta_in", a.comune)
        return a.chiama(a.pl(tool, ti, sid=S_COMUNE, **kw))

    for etichetta, f in (("la memoria di alfa", mem_alfa), ("una trascrizione di alfa", trascr_alfa),
                         ("un file di un subagente di alfa", sub_alfa),
                         ("la cartella di una discendente di alfa (alfa/sotto)", disc_alfa),
                         ("la memoria di beta", mem_beta)):
        r = pred("Read", {"file_path": str(f)})
        prova(f"specchio: predefinito, Read di {etichetta} sotto ~/.claude/projects: negato",
              r.negato and "appartiene a" in r.motivo, repr(r))
    r = pred("Read", {"file_path": str(mem_alfa)})
    prova("specchio: ...il motivo dice a quale compartimento appartiene", "alfa" in r.motivo, r.motivo)
    prova("specchio: predefinito, Read di una cartella sorella con lo stesso inizio ma senza il "
          "trattino di confine (alfa-unoaltro): ammesso",
          pred("Read", {"file_path": str(sorella)}).ammesso)
    prova("specchio: predefinito, Read della propria trascrizione e della propria memoria: ammesso",
          pred("Read", {"file_path": str(propria)}).ammesso
          and pred("Read", {"file_path": str(mem_com)}).ammesso)
    prova("specchio: predefinito, Write nella memoria di alfa: negato",
          pred("Write", {"file_path": str(mem_alfa), "content": "x"}).negato)
    prova("specchio: predefinito, Edit di una trascrizione di beta: negato",
          pred("Edit", {"file_path": str(mem_beta), "old_string": "a", "new_string": "b"}).negato)
    # ricerche
    r = pred("Grep", {"pattern": "segreto", "path": str(proj)})
    prova("specchio: predefinito, Grep che parte da ~/.claude/projects: negato (include lo "
          "specchio di alfa), con l'invito a restringere", r.negato and "restringi" in r.motivo, repr(r))
    prova("specchio: predefinito, Grep da ~/.claude (antenato): negato",
          pred("Grep", {"pattern": "segreto", "path": str(a.claude)}).negato)
    prova("specchio: predefinito, Grep nella propria cartella di progetto: ammesso",
          pred("Grep", {"pattern": "segreto", "path": str(proj / enc_com)}).ammesso)
    prova("specchio: predefinito, Grep nella cartella di progetto di alfa: negato",
          pred("Grep", {"pattern": "segreto", "path": str(proj / enc_alfa)}).negato)
    prova("specchio: predefinito, Glob assoluto ~/.claude/projects/*/*.jsonl: negato",
          pred("Glob", {"pattern": f"{proj}/*/*.jsonl"}).negato)
    prova("specchio: predefinito, Glob con path=~/.claude/projects: negato",
          pred("Glob", {"pattern": "**/*.jsonl", "path": str(proj)}).negato)
    for cmd in (f"grep -r segreto {proj}", f"cat {mem_alfa}", f"cat {proj}/*/memory/MEMORY.md",
                f"find {a.claude} -name '*.jsonl'", f"rg segreto {proj}", f"ls -R {proj}",
                f"cd {proj} && grep -rn segreto ."):
        r = pred("Bash", {"command": cmd})
        prova(f"specchio: predefinito, Bash `{cmd[:52]}`: negato", r.negato, repr(r))
    for cmd in (f"cat {propria}", f"grep -r segreto {proj / enc_com}", f"ls {proj}"):
        r = pred("Bash", {"command": cmd})
        prova(f"specchio: predefinito, Bash `{cmd[:52]}`: ammesso (la propria cartella; `ls` non "
              "e' ricorsivo, limite dichiarato)", r.ammesso, repr(r))
    # un nominato legge solo le sue
    def alfa(tool, ti):
        return a.chiama(a.pl(tool, ti, sid=S_ALFA_LIBERA, aperta_in=a.alfa1))
    prova("specchio: alfa (aperta nella sua cartella), Read della propria memoria: ammesso",
          alfa("Read", {"file_path": str(mem_alfa)}).ammesso)
    prova("specchio: alfa, Read della memoria di beta: negato",
          alfa("Read", {"file_path": str(mem_beta)}).negato)
    prova("specchio: alfa, Grep che parte da ~/.claude/projects: negato",
          alfa("Grep", {"pattern": "x", "path": str(proj)}).negato)
    prova("specchio: alfa, Bash `grep -r x ~/.claude/projects`: negato",
          alfa("Bash", {"command": f"grep -r x {proj}"}).negato)
    # senza CLAUDE_CONFIG_DIR vale ~/.claude
    env = dict(a.env())
    env.pop("CLAUDE_CONFIG_DIR", None)
    home_proj = a.home / ".claude" / "projects" / enc_alfa
    home_proj.mkdir(parents=True, exist_ok=True)
    (home_proj / "memory").mkdir(exist_ok=True)
    (home_proj / "memory" / "MEMORY.md").write_text("x", "utf-8")
    r = a.chiama(a.pl("Read", {"file_path": str(home_proj / "memory" / "MEMORY.md")},
                      sid=S_COMUNE, aperta_in=a.comune), env=env)
    prova("specchio: senza CLAUDE_CONFIG_DIR la cartella e' ~/.claude: Read della memoria di alfa "
          "negata", r.negato, repr(r))
    r = a.chiama(a.pl("Read", {"file_path": str(mem_alfa)}, sid=S_COMUNE, aperta_in=a.comune), env=env)
    prova("specchio: ...e in quel caso una CLAUDE_CONFIG_DIR diversa non e' quella in uso (ammesso)",
          r.ammesso, repr(r))
    # la funzione che E1 riusera'
    try:
        sys.path.insert(0, str(RADICE))
        cm = importlib.import_module("plancia.compartimenti")
        importlib.reload(cm)
        cfg = cm.valida_compartimenti(a.config()["compartimenti"])
        amb = cm.Ambito(cfg, home=str(a.home), data_dir=str(a.dati), claude_dir=str(a.claude))
        p1 = cm.proprietario_specchio(os.path.realpath(str(mem_alfa)), amb)
        p2 = cm.proprietario_specchio(os.path.realpath(str(propria)), amb)
        p3 = cm.proprietario_specchio(os.path.realpath(str(sorella)), amb)
        ok = (p1 == "alfa" and p2 is None and p3 is None)
    except Exception as exc:  # noqa: BLE001
        ok, p1, p2, p3 = False, exc, None, None
    finally:
        try:
            sys.path.remove(str(RADICE))
        except ValueError:
            pass
    prova("specchio: `compartimenti.proprietario_specchio` (per E1) dice a chi appartiene "
          "un percorso sotto projects: alfa, nessuno, nessuno", ok, f"{p1!r} {p2!r} {p3!r}")
    a.togli_config()


def _prove_autoprotezione_cli(prova, a: Ambiente):
    """Il guardiano non si spegne con la CLI di Plancia ne' con un comando che
    scrive i suoi file per altre vie. Negato a TUTTE le sessioni. Euristico e
    dichiarato: chi vuole aggirarlo ci riesce, il caso ordinario si chiude."""
    a.togli_config()
    a.scrivi_config(a.config("bloccante"))
    a.chiama(a.pl("Read", {"file_path": str(a.comune / "nota.txt")}, sid=S_COMUNE))  # scrive la copia
    config, copia = a.dati / "config.json", a.dati / "compartimenti.ultima-valida.json"
    log = a.dati / "guardiano.log"
    log.write_text("", "utf-8")
    prova("autoprotezione-cli: la copia esiste (il bloccante l'ha scritta)", copia.exists())

    def pred(cmd):
        return a.chiama(a.pl("Bash", {"command": cmd}, sid=S_COMUNE, aperta_in=a.progetto))

    def alfa(cmd):
        return a.chiama(a.pl("Bash", {"command": cmd}, sid=S_ALFA_LIBERA, aperta_in=a.alfa1))

    spegne = [
        "plancia config guardiano spento",
        "./bin/plancia config guardiano spento",
        f"{RADICE}/bin/plancia config guardiano solo-registro",
        "python3 -m plancia.cli config guardiano spento",
        "python3 bin/plancia config guardiano spento",
        "python3 plancia/cli.py config guardiano spento",
        "PLANCIA_HOME=/x plancia config guardiano spento",
        "env PLANCIA_HOME=/x plancia config guardiano spento",
        "cd /x && plancia config guardiano spento",
        "plancia config guardiano spento && plancia guardiano --stato",
        "plancia config compartimenti '{}'",
        "plancia config strumenti_drive '[]'",
        "plancia config \"guardiano\" \"spento\"",
        "python3 -c \"from plancia import config; c = config.load_config(); c['guardiano'] = 'spento'; config.save_config(c)\"",
        "python3 - <<'EOF'\nfrom plancia import config\nc = config.load_config()\nc['guardiano'] = 'spento'\nconfig.save_config(c)\nEOF",
        f"python3 -c \"open('{config}', 'w').write('{{}}')\"",
        f"python3 -c \"import json; json.dump({{}}, open('{config}', 'w'))\"",
        f"python3 -c \"import os; os.remove('{copia}')\"",
        f"python3 -c \"from pathlib import Path; Path('{config}').write_text('{{}}')\"",
        f"sed -i '' s/bloccante/spento/ {config}",
        f"echo '{{}}' > {config}",
        f"echo '{{}}' >| {config}",
        f": > {log}",
        f"cat /dev/null > {log}",
        f"printf x >> {log}",
        f"echo x | tee {config}",
        f"echo x | tee -a {log}",
        f"truncate -s 0 {log}",
        f"cp /dev/null {config}",
        f"cp x.json {a.dati}/",
        f"cp {a.manifesto} {config}",
        f"install -m 600 x.json {config}",
        f"rsync x.json {config}",
        f"perl -pi -e 's/a/b/' {config}",
        f"dd if=/dev/null of={config}",
        f"rm {log}",
        f"rm -rf {a.dati}",
        f"mv {config} {config}.old",
        f"mv x.json {a.dati}/",
        f"ln -sf /dev/null {config}",
        f"chmod 000 {config}",
    ]
    # `cp x.json <dati>/` non tocca config.json (nome diverso): si prova sotto;
    # qui il file ha il nome di uno protetto
    spegne = [c for c in spegne if c not in (f"cp x.json {a.dati}/", f"mv x.json {a.dati}/")]
    spegne += [f"cp config.json {a.dati}/", f"mv guardiano.log {a.dati}/"]
    for cmd in spegne:
        r = pred(cmd)
        prova(f"autoprotezione-cli: predefinito, `{cmd[:60].splitlines()[0]}`: negato",
              r.negato, repr(r))
    r = pred("plancia config guardiano spento")
    prova("autoprotezione-cli: il motivo dice che le impostazioni del guardiano si cambiano a mano",
          r.negato and "le impostazioni del guardiano le cambia" in r.motivo
          and "a mano" in r.motivo, r.motivo)
    for cmd in ("plancia config guardiano spento", "python3 -m plancia.cli config guardiano spento",
                f"echo '{{}}' > {config}", f"sed -i '' s/a/b/ {config}",
                f"python3 -c \"open('{config}', 'w')\"", "./bin/plancia config compartimenti '{}'"):
        r = alfa(cmd)
        prova(f"autoprotezione-cli: alfa (un nominato), `{cmd[:52]}`: negato", r.negato, repr(r))
    # tutto lo stato del guardiano e' rimasto com'era
    prova("autoprotezione-cli: config.json e la copia non sono cambiati (il guardiano e' ancora acceso: "
          "una chiamata vietata e' ancora negata)",
          json.loads(config.read_text("utf-8"))["guardiano"] == "bloccante"
          and a.chiama(a.pl("Read", {"file_path": str(a.alfa1 / "segreto.txt")}, sid=S_COMUNE)).negato)
    # la lettura e gli usi ordinari restano ammessi
    for cmd in ("plancia config", "plancia config guardiano", "plancia config compartimenti",
                "plancia config locale it", "plancia config sync_interval_minutes 30",
                "plancia guardiano --stato", "plancia guardiano --registro 20",
                "python3 -m plancia.cli sync --skip-git", "python3 -m pytest tests",
                "git commit -m \"plancia config guardiano spento\"",
                "grep plancia config guardiano.txt", "grep -rn save_config plancia/",
                "echo plancia config guardiano spento",
                f"cat {config}", f"cat {config} 2>/dev/null", f"grep guardiano {config} > /dev/null",
                f"cp {config} /tmp/backup-config.json", f"head -3 {log}", f"wc -l {log}",
                f"python3 -c \"import json; json.load(open('{config}'))\"",
                f"python3 -c \"print(open('{log}').read())\"",
                f"echo x > {a.dati}/altro.txt", f"cp x.json {a.dati}/altro.json",
                f"rm {a.dati}/altro.txt", f"ls -la {a.dati}"):
        r = pred(cmd)
        prova(f"autoprotezione-cli: predefinito, `{cmd[:60]}`: ammesso", r.ammesso, repr(r))
    # gli strumenti di scrittura sui file protetti restano negati (gia' provato altrove),
    # e MultiEdit/NotebookEdit come gli altri
    for tool, ti in (("MultiEdit", {"file_path": str(config), "edits": []}),
                     ("NotebookEdit", {"notebook_path": str(log), "new_source": "x"}),
                     ("Write", {"file_path": str(copia), "content": "{}"})):
        prova(f"autoprotezione-cli: {tool} su un file di stato del guardiano: negato",
              a.chiama(a.pl(tool, ti, sid=S_ALFA_LIBERA, aperta_in=a.alfa1)).negato
              and a.chiama(a.pl(tool, ti, sid=S_COMUNE)).negato)
    # in solo-registro non si nega, ma si scrive la riga
    a.scrivi_config(a.config("solo-registro"))
    n0 = len(a.registro())
    r = pred("plancia config guardiano spento")
    righe = a.registro()
    prova("autoprotezione-cli: in solo-registro il comando e' ammesso e lascia una riga "
          "`avrebbe-negato`", r.ammesso and len(righe) == n0 + 1
          and righe[-1]["esito"] == "avrebbe-negato", str(righe[-1:]))
    a.togli_config()


def _prove_falsi_positivi_bash(prova, a: Ambiente):
    """Il registro deve dire la verita': un comando che non tocca un percorso
    fuori dai permessi non e' un "avrebbe negato". Un percorso vero fuori resta
    negato (la prudenza dove conta)."""
    a.togli_config()
    a.scrivi_config(a.config("bloccante"))
    fuori = str(a.comune / "nota.txt")

    def alfa(cmd, env=None, **kw):
        p = a.pl("Bash", {"command": cmd}, sid=S_ALFA_LIBERA, aperta_in=a.alfa1, **kw)
        if env is not None:
            p["env"] = env
        return a.chiama(p)

    def pred(cmd, **kw):
        return a.chiama(a.pl("Bash", {"command": cmd}, sid=S_COMUNE, aperta_in=a.progetto, **kw))

    ammessi = [
        "echo $HOME", "echo ${HOME} e $USER", "echo \"home: $HOME\"", "printf '%s\\n' $HOME",
        "echo $VARIABILE_INESISTENTE/file", "cat $VARIABILE_INESISTENTE/file",
        "python3 -c \"import os; print(os.listdir('/'))\"",
        "python3 -c \"print(1/2)\"", "ls /", "echo /", "ls -la / | head",
        "cat <<'EOF'\nhello /tmp/foo e /etc/hosts\nEOF",
        "cat > note.txt <<'EOF'\nsee /tmp/foo and " + fuori + "\nEOF",
        "git commit -m \"$(cat <<'EOF'\nfix: legge /tmp/foo e " + fuori + "\nEOF\n)\"",
        "git commit -m \"vedi /tmp/foo\"", "echo \"vedi " + fuori + "\"",
        "cat <<EOF\ndon't touch " + fuori + "\nEOF",
        "cat <<'EOF'\n$(cat " + fuori + ")\nEOF", "cat <<\\EOF\n$(cat " + fuori + ")\nEOF",
        "grep -n x segreto.txt", "sed -n '1,5p' segreto.txt",
    ]
    for cmd in ammessi:
        r = alfa(cmd)
        prova(f"falsi-positivi: alfa, `{cmd[:58].splitlines()[0]}`: ammesso", r.ammesso, repr(r))
    negati = [
        f"cat {fuori}", f"echo x > {fuori}", f"echo ok && cat {fuori}",
        "cat $HOME/appunti.txt", "ls $HOME", "cd $HOME && ls",
        f"python3 -c \"print(open('{fuori}').read())\"",
        f"python3 - <<'EOF'\nprint(open('{fuori}').read())\nEOF",
        f"bash <<'EOF'\ncat {fuori}\nEOF",
        f"sh -c 'cat {fuori}'",
        f"echo $(cat {fuori})", f"echo `cat {fuori}`",
        f"cat <<EOF > {fuori}\nx\nEOF",
        f"cat <<EOF\n$(cat {fuori})\nEOF",
        "find / -name x", "grep -r x /", "ls -R /",
    ]
    for cmd in negati:
        r = alfa(cmd)
        prova(f"falsi-positivi: alfa, `{cmd[:58].splitlines()[0]}`: negato (un percorso vero fuori "
              "dai permessi resta negato)", r.negato, repr(r))
    # l'ambiente del payload, se c'e', espande le variabili
    r = alfa("cat $DOVE/nota.txt", env={"DOVE": str(a.comune)})
    prova("falsi-positivi: una variabile definita nell'ambiente del payload si espande "
          "($DOVE/nota.txt fuori dai permessi): negato", r.negato, repr(r))
    r = alfa("cat $DOVE/segreto.txt", env={"DOVE": str(a.alfa1)})
    prova("falsi-positivi: ...e se punta dentro le sue cartelle: ammesso", r.ammesso, repr(r))
    # /tmp e la cartella temporanea per utente restano fuori dai permessi per
    # scelta (un posto dove passarsi file), ma il motivo non dice che sono di
    # qualcuno
    for cmd in ("tar czf /tmp/x.tgz segreto.txt", "echo x > /tmp/f", "cat /var/folders/xx/f",
                "cat /private/tmp/altro/f"):
        r = alfa(cmd)
        prova(f"falsi-positivi: alfa, `{cmd}`: negato, e il motivo NON dice che appartiene "
              "al predefinito (la cartella temporanea non e' di nessuno)",
              r.negato and "appartiene a predefinito" not in r.motivo
              and "nessun compartimento" in r.motivo and "cartella di sessione" in r.motivo, r.motivo)
    r = alfa("cat /opt/altro/dato.txt")
    prova("falsi-positivi: un percorso del lavoro comune (non temporaneo) dice ancora "
          "`appartiene a predefinito`", r.negato and "appartiene a predefinito" in r.motivo, r.motivo)
    # il predefinito
    dentro_alfa = str(a.alfa1 / "segreto.txt")
    for cmd in ("echo $HOME", "cat <<'EOF'\n" + dentro_alfa + "\nEOF", f"echo {dentro_alfa}",
                f"git commit -m \"nota su {dentro_alfa}\"", "python3 -c \"print(1/2)\"",
                "tar czf /tmp/x.tgz p.txt", "echo x > /tmp/f", "ls /"):
        r = pred(cmd)
        prova(f"falsi-positivi: predefinito, `{cmd[:58].splitlines()[0]}`: ammesso", r.ammesso, repr(r))
    for cmd in (f"cat {dentro_alfa}", f"echo $(cat {dentro_alfa})", f"echo x > {dentro_alfa}",
                f"cat <<EOF > {dentro_alfa}\nx\nEOF",
                f"python3 - <<'EOF'\nprint(open('{dentro_alfa}').read())\nEOF",
                f"grep -r x {a.alfa1}", "find / -name x", "grep -r x /"):
        r = pred(cmd)
        prova(f"falsi-positivi: predefinito, `{cmd[:58].splitlines()[0]}`: negato", r.negato, repr(r))
    a.togli_config()


def _prove_ricerca_trascrizioni(prova, a: Ambiente):
    """`search_session_transcripts` cerca nelle trascrizioni di TUTTE le
    sessioni: negato ai nominati sempre e al predefinito quando esistono
    nominati. `list_sessions` e `ListAgents` restano ammessi al predefinito
    (elenchi, non contenuti: limite dichiarato)."""
    ss = "mcp__ccd_session_mgmt__"
    a.togli_config()
    a.scrivi_config(a.config("bloccante"))
    r = a.chiama(a.pl(ss + "search_session_transcripts", {"query": "segreto"}, sid=S_COMUNE))
    prova("ricerca-trascrizioni: predefinito, search_session_transcripts con nominati: negato",
          r.negato and "alfa" not in r.motivo and "trascrizioni" in r.motivo, repr(r))
    prova("ricerca-trascrizioni: ...anche con un filtro di sessione nel tool_input",
          a.chiama(a.pl(ss + "search_session_transcripts",
                        {"query": "x", "session_id": S_COMUNE}, sid=S_COMUNE)).negato)
    prova("ricerca-trascrizioni: alfa, search_session_transcripts: negato",
          a.chiama(a.pl(ss + "search_session_transcripts", {"query": "x"}, sid=S_ALFA_LIBERA,
                        aperta_in=a.alfa1)).negato)
    prova("ricerca-trascrizioni: predefinito, list_sessions: ammesso (limite dichiarato)",
          a.chiama(a.pl(ss + "list_sessions", {}, sid=S_COMUNE)).ammesso)
    prova("ricerca-trascrizioni: alfa, list_sessions: negato",
          a.chiama(a.pl(ss + "list_sessions", {}, sid=S_ALFA_LIBERA, aperta_in=a.alfa1)).negato)
    a.togli_config()
    a.scrivi_config(a.config("solo-registro"))
    r = a.chiama(a.pl(ss + "search_session_transcripts", {"query": "x"}, sid=S_COMUNE))
    righe = a.registro()
    prova("ricerca-trascrizioni: in solo-registro e' ammesso e la riga e' `avrebbe-negato`",
          r.ammesso and len(righe) == 1 and righe[0]["esito"] == "avrebbe-negato"
          and righe[0]["strumento"].endswith("search_session_transcripts"), str(righe))
    a.togli_config()
    cfg = a.config("bloccante")
    cfg["compartimenti"] = {"predefinito": cfg["compartimenti"]["predefinito"]}
    a.scrivi_config(cfg)
    r = a.chiama(a.pl(ss + "search_session_transcripts", {"query": "x"}, sid=S_COMUNE))
    prova("ricerca-trascrizioni: senza nominati non c'e' niente da proteggere: ammesso",
          r.ammesso, repr(r))
    a.togli_config()


def _prove_cli_config(prova, a: Ambiente):
    """`plancia config guardiano <valore>` rifiuta i valori fuori da
    spento / solo-registro / bloccante (e non salva niente)."""
    a.togli_config()
    env = dict(a.env())
    env["PYTHONPATH"] = str(RADICE)

    def plancia(*args):
        p = subprocess.run([sys.executable, str(RADICE / "bin" / "plancia"), "config", *args],
                           env=env, cwd=str(RADICE), capture_output=True, timeout=60)
        return p.returncode, p.stdout.decode("utf-8", "replace") + p.stderr.decode("utf-8", "replace")

    def valore():
        try:
            return json.loads((a.dati / "config.json").read_text("utf-8")).get("guardiano")
        except (OSError, ValueError):
            return None

    rc, out = plancia("guardiano", "solo-registro")
    prova("cli-config: `config guardiano solo-registro`: accettato e salvato",
          rc == 0 and valore() == "solo-registro", f"{rc} {out}")
    for sbagliato in ("bloccantee", "boh", "", "true", "1", "spento!", "[\"spento\"]"):
        rc, out = plancia("guardiano", sbagliato)
        prova(f"cli-config: `config guardiano {sbagliato!r}`: rifiutato (uscita diversa da 0, "
              "dice i valori ammessi) e il valore salvato non cambia",
              rc != 0 and "spento" in out and "solo-registro" in out and "bloccante" in out
              and valore() == "solo-registro", f"{rc} {out} {valore()}")
    for buono, atteso in (("bloccante", "bloccante"), ("Spento", "spento"),
                          ("\"solo-registro\"", "solo-registro"), (" bloccante ", "bloccante")):
        rc, out = plancia("guardiano", buono)
        prova(f"cli-config: `config guardiano {buono!r}`: accettato, salvato come {atteso!r}",
              rc == 0 and valore() == atteso, f"{rc} {out} {valore()}")
    rc, out = plancia("guardiano")
    prova("cli-config: `config guardiano` senza valore legge e basta (e non cambia niente)",
          rc == 0 and "bloccante" in out and valore() == "bloccante", out)
    rc, out = plancia("locale", "en")
    prova("cli-config: un'altra chiave si scrive come prima (il controllo e' solo sul guardiano)",
          rc == 0 and json.loads((a.dati / "config.json").read_text("utf-8")).get("locale") == "en", out)
    a.togli_config()


# --------------------------------------------------------------------------
# quarto giro
# --------------------------------------------------------------------------

# I 58 idiomi con cui un agente appena rifiutato prova a leggere lo stesso file
# passando il percorso da un comando che lo usa (una pipe, una sostituzione,
# una shell, un heredoc dato a un esecutore). `@@` e' il bersaglio vietato,
# `@D@` una cartella dove chi chiama puo' scrivere. Devono essere tutti negati.
CASI_FLUSSO = [
    "echo @@ | xargs cat",
    "printf 'PFMT' @@ | xargs cat",
    "printf '@@' | xargs -0 cat",
    "echo \"cat @@\" | sh",
    "echo \"cat @@\" | bash",
    "echo 'cat @@' | zsh",
    "echo @@ | while read f; do cat $f; done",
    "f=$(echo @@); cat $f",
    "f=$(echo @@); cat \"$f\"",
    "cat $(echo @@)",
    "cat `echo @@`",
    "echo @@ > @D@/lista; xargs cat < @D@/lista",
    "read f <<< @@; cat $f",
    "eval \"$(cat <<'EOF'\ncat @@\nEOF\n)\"",
    "cat <<'EOF' | bash\ncat @@\nEOF",
    "cat <<'EOF' | sh\ncat @@\nEOF",
    "cat <<EOF > /dev/null\nx\nEOF\ncat @@",
    "cat <<-EOF\n\tx\n\tEOF\ncat @@",
    "bash -s <<'EOF'\ncat @@\nEOF",
    "source /dev/stdin <<'EOF'\ncat @@\nEOF",
    ". /dev/stdin <<'EOF'\ncat @@\nEOF",
    "sh -c \"$(cat <<'EOF'\ncat @@\nEOF\n)\"",
    "xargs -I{} sh -c '{}' <<'EOF'\ncat @@\nEOF",
    "python3 <<'EOF'\nprint(open('@@').read())\nEOF",
    "python3 - <<'EOF'\nimport os\nprint(open(os.path.join('@@')).read())\nEOF",
    "node <<'EOF'\nconsole.log(require('fs').readFileSync('@@','utf8'))\nEOF",
    "ruby <<'EOF'\nputs File.read('@@')\nEOF",
    "perl <<'EOF'\nopen(F,'@@'); print <F>;\nEOF",
    "awk -f - <<'EOF'\nBEGIN{while((getline l < \"@@\")>0) print l}\nEOF",
    "sqlite3 :memory: <<'EOF'\n.read @@\nEOF",
    "ssh localhost <<'EOF'\ncat @@\nEOF",
    "cat << EOF > @D@/s.sh\ncat @@\nEOF\nbash @D@/s.sh",
    "echo 'cat @@' > @D@/s.sh && sh @D@/s.sh",
    "echo 'cat @@' > run.sh && bash run.sh",
    "printf 'cat @@' > @D@/x.sh; . @D@/x.sh",
    "cat -- @@",
    "cat < @@",
    "cat @@/../segreto.txt",
    "tail -n +1 @@",
    "$(echo cat) @@",
    "'cat' @@",
    "c=cat; $c @@",
    "\\cat @@",
    "command cat @@",
    "env cat @@",
    "nice cat @@",
    "time cat @@",
    "sudo cat @@",
    "exec cat @@",
    "builtin echo x; cat @@",
    "{ cat @@; }",
    "( cat @@ )",
    "if true; then cat @@; fi",
    "while false; do :; done; cat @@",
    "cat @@ | head -1",
    "test -f @@ && cat @@",
    "cat @@ 2>&1",
    "cat @@ &",
]


def _prove_flusso_testo(prova, a: Ambiente):
    """Quarto giro, punto 1: il testo di echo/printf e il corpo di un heredoc
    sono inerti SOLO se non arrivano a un comando che li usa. I 58 idiomi del
    tester devono essere negati tutti, dal predefinito (verso alfa) e da alfa
    (verso il comune); gli usi ordinari (echo $HOME, git commit con heredoc,
    heredoc verso un file, echo verso un file) restano ammessi."""
    a.togli_config()
    a.scrivi_config(a.config("bloccante"))
    prova("flusso-testo: la lista dei casi e' di 58 idiomi", len(CASI_FLUSSO) == 58)
    fuori_alfa, fuori_comune = str(a.alfa1 / "segreto.txt"), str(a.comune / "nota.txt")

    def esegui(chi, cmd):
        if chi == "P":
            return a.chiama(a.pl("Bash", {"command": cmd}, sid=S_COMUNE, aperta_in=a.progetto))
        return a.chiama(a.pl("Bash", {"command": cmd}, sid=S_ALFA_LIBERA, aperta_in=a.alfa1))

    passati = {"P": [], "A": []}
    for c in CASI_FLUSSO:
        for chi, tgt, cartella in (("P", fuori_alfa, str(a.progetto)),
                                   ("A", fuori_comune, str(a.alfa1))):
            cmd = c.replace("@@", tgt).replace("PFMT", "%s\\n").replace("@D@", cartella)
            if not esegui(chi, cmd).negato:
                passati[chi].append(cmd[:80])
    prova("flusso-testo: dal predefinito 0 idiomi su 58 passano (verso un file di alfa)",
          not passati["P"], f"{len(passati['P'])} passati: {passati['P'][:6]}")
    prova("flusso-testo: da alfa 0 idiomi su 58 passano (verso un file del comune)",
          not passati["A"], f"{len(passati['A'])} passati: {passati['A'][:6]}")
    for chi, tgt in (("P", fuori_alfa), ("A", fuori_comune)):
        for nome, cmd in (
                ("echo | xargs cat", f"echo {tgt} | xargs cat"),
                ("echo | sh", f"echo \"cat {tgt}\" | sh"),
                ("echo | while read", f"echo {tgt} | while read f; do cat $f; done"),
                ("variabile con $(echo)", f"f=$(echo {tgt}); cat \"$f\""),
                ("apici inversi", f"cat `echo {tgt}`"),
                ("cat <<EOF | bash", f"cat <<'EOF' | bash\ncat {tgt}\nEOF"),
                ("eval con heredoc", f"eval \"$(cat <<'EOF'\ncat {tgt}\nEOF\n)\""),
                ("source /dev/stdin", f"source /dev/stdin <<'EOF'\ncat {tgt}\nEOF")):
            r = esegui(chi, cmd)
            prova(f"flusso-testo: {chi}, {nome}: negato", r.negato, repr(r))
    # gli usi ordinari restano ammessi (i falsi positivi chiusi nel terzo giro)
    nota = str(a.alfa1 / "nota-nuova.txt")
    for cmd in ("echo $HOME", "echo \"vedi " + fuori_comune + "\"",
                "echo \"vedi " + fuori_comune + "\" > " + nota,
                "echo \"vedi " + fuori_comune + "\" > " + nota + " && cat " + nota,
                "printf 'vedi %s' " + fuori_comune + " >> " + nota,
                "cat <<'EOF' > " + nota + "\nvedi " + fuori_comune + "\nEOF",
                "cat > " + nota + " <<'EOF'\nvedi " + fuori_comune + "\nEOF",
                "cat <<'EOF' | git commit -F -\nnota su " + fuori_comune + "\nEOF",
                "git commit -F - <<'EOF'\nnota su " + fuori_comune + "\nEOF",
                "git commit -m \"$(cat <<'EOF'\nnota su " + fuori_comune + "\nEOF\n)\"",
                "cat <<'EOF' | tee " + nota + "\nvedi " + fuori_comune + "\nEOF",
                "cat <<'EOF'\nvedi " + fuori_comune + "\nEOF"):
        r = esegui("A", cmd)
        prova(f"flusso-testo: alfa, `{cmd[:60].splitlines()[0]}...`: ammesso (testo inerte)",
              r.ammesso, repr(r))
    nota_p = str(a.progetto / "nota-nuova.txt")
    for cmd in ("echo \"vedi " + fuori_alfa + "\" > " + nota_p,
                "cat <<'EOF' > " + nota_p + "\nvedi " + fuori_alfa + "\nEOF",
                "git commit -m \"$(cat <<'EOF'\nnota su " + fuori_alfa + "\nEOF\n)\"",
                "echo \"vedi " + fuori_alfa + "\"", "ls /"):
        r = esegui("P", cmd)
        prova(f"flusso-testo: predefinito, `{cmd[:60].splitlines()[0]}...`: ammesso",
              r.ammesso, repr(r))
    a.togli_config()


def _prove_cd_variabili(prova, a: Ambiente):
    """Quarto giro, punto 2: la cartella e le variabili si simulano lungo il
    comando (`cd X && ...`, `cd X; ...`, `pushd`, subshell, `VAR=x; ...`)."""
    a.togli_config()
    a.scrivi_config(a.config("bloccante"))
    r_ = str(a.radice)
    enc = _codifica(a.alfa1)
    proj = str(a.claude / "projects")
    dati = str(a.dati)
    (a.claude / "projects" / enc / "memory").mkdir(parents=True, exist_ok=True)
    (a.claude / "projects" / enc / "memory" / "MEMORY.md").write_text("ricordo", "utf-8")
    (a.claude / "projects" / enc / "sess-1.jsonl").write_text("{}", "utf-8")

    def pred(cmd, cwd=None, aperta_in=None):
        return a.chiama(a.pl("Bash", {"command": cmd}, sid=S_COMUNE,
                             aperta_in=aperta_in or a.comune, cwd=cwd or a.radice))

    negati = [
        f"cd {r_} && cat alfa-uno/segreto.txt", f"cd {r_} && ls alfa-uno",
        f"cd {r_} && cat */segreto.txt", f"cd {r_}; cat alfa-uno/segreto.txt",
        f"cd {r_}\ncat alfa-uno/segreto.txt", f"(cd {r_}; cat alfa-uno/segreto.txt)",
        f"pushd {r_} >/dev/null; cat alfa-uno/segreto.txt",
        f"cd {r_}; python3 -c \"print(open('alfa-uno/segreto.txt').read())\"",
        f"cd {r_}/alfa-uno/.. && cat alfa-uno/segreto.txt",
        f"d={r_}; cat \"$d/alfa-uno/segreto.txt\"",
        f"export d={r_}; cat $d/alfa-uno/segreto.txt", f"P={r_} && cat $P/alfa-uno/segreto.txt",
        f"cd {proj} && cat {enc}/memory/MEMORY.md", f"cd {proj} && cat *alfa*/sess-1.jsonl",
        f"cd {proj} && grep -r segreto .", f"cd {a.claude} && cat projects/{enc}/memory/MEMORY.md",
        # la cartella che non si sa: si nega (prudenza)
        "cd - && cat alfa-uno/segreto.txt", "cd $DIR_NON_DEFINITA && cat alfa-uno/segreto.txt",
        f"cd {a.progetto} || cd {r_}; cat alfa-uno/segreto.txt",
        # una subshell non sposta niente: dopo, si e' ancora dove si era
        f"(cd {a.progetto}); cat alfa-uno/segreto.txt",
    ]
    for cmd in negati:
        r = pred(cmd)
        prova(f"cd: predefinito (cwd sopra alfa), `{cmd[:66].splitlines()[0]}`: negato",
              r.negato, repr(r))
    # il falso positivo opposto: `cd` dentro una cartella senza divieti e ricerca li'
    for cmd in ("cd progetto && grep -rn x .", "cd progetto && find . -name '*.txt'",
                "cd progetto && rg x", "cd progetto && ls -R", "cd progetto && cat p.txt",
                "cd progetto; cat p.txt", "cd progetto && git grep x || true",
                "d=progetto; cat $d/p.txt", "cd progetto && cd .. && ls progetto",
                f"cd {a.progetto} && grep -rn x ."):
        r = pred(cmd, cwd=a.comune)
        prova(f"cd: predefinito (cwd che contiene percorsi vietati), `{cmd}`: ammesso "
              "(la cartella simulata non ha divieti sotto)", r.ammesso, repr(r))
    prova("cd: `grep -rn x .` senza `cd` dalla stessa cwd: negato (il `cd` e' quello che lo cambia)",
          pred("grep -rn x .", cwd=a.comune).negato)
    # il nominato
    def alfa(cmd, aperta_in=None, cwd=None, sid=S_ALFA_LIBERA):
        return a.chiama(a.pl("Bash", {"command": cmd}, sid=sid,
                             aperta_in=aperta_in or a.alfa1, cwd=cwd))

    r = alfa(f"cd {a.alfa2} && cat due.txt")
    prova("cd: alfa, `cd <sua cartella> && cat due.txt`: ammesso", r.ammesso, repr(r))
    r = alfa(f"cd {a.comune} && cat nota.txt")
    prova("cd: alfa, `cd <comune> && cat nota.txt`: negato", r.negato, repr(r))
    r = alfa("cd .. && ls")
    prova("cd: alfa, `cd .. && ls`: negato", r.negato, repr(r))
    r = alfa("cd - && ls sotto/")
    prova("cd: alfa, `cd - && ls sotto/`: negato (cartella sconosciuta e un relativo con una barra)",
          r.negato and "non si sa determinare" in r.motivo, repr(r))
    r = alfa("cd - && ls")
    prova("cd: alfa, `cd - && ls`: ammesso (sesto giro: un nome semplice dopo una cartella "
          "sconosciuta non nega)", r.ammesso, repr(r))
    r = alfa(f"cd {a.alfa1} && cat segreto.txt", aperta_in=a.comune, sid=S_ALFA)
    prova("cd: alfa aperta fuori, `cd <sua cartella> && cat segreto.txt`: ammesso "
          "(parte da dentro)", r.ammesso, repr(r))
    r = alfa("cat segreto.txt", aperta_in=a.comune, sid=S_ALFA)
    prova("cd: ...e senza il `cd` resta negato (la cwd e' fuori)", r.negato, repr(r))
    # l'autoprotezione non si aggira entrando nella cartella dei dati
    for cmd in (f"cd {dati} && sed -i '' s/bloccante/spento/ config.json",
                f"cd {dati}; sed -i '' s/a/b/ config.json",
                f"cd {dati} && echo '{{}}' > config.json",
                f"(cd {dati} && rm config.json)", f"cd {dati} && rm -rf .",
                f"cd {dati} && rm -f *", f"F=config.json; cd {dati}; rm $F",
                f"cd {dati} && mv config.json x", f"cd {dati}\nprintf x >> guardiano.log",
                f"cd {dati} && truncate -s0 config.json", f"pushd {dati}; rm config.json"):
        for chi, kw in (("predefinito", dict(sid=S_COMUNE, aperta_in=a.progetto)),
                        ("alfa", dict(sid=S_ALFA_LIBERA, aperta_in=a.alfa1))):
            r = a.chiama(a.pl("Bash", {"command": cmd}, **kw))
            prova(f"cd: {chi}, `{cmd[:60].splitlines()[0]}`: negato", r.negato, repr(r))
    r = a.chiama(a.pl("Bash", {"command": f"cd {dati} && cat config.json"}, sid=S_COMUNE,
                      aperta_in=a.progetto))
    prova("cd: ...la lettura della config dopo un `cd` resta ammessa", r.ammesso, repr(r))
    a.togli_config()


def _copia_checkout(a: Ambiente, dove: Path, completa=False):
    """Una copia minima del checkout da cui gira l'hook (`bin/` e `plancia/`),
    per romperla senza toccare quella vera. Con `completa` tutto il pacchetto."""
    shutil.copytree(RADICE / "bin", dove / "bin", ignore=shutil.ignore_patterns("__pycache__"))
    (dove / "plancia").mkdir()
    for f in (RADICE / "plancia").iterdir():
        if f.is_file() and f.suffix in (".py", ".json") and (
                completa or f.name in ("__init__.py", "compartimenti.py")):
            shutil.copy(f, dove / "plancia" / f.name)
    return dove / "bin" / "plancia-guardiano"


def _prove_non_parte(prova, a: Ambiente):
    """Quarto giro, punto 3: il guardiano che non parte non e' silenzioso. Resta
    fail-open (rc 0, nessun diniego), ma scrive `guardiano-non-parte` nel
    registro, avvisa l'utente con `systemMessage`, e `plancia guardiano --stato`
    lo mostra. Un `json.py` o un `re.py` accanto non lo spengono piu'."""
    a.togli_config()
    a.scrivi_config(a.config("bloccante"))
    base = a.radice / "copia-hook"
    hook = _copia_checkout(a, base)
    seg = a.pl("Bash", {"command": f"cat {a.alfa1}/segreto.txt"}, sid=S_COMUNE, aperta_in=a.progetto)

    def corri(payload=seg):
        t0 = time.time()
        p = subprocess.run([PYTHON, str(hook)], input=json.dumps(payload).encode(),
                           capture_output=True, env=a.env(), timeout=60)
        return Esito(p.returncode, p.stdout.decode("utf-8", "replace"),
                     p.stderr.decode("utf-8", "replace"), time.time() - t0)

    r = corri()
    prova("non-parte: la copia intera nega (rc 0 con diniego)", r.negato, repr(r))
    # un json.py nella radice e un re.py in bin/ non prendono il posto dei moduli di sistema
    (base / "json.py").write_text("raise SystemExit(0)\n", "utf-8")
    (base / "bin" / "re.py").write_text("raise SystemExit(0)\n", "utf-8")
    (base / "bin" / "shlex.py").write_text("raise SystemExit(0)\n", "utf-8")
    r = corri()
    prova("non-parte: json.py nella radice, re.py e shlex.py in bin/: l'hook nega lo stesso",
          r.negato, repr(r))
    os.remove(base / "json.py")
    os.remove(base / "bin" / "re.py")
    os.remove(base / "bin" / "shlex.py")
    log = a.dati / "guardiano.log"
    guasti = {
        "un refuso in plancia/__init__.py": lambda: (base / "plancia" / "__init__.py").write_text(
            '__version__ = "1.1.0"\nsyntax error here (\n', "utf-8"),
        "compartimenti.py che manca": lambda: os.remove(base / "plancia" / "compartimenti.py"),
    }
    ripristini = {
        "un refuso in plancia/__init__.py": lambda: shutil.copy(
            RADICE / "plancia" / "__init__.py", base / "plancia" / "__init__.py"),
        "compartimenti.py che manca": lambda: shutil.copy(
            RADICE / "plancia" / "compartimenti.py", base / "plancia" / "compartimenti.py"),
    }
    for guasto, rompi in guasti.items():
        righe0 = len(a.registro())
        marca = a.dati / "guardiano.non-parte"
        if marca.exists():
            marca.unlink()
        rompi()
        r = corri()
        righe = a.registro()
        nuove = [x for x in righe[righe0:] if x.get("esito") == "guardiano-non-parte"]
        prova(f"non-parte: {guasto}: rc 0 e nessun diniego (fail-open)",
              r.rc == 0 and not r.negato, repr(r))
        prova(f"non-parte: {guasto}: una riga `guardiano-non-parte` nel registro",
              len(nuove) == 1 and "guardiano-non-parte" in nuove[0].get("motivo", ""), str(righe[righe0:]))
        try:
            avviso = json.loads(r.out).get("systemMessage", "")
        except ValueError:
            avviso = ""
        prova(f"non-parte: {guasto}: stdout e' JSON con `systemMessage` per l'utente",
              "plancia-guardiano non parte" in avviso and "NON sono protetti" in avviso, r.out[:200])
        r2 = corri()
        prova(f"non-parte: {guasto}: una seconda chiamata subito dopo non riscrive la riga "
              "ne' rimanda l'avviso (limite come per la config illeggibile)",
              r2.rc == 0 and r2.out == ""
              and len([x for x in a.registro() if x.get("esito") == "guardiano-non-parte"]) == len(
                  [x for x in righe if x.get("esito") == "guardiano-non-parte"]),
              repr(r2))
        env = dict(a.env())
        p = subprocess.run([PYTHON, str(RADICE / "bin" / "plancia"), "guardiano", "--stato"],
                           env=env, capture_output=True, timeout=60)
        out = p.stdout.decode("utf-8", "replace")
        prova(f"non-parte: {guasto}: `plancia guardiano --stato` la mostra",
              p.returncode == 0 and "ATTENZIONE" in out and "NON PARTE" in out
              and "guardiano-non-parte" in out, out[:300])
        ripristini[guasto]()
    r = corri()
    prova("non-parte: riparato, l'hook torna a negare", r.negato, repr(r))
    # in `spento` un guasto non lascia niente: non fa danno
    a.scrivi_config(a.config("spento"))
    n0 = len(a.registro())
    (base / "plancia" / "__init__.py").write_text("syntax error here (\n", "utf-8")
    marca = a.dati / "guardiano.non-parte"
    if marca.exists():
        marca.unlink()
    r = corri()
    prova("non-parte: guardiano `spento` e pacchetto rotto: niente riga, niente avviso, rc 0",
          r.ammesso and len(a.registro()) == n0, repr(r))
    # senza config (guardiano mai acceso) neppure
    (a.dati / "config.json").unlink()
    r = corri()
    prova("non-parte: senza config e pacchetto rotto: niente riga, niente avviso, rc 0",
          r.ammesso and len(a.registro()) == n0, repr(r))
    # una config illeggibile potrebbe essere accesa: si avvisa
    a.scrivi_config("{ non json")
    if marca.exists():
        marca.unlink()
    r = corri()
    prova("non-parte: config illeggibile e pacchetto rotto: si avvisa (potrebbe essere acceso)",
          r.rc == 0 and "systemMessage" in r.out, repr(r))
    # `plancia guardiano --stato` senza il modulo: lo dice lo stesso
    a.togli_config()
    a.scrivi_config(a.config("bloccante"))
    completa = a.radice / "copia-completa"
    completa.mkdir()
    _copia_checkout(a, completa, completa=True)
    (completa / "plancia" / "compartimenti.py").write_text("syntax error here (\n", "utf-8")
    log.write_text(json.dumps({"ts": "2999-01-01T00:00:00Z", "esito": "guardiano-non-parte",
                               "motivo": "guardiano-non-parte: SyntaxError: finto"}) + "\n", "utf-8")
    p = subprocess.run([PYTHON, str(completa / "bin" / "plancia"), "guardiano", "--stato"],
                       env=dict(a.env()), capture_output=True, timeout=60)
    out = p.stdout.decode("utf-8", "replace")
    prova("non-parte: `--stato` con compartimenti.py che non si importa lo dice e mostra "
          "l'ultima riga del guasto",
          "non si importa" in out and "SyntaxError: finto" in out, out[:300])
    # i file da cui l'hook dipende non si scrivono da una sessione
    for chi, kw in (("predefinito", dict(sid=S_COMUNE, aperta_in=a.progetto)),
                    ("alfa", dict(sid=S_ALFA_LIBERA, aperta_in=a.alfa1))):
        for f in ("plancia/__init__.py", "plancia/config.py", "plancia/compartimenti.py",
                  "bin/plancia-guardiano", "bin/re.py", "bin/nuovo.py", "json.py",
                  "sitecustomize.py", "json/__init__.py"):
            r = a.chiama(a.pl("Write", {"file_path": str(RADICE / f), "content": "x"}, **kw))
            prova(f"non-parte: {chi}, Write su {f}: negato", r.negato, repr(r))
        r = a.chiama(a.pl("Edit", {"file_path": str(RADICE / "plancia" / "__init__.py"),
                                   "old_string": "1.1.0", "new_string": "9"}, **kw))
        prova(f"non-parte: {chi}, Edit di plancia/__init__.py: negato", r.negato, repr(r))
        for cmd in (f"echo x >> {RADICE}/plancia/__init__.py", f"cp x {RADICE}/json.py",
                    f"sed -i '' s/a/b/ {RADICE}/plancia/config.py", f"touch {RADICE}/bin/re.py",
                    f"cd {RADICE}/bin && echo x > re.py", f"rm {RADICE}/plancia/__init__.py"):
            r = a.chiama(a.pl("Bash", {"command": cmd}, **kw))
            prova(f"non-parte: {chi}, `{cmd[:56]}`: negato", r.negato, repr(r))
    r = a.chiama(a.pl("Write", {"file_path": str(RADICE / "plancia" / "store.py"),
                                "content": "x"}, sid=S_COMUNE, aperta_in=a.progetto))
    prova("non-parte: un altro modulo del pacchetto (store.py) non e' protetto: ammesso",
          r.ammesso, repr(r))
    r = a.chiama(a.pl("Bash", {"command": f"cat {RADICE}/plancia/__init__.py"},
                      sid=S_COMUNE, aperta_in=a.progetto))
    prova("non-parte: leggere plancia/__init__.py resta ammesso", r.ammesso, repr(r))
    a.togli_config()


def _prove_config_illeggibile(prova, a: Ambiente):
    """Quarto giro, punto 4a: `plancia config <chiave>` su un config.json che non
    si legge non lo riscrive con i default (cancellerebbe guardiano,
    compartimenti, esclusi): esce 2 senza scrivere."""
    a.togli_config()
    env = dict(a.env())
    env["PYTHONPATH"] = str(RADICE)
    guasto = ('{"guardiano": "bloccante", "cartelle_escluse": ["/x"], "compartimenti": '
              '{"alfa": {"cartelle": ["/a"]}},}')
    (a.dati / "config.json").write_text(guasto, "utf-8")

    def plancia(*args):
        p = subprocess.run([sys.executable, str(RADICE / "bin" / "plancia"), "config", *args],
                           env=env, cwd=str(RADICE), capture_output=True, timeout=60)
        return p.returncode, p.stdout.decode("utf-8", "replace") + p.stderr.decode("utf-8", "replace")

    for args in (("port", "9999"), ("guardiano", "spento"), ("locale", "en")):
        rc, out = plancia(*args)
        prova(f"config-illeggibile: `config {' '.join(args)}` su un config.json rotto: "
              "uscita 2, dice di ripararlo, il file non cambia",
              rc == 2 and "riparalo a mano" in out
              and (a.dati / "config.json").read_text("utf-8") == guasto, f"{rc} {out}")
    rc, out = plancia("port")
    prova("config-illeggibile: la lettura (`config port`) non scrive e non fallisce",
          rc == 0 and (a.dati / "config.json").read_text("utf-8") == guasto, f"{rc} {out}")
    codice = ("from plancia import config\n"
              "try:\n    config.save_config({'port': 1})\n"
              "except config.ConfigIlleggibile as e:\n    print('rifiutato')\n")
    p = subprocess.run([sys.executable, "-c", codice], env=env, cwd=str(RADICE),
                       capture_output=True, timeout=60)
    prova("config-illeggibile: `save_config` solleva ConfigIlleggibile e non scrive",
          b"rifiutato" in p.stdout and (a.dati / "config.json").read_text("utf-8") == guasto,
          p.stdout.decode() + p.stderr.decode())
    (a.dati / "config.json").write_text("[1, 2]", "utf-8")
    rc, out = plancia("port", "9999")
    prova("config-illeggibile: un config.json che e' JSON ma non un oggetto: rifiutato uguale",
          rc == 2 and (a.dati / "config.json").read_text("utf-8") == "[1, 2]", f"{rc} {out}")
    (a.dati / "config.json").write_text('{"guardiano": "solo-registro", "port": 1}', "utf-8")
    rc, out = plancia("port", "9999")
    valori = json.loads((a.dati / "config.json").read_text("utf-8"))
    prova("config-illeggibile: riparato, `config port 9999` scrive e conserva il resto",
          rc == 0 and valori.get("port") == 9999 and valori.get("guardiano") == "solo-registro",
          f"{rc} {out} {valori}")
    a.togli_config()
    rc, out = plancia("port", "8888")
    prova("config-illeggibile: senza config.json `config port 8888` lo crea (nessun guasto)",
          rc == 0 and json.loads((a.dati / "config.json").read_text("utf-8")).get("port") == 8888,
          f"{rc} {out}")
    a.togli_config()


VOCE_GUARDIANO = str(RADICE / "bin" / "plancia-guardiano")


def _settings(extra=None, con_voce=True):
    d = {"theme": "dark"}
    if con_voce:
        d["hooks"] = {"PreToolUse": [{"matcher": "*", "hooks": [
            {"type": "command", "command": VOCE_GUARDIANO}]}]}
    d.update(extra or {})
    return json.dumps(d, indent=2)


def _prove_settings(prova, a: Ambiente):
    """Quarto giro, punto 4b: settings.json e settings.local.json (di ~, di
    CLAUDE_CONFIG_DIR e dei progetti) sono protetti in modo MIRATO: Write/Edit/
    MultiEdit passano solo se il risultato ha ancora la voce PreToolUse del
    guardiano e non ha disableAllHooks a vero; Bash che li scrive e' negato con
    l'invito a usare Edit."""
    a.togli_config()
    a.scrivi_config(a.config("bloccante"))
    utente = a.claude / "settings.json"
    utente.write_text(_settings(), "utf-8")
    home_locale = a.home / ".claude" / "settings.local.json"
    home_locale.parent.mkdir(parents=True, exist_ok=True)
    home_locale.write_text(_settings(con_voce=False), "utf-8")
    proj = a.progetto / ".claude" / "settings.local.json"
    proj.parent.mkdir(parents=True, exist_ok=True)
    proj.write_text('{"permissions": {"allow": ["Bash(ls:*)"]}}', "utf-8")
    dentro_alfa = a.alfa1 / ".claude" / "settings.local.json"
    dentro_alfa.parent.mkdir(parents=True, exist_ok=True)
    dentro_alfa.write_text("{}", "utf-8")

    def pred(tool, ti):
        return a.chiama(a.pl(tool, ti, sid=S_COMUNE, aperta_in=a.progetto))

    def alfa(tool, ti):
        return a.chiama(a.pl(tool, ti, sid=S_ALFA_LIBERA, aperta_in=a.alfa1))

    # Write
    r = pred("Write", {"file_path": str(utente), "content": _settings({"model": "sonnet"})})
    prova("settings: Write di ~/.claude/settings.json che tiene la voce del guardiano e cambia "
          "altro: ammesso", r.ammesso, repr(r))
    r = pred("Write", {"file_path": str(utente), "content": json.dumps({"theme": "dark"})})
    prova("settings: Write che toglie la voce del guardiano: negato, dice perche'",
          r.negato and "plancia-guardiano" in r.motivo, repr(r))
    r = pred("Write", {"file_path": str(utente), "content": _settings({"disableAllHooks": True})})
    prova("settings: Write con disableAllHooks true: negato",
          r.negato and "disableAllHooks" in r.motivo, repr(r))
    r = pred("Write", {"file_path": str(utente), "content": "{ non json"})
    prova("settings: Write di un JSON rotto che perde la voce: negato", r.negato, repr(r))
    r = pred("Write", {"file_path": str(utente), "content": _settings({"disableAllHooks": False})})
    prova("settings: Write con disableAllHooks false: ammesso", r.ammesso, repr(r))
    # Edit / MultiEdit
    r = pred("Edit", {"file_path": str(utente), "old_string": '"theme": "dark"',
                      "new_string": '"theme": "light"'})
    prova("settings: Edit di un'altra chiave (chi modifica settings.json per altri motivi "
          "non inciampa): ammesso", r.ammesso, repr(r))
    r = pred("Edit", {"file_path": str(utente), "old_string": VOCE_GUARDIANO,
                      "new_string": "/usr/bin/true"})
    prova("settings: Edit che sostituisce il comando del guardiano: negato", r.negato, repr(r))
    r = pred("Edit", {"file_path": str(utente), "old_string": '"theme": "dark"',
                      "new_string": '"theme": "dark", "disableAllHooks": true'})
    prova("settings: Edit che aggiunge disableAllHooks true: negato", r.negato, repr(r))
    r = pred("Edit", {"file_path": str(utente), "old_string": "testo-che-non-c-e",
                      "new_string": "x"})
    prova("settings: Edit con un old_string che non c'e' (lo strumento fallira' da solo): ammesso",
          r.ammesso, repr(r))
    r = pred("MultiEdit", {"file_path": str(utente), "edits": [
        {"old_string": '"theme": "dark"', "new_string": '"theme": "light"'},
        {"old_string": VOCE_GUARDIANO, "new_string": "/usr/bin/true"}]})
    prova("settings: MultiEdit dove la seconda modifica toglie la voce: negato", r.negato, repr(r))
    r = pred("MultiEdit", {"file_path": str(utente), "edits": [
        {"old_string": '"theme": "dark"', "new_string": '"theme": "light"'}]})
    prova("settings: MultiEdit innocuo: ammesso", r.ammesso, repr(r))
    # settings.local.json e i progetti
    r = pred("Write", {"file_path": str(home_locale), "content": '{"disableAllHooks": true}'})
    prova("settings: Write di ~/.claude/settings.local.json con disableAllHooks true: negato",
          r.negato, repr(r))
    r = pred("Write", {"file_path": str(home_locale), "content": '{"permissions": {}}'})
    prova("settings: ...ma un altro contenuto (senza obbligo della voce) e' ammesso",
          r.ammesso, repr(r))
    r = pred("Write", {"file_path": str(proj), "content": '{"disableAllHooks": true}'})
    prova("settings: Write di <progetto>/.claude/settings.local.json con disableAllHooks true: negato",
          r.negato, repr(r))
    r = pred("Write", {"file_path": str(proj), "content": '{"permissions": {"allow": []}}'})
    prova("settings: ...e senza: ammesso", r.ammesso, repr(r))
    r = pred("Write", {"file_path": str(a.progetto / ".claude" / "settings.json"),
                       "content": '{"disableAllHooks": true}'})
    prova("settings: settings.json di un progetto con disableAllHooks true: negato", r.negato, repr(r))
    r = alfa("Write", {"file_path": str(dentro_alfa), "content": '{"disableAllHooks": true}'})
    prova("settings: alfa, settings.local.json dentro la sua cartella con disableAllHooks: negato",
          r.negato, repr(r))
    r = alfa("Write", {"file_path": str(dentro_alfa), "content": '{"permissions": {}}'})
    prova("settings: alfa, ...senza: ammesso", r.ammesso, repr(r))
    # Bash
    tmp = str(a.progetto / "s.json")
    negati = [
        f"sed -i '' s/plancia-guardiano/x/ {utente}", f"sed -i.bak s/a/b/ {utente}",
        f"jq 'del(.hooks)' {utente} > {tmp} && mv {tmp} {utente}",
        f"jq 'del(.hooks)' {utente} | sponge {utente}", f"echo '{{}}' > {utente}",
        f"echo '{{}}' | tee {utente}", f"cp {tmp} {utente}", f"mv {tmp} {utente}",
        f"cat {tmp} > {home_locale}", f"echo '{{\"disableAllHooks\": true}}' > {proj}",
        f"python3 -c \"open('{utente}', 'w').write('{{}}')\"",
        f"cd {a.claude} && sed -i '' s/a/b/ settings.json", f"rm {utente}", f"rm -rf {a.claude}",
        f"perl -pi -e 's/a/b/' {proj}",
    ]
    for cmd in negati:
        r = pred("Bash", {"command": cmd})
        prova(f"settings: Bash `{cmd[:62]}`: negato, con l'invito a usare Edit",
              r.negato and "Edit" in r.motivo, repr(r))
    for cmd in (f"cat {utente}", f"jq . {utente}", f"grep hooks {utente}", f"head {proj}",
                f"cp {utente} {a.progetto}/copia-settings.json", f"jq .hooks {utente} > {tmp}"):
        r = pred("Bash", {"command": cmd})
        prova(f"settings: Bash `{cmd[:62]}` (lettura): ammesso", r.ammesso, repr(r))
    # in solo-registro non si nega ma si scrive la riga
    a.scrivi_config(a.config("solo-registro"))
    n0 = len(a.registro())
    r = pred("Write", {"file_path": str(utente), "content": "{}"})
    righe = a.registro()
    prova("settings: in solo-registro il Write che spegne e' ammesso e lascia `avrebbe-negato`",
          r.ammesso and len(righe) == n0 + 1 and righe[-1]["esito"] == "avrebbe-negato", str(righe[-1:]))
    a.togli_config()


def _prove_interpreti_e_scritture(prova, a: Ambiente):
    """Quarto giro, punti 4c e 4d: interpreti con il percorso costruito e altre
    scritture nella cartella dei dati di Plancia, negate a TUTTE le sessioni."""
    a.togli_config()
    a.scrivi_config(a.config("bloccante"))
    dati, cfg = str(a.dati), str(a.dati / "config.json")
    p = str(a.progetto)

    def pred(cmd):
        return a.chiama(a.pl("Bash", {"command": cmd}, sid=S_COMUNE, aperta_in=a.progetto))

    def alfa(cmd):
        return a.chiama(a.pl("Bash", {"command": cmd}, sid=S_ALFA_LIBERA, aperta_in=a.alfa1))

    costruiti = [
        "python3 -c \"from plancia.cli import main; main(['config','guardiano','spento'])\"",
        "python3 -c \"import sys; sys.argv=['plancia','config','guardiano','spento']; "
        "from plancia.cli import main; main()\"",
        "python3 -c \"from plancia import config as c; c.CONFIG_FILE.write_text('{}')\"",
        "python3 -c \"import os; p=os.path.join(os.environ['PLANCIA_HOME'],'config.json'); "
        "open(p,'w').write('{}')\"",
        "python3 - <<'PY'\nimport json,os\np=os.path.expanduser('~/.plancia/config.json')\n"
        "d=json.load(open(p)); d['guardiano']='spento'; json.dump(d,open(p,'w'))\nPY",
        "node -e \"require('fs').writeFileSync(process.env.HOME+'/.plancia/config.json','{}')\"",
        "ruby -e \"File.write(ENV['HOME']+'/.plancia/config.json','{}')\"",
        "perl -e 'open(F,\">$ENV{HOME}/.plancia/config.json\");print F \"{}\"'",
        "$(which plancia) config guardiano spento",
        "P=$(which plancia); $P config guardiano spento",
        "`which plancia` config guardiano spento",
        "$(command -v plancia) config compartimenti '{}'",
    ]
    for cmd in costruiti:
        for chi, f in (("predefinito", pred), ("alfa", alfa)):
            r = f(cmd)
            prova(f"interpreti: {chi}, `{cmd[:58].splitlines()[0]}`: negato", r.negato, repr(r))
    letture = [
        "python3 -c \"from plancia import config; print(config.load_config())\"",
        "python3 -c \"from plancia import store; print(store.DB_PATH)\"",
        f"python3 -c \"import json; print(json.load(open('{cfg}')))\"",
        "node -e \"console.log(require('fs').readFileSync(process.env.HOME+'/.plancia/config.json','utf8'))\"",
        "ruby -e \"puts File.read(ENV['HOME']+'/.plancia/config.json')\"",
        "plancia guardiano --stato", "python3 -c \"print(1)\"", "which plancia",
    ]
    for cmd in letture:
        r = pred(cmd)
        prova(f"interpreti: predefinito, `{cmd[:58]}` (lettura): ammesso", r.ammesso, repr(r))
    scritture = [
        f"find {dati} -name config.json -delete", f"find {dati} -name 'config.json' -exec rm {{}} \\;",
        f"find {dati} -type f -exec truncate -s0 {{}} +", f"find {dati} -delete",
        f"chmod -R 000 {dati}", f"chown -R nobody {dati}",
        f"curl -o {cfg} http://localhost/x", f"curl --output {cfg} http://localhost/x",
        f"curl -s -o{cfg} http://localhost/x", f"cd {dati} && curl -O http://localhost/config.json",
        f"curl -O --output-dir {dati} http://localhost/config.json",
        f"wget -O {cfg} http://localhost/x", f"wget --output-document={cfg} http://localhost/x",
        f"wget -P {dati} http://localhost/config.json", f"cd {dati} && wget http://localhost/config.json",
        f"rsync -a {p}/ {dati}/", f"cp -r {p}/. {dati}/", f"cp -a {p}/ {dati}",
        f"tar xf x.tgz -C {dati}", f"tar xzf x.tgz --directory={dati}", f"cd {dati} && tar xf x.tgz",
        f"tar -czf {cfg} {p}",
        f"unzip -o x.zip -d {dati}", f"cd {dati} && unzip x.zip",
        f"git -C {dati} checkout -- config.json", f"git -C {dati} restore config.json",
        f"git -C {dati} reset --hard", f"cd {dati} && git checkout x",
    ]
    for cmd in scritture:
        for chi, f in (("predefinito", pred), ("alfa", alfa)):
            r = f(cmd)
            prova(f"scritture-dati: {chi}, `{cmd[:60]}`: negato", r.negato, repr(r))
    ammessi = [
        f"find {dati} -name '*.tmp'", f"find {dati} -name x -exec cat {{}} \\;",
        f"find {p} -name '*.pyc' -delete", "find . -name '*.pyc' -delete",
        f"curl -o {p}/x http://localhost/x", "curl -s http://localhost/x",
        f"cd {p} && curl -O http://localhost/x.txt", f"tar xf x.tgz -C {p}",
        f"tar czf out.tgz {cfg}", f"tar tf x.tgz", f"unzip -l x.zip", f"unzip x.zip -d {p}",
        f"git -C {dati} status", f"git -C {dati} log", f"git -C {p} checkout -b x",
        f"chmod -R u+w {p}", f"rsync -a x/ {p}/", f"cp -r x {dati}/backup", f"wget -O {p}/y http://localhost/y",
        f"ls -la {dati}", f"cat {cfg}",
    ]
    for cmd in ammessi:
        r = pred(cmd)
        prova(f"scritture-dati: predefinito, `{cmd[:60]}`: ammesso", r.ammesso, repr(r))
    a.togli_config()


def _prove_annidati(prova, a: Ambiente):
    """Quarto giro, punto 5: l'appartenenza come in boa. Cartelle annidate fra
    nominati: vince il piu' specifico (per componenti, indipendente dall'ordine
    della config); due nominati sulla stessa cartella sono incerti; l'id della
    madre di un subagente conta solo se il transcript esiste davvero."""
    nido = a.radice / "nido"
    interno = nido / "interno"
    doppia = a.radice / "doppia"
    for d in (interno / "x", nido / "altro", doppia):
        d.mkdir(parents=True, exist_ok=True)
    (nido / "f.txt").write_text("di gamma", "utf-8")
    (nido / "altro" / "g.txt").write_text("di gamma", "utf-8")
    (interno / "h.txt").write_text("di delta", "utf-8")
    (interno / "x" / "k.txt").write_text("di delta", "utf-8")
    (doppia / "d.txt").write_text("incerto", "utf-8")

    def config(ordine, doppi=False):
        comp = {}
        for nome in ordine:
            comp[nome] = {"cartelle": [str(nido) if nome == "gamma" else str(interno)]}
        if doppi:
            comp["uno"] = {"cartelle": [str(doppia)]}
            comp["due"] = {"cartelle": [str(doppia)]}
        comp["predefinito"] = {"manifesto_divieti": "", "divieti": [], "comandi_vietati": []}
        return {"guardiano": "bloccante", "compartimenti": comp}

    def sess(tool, ti, aperta_in, sid="s-annidata"):
        return a.chiama(a.pl(tool, ti, sid=sid, aperta_in=aperta_in))

    for ordine in (("gamma", "delta"), ("delta", "gamma")):
        a.togli_config()
        a.scrivi_config(config(ordine))
        et = "/".join(ordine)
        r = sess("Read", {"file_path": str(interno / "h.txt")}, interno / "x")
        prova(f"annidati ({et}): una sessione in nido/interno/x e' di delta: Read di interno/h: ammesso",
              r.ammesso, repr(r))
        r = sess("Read", {"file_path": str(nido / "f.txt")}, interno / "x")
        prova(f"annidati ({et}): ...e non entra in nido (di gamma): negato, appartiene a gamma",
              r.negato and "appartiene a gamma" in r.motivo, repr(r))
        r = sess("Read", {"file_path": str(nido / "altro" / "g.txt")}, nido / "altro")
        prova(f"annidati ({et}): una sessione in nido/altro e' di gamma: Read di nido/altro/g: ammesso",
              r.ammesso, repr(r))
        r = sess("Read", {"file_path": str(interno / "h.txt")}, nido / "altro")
        prova(f"annidati ({et}): ...ma dentro nido/interno (di delta, il piu' specifico) non entra: "
              "negato, appartiene a delta", r.negato and "appartiene a delta" in r.motivo, repr(r))
        r = sess("Read", {"file_path": str(interno / "x" / "k.txt")}, nido / "altro")
        prova(f"annidati ({et}): ...neanche piu' in fondo (nido/interno/x/k)", r.negato, repr(r))
        r = sess("Grep", {"pattern": "x", "path": str(nido)}, nido / "altro")
        prova(f"annidati ({et}): gamma cerca in nido: la ricerca include interno, di delta: negata",
              r.negato and "restringi" in r.motivo, repr(r))
        r = sess("Grep", {"pattern": "x", "path": str(nido / "altro")}, nido / "altro")
        prova(f"annidati ({et}): gamma cerca in nido/altro (niente di delta sotto): ammessa",
              r.ammesso, repr(r))
        r = sess("Bash", {"command": "cat h.txt"}, interno / "x")
        prova(f"annidati ({et}): delta con la cwd in nido/interno/x, Bash `cat` relativo di un "
              "file inesistente li': ammesso (la cwd e' sua)", r.ammesso, repr(r))
        r = a.chiama(a.pl("Read", {"file_path": str(interno / "h.txt")}, sid=S_COMUNE,
                          aperta_in=a.comune))
        prova(f"annidati ({et}): il predefinito non entra in nido/interno: negato, appartiene a delta",
              r.negato and "appartiene a delta" in r.motivo, repr(r))
        r = a.chiama(a.pl("Read", {"file_path": str(nido / "f.txt")}, sid=S_COMUNE,
                          aperta_in=a.comune))
        prova(f"annidati ({et}): ...ne' in nido: appartiene a gamma",
              r.negato and "appartiene a gamma" in r.motivo, repr(r))
    # due nominati sulla stessa cartella: incerto, niente
    a.togli_config()
    a.scrivi_config(config(("gamma", "delta"), doppi=True))
    for chi, kw in (("una sessione in doppia", dict(sid="s-doppia", aperta_in=doppia)),
                    ("il predefinito", dict(sid=S_COMUNE, aperta_in=a.comune))):
        r = a.chiama(a.pl("Read", {"file_path": str(doppia / "d.txt")}, **kw))
        prova(f"annidati: due nominati sulla stessa cartella, {chi}, Read: negato"
              + (", e il motivo dice che la config e' ambigua" if kw["sid"] == "s-doppia" else ""),
              r.negato and (kw["sid"] != "s-doppia" or "piu' di un compartimento" in r.motivo),
              repr(r))
    r = a.chiama(a.pl("Read", {"file_path": str(nido / "f.txt")}, sid="s-doppia", aperta_in=doppia))
    prova("annidati: ...e la sessione incerta non legge neanche altrove", r.negato, repr(r))
    # il subagente: l'id della madre conta solo se i transcript esistono davvero
    a.togli_config()
    cfg = a.config()
    cfg["compartimenti"]["alfa"]["sessioni"].append(S_MADRE)
    a.scrivi_config(cfg)
    fuori = str(a.comune / "nota.txt")
    base_p = a.claude / "projects" / _codifica(a.comune)
    r = a.chiama(a.pl("Read", {"file_path": fuori}, sid="agent-v", aperta_in=a.comune, madre=S_MADRE))
    prova("madre: subagente con i transcript veri (suo e della madre): la madre e' in alfa.sessioni: negato",
          r.negato, repr(r))
    finto = a.pl("Read", {"file_path": fuori}, sid="agent-f", aperta_in=a.radice / "finto-1")
    finto["transcript_path"] = str(a.claude / "projects" / "cartella-finta" / S_MADRE / "subagents" / "agent-f.jsonl")
    r = a.chiama(finto)
    prova("madre: un transcript_path di subagente INVENTATO (nessun file): l'id della madre non conta: "
          "Read nel comune ammesso", r.ammesso, repr(r))
    senza = a.radice / "senza-madre"
    senza.mkdir(exist_ok=True)
    solo_sub = a.claude / "projects" / _codifica(senza) / S_MADRE / "subagents"
    solo_sub.mkdir(parents=True, exist_ok=True)
    (solo_sub / "agent-s.jsonl").write_text("{}\n", "utf-8")
    payload = a.pl("Read", {"file_path": fuori}, sid="agent-s", aperta_in=senza)
    payload["transcript_path"] = str(solo_sub / "agent-s.jsonl")
    r = a.chiama(payload)
    prova("madre: il file del subagente c'e' ma la madre non ha il suo transcript: non conta: ammesso",
          r.ammesso, repr(r))
    lontano = a.radice / "fuori-projects" / _codifica(a.progetto) / S_MADRE / "subagents"
    lontano.mkdir(parents=True, exist_ok=True)
    (lontano / "agent-l.jsonl").write_text("{}\n", "utf-8")
    (lontano.parent.parent / f"{S_MADRE}.jsonl").write_text("{}\n", "utf-8")
    payload = a.pl("Read", {"file_path": fuori}, sid="agent-l", aperta_in=a.progetto)
    payload["transcript_path"] = str(lontano / "agent-l.jsonl")
    r = a.chiama(payload)
    prova("madre: i file esistono ma fuori da <claude>/projects: non conta: ammesso", r.ammesso, repr(r))
    a.togli_config()


def _prove_minori(prova, a: Ambiente):
    """Quarto giro, punto 6: find -maxdepth e tree -L, Glob con pattern
    assoluto, url file://, id di sessione crudo, strumenti di sessione senza id."""
    a.togli_config()
    a.scrivi_config(a.config("bloccante"))

    def pred(tool, ti, **kw):
        kw.setdefault("aperta_in", a.albero)
        return a.chiama(a.pl(tool, ti, sid=S_COMUNE, **kw))

    # la cwd e' albero, che ha sotto alfa-tre (di alfa) alla profondita' 1
    for cmd in ("find . -maxdepth 1", "find . -maxdepth 1 -name '*.md'", "tree -L 1", "tree -L 1 .",
                "find . -maxdepth 1 -type f", "du -sh *"):
        r = pred("Bash", {"command": cmd})
        prova(f"minori: predefinito (cwd sopra alfa-tre), `{cmd}`: ammesso (non e' una ricerca "
              "illimitata)", r.ammesso, repr(r))
    for cmd in ("find . -maxdepth 2", "find . -maxdepth 1 -exec cat {} +", "tree -L 2", "find . -name x",
                "find . -maxdepth 2 -name '*.py'", "tree", "ls -R"):
        r = pred("Bash", {"command": cmd})
        prova(f"minori: predefinito (cwd sopra alfa-tre), `{cmd}`: negato (arriva a alfa-tre)",
              r.negato, repr(r))
    # Glob con un pattern assoluto e senza path: la cwd non c'entra
    r = pred("Glob", {"pattern": f"{a.progetto}/**/*.txt"})
    prova("minori: Glob con pattern assoluto e senza path (cwd sopra una cartella di alfa): ammesso",
          r.ammesso, repr(r))
    r = pred("Glob", {"pattern": "~/nulla-di-questo/**/*.py"})
    prova("minori: Glob con pattern che comincia con ~ e senza path: ammesso", r.ammesso, repr(r))
    r = pred("Glob", {"pattern": "**/*.txt"})
    prova("minori: Glob con pattern relativo e senza path da quella cwd: resta negato",
          r.negato, repr(r))
    r = pred("Glob", {"pattern": f"{a.alfa1}/**/*.txt"})
    prova("minori: Glob con pattern assoluto dentro alfa: negato", r.negato, repr(r))
    r = pred("Grep", {"pattern": "x"})
    prova("minori: Grep senza path da quella cwd: resta negato", r.negato, repr(r))
    # url file://
    alfa_f, comune_f = str(a.alfa1 / "segreto.txt"), str(a.comune / "nota.txt")
    for tool, chiave in (("WebFetch", "url"), ("mcp__Claude_Browser__navigate", "url"),
                         ("mcp__claude-in-chrome__navigate", "url")):
        r = pred(tool, {chiave: "file://" + alfa_f, "prompt": "x"})
        prova(f"minori: predefinito, {tool} con un url file:// verso alfa: negato", r.negato, repr(r))
        r = pred(tool, {chiave: "file://localhost" + alfa_f})
        prova(f"minori: ...con file://localhost: negato", r.negato, repr(r))
        r = pred(tool, {chiave: "file:" + alfa_f})
        prova(f"minori: ...con file: senza barre: negato", r.negato, repr(r))
        r = a.chiama(a.pl(tool, {chiave: "file://" + comune_f}, sid=S_ALFA_LIBERA, aperta_in=a.alfa1))
        prova(f"minori: alfa, {tool} con un url file:// verso il comune: negato", r.negato, repr(r))
        r = pred(tool, {chiave: "https://esempio.test/a/b"})
        prova(f"minori: {tool} con un url https: ammesso", r.ammesso, repr(r))
        r = pred(tool, {chiave: "file://" + str(a.progetto / "p.txt")})
        prova(f"minori: ...e un file:// verso un posto non vietato: ammesso", r.ammesso, repr(r))
    r = pred("Bash", {"command": f"curl file://{alfa_f}"})
    prova("minori: Bash `curl file://...alfa`: negato", r.negato, repr(r))
    r = pred("Bash", {"command": f"python3 -c \"import urllib.request as u; u.urlopen('file://{alfa_f}')\""})
    prova("minori: python -c con un url file:// verso alfa: negato", r.negato, repr(r))
    r = pred("Bash", {"command": "curl -s https://esempio.test/a/b"})
    prova("minori: Bash `curl` https: ammesso", r.ammesso, repr(r))
    # un id di sessione crudo (l'uuid del .jsonl) di una sessione che sta solo nel registro dell'app
    nuova = "a4a4a4a4-0000-4000-8000-000000000020"
    a.registra_app("local_aaaa0000-0000-4000-8000-000000000021", nuova, a.alfa1, "Solo nel registro")
    ss = "mcp__ccd_session_mgmt__"
    r = a.chiama(a.pl(ss + "get_session", {"session_id": nuova}, sid=S_COMUNE))
    prova("minori: get_session con il session_id crudo (uuid) di una sessione di alfa che sta solo "
          "nel registro dell'app: negato", r.negato and "alfa" in r.motivo, repr(r))
    r = a.chiama(a.pl(ss + "get_session", {"session_id": "e5e5e5e5-0000-4000-8000-000000000022"},
                      sid=S_COMUNE))
    prova("minori: ...un uuid che nessuno conosce resta ammesso al predefinito", r.ammesso, repr(r))
    # strumenti di sessione senza id da un nominato: negati (non e' certo che agiscano su di lei),
    # con l'indicazione di passare "self"
    for corto, ti in (("set_session_title", {"title": "x"}), ("clear_session", {}),
                      ("set_session_model", {"model": "x"})):
        r = a.chiama(a.pl(ss + corto, ti, sid=S_ALFA_LIBERA, aperta_in=a.alfa1))
        prova(f"minori: alfa, {corto} senza id: negato, e il motivo dice di passare \"self\"",
              r.negato and "self" in r.motivo, repr(r))
        ti2 = dict(ti)
        ti2["session_id"] = "self"
        r = a.chiama(a.pl(ss + corto, ti2, sid=S_ALFA_LIBERA, aperta_in=a.alfa1))
        prova(f"minori: alfa, {corto} con session_id \"self\": ammesso", r.ammesso, repr(r))
    r = a.chiama(a.pl(ss + "get_usage", {}, sid=S_ALFA_LIBERA, aperta_in=a.alfa1))
    prova("minori: alfa, get_usage senza id (il suo default e' \"self\"): ammesso", r.ammesso, repr(r))
    a.togli_config()


# --------------------------------------------------------------------------
# quinto giro
# --------------------------------------------------------------------------

def _importa_compartimenti():
    """Il modulo, per le prove che chiamano una sua funzione (None se non c'e':
    sul commit di base la prova diventa rossa, non va in errore)."""
    sys.path.insert(0, str(RADICE))
    try:
        from plancia import compartimenti
        return compartimenti
    except Exception:  # noqa: BLE001
        return None
    finally:
        try:
            sys.path.remove(str(RADICE))
        except ValueError:
            pass


CASI_ONESTI = [
    "sed -n '/^## Parte 1/,/^## Parte 2/p' file.md",
    "awk '/^## Parte 1/{f=1;next} /^## Parte 2/{f=0} f' file.md",
    "sed -n '/void load_remote_marker/,/^        }/p' src/x.cpp",
    "sed -n '/60,min/p' f",
    "sed -e '/foo/d' f",
    "sed '/x/!d' f",
    "sed -n '/a/,/b/{p}' f",
    "awk '/foo/ {print $1}' f",
    "awk '/foo/' f",
    "awk '$1 ~ /x/' f",
    "awk -F/ '{print $NF}' f",
    "grep -n '</article>' index.html",
    "grep '</div>' index.html",
    "sed -i '' 's#</article>#</article>\\n#' page.html",
    "sed -i '' 's|/usr/bin|/opt|' f",
    "echo '</item>' >> feed.xml",
    'echo \'<a href="/form.html">x</a>\' >> index.html',
    "printf '</p>\\n' >> index.html",
    'cat > form.html <<\'EOF\'\n<form action="/form.json"><input></form></article>\nEOF',
    'cat > page.html <<EOF\n<article><a href="/prizes.html">x</a></article>\nEOF',
    "python3 - <<'PY'\nprint('</item>')\nPY",
    'python3 -c "print(\'</article>\')"',
    'python3 -c "import re; print(re.sub(r\'/x/\', \'\', \'a/x/b\'))"',
    'curl -s -X POST -d @form.json http://localhost:3000/form.html',
    'curl -o out.json https://api.example.com/v1/x',
    'curl http://localhost:3000/api/x',
    "curl -s https://api.github.com/repos/x/y/pulls | jq '.[0].title'",
    'gh api /repos/x/y/pulls',
    'gh api repos/x/y/pulls',
    'git clone https://github.com/x/y',
    'pip install git+https://github.com/x/y.git',
    'docker pull ghcr.io/x/y:tag',
    "grep -rn '/api/users' src",
    "rg '/api/v1' src",
    "grep -E '^/[a-z]+' f",
    "find . -path '*/x/*' -name '*.py'",
    "git log --format='%h /%s' -5",
    'ls */',
    "tr '/' '_' < f",
    'cut -d/ -f1 f',
    'date +%Y/%m/%d',
    "printf '%s/%s\\n' a b",
    'echo $((10/2))',
    'expr 4 / 2',
    "awk 'BEGIN{print 4/2}'",
    "jq '.a/2' data.json",
    "bc <<< '4/2'",
    'echo a/b',
    'echo "a/b/c"',
    'echo /article>',
    'git show HEAD:src/x.cpp',
    'git diff HEAD~1 -- src/x.cpp',
    "git log -S'/foo/' --oneline",
    "git grep '/foo'",
    "git log --grep='/x'",
    "git commit -m 'fix /api/users path'",
    'git commit -m "fix: handle /item and </article> tags"',
    "gh pr create --title 'x' --body 'touches /etc/hosts and </div>'",
    "sed -n '1,/^$/p' f",
    "sed '1d;$d' f",
    "sed 's/\\//_/g' f",
    "sed 's,/,_,g' f",
    "perl -pe 's/\\/x\\//y/' f",
    "perl -ne 'print if /^\\/x/' f",
    'python3 -c "print(open(\'f\').read().split(\'/\'))"',
    'node -e "console.log(\'a/b\'.split(\'/\'))"',
    'ssh host cat /etc/hosts',
    'docker exec c cat /app/x',
    'scp host:/remote/path .',
    'rsync host:/path .',
    'kubectl exec p -- cat /etc/x',
    'aws s3 ls s3://bucket/prefix/',
    'unzip -p a.zip x/y',
    'tar tf a.tgz x/y',
    'docker run -v $PWD:/app -w /app x ls /app',
]


PIPE_ONESTE = [
    "find . -name x | awk -F/ '{print $NF}'",
    "find . -name '*.py' | sed 's,/,_,g'",
    "find . -type f | tr '/' '_'",
    "git ls-files | cut -d/ -f1 | sort -u",
    "grep -rn foo . | awk -F: '{print $1}' | sed 's#/#-#g'",
    "find . -name '*.md' | xargs grep -l '/etc/hosts'",
    "rg -l '/api/v1' . | head",
    "sed -n '/^# /p' file.md | awk '/x/'",
    "gh api /repos/x/y/pulls --jq '.[].title'",
    "gh pr view 3 --json title --jq '.title'",
    "curl -s https://api.esempio.test/y | jq '.a/2'",
    "git log --oneline | sed '/wip/d'",
    "python3 -c \"print('</b>')\" && echo done",
    "ls */ | grep '^/'",
]


def _prove_falsi_positivi_regex(prova, a: Ambiente):
    """Quinto giro, punto 1: un argomento che comincia con `/` ma non e' un
    percorso (la regex di sed/awk/grep/rg, un tag HTML, un endpoint di API, un
    url) non fa negare un nominato. Un token e' un percorso candidato solo se sta
    nella posizione di un file per un comando noto, o (comando sconosciuto) se
    esiste o sta sotto una cartella che esiste. I 75 comandi onesti del quarto
    tester: 0 negati per il nominato."""
    a.togli_config()
    # una cartella di alfa tutta nuova: le altre prove ci lasciano collegamenti e
    # sottocartelle che un `ls */` seguirebbe fuori dai permessi (a ragione)
    pulita = a.radice / "alfa-pulita"
    pulita.mkdir(exist_ok=True)
    cfg = a.config("bloccante")
    cfg["compartimenti"]["alfa"]["cartelle"].append(str(pulita))
    a.scrivi_config(cfg)
    for f in ("file.md", "index.html", "page.html", "feed.xml", "src/x.cpp", "form.json",
              "data.json", "f", "list.txt"):
        p = pulita / f
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x\n", "utf-8")
    prova("regex: la lista dei comandi onesti e' di 75", len(CASI_ONESTI) == 75)

    def alfa(cmd):
        return a.chiama(a.pl("Bash", {"command": cmd}, sid=S_ALFA_LIBERA, aperta_in=pulita))

    negati = []
    for c in CASI_ONESTI:
        if not alfa(c).ammesso:
            negati.append(c[:70])
    prova("regex: alfa, 75 comandi onesti con argomenti che cominciano con `/` senza esserlo: "
          "0 negati", not negati, f"{len(negati)} negati: {negati[:6]}")
    for c in PIPE_ONESTE:
        r = alfa(c)
        prova(f"regex: alfa, `{c[:56]}`: ammesso (nessun `/` di regex, `-F/` o `tr '/'` "
              "diventa un percorso)", r.ammesso, repr(r))
    # dal predefinito (cwd in un progetto senza divieti): i primi 60 restano ammessi
    for f in ("file.md", "index.html", "page.html", "feed.xml", "src/x.cpp", "form.json",
              "data.json", "f", "list.txt"):
        p = a.progetto / f
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x\n", "utf-8")
    p_neg = [c[:70] for c in CASI_ONESTI[:60]
             if not a.chiama(a.pl("Bash", {"command": c}, sid=S_COMUNE,
                                  aperta_in=a.progetto)).ammesso]
    prova("regex: predefinito, i primi 60 comandi onesti: 0 negati", not p_neg, str(p_neg[:6]))
    # i veri accessi restano negati: la posizione di un file, o un percorso che esiste
    nota = str(a.comune / "nota.txt")
    nuovo = str(a.comune / "nuovo-file.txt")
    veri = [
        "find / -name x", "grep -r foo /", f"awk '{{print}}' {nota}",
        f"sed -n '/x/p' {nota}", f"grep foo {nota}", f"rg foo {a.comune}",
        f"mytool {nota}", f"mytool {nuovo}", f"git -C {a.comune} log",
        f"python3 -c \"open('{nota}')\"", f"perl -ne print {nota}", f"jq . {nota}",
        f"gh api --input {nota} /x", "cat /opt-inesistente-x/file", f"cat {nuovo}",
        f"touch {nuovo}", f"mkdir {a.comune}/nuova-cartella", f"cp x {nuovo}",
        f"mytool --out={nota}", f"docker run -v {a.comune}:/app x ls /app",
        f"echo x > {nuovo}", f"sed -i '' s/a/b/ {nota}", f"awk -f {nota}",
        f"grep -e foo -f {nota}", f"grep --include='*.py' foo {nota}",
    ]
    for c in veri:
        r = alfa(c)
        prova(f"regex: alfa, `{c[:60].replace(str(a.radice), '<R>')}`: resta negato (un file "
              "vero nella posizione di un file, o un percorso che esiste)", r.negato, repr(r))
    # una `/` da sola conta solo come radice di una ricerca del suo stesso comando
    for c in ("ls /", "find . -name x | awk -F/ '{print $NF}'", "echo / | tr '/' _"):
        prova(f"regex: alfa, `{c}`: ammesso (la `/` non e' una ricerca)", alfa(c).ammesso)
    # il registro vero della macchina, rigiocato: i frammenti che compaiono come
    # bersaglio (regex, HTML, `/script`) non sono percorsi plausibili, un percorso si
    C = _importa_compartimenti()
    plaus = getattr(C, "_plausibile", None)
    frammenti = ["/script", "/article>", "/item", "/x", "/api/users", "/repos/x/y/pulls",
                 "/app/x", "/^## Parte 1/,/^## Parte 2/p", "//y/",
                 "/void load_remote_marker/,/^        }/p",
                 "/^## Parte 1/{f=1;next} /^## Parte 2/{f=0} f", "/form.html", "/</b>"]
    prova("regex: i frammenti di regex e HTML del registro vero non sono percorsi plausibili",
          plaus is not None and not any(plaus(f) for f in frammenti),
          str([f for f in frammenti if plaus and plaus(f)]))
    prova("regex: ...un percorso che esiste, uno nuovo in una cartella che esiste, ~/x si",
          plaus is not None and plaus(nota) and plaus(nuovo) and plaus("/etc/hosts")
          and plaus("~/x") and plaus("relativo/x"))
    a.togli_config()


def _prove_condivise(prova, a: Ambiente):
    """Quinto giro, punto 2: `condivise`, cartelle di codice (i checkout degli
    strumenti) che tutti i compartimenti LEGGONO e in cui ESEGUONO, e in cui nessuno
    scrive fuori dai propri permessi. La cartella dei dati di Plancia non e' mai
    condivisa."""
    cod = a.radice / "codice-condiviso"
    (cod / "sub").mkdir(parents=True, exist_ok=True)
    (cod / "tool.py").write_text("print(1)\n", "utf-8")
    (cod / "README").write_text("x\n", "utf-8")
    X = str(cod)
    a.togli_config()

    def alfa(cmd, cwd=None):
        return a.chiama(a.pl("Bash", {"command": cmd}, sid=S_ALFA_LIBERA, aperta_in=a.alfa1,
                             cwd=cwd))

    # senza `condivise` la cartella e' fuori dai permessi come ogni altra
    a.scrivi_config(a.config("bloccante"))
    prova("condivise: senza la chiave, alfa non legge la cartella di codice",
          alfa(f"cat {X}/README").negato)
    prova("condivise: ...il default e' una lista vuota (config.DEFAULTS)",
          _default_condivise() == [])
    a.togli_config()
    a.scrivi_config(a.config("bloccante", condivise=[X]))
    for c in (f"cat {X}/README", f"python3 {X}/tool.py", f"ls -la {X}", f"grep -rn x {X}",
              f"cd {X} && ls", f"cd {X} && python3 tool.py", f"find {X} -name '*.py'",
              f"git -C {X} log --oneline", f"git -C {X} status", f"head -1 {X}/sub/../README",
              f"bash {X}/tool.py", f"cp {X}/README {a.alfa1}/copia.txt",
              f"cd {a.alfa1} && cp {X}/README . && python3 {X}/tool.py > out.txt"):
        r = alfa(c)
        prova(f"condivise: alfa, `{c[:58].replace(str(a.radice), '<R>')}`: ammesso "
              "(lettura e esecuzione)", r.ammesso, repr(r))
    for tool, ti in (("Read", {"file_path": X + "/tool.py"}),
                     ("Grep", {"pattern": "x", "path": X}),
                     ("Glob", {"pattern": "**/*.py", "path": X}),
                     ("SendUserFile", {"files": [X + "/README"]})):
        r = a.chiama(a.pl(tool, ti, sid=S_ALFA_LIBERA, aperta_in=a.alfa1))
        prova(f"condivise: alfa, {tool} nella cartella condivisa: ammesso", r.ammesso, repr(r))
    scrivono = [
        f"echo x > {X}/x", f"touch {X}/y", f"cp {a.alfa1}/segreto.txt {X}/",
        f"cp {a.alfa1}/segreto.txt {X}/z", f"rm {X}/README", f"git -C {X} pull",
        f"sed -i '' s/a/b/ {X}/README", f"tar xf a.tgz -C {X}",
        f"python3 -c \"open('{X}/x','w')\"", f"cd {X} && touch y", f"cd {X} && echo x > y",
        f"mv {X}/README {X}/R2", f"tee {X}/t <<< x", f"rm -rf {X}/sub", f"mkdir {X}/nuova",
        f"ln -s a {X}/l", f"python3 -c \"import os; os.system('rm {X}/README')\"",
        f"find {X} -name README -delete", f"cd {X} && git checkout .",
        f"cd {X} && cat > n.txt <<'EOF'\nx\nEOF", f"for f in {X}/*; do rm $f; done",
        f"cd {X}/sub && rm -f ../README", f"chmod 000 {X}/README", f"truncate -s0 {X}/README",
        f"rsync -a {a.alfa1}/ {X}/", f"curl -o {X}/x http://localhost/x",
        f"git -C {X} checkout -b nuovo", f"echo x | xargs -I{{}} touch {X}/{{}}",
    ]
    for c in scrivono:
        r = alfa(c)
        prova(f"condivise: alfa, `{c[:58].replace(str(a.radice), '<R>').splitlines()[0]}`: negato "
              "(la cartella condivisa non si scrive)",
              r.negato and "condivisa" in r.motivo, repr(r))
    for tool, ti in (("Write", {"file_path": X + "/new.py", "content": "x"}),
                     ("Edit", {"file_path": X + "/tool.py", "old_string": "1", "new_string": "2"}),
                     ("MultiEdit", {"file_path": X + "/tool.py",
                                    "edits": [{"old_string": "1", "new_string": "2"}]}),
                     ("NotebookEdit", {"notebook_path": X + "/n.ipynb"})):
        r = a.chiama(a.pl(tool, ti, sid=S_ALFA_LIBERA, aperta_in=a.alfa1))
        prova(f"condivise: alfa, {tool} nella cartella condivisa: negato, dice `condivisa`",
              r.negato and "condivisa" in r.motivo, repr(r))
    prova("condivise: alfa, il comune resta fuori dai permessi",
          a.chiama(a.pl("Read", {"file_path": str(a.comune / "nota.txt")}, sid=S_ALFA_LIBERA,
                        aperta_in=a.alfa1)).negato)
    prova("condivise: alfa, scrivere nella propria cartella resta ammesso",
          alfa(f"echo x > {a.alfa1}/mio.txt").ammesso)
    prova("condivise: il predefinito non e' toccato (scrive e legge come prima)",
          a.chiama(a.pl("Bash", {"command": f"echo x > {X}/x; cat {X}/README"},
                        sid=S_COMUNE, aperta_in=a.progetto)).ammesso)
    # cartelle di un nominato dentro una condivisa: vince il piu' specifico
    a.togli_config()
    zona = a.radice / "zona-condivisa"
    (zona / "beta-in-zona").mkdir(parents=True, exist_ok=True)
    (zona / "beta-in-zona" / "b.txt").write_text("dentro beta", "utf-8")
    (zona / "nota.txt").write_text("nota della zona", "utf-8")
    cfg_z = a.config("bloccante", condivise=[str(zona)])
    cfg_z["compartimenti"]["beta"]["cartelle"].append(str(zona / "beta-in-zona"))
    a.scrivi_config(cfg_z)
    prova("condivise: una condivisa che ha dentro una cartella di beta: alfa legge il resto",
          alfa(f"cat {zona}/nota.txt").ammesso)
    r = alfa(f"cat {zona}/beta-in-zona/b.txt")
    prova("condivise: ...ma non la cartella di beta (piu' specifica): negato, appartiene a beta",
          r.negato and "beta" in r.motivo, repr(r))
    r = alfa(f"grep -rn x {zona}")
    prova("condivise: ...e una ricerca dalla radice condivisa che include beta e' negata",
          r.negato, repr(r))
    prova("condivise: ...scrivere nella propria cartella dentro la condivisa e' ammesso",
          alfa(f"echo x > {a.alfa1}/n2.txt").ammesso)
    prova("condivise: ...scrivere nella condivisa (fuori dai propri permessi) no",
          alfa(f"echo x > {zona}/n2.txt").negato)
    # la cartella dei dati non e' mai condivisa: una voce che la contiene e' ignorata
    # (vedi `_prove_condivise_6`)
    a.togli_config()
    a.scrivi_config(a.config("bloccante", condivise=[str(a.radice)]))
    for chi, tgt in (("dentro una condivisa", f"cat {a.dati}/config.json"),
                     ("le trascrizioni", f"cat {a.claude}/projects/x.jsonl")):
        r = alfa(tgt)
        prova(f"condivise: {chi} (la voce che li contiene e' ignorata): i dati/le trascrizioni "
              "restano fuori dai permessi", r.negato, repr(r))
    a.togli_config()
    try:
        (a.dati / "guardiano.condivise-nota").unlink()      # la nota e' limitata nel tempo
    except OSError:
        pass
    a.scrivi_config(a.config("bloccante", condivise=[str(a.dati), str(a.dati / "sotto"), X]))
    r = alfa(f"cat {a.dati}/config.json")
    righe = [x for x in a.registro() if x.get("esito") == "nota"]
    prova("condivise: una voce che e' la cartella dei dati (o sta dentro) e' ignorata: i dati "
          "restano negati", r.negato, repr(r))
    prova("condivise: ...con una nota nel registro (e le altre voci valgono)",
          len(righe) == 1 and "dati" in righe[0].get("motivo", "")
          and alfa(f"cat {X}/README").ammesso, str(righe))
    # `solo-registro`: non nega, scrive `avrebbe-negato`
    a.togli_config()
    a.scrivi_config(a.config("solo-registro", condivise=[X]))
    n0 = len(a.registro())
    r = alfa(f"echo x > {X}/x")
    righe = a.registro()
    prova("condivise: solo-registro: la scrittura e' ammessa e lascia `avrebbe-negato`",
          r.ammesso and len(righe) == n0 + 1 and righe[-1]["esito"] == "avrebbe-negato",
          str(righe[-1:]))
    # config: chiave con tipo sbagliato = config rotta (fail-closed con la copia)
    a.togli_config()
    a.scrivi_config(a.config("bloccante", condivise=[X]))
    alfa(f"cat {X}/README")
    a.scrivi_config(a.config("bloccante", condivise="non-una-lista"))
    r = alfa(f"cat {a.comune}/nota.txt")
    prova("condivise: `condivise` di tipo sbagliato e' config rotta: alfa e' ancora confinata "
          "con l'ultima config valida", r.negato, repr(r))
    prova("condivise: ...e l'ultima config valida ha ancora la condivisa",
          alfa(f"cat {X}/README").ammesso)
    # la CLI e l'autoprotezione
    a.togli_config()
    a.scrivi_config(a.config("bloccante", condivise=[X]))
    for chi, kw in (("predefinito", dict(sid=S_COMUNE, aperta_in=a.progetto)),
                    ("alfa", dict(sid=S_ALFA_LIBERA, aperta_in=a.alfa1))):
        for cmd in ("plancia config condivise '[\"/tmp/x\"]'",
                    "python3 -m plancia.cli config condivise '[]'"):
            r = a.chiama(a.pl("Bash", {"command": cmd}, **kw))
            prova(f"condivise: {chi}, `{cmd[:50]}`: negato (chiave del guardiano)", r.negato, repr(r))
    env = dict(a.env())
    env["PYTHONPATH"] = str(RADICE)

    def plancia(*args):
        p = subprocess.run([sys.executable, str(RADICE / "bin" / "plancia"), *args], env=env,
                           cwd=str(RADICE), capture_output=True, timeout=60)
        return p.returncode, p.stdout.decode("utf-8", "replace") + p.stderr.decode("utf-8", "replace")

    a.togli_config()
    rc, out = plancia("config", "condivise", json.dumps([X]))
    letta = _testo(a.dati / "config.json")
    prova("condivise: `plancia config condivise '[...]'` scrive la lista", rc == 0 and X in letta,
          out + letta[:200])
    rc, out = plancia("config", "condivise", json.dumps([str(a.dati)]))
    prova("condivise: ...rifiuta la cartella dei dati (uscita 2, config invariata)",
          rc == 2 and "dati" in out and X in _testo(a.dati / "config.json")
          and str(a.dati) not in _testo(a.dati / "config.json"), out)
    rc, out = plancia("config", "condivise", "solo-una-stringa")
    prova("condivise: ...rifiuta un valore che non e' una lista di cartelle (uscita 2)",
          rc == 2, out)
    rc, out = plancia("config", "condivise", json.dumps(["relativa/x"]))
    prova("condivise: ...rifiuta una cartella non assoluta (uscita 2)", rc == 2, out)
    a.scrivi_config(a.config("solo-registro", condivise=[X]))
    rc, out = plancia("guardiano", "--stato")
    prova("condivise: `plancia guardiano --stato` dice quante cartelle condivise (non i percorsi)",
          rc == 0 and "condivise: 1" in out and X not in out, out)
    a.togli_config()


def _default_condivise():
    """`config.DEFAULTS["condivise"]`, o None se la chiave non c'e'."""
    try:
        from plancia import config
        return config.DEFAULTS.get("condivise")
    except Exception:  # noqa: BLE001
        return None


# Testo che arriva a un esecutore per vie non coperte dal quarto giro. `@@` e' il
# file da leggere (di un altro compartimento), `@D@` la cartella di lavoro.
CASI_G5_TESTO = [
    # here-string a una shell o a un interprete
    "sh <<< 'cat @@'", "bash <<< \"cat @@\"", "zsh <<< 'cat @@'", "sh -s <<< 'cat @@'",
    "sh - <<< 'cat @@'", "eval <<< 'cat @@'", "echo x | sh <<< 'cat @@'",
    "read c <<< 'cat @@'; sh -c \"$c\"", "python3 <<< \"print(open('@@').read())\"",
    "sh <<<'cat @@'", "sh <<<\"cat @@\"", "cat <<< 'x'; sh <<< 'cat @@'",
    "node <<< \"console.log(require('fs').readFileSync('@@','utf8'))\"",
    # sostituzione di processo e eval con $(echo ...)
    "bash <(echo 'cat @@')", "source <(echo 'cat @@')", ". <(echo 'cat @@')",
    "sh <(printf 'cat @@')", "bash --rcfile <(echo 'cat @@') -i",
    "eval \"$(echo 'cat @@')\"", "sh -c \"$(echo 'cat @@')\"",
    "bash -c \"$(printf 'cat @@')\"", "sh <(echo cat @@)", "bash <(printf 'cat %s' @@)",
    "echo 'cat @@' | /usr/bin/env bash", "echo 'cat @@' | env sh",
    # script scritto e poi lanciato per percorso
    "echo 'cat @@' > run.sh; ./run.sh", "echo 'cat @@' > run.sh; chmod +x run.sh; ./run.sh",
    "printf 'cat @@\\n' > run.sh; chmod 755 run.sh && ./run.sh",
    "cat > run.sh <<'EOF'\ncat @@\nEOF\nchmod +x run.sh && ./run.sh",
    "tee run.sh <<EOF\ncat @@\nEOF\nsh run.sh",
    "echo 'cat @@' | tee run.sh; sh run.sh",
    "echo 'cat @@' > run.sh; chmod 755 run.sh; ./run.sh",
    "f=$(mktemp); echo 'cat @@' > $f; sh $f", "f=$(mktemp); echo 'cat @@' > $f; bash < $f",
    "f=$(mktemp); printf 'cat @@' > \"$f\"; . \"$f\"", "f=$(mktemp); echo 'cat @@' > $f; chmod +x $f; $f",
    "echo 'cat @@' > /tmp/run.sh; /tmp/run.sh",
    "echo 'cat @@' > s.sh && sh -c \"$(<s.sh)\"", "echo 'cat @@' > s.sh && sh -c \"$(cat s.sh)\"",
    "echo 'cat @@' > s.sh && sh -c `cat s.sh`", "echo 'cat @@' > s.sh && eval \"`cat s.sh`\"",
    "echo 'cat @@' > s.sh && eval $(cat s.sh)", "echo 'cat @@' > s.sh; eval \"$(cat s.sh)\"",
    "echo @@ > list && cat $(<list)", "echo @@ > list && cat $(cat list)",
    "echo @@ > list && cat `cat list`", "echo @@ > list && head -1 $(cat list)",
    "echo @@ > list && ls -la $(cat list)", "echo @@ > list && cat \"$(cat list)\"",
    "echo @@ > list && cat < $(cat list)", "echo @@ > list && cat list | xargs cat",
    "echo @@ > list; for f in $(cat list); do cat $f; done",
    "echo @@ > list && xargs -a list cat",
    # virgolette ANSI-C
    "cat $'@@'", "cat $\"@@\"",
]

# Scritture ai file del guardiano e alla sua cartella. `@D@` e' la cartella dei
# dati, `@R@` il checkout da cui gira l'hook.
CASI_G5_DATI = [
    # chmod senza -R sulla cartella dei dati e sul codice
    "chmod 000 @D@", "chmod 0 @D@", "chmod u-x @D@", "chmod a-rwx @D@/config.json",
    "chmod 000 @R@/plancia", "chmod 000 @R@/bin", "chmod -x @D@", "chown nobody @D@",
    "python3 -c \"import os; os.chmod(os.path.expanduser('~/.plancia'),0)\"",
    "python3 -c \"import os; os.chmod('@D@',0)\"", "python3 -c \"import os; os.chmod('@R@/plancia',0)\"",
    "ln -sfn /tmp/x @D@", "ln -sfn /tmp/x @R@/plancia",
    # xargs, cicli, graffe, sostituzioni
    "find @D@ -name config.json | xargs rm", "find @D@ -name config.json -print0 | xargs -0 rm",
    "find @D@ -type f | xargs rm -f", "ls @D@ | xargs rm", "ls @D@/config.json | xargs rm",
    "echo @D@/config.json | xargs rm", "echo @D@/config.json | xargs -I{} truncate -s0 {}",
    "echo @D@/config.json | xargs sed -i '' s/a/b/", "xargs rm <<< @D@/config.json",
    "xargs rm <<'EOF'\n@D@/config.json\nEOF",
    "rm @D@/{config,x}.json", "rm @D@/config.{json,bak}", "rm @D@/{config.json,x}",
    "rm @D@/con{fig,x}.json", "mv @D@/{config.json,x}", "rm @D@/{config.json,x}",
    "rm $(ls @D@/config.json)", "rm `ls @D@/config.json`", "rm $(echo @D@/config.json)",
    "truncate -s0 $(echo @D@/config.json)", "mv $(ls @D@/config.json) /tmp/x",
    "for f in @D@/config.json; do rm $f; done", "for f in @D@/*.json; do : > $f; done",
    "for f in @D@/config.json @D@/x; do rm -f \"$f\"; done",
    "for f in @D@/*.json; do\n  truncate -s0 $f\ndone",
    "while read f; do rm $f; done <<< @D@/config.json",
    "find @D@ -name config.json | while read f; do rm $f; done",
    "cat <<'EOF' | xargs rm\n@D@/config.json\nEOF",
    # scritture dentro interpreti (system, subprocess, fs, rename, open con parentesi annidate)
    "python3 -c \"import os; os.system('rm @D@/config.json')\"",
    "python3 -c \"import subprocess; subprocess.run(['rm', '@D@/config.json'])\"",
    "python3 -c \"import subprocess; subprocess.check_call('rm @D@/config.json', shell=True)\"",
    "python3 -c \"import subprocess; subprocess.run(['plancia','config','guardiano','spento'])\"",
    "python3 -c \"import os; os.system('plancia config guardiano spento')\"",
    "python3 -c \"import os; os.system('sed -i s/a/b/ @D@/config.json')\"",
    "python3 -c \"import os; open(os.path.expanduser('~/.plancia/config.json'), 'w').close()\"",
    "python3 -c \"import os; open(os.path.expanduser('~/.plancia/config.json'), 'w')\"",
    "python3 -c \"import os; open(os.path.join(os.path.expanduser('~'), '.plancia', 'config.json'), 'w')\"",
    "python3 -c \"open('@D@/config.json', 'w')\"",
    "python3 -c \"import os; open(os.path.expanduser('~/.plan'+'cia/config.json'),'w')\"",
    "python3 -c \"import shutil; shutil.rmtree('@R@/plancia')\"",
    "node -e \"require('child_process').execSync('rm @D@/config.json')\"",
    "node -e \"require('fs').rmSync('@D@/config.json')\"",
    "node -e \"require('fs').rmSync('@D@',{recursive:true})\"",
    "node -e \"require('fs').renameSync('@D@/config.json','/tmp/x')\"",
    "node -e \"require('fs').truncateSync('@D@/config.json')\"",
    "ruby -e 'system(\"rm @D@/config.json\")'", "perl -e 'system(\"rm @D@/config.json\")'",
    "perl -e 'rename \"@D@/config.json\", \"/tmp/x\"'",
    "osascript -e 'do shell script \"rm @D@/config.json\"'",
    "echo hi >& @D@/config.json", "echo hi 1<> @D@/config.json", "echo hi &> @D@/config.json",
    "patch @D@/config.json /tmp/p.diff", "ditto /tmp/c.json @D@/config.json",
    "gzip @D@/config.json", "sort -o @D@/config.json /tmp/x",
    "mkdir -p @R@/plancia/__pycache__ && echo x > @R@/plancia/__pycache__/compartimenti.cpython-39.pyc",
]


def _prove_gravi_5(prova, a: Ambiente):
    """Quinto giro, punto 3: buchi di elenco del quarto tester. Il testo che arriva a
    un esecutore per vie nuove (here-string, sostituzione di processo, script scritto
    e lanciato per percorso, `$(cat f)`), e le scritture al guardiano con `chmod`
    senza -R, `xargs`, cicli, graffe, sostituzioni, e dentro gli interpreti. Ognuna
    negata al predefinito (verso un file di alfa) e a alfa (verso il comune)."""
    a.togli_config()
    a.scrivi_config(a.config("bloccante"))
    fuori_alfa, fuori_comune = str(a.alfa1 / "segreto.txt"), str(a.comune / "nota.txt")
    dati, radice = str(a.dati), str(RADICE)

    def esegui(chi, cmd):
        if chi == "P":
            return a.chiama(a.pl("Bash", {"command": cmd}, sid=S_COMUNE, aperta_in=a.progetto))
        return a.chiama(a.pl("Bash", {"command": cmd}, sid=S_ALFA_LIBERA, aperta_in=a.alfa1))

    passati = {"P": [], "A": []}
    for c in CASI_G5_TESTO:
        for chi, tgt in (("P", fuori_alfa), ("A", fuori_comune)):
            cmd = c.replace("@@", tgt)
            if not esegui(chi, cmd).negato:
                passati[chi].append(cmd.replace(str(a.radice), "<R>")[:80])
    prova("gravi5-testo: la lista dei casi e' di almeno 50", len(CASI_G5_TESTO) >= 50,
          str(len(CASI_G5_TESTO)))
    prova("gravi5-testo: dal predefinito nessun idioma passa (verso un file di alfa)",
          not passati["P"], f"{len(passati['P'])} passati: {passati['P'][:6]}")
    prova("gravi5-testo: da alfa nessun idioma passa (verso un file del comune)",
          not passati["A"], f"{len(passati['A'])} passati: {passati['A'][:6]}")
    # usi ordinari che devono restare ammessi
    nota = str(a.alfa1 / "nota-nuova.txt")
    ammessi_a = [
        f"cat <<< 'vedi {fuori_comune}' > {nota}", "cat <<< 'ciao'", "read x <<< 'ciao'; echo $x",
        f"echo 'vedi {fuori_comune}' > s.sh && cat s.sh", f"echo 'vedi {fuori_comune}' > s.sh; ls",
        f"echo 'vedi {fuori_comune}' | tee s.sh", "f=$(mktemp); echo ciao > $f; cat $f",
        "echo ciao > lista && cat lista | wc -l", "echo ciao > lista; git commit -m \"$(cat lista)\"",
        "grep -c x <<< 'x'", "bc <<< '4/2'", "cat <(echo ciao)", "diff <(echo a) <(echo b)",
        f"echo 'cat {fuori_comune}' > note.txt; cat note.txt",
        "for f in a b c; do echo $f; done", "for f in *.txt; do wc -l $f; done",
        "while read l; do echo $l; done <<< 'a b'",
    ]
    for cmd in ammessi_a:
        r = esegui("A", cmd)
        prova(f"gravi5-testo: alfa, `{cmd[:60].splitlines()[0]}`: ammesso (uso ordinario)",
              r.ammesso, repr(r))
    # scritture al guardiano
    # dal predefinito: per alfa la cartella dei dati e' comunque fuori dai permessi
    passate = []
    for c in CASI_G5_DATI:
        cmd = c.replace("@D@", dati).replace("@R@", radice)
        if not esegui("P", cmd).negato:
            passate.append(cmd.replace(dati, "<dati>").replace(radice, "<R>")[:80])
    prova("gravi5-dati: la lista dei casi e' di almeno 70", len(CASI_G5_DATI) >= 70,
          str(len(CASI_G5_DATI)))
    prova("gravi5-dati: dal predefinito nessuna scrittura al guardiano passa",
          not passate, f"{len(passate)} passate: {passate[:6]}")
    p = str(a.progetto)
    (a.progetto / "a.txt").write_text("x", "utf-8")
    ammessi = [
        f"chmod +x {dati}/qualcosa.sh", f"chmod 644 {p}/a.txt", f"chmod 000 {p}",
        f"rm {p}/a.txt", f"for f in {p}/*.txt; do rm $f; done",
        f"find {p} -name '*.tmp' | xargs rm", f"find {p} -name '*.tmp' -print0 | xargs -0 rm -f",
        "echo x | xargs rm", f"rm $(ls {p}/a.txt)", f"rm {p}/{{a,b}}.txt",
        f"python3 -c \"import subprocess; subprocess.run(['cat','{dati}/config.json'])\"",
        f"python3 -c \"import os; os.system('cat {dati}/config.json')\"",
        f"python3 -c \"import subprocess; subprocess.run(['rm','{p}/a.txt'])\"",
        f"node -e \"console.log(require('fs').readFileSync('{dati}/config.json','utf8'))\"",
        f"cat {dati}/config.json | xargs -I{{}} echo {{}}", f"ls {dati} | xargs -n1 echo",
        "echo hi 2>&1 | tee log.txt", "echo x >&2", "ls > /dev/null 2>&1", "echo hi >& /dev/null",
        f"python3 -c \"open('{p}/x.txt', 'w')\"", f"gzip {p}/a.txt", f"sort -o {p}/b.txt {p}/a.txt",
        f"ln -s {p}/a.txt {p}/l", f"ln -sfn {p}/a.txt {p}/l2",
        f"cat {dati}/config.json", f"ls -la {dati}", f"stat {dati}", f"chmod -R u+w {p}",
    ]
    for cmd in ammessi:
        r = esegui("P", cmd)
        prova(f"gravi5-dati: predefinito, `{cmd[:60]}`: ammesso", r.ammesso, repr(r))
    a.togli_config()
    _prove_permessi_dati(prova, a)


def _prove_permessi_dati(prova, a: Ambiente):
    """Un `chmod 000` che c'e' gia' stato (a mano, o prima che il guardiano fosse
    bloccante) non spegne il guardiano in silenzio: senza permessi sulla cartella
    dei dati l'hook lo dice con un `systemMessage`; se resta leggibile la copia
    dell'ultima config, l'hook continua a negare."""
    a.togli_config()
    a.scrivi_config(a.config("bloccante"))
    alfa_f = str(a.alfa1 / "segreto.txt")
    lett = a.pl("Bash", {"command": f"cat {alfa_f}"}, sid=S_COMUNE, aperta_in=a.progetto)
    innocua = a.pl("Read", {"file_path": str(a.progetto / "p.txt")}, sid=S_COMUNE,
                   aperta_in=a.progetto)
    r0 = a.chiama(lett)
    prova("permessi: base, il predefinito che legge un file di alfa e' negato (e la copia "
          "dell'ultima config c'e')", r0.negato
          and (a.dati / "compartimenti.ultima-valida.json").exists(), repr(r0))
    for f in ("guardiano.permessi-avviso", "guardiano.config-illeggibile"):
        try:
            (a.dati / f).unlink()
        except OSError:
            pass
    # `chmod 000` su Windows non toglie la lettura (cambia solo l'attributo di sola
    # lettura): i controlli che dipendono da un file illeggibile non si possono fare li'
    non_si_puo = "saltato: su Windows chmod 000 non rende illeggibile un file" if _finti.WIN else ""
    os.chmod(a.dati / "config.json", 0)
    try:
        r = a.chiama(innocua)
        prova("permessi: config.json senza permessi (la copia si legge): un avviso "
              "`systemMessage` a chi non e' negato",
              bool(non_si_puo) or (r.rc == 0 and "systemMessage" in r.out
                                   and "permessi" in r.out), non_si_puo or repr(r))
        r = a.chiama(lett)
        prova("permessi: ...e l'hook continua a negare con la copia dell'ultima config",
              r.negato, repr(r))
    finally:
        os.chmod(a.dati / "config.json", 0o644)
    for f in ("guardiano.permessi-avviso", "guardiano.config-illeggibile"):
        try:
            (a.dati / f).unlink()
        except OSError:
            pass
    os.chmod(a.dati, 0)
    try:
        r = a.chiama(lett)
        prova("permessi: la cartella dei dati con `chmod 000`: l'hook esce 0 ma lo DICE "
              "(`systemMessage` con i permessi), non e' un fail-open muto",
              bool(non_si_puo) or (r.rc == 0 and "systemMessage" in r.out
                                   and "permessi" in r.out), non_si_puo or repr(r))
        r2 = a.chiama(lett)
        prova("permessi: ...e lo dice a ogni chiamata finche' non si riparano (la marca "
              "non si puo' scrivere)",
              bool(non_si_puo) or (r2.rc == 0 and "systemMessage" in r2.out),
              non_si_puo or repr(r2))
    finally:
        os.chmod(a.dati, 0o755)
    r = a.chiama(lett)
    prova("permessi: ripristinati i permessi l'hook torna a negare, senza avvisi",
          r.negato and "systemMessage" not in r.out, repr(r))
    a.togli_config()


def _voce(**extra_hook):
    """La voce PreToolUse del guardiano con un campo del comando cambiato."""
    h = {"type": "command", "command": VOCE_GUARDIANO}
    h.update(extra_hook)
    return h


def _prove_settings_5(prova, a: Ambiente):
    """Quinto giro, punto 3: oltre alla voce e a disableAllHooks, un settings.json
    non puo' neutralizzare il guardiano con un `env` (PLANCIA_HOME, PYTHONPATH,
    HOME...), un `matcher` che lo restringe, un `timeout` di zero, `async`, un `if`,
    o spostando la voce sotto un altro evento."""
    a.togli_config()
    a.scrivi_config(a.config("bloccante"))
    utente = a.claude / "settings.json"
    utente.write_text(_settings(), "utf-8")
    proj = a.progetto / ".claude" / "settings.local.json"
    proj.parent.mkdir(parents=True, exist_ok=True)
    proj.write_text('{"permissions": {"allow": ["Bash(ls:*)"]}}', "utf-8")

    def pred(tool, ti):
        return a.chiama(a.pl(tool, ti, sid=S_COMUNE, aperta_in=a.progetto))

    def scrivi(extra=None, hooks=None, file=None):
        d = {"theme": "dark", "hooks": hooks if hooks is not None else {
            "PreToolUse": [{"matcher": "*", "hooks": [_voce()]}]}}
        d.update(extra or {})
        return pred("Write", {"file_path": str(file or utente), "content": json.dumps(d)})

    r = scrivi()
    prova("settings5: base, la stessa voce riscritta identica: ammesso", r.ammesso, repr(r))
    for nome, hooks in (
            ("matcher Nothing", {"PreToolUse": [{"matcher": "Nothing", "hooks": [_voce()]}]}),
            ("matcher Read", {"PreToolUse": [{"matcher": "Read", "hooks": [_voce()]}]}),
            ("matcher Bash|Edit", {"PreToolUse": [{"matcher": "Bash|Edit", "hooks": [_voce()]}]}),
            ("timeout 0", {"PreToolUse": [{"matcher": "*", "hooks": [_voce(timeout=0)]}]}),
            ("timeout 0.1", {"PreToolUse": [{"matcher": "*", "hooks": [_voce(timeout=0.1)]}]}),
            ("timeout negativo", {"PreToolUse": [{"matcher": "*", "hooks": [_voce(timeout=-1)]}]}),
            ("async true", {"PreToolUse": [{"matcher": "*", "hooks": [_voce(**{"async": True})]}]}),
            ("if Bash(ls)", {"PreToolUse": [{"matcher": "*", "hooks": [_voce(**{"if": "Bash(ls)"})]}]}),
            ("type diverso", {"PreToolUse": [{"matcher": "*", "hooks": [_voce(type="prompt")]}]}),
            ("la voce sotto PostToolUse", {"PostToolUse": [{"matcher": "*", "hooks": [_voce()]}]}),
            ("la voce sotto Stop", {"Stop": [{"hooks": [_voce()]}]}),
            ("la voce sotto un evento e un'altra al suo posto",
             {"PreToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": "/usr/bin/true"}]}],
              "Stop": [{"hooks": [_voce()]}]}),
            ("il comando con un ripiego", {"PreToolUse": [{"matcher": "*", "hooks": [
                _voce(command=VOCE_GUARDIANO + " || true")]}]}),
    ):
        r = scrivi(hooks=hooks)
        prova(f"settings5: Write con {nome}: negato, dice che spegnerebbe il guardiano",
              r.negato and "plancia-guardiano" in r.motivo, repr(r))
    for k, v in (("PLANCIA_HOME", "/tmp/nessuno"), ("HOME", "/tmp/nessuno"),
                 ("CLAUDE_CONFIG_DIR", "/tmp/nessuno"), ("PYTHONPATH", "/tmp/pp"),
                 ("PYTHONHOME", "/tmp/pp"), ("PYTHONSTARTUP", "/tmp/s.py"), ("PATH", "/tmp/bin"),
                 ("LD_PRELOAD", "/tmp/x.so"), ("DYLD_INSERT_LIBRARIES", "/tmp/x.dylib")):
        r = scrivi({"env": {k: v}})
        prova(f"settings5: Write con env {k}: negato, dice `env`",
              r.negato and "env" in r.motivo and k in r.motivo, repr(r))
    r = pred("Edit", {"file_path": str(utente), "old_string": '"theme": "dark"',
                      "new_string": '"theme": "dark", "env": {"PYTHONPATH": "/tmp/pp"}'})
    prova("settings5: Edit che aggiunge env PYTHONPATH: negato", r.negato, repr(r))
    r = pred("MultiEdit", {"file_path": str(utente), "edits": [
        {"old_string": '"theme": "dark"', "new_string": '"theme": "dark", "env": {"PLANCIA_HOME": "/x"}'}]})
    prova("settings5: MultiEdit che aggiunge env PLANCIA_HOME: negato", r.negato, repr(r))
    r = pred("Edit", {"file_path": str(utente), "old_string": '"matcher": "*"',
                      "new_string": '"matcher": "Nothing"'})
    prova("settings5: Edit che cambia il matcher della voce: negato", r.negato, repr(r))
    # l'env pericolosa vale per TUTTI i settings, anche senza la voce
    r = scrivi({"env": {"PLANCIA_HOME": "/tmp/nessuno"}}, hooks={}, file=proj)
    prova("settings5: settings.local.json di un progetto (senza la voce) con env PLANCIA_HOME: "
          "negato (l'env dei progetti arriva anche all'hook)", r.negato, repr(r))
    r = pred("Write", {"file_path": str(proj), "content": json.dumps({"env": {"PYTHONPATH": "/x"}})})
    prova("settings5: ...con env PYTHONPATH: negato", r.negato, repr(r))
    # quello che resta ammesso
    for nome, extra, hooks in (
            ("env innocua", {"env": {"FOO": "bar", "PYTHONIOENCODING": "utf-8",
                                     "PYTHONDONTWRITEBYTECODE": "1"}}, None),
            ("timeout 30", None, {"PreToolUse": [{"matcher": "*", "hooks": [_voce(timeout=30)]}]}),
            ("timeout 5 e un'altra voce", None, {"PreToolUse": [
                {"matcher": "*", "hooks": [_voce(timeout=5)]},
                {"matcher": "Bash", "hooks": [{"type": "command", "command": "/usr/bin/true"}]}]}),
            ("matcher vuoto (vale per tutti)", None,
             {"PreToolUse": [{"matcher": "", "hooks": [_voce()]}]}),
            ("un altro evento in piu'", None, {
                "PreToolUse": [{"matcher": "*", "hooks": [_voce()]}], "Stop": []}),
            ("async false", None, {"PreToolUse": [{"matcher": "*", "hooks": [_voce(**{"async": False})]}]}),
            ("disableAllHooks false", {"disableAllHooks": False}, None)):
        r = scrivi(extra, hooks)
        prova(f"settings5: Write con {nome}: ammesso", r.ammesso, repr(r))
    # un file che ha GIA' un'env pericolosa: cambiare altro non inciampa
    utente.write_text(_settings({"env": {"PATH": "/usr/local/bin:/usr/bin"}}), "utf-8")
    r = pred("Edit", {"file_path": str(utente), "old_string": '"theme": "dark"',
                      "new_string": '"theme": "light"'})
    prova("settings5: env pericolosa GIA' presente e invariata: un'altra modifica e' ammessa",
          r.ammesso, repr(r))
    r = pred("Edit", {"file_path": str(utente), "old_string": "/usr/local/bin:/usr/bin",
                      "new_string": "/tmp/bin"})
    prova("settings5: ...cambiarne il valore no", r.negato, repr(r))
    a.togli_config()


def _corri_copia(a: Ambiente, hook: Path, payload, timeout=20):
    """Lancia l'hook di una copia del checkout; None se non torna in `timeout`."""
    t0 = time.time()
    try:
        p = subprocess.run([PYTHON, str(hook)], input=json.dumps(payload).encode(),
                           capture_output=True, env=a.env(), timeout=timeout)
    except subprocess.TimeoutExpired:
        return None
    return Esito(p.returncode, p.stdout.decode("utf-8", "replace"),
                 p.stderr.decode("utf-8", "replace"), time.time() - t0)


def _prove_minori_5(prova, a: Ambiente):
    """Quinto giro, punto 4: virgolette ANSI-C, `cd` con graffe o con sostituzione,
    il tetto dei percorsi che non e' silenzioso, BaseException e hang dell'hook,
    PYTHONPATH che non lo spegne."""
    a.togli_config()
    a.scrivi_config(a.config("bloccante"))
    fuori_alfa, fuori_comune = str(a.alfa1 / "segreto.txt"), str(a.comune / "nota.txt")

    def pred(cmd, **kw):
        kw.setdefault("aperta_in", a.progetto)
        return a.chiama(a.pl("Bash", {"command": cmd}, sid=S_COMUNE, **kw))

    def alfa(cmd, **kw):
        kw.setdefault("aperta_in", a.alfa1)
        return a.chiama(a.pl("Bash", {"command": cmd}, sid=S_ALFA_LIBERA, **kw))

    # ANSI-C e virgolette di traduzione
    esadecimale = fuori_alfa.replace("/", "\\x2f")
    for cmd in (f"cat $'{fuori_alfa}'", f"cat $\"{fuori_alfa}\"", f"cat $'{esadecimale}'",
                f"cat $'{a.alfa1}'/segreto.txt", f"cat $'{fuori_alfa}' 2>&1"):
        prova(f"minori5: predefinito, `{cmd[:50].replace(str(a.radice), '<R>')}`: negato "
              "(ANSI-C risolto)", pred(cmd).negato)
    for cmd in (f"cat $'{fuori_comune}'", f"cat $\"{fuori_comune}\"",
                f"cat $'{fuori_comune.replace('/', chr(92) + 'x2f')}'"):
        prova(f"minori5: alfa, `{cmd[:50].replace(str(a.radice), '<R>')}`: negato", alfa(cmd).negato)
    prova("minori5: `cat $'a b'` senza percorsi vietati: ammesso (l'espansione non inventa niente)",
          pred("cat $'p.txt'", cwd=a.progetto).ammesso)
    # cd con graffe o con sostituzione: cartella sconosciuta, un relativo dopo si nega
    for cmd in ("cd alfa-{uno,due} && cat sotto/f.txt", "cd $(echo alfa-uno) && cat sotto/f.txt",
                "cd \"$(echo alfa-uno)\" && cat sotto/f.txt", "cd `echo alfa-uno` && cat sotto/f.txt",
                "cd \"$(pwd)/alfa-uno\" && cat sotto/f.txt", "cd $(pwd)/alfa-uno && cat sotto/f.txt",
                "cd alfa-uno && cat sotto/f.txt"):
        r = pred(cmd, aperta_in=a.comune, cwd=a.radice)
        prova(f"minori5: predefinito (cwd sopra alfa), `{cmd}`: negato", r.negato, repr(r))
    for cmd in ("cd progetto && cat p.txt", "cd $(pwd)/progetto && cat p.txt",
                "cd \"$(pwd)/progetto\" && cat p.txt"):
        r = pred(cmd, aperta_in=a.comune, cwd=a.comune)
        prova(f"minori5: predefinito, `{cmd}` (cartella senza divieti): ammesso", r.ammesso, repr(r))
    r = alfa(f"cd {a.alfa1}{{,/sotto}} && cat sotto/f.txt")
    prova("minori5: alfa, `cd <sua>{,/sotto} && cat sotto/f.txt`: cartella sconosciuta, negato "
          "(scrivi il percorso)", r.negato, repr(r))
    # il tetto: non e' silenzioso, e non e' un modo di nascondere un percorso
    padding = "true; " * 400 + f"cat {fuori_alfa}"
    prova("minori5: `true;` x400 e poi un file di alfa: negato (il padding non nasconde niente)",
          pred(padding).negato)
    nomi = "true " + " ".join(f"n{i}" for i in range(400))
    r = pred(nomi + f"; cat {fuori_alfa}")
    prova("minori5: 400 nomi distinti e poi un file di alfa: negato (un percorso vero non e' "
          "fermato dal tetto dei nomi)", r.negato, repr(r))
    n0 = len(a.registro())
    r = pred(nomi, aperta_in=a.progetto)
    nuove = a.registro()[n0:]
    prova("minori5: 400 nomi distinti da soli, dal predefinito: ammesso ma con una riga "
          "`nota` nel registro (il tetto non e' silenzioso)",
          r.ammesso and len(nuove) == 1 and nuove[0]["esito"] == "nota"
          and "troppi" in nuove[0]["motivo"], f"{r!r} {nuove}")
    grande = a.alfa1 / "grande"
    grande.mkdir(exist_ok=True)
    for i in range(210):
        (grande / f"f{i:03d}.txt").write_text("x", "utf-8")
    cmd = "cat " + " ".join(["grande/*", "grande/f*", "grande/f?*", "grande/*.txt",
                             "grande/f*.txt", "grande/f0*"])
    r = alfa(cmd)
    prova("minori5: alfa, sei glob da 210 voci (oltre il tetto delle espansioni): negato, "
          "il motivo dice 'troppi percorsi'", r.negato and "troppi percorsi" in r.motivo, repr(r))
    r = alfa("cat grande/* > /dev/null")
    prova("minori5: alfa, un glob da 210 voci (sotto il tetto): ammesso", r.ammesso, repr(r))
    C = _importa_compartimenti()
    if C is not None and hasattr(C, "MAX_PERCORSI_DURO"):
        vecchio = C.MAX_PERCORSI_DURO
        try:
            C.MAX_PERCORSI_DURO = 20
            avvisi = []
            C.percorsi_richiesti("Bash", {"command": "cat " + " ".join(
                f"{a.progetto}/x{i}" for i in range(50))}, str(a.progetto), avvisi=avvisi)
            prova("minori5: oltre il tetto duro dei percorsi l'analisi lo dice (avvisi)",
                  "percorsi" in avvisi, str(avvisi))
        finally:
            C.MAX_PERCORSI_DURO = vecchio
    else:
        prova("minori5: oltre il tetto duro dei percorsi l'analisi lo dice (avvisi)", False,
              "MAX_PERCORSI_DURO non c'e'")
    # PYTHONPATH con un json.py che esce: non spegne l'hook
    tmp = a.radice / "pp"
    tmp.mkdir(exist_ok=True)
    (tmp / "json.py").write_text("raise SystemExit(0)\n", "utf-8")
    (tmp / "re.py").write_text("raise SystemExit(0)\n", "utf-8")
    env = dict(a.env())
    env["PYTHONPATH"] = str(tmp)
    r = a.chiama(a.pl("Bash", {"command": f"cat {fuori_alfa}"}, sid=S_COMUNE, aperta_in=a.progetto),
                 env=env)
    prova("minori5: PYTHONPATH con un json.py e un re.py che escono: l'hook nega lo stesso",
          r.negato, repr(r))
    # BaseException e hang: l'hook esce 0 con la riga e l'avviso
    seg = a.pl("Bash", {"command": f"cat {fuori_alfa}"}, sid=S_COMUNE, aperta_in=a.progetto)
    base = a.radice / "copia-hook-5"
    hook = _copia_checkout(a, base)
    comp = base / "plancia" / "compartimenti.py"
    originale = comp.read_text("utf-8")
    marca = a.dati / "guardiano.non-parte"
    r = _corri_copia(a, hook, seg)
    prova("minori5: la copia intatta nega", r is not None and r.negato, repr(r))
    guasti = {
        "sys.exit(0) in fondo al modulo": "\nimport sys\nsys.exit(0)\n",
        "sys.exit(1) in fondo al modulo": "\nimport sys\nsys.exit(1)\n",
        "raise KeyboardInterrupt": "\nraise KeyboardInterrupt\n",
        "un ciclo infinito (hang)": "\nwhile True:\n    pass\n",
        "un sonno lunghissimo (hang)": "\nimport time\ntime.sleep(600)\n",
    }
    for nome, codice in guasti.items():
        comp.write_text(originale + codice, "utf-8")
        if marca.exists():
            marca.unlink()
        n0 = len(a.registro())
        r = _corri_copia(a, hook, seg, timeout=20)
        nuove = [x for x in a.registro()[n0:] if x.get("esito") == "guardiano-non-parte"]
        if r is None:
            prova(f"minori5: {nome}: l'hook torna entro il tempo massimo (non resta appeso)",
                  False, "non e' tornato in 20 s")
            continue
        try:
            avviso = json.loads(r.out).get("systemMessage", "")
        except ValueError:
            avviso = ""
        prova(f"minori5: {nome}: rc 0, nessun diniego, una riga `guardiano-non-parte` e il "
              "`systemMessage`", r.rc == 0 and not r.negato and len(nuove) == 1
              and "plancia-guardiano non parte" in avviso, f"{r!r} {nuove}")
        if "hang" in nome:
            prova(f"minori5: {nome}: torna in meno di 8 secondi (il tempo massimo e' 2)",
                  r.secondi < 8, f"{r.secondi:.1f} s")
    comp.write_text(originale, "utf-8")
    if marca.exists():
        marca.unlink()
    r = _corri_copia(a, hook, seg)
    prova("minori5: riparata, la copia torna a negare", r is not None and r.negato, repr(r))
    a.togli_config()


def _alfa_pulita(a: Ambiente):
    """Una cartella di alfa tutta nuova (un repository finto, con qualche file), e
    la config `bloccante` che la include. Le altre prove lasciano collegamenti e
    sottocartelle in `alfa-uno` che un comando ricorsivo seguirebbe fuori dai permessi
    (a ragione)."""
    pulita = a.radice / "alfa-pulita-6"
    (pulita / ".git").mkdir(parents=True, exist_ok=True)
    (pulita / "src").mkdir(exist_ok=True)
    for f in ("body.md", "list.txt", "src/f.txt", "f", "sotto.txt"):
        (pulita / f).write_text("x\n", "utf-8")
    cfg = a.config("bloccante")
    cfg["compartimenti"]["alfa"]["cartelle"].append(str(pulita))
    a.scrivi_config(cfg)
    return pulita


def _prove_regressioni_6(prova, a: Ambiente):
    """Sesto giro, punto 1: le tre regressioni del quinto giro (gli argomenti che il
    comando LEGGE come file tornano percorsi: `gh -F`, `gh api -F k=@file`, `grep -rf`,
    `git -c include.path=`, `curl -d @file`) e i falsi positivi nuovi (`cd` con una
    sostituzione di comando o con graffe, `echo $PATH` verso un altro comando)."""
    a.togli_config()
    pulita = _alfa_pulita(a)
    (a.comune / "bin").mkdir(exist_ok=True)
    nota = str(a.comune / "nota.txt")
    segreto = str(a.alfa1 / "segreto.txt")

    def alfa(cmd, env=None):
        return a.chiama(a.pl("Bash", {"command": cmd}, sid=S_ALFA_LIBERA, aperta_in=pulita),
                        env=env)

    def pred(cmd):
        return a.chiama(a.pl("Bash", {"command": cmd}, sid=S_COMUNE, aperta_in=a.progetto))

    leggono = [
        f"gh issue create -F {{}}", f"gh pr create -F {{}} -t x", f"gh issue comment 3 -F {{}}",
        f"gh api repos/x/y/issues -F body=@{{}}", f"gh api repos/x/y/issues --field body=@{{}}",
        f"gh api repos/x/y/issues --field=body=@{{}}", f"gh api repos/x/y --input {{}}",
        f"gh pr create --body-file {{}}", f"grep -rf {{}} .", f"grep -nf {{}} f",
        f"grep -f {{}} f", f"grep -e x -f {{}} f", f"grep -rif {{}} .", f"rg -f {{}} .",
        f"git -c include.path={{}} status", f"git -c core.excludesFile={{}} status",
        f"git -c core.hooksPath={{}} status", f"curl -d @{{}} http://localhost/x",
        f"curl --data-binary @{{}} http://localhost/x", f"curl -F f=@{{}} http://localhost/x",
        f"sed -nf {{}} f", f"sed -f {{}} f", f"awk -f {{}} f", f"jq --slurpfile a {{}} . f",
    ]
    for c in leggono:
        cmd = c.format(nota)
        r = alfa(cmd)
        prova(f"reg6: alfa, `{cmd[:60].replace(str(a.radice), '<R>')}`: negato (il file letto "
              "e' di fuori)", r.negato, repr(r))
        cmd = c.format(segreto)
        r = pred(cmd)
        prova(f"reg6: predefinito, `{cmd[:60].replace(str(a.radice), '<R>')}`: negato (il file "
              "letto e' di alfa)", r.negato, repr(r))
    onesti = [
        "gh api repos/x/y/issues -F title=ciao -f body=testo", "gh api /repos/x/y/pulls",
        "gh api repos/x/y/issues -F n=5", "gh issue create -F body.md",
        "gh pr create --body-file body.md", "gh api repos/x/y --input body.md",
        "gh issue create -t titolo -b 'un corpo con /path/x'", "grep -rf list.txt .",
        "grep -nf list.txt f", "git -c user.name=x status", "git -c core.pager=cat log -1",
        "curl -d @body.md http://localhost/x", "sed -nf list.txt f",
        "jq --arg f /opt/x . f", "find . -path /opt/x/y -name z",
        "gh workflow run x.yml -f a=b", "grep -rn foo .",
    ]
    for c in onesti:
        r = alfa(c)
        prova(f"reg6: alfa, `{c[:60]}`: ammesso", r.ammesso, repr(r))
    # `cd` con una sostituzione di comando o con graffe
    cd_ok = [
        "cd $(git rev-parse --show-toplevel) && git status", "cd $(git rev-parse --show-toplevel) && ls",
        f"cd \"$(dirname {pulita}/f)\" && ls", "cd $(dirname $0) && ls", "cd $(realpath src) && ls",
        "cd $(readlink -f .) && ls", "cd $(echo src) && ls", "cd {src,tests} && ls",
        "cd src{,} && ls", "cd \"$(mktemp -d)\" && ls", "cd $(pwd) && ls", "cd $PWD && ls",
        "cd `pwd` && ls", "cd \"$(cd src && pwd)\" && ls", "cd $(dirname $(realpath f)) && git status",
        "cd \"$(dirname \"$0\")\" && pwd", "cd - && ls", "cd $(git rev-parse --show-toplevel)/src && cat f.txt",
        "cd $(git rev-parse --show-toplevel) && cat src/f.txt",
        "cd \"$(dirname \"$(realpath f)\")\" && ls src/",
    ]
    for c in cd_ok:
        r = alfa(c)
        prova(f"reg6: alfa, `{c}`: ammesso (la cartella si risolve, o e' sconosciuta e non nega "
              "un nome semplice)", r.ammesso, repr(r))
    cd_no = [
        f"cd $(dirname {nota}) && ls", f"cd $(echo {a.comune}) && cat nota.txt",
        f"cd \"$(dirname {nota})\" && cat nota.txt", f"cd $(realpath {a.comune}) && ls",
        f"cd $(readlink -f {a.comune}) && ls", "cd $(git rev-parse --show-toplevel)/.. && ls",
        f"cd \"$(cd {a.comune} && pwd)\" && ls", "cd $(dirname $0) && cat src/f.txt",
        "cd - && cat src/f.txt", "cd {src,tests} && cat src/f.txt", "cd $(mktemp -d) && ls ../x",
        f"cd $(dirname $0) && cat {nota}",
    ]
    for c in cd_no:
        r = alfa(c)
        prova(f"reg6: alfa, `{c[:66].replace(str(a.radice), '<R>')}`: negato (la cartella e' fuori, o "
              "un relativo con una barra dopo una cartella sconosciuta)", r.negato, repr(r))
    r = alfa("cd - && ls src/")
    prova("reg6: alfa, `cd - && ls src/`: negato, il motivo dice che la cartella non si sa "
          "determinare", r.negato and "non si sa determinare" in r.motivo, repr(r))
    # predefinito: la cartella si risolve e il divieto sotto resta
    r = a.chiama(a.pl("Bash", {"command": f"cd $(dirname {segreto}) && cat segreto.txt"},
                      sid=S_COMUNE, aperta_in=a.progetto))
    prova("reg6: predefinito, `cd $(dirname <file di alfa>) && cat segreto.txt`: negato",
          r.negato, repr(r))
    r = a.chiama(a.pl("Bash", {"command": f"cd $(dirname {a.progetto}/p.txt) && cat p.txt"},
                      sid=S_COMUNE, aperta_in=a.progetto))
    prova("reg6: predefinito, `cd $(dirname <file del progetto>) && cat p.txt`: ammesso",
          r.ammesso, repr(r))
    # `echo $PATH` verso un altro comando: non produce percorsi dai due punti
    env = dict(a.env())
    env["PATH"] = f"/usr/bin:{a.comune}/bin:{a.beta1}:/bin"
    for c in ("echo $PATH | tr : '\\n'", "echo $PATH | wc -c", "echo $PATH | cut -d: -f1",
              "echo $PATH | grep -c bin", "echo $PATH | awk -F: '{print $1}'",
              "echo $PATH | sed 's/:/ /g'", "echo $PATH | xargs -n1", "echo $PATH | head -c 20",
              "printf %s $PATH | tr : '\\n'", "echo $PATH", "echo \"$PATH\" | tr : '\\n' | sort",
              "PATH=/opt/x:$PATH python3 -V", "export PATH=$HOME/bin:$PATH", "env PATH=$PATH:/opt/x ls",
              "echo $PATH | tr ':' '\\n' | while read d; do ls -d \"$d\" > /dev/null; done"):
        r = alfa(c, env=env)
        prova(f"reg6: alfa, `{c[:60]}`, PATH con cartelle fuori dai permessi: ammesso "
              "(un elenco da una variabile non e' un percorso)", r.ammesso, repr(r))
    r = alfa(f"docker run -v {a.comune}:/app x ls /app")
    prova("reg6: alfa, `docker -v <fuori>:/app`: negato (i due punti scritti nel comando "
          "dividono ancora)", r.negato, repr(r))
    r = alfa(f"cat {nota}:{pulita}/f")
    prova("reg6: alfa, `cat <fuori>:<dentro>`: negato", r.negato, repr(r))
    a.togli_config()


CASI_G6_COMMENTI = [
    "# nota: usa <<EOF per il testo\ncat @@\nEOF",
    "# nota: usa <<EOF per il testo\ncat @@",
    "# <<-EOF\ncat @@", "echo hi # <<EOF\ncat @@", "[[ 1 == 1 ]] # <<EOF\ncat @@",
    "if false; then # <<EOF\ncat @@\nfi", "x=${x:-<<EOF}\ncat @@", "echo $((1 << b))\ncat @@",
    "# non e' un heredoc, e non apre virgolette\ncat @@", "echo x # <<'EOF'\ncat @@\nEOF",
    "true # <<EOF\ntrue # <<EOF\ncat @@", "echo ${#PATH}\ncat @@",
    "echo a#b\ncat @@", "# un `apice inverso\ncat @@", "# usa <<EOF\necho ok\n# <<EOF\ncat @@\nEOF",
]
CASI_G6_COMMENTI_ONESTI = [
    "ls # vedi @F@", "ls # vedi @F@\n# e anche <<EOF", "true # cat @F@",
    "# cat @F@\nls", "git status # @F@", "echo ok # <<EOF\nls",
    "cat <<EOF\n# non e' un commento, e' testo\nEOF", "cat > f <<'EOF'\n# x <<EOF\nEOF",
]


def _prove_commenti_6(prova, a: Ambiente):
    """Sesto giro, punto 3: un commento con `<<` non nasconde il resto (i commenti
    si tolgono prima di cercare gli heredoc), e un percorso dentro un commento non e'
    un percorso."""
    a.togli_config()
    pulita = _alfa_pulita(a)
    nota = str(a.comune / "nota.txt")
    segreto = str(a.alfa1 / "segreto.txt")
    for c in CASI_G6_COMMENTI:
        cmd = c.replace("@@", segreto)
        r = a.chiama(a.pl("Bash", {"command": cmd}, sid=S_COMUNE, aperta_in=a.progetto))
        prova(f"commenti6: predefinito, `{cmd[:50].splitlines()[0]}...`: negato (il resto non e' "
              "nascosto)", r.negato, repr(r))
        cmd = c.replace("@@", nota)
        r = a.chiama(a.pl("Bash", {"command": cmd}, sid=S_ALFA_LIBERA, aperta_in=pulita))
        prova(f"commenti6: alfa, `{cmd[:50].splitlines()[0]}...`: negato", r.negato, repr(r))
    for c in CASI_G6_COMMENTI_ONESTI:
        cmd = c.replace("@F@", nota)
        r = a.chiama(a.pl("Bash", {"command": cmd}, sid=S_ALFA_LIBERA, aperta_in=pulita))
        prova(f"commenti6: alfa, `{cmd[:50].splitlines()[0]}...`: ammesso (un commento non e' "
              "codice)", r.ammesso, repr(r))
    # il commento non si scambia per un `#` dentro una parola o dentro virgolette
    for cmd in (f"cat {segreto}#x", f"echo '# <<EOF'\ncat {segreto}", f"echo \"a # b\"; cat {segreto}",
                f"echo a\\ #b; cat {segreto}"):
        r = a.chiama(a.pl("Bash", {"command": cmd}, sid=S_COMUNE, aperta_in=a.progetto))
        prova(f"commenti6: predefinito, `{cmd[:50].splitlines()[0]}...`: negato (`#` che non "
              "e' un commento)", r.negato, repr(r))
    a.togli_config()


def _prove_prefissi_6(prova, a: Ambiente):
    """Sesto giro, punto 4: i prefissi di comando si svolgono (`timeout 5`, `nice -n 5`,
    `sudo -u X`, `caffeinate`, `stdbuf -o0`, `arch -arm64`, `time`, `command`,
    `builtin`, `exec`, `nohup`, `env` con opzioni e `VAR=`, `xargs -I {}`): il comando
    vero e' quello dopo."""
    a.togli_config()
    pulita = _alfa_pulita(a)
    dati_cfg = str(a.dati / "config.json")
    segreto = str(a.alfa1 / "segreto.txt")
    prefissi = [
        "timeout 5 {}", "gtimeout 5 {}", "timeout -s KILL 5 {}", "timeout --signal=KILL 5s {}",
        "nice -n 5 {}", "nice -5 {}", "nice {}", "ionice -c 3 {}", "ionice -c 2 -n 5 {}",
        "sudo -u root {}", "sudo -E {}", "sudo -n -u root -H {}", "sudo -- {}", "doas -u root {}",
        "caffeinate {}", "caffeinate -i {}", "caffeinate -t 60 {}", "stdbuf -o0 {}",
        "stdbuf -o 0 -e L {}", "arch -arm64 {}", "arch -x86_64 {}", "time {}", "time -p {}",
        "command {}", "builtin {}", "exec {}", "nohup {}", "env {}", "env -i {}",
        "env -i A=1 {}", "env -u X A=b {}", "env A=1 B=2 {}", "/usr/bin/env A=1 {}",
        "setsid {}", "flock /tmp/l {}", "nohup nice -n 5 timeout 5 {}",
        "sudo -E timeout 5 nice -n 1 {}", "A=1 {}", "A=1 nice -n 5 {}",
    ]
    for p in prefissi:
        for chi, kw, bersaglio in (("predefinito", dict(sid=S_COMUNE, aperta_in=a.progetto),
                                    f"rm {dati_cfg}"),
                                   ("alfa", dict(sid=S_ALFA_LIBERA, aperta_in=pulita),
                                    f"rm {dati_cfg}")):
            cmd = p.format(bersaglio)
            r = a.chiama(a.pl("Bash", {"command": cmd}, **kw))
            prova(f"pref6: {chi}, `{cmd[:60].replace(str(a.radice), '<R>')}`: negato (il file "
                  "del guardiano)", r.negato, repr(r))
    for cmd in (f"timeout 5 sh -c 'rm {dati_cfg}'", f"nice -n 5 sh -c \"echo x > {dati_cfg}\"",
                f"trap 'rm {dati_cfg}' EXIT", f"timeout 5 sed -i '' s/a/b/ {dati_cfg}",
                f"sudo -u root truncate -s0 {dati_cfg}", f"nice -n 5 tee {dati_cfg} < /dev/null",
                f"echo 'rm {dati_cfg}' > s.sh; nice -n 5 bash s.sh",
                f"echo 'plancia config guardiano spento' > s.sh; caffeinate -i sh s.sh",
                f"timeout 5 plancia config guardiano spento", f"nice -n 1 plancia config guardiano spento",
                f"sudo -u root python3 -m plancia.cli config guardiano spento",
                f"echo {dati_cfg} | xargs -I {{}} rm {{}}", f"echo {dati_cfg} | xargs -n 1 rm",
                f"echo {dati_cfg} | timeout 5 xargs rm"):
        for chi, kw in (("predefinito", dict(sid=S_COMUNE, aperta_in=a.progetto)),
                        ("alfa", dict(sid=S_ALFA_LIBERA, aperta_in=pulita))):
            r = a.chiama(a.pl("Bash", {"command": cmd}, **kw))
            prova(f"pref6: {chi}, `{cmd[:60].replace(str(a.radice), '<R>')}`: negato", r.negato,
                  repr(r))
    r = a.chiama(a.pl("Bash", {"command": f"echo 'cat {segreto}' > s.sh; timeout 5 sh s.sh"},
                      sid=S_COMUNE, aperta_in=a.progetto))
    prova("pref6: predefinito, uno script scritto e lanciato con `timeout 5 sh s.sh`: negato",
          r.negato, repr(r))
    for p in ("timeout 10 {}", "nice -n 5 {}", "sudo -u root {}", "caffeinate -i {}",
              "env -i A=1 {}", "xargs -I {{}} {}", "time -p {}"):
        cmd = p.format(f"cat {segreto}")
        r = a.chiama(a.pl("Bash", {"command": cmd}, sid=S_COMUNE, aperta_in=a.progetto))
        prova(f"pref6: predefinito, `{cmd[:60].replace(str(a.radice), '<R>')}`: la lettura di un "
              "file di alfa resta negata", r.negato, repr(r))
    for cmd in ("timeout 5 ls", "nice -n 5 make", "sudo -u x ls .", "env -i FOO=1 ls",
                "time -p ls", "caffeinate -i ls", "stdbuf -o0 cat f", "arch -arm64 ls",
                "nohup ls", "timeout 5 grep -rn x src", "nice -n 19 python3 -c 'print(1)'",
                "xargs -I {} echo {} < list.txt", f"timeout 5 cat {pulita}/f", "ionice -c 3 ls src",
                f"echo x > {dati_cfg}.non-e-vero".replace(str(a.dati), str(pulita))):
        r = a.chiama(a.pl("Bash", {"command": cmd}, sid=S_ALFA_LIBERA, aperta_in=pulita))
        prova(f"pref6: alfa, `{cmd[:60]}`: ammesso (un prefisso non nega niente)", r.ammesso,
              repr(r))
    a.togli_config()


def _prove_sed_awk_6(prova, a: Ambiente):
    """Sesto giro, punto 5: sed e awk che scrivono (`w`, `W`, `s///w`, `print > "f"`,
    `printf >> "f"`), leggono (`r`, `R`, `getline < "f"`) o lanciano (`e`, `system()`,
    `print | "cmd"`, `"cmd" | getline`) sono scritture, letture, esecuzioni dei file e
    dei comandi indicati."""
    a.togli_config()
    pulita = _alfa_pulita(a)
    D = str(a.dati / "config.json")
    nota = str(a.comune / "nota.txt")
    segreto = str(a.alfa1 / "segreto.txt")
    scrivono = [
        "sed -n 'w @@' f", "sed 's/a/b/w @@' f", "sed -n 'W @@' f", "sed -e 'w @@' f",
        "sed -n '1w @@' f", "sed -n '/x/w @@' f", "sed -n '$!w @@' f", "sed -n 'p;w @@' f",
        "sed --expression='w @@' f", "sed -n -e p -e 'w @@' f", "gsed -n 'w @@' f",
        "sed -n \"s/a/b/gw @@\" f", "sed '1{p;w @@\n}' f",
        "awk 'BEGIN{print \"{}\" > \"@@\"}'", "awk '{print > \"@@\"}' f",
        "awk '{printf \"x\" >> \"@@\"}' f", "awk 'BEGIN{printf(\"{}\") > \"@@\"}'",
        "awk 'BEGIN{system(\"rm @@\")}'", "awk 'BEGIN{printf \"{}\" | \"tee @@\"}'",
        "awk 'BEGIN{\"rm @@\" | getline}'", "sed 'e rm @@' f", "sed -n '1e rm @@' f",
        "awk -v x=@@ 'BEGIN{print \"x\" > x}'", "awk -v x=@@ '{print >> x}' f",
        "gawk '{print > \"@@\"}' f", "awk 'BEGIN{system(\"echo x > @@\")}'",
    ]
    for c in scrivono:
        cmd = c.replace("@@", D)
        for chi, kw in (("predefinito", dict(sid=S_COMUNE, aperta_in=a.progetto)),
                        ("alfa", dict(sid=S_ALFA_LIBERA, aperta_in=pulita))):
            r = a.chiama(a.pl("Bash", {"command": cmd}, **kw))
            prova(f"sedawk6: {chi}, `{cmd[:58].splitlines()[0].replace(str(a.radice), '<R>')}`: "
                  "negato (scrive il file del guardiano)", r.negato, repr(r))
    leggono = [
        "sed 'r @@' f", "sed -n 'R @@' f", "sed 'e cat @@' f", "sed -n '/x/r @@' f",
        "awk 'BEGIN{while((getline l < \"@@\")>0) print l}'",
        "awk -v x=@@ 'BEGIN{while((getline l<x)>0)print l}'",
        "awk 'BEGIN{\"cat @@\" | getline l; print l}'", "awk 'BEGIN{system(\"cat @@\")}'",
        "awk 'BEGIN{print | \"cat @@\"}'",
    ]
    for c in leggono:
        cmd = c.replace("@@", segreto)
        r = a.chiama(a.pl("Bash", {"command": cmd}, sid=S_COMUNE, aperta_in=a.progetto))
        prova(f"sedawk6: predefinito, `{cmd[:58].replace(str(a.radice), '<R>')}`: negato (legge "
              "un file di alfa)", r.negato, repr(r))
        cmd = c.replace("@@", nota)
        r = a.chiama(a.pl("Bash", {"command": cmd}, sid=S_ALFA_LIBERA, aperta_in=pulita))
        prova(f"sedawk6: alfa, `{cmd[:58].replace(str(a.radice), '<R>')}`: negato (legge un file "
              "di fuori)", r.negato, repr(r))
    onesti = [
        "sed 's/a/b/' f", "sed -n '/x/p' f", "sed 's/w/x/g' f", "sed 's/a/w b/' f",
        "sed -n '2{p;q}' f", "sed 'y/abc/xyz/' f", "sed '1!G;h;$!d' f", "sed -n 'p;p' f",
        "sed -i '' 's/a/b/' f", "sed 's/[wr]/x/' f", "sed '/^$/d' f", "sed -E 's/(a|b)+/x/' f",
        "sed 'a\\\ntesto con w e r' f", "sed 's/a/b/;s/c/d/' f", "sed -n '/start/,/end/p' f",
        "awk '$1 > 5' f", "awk '{print $1 > \"/dev/stderr\"}' f", "awk '{print > \"out.txt\"}' f",
        "sed -n 'w out.txt' f", "awk 'BEGIN{system(\"ls\")}'", "awk '{print}' f",
        "awk '$1 > \"m\"' f", "awk 'BEGIN{print \"a\" | \"sort\"}'", "awk -v n=3 '$1 > n' f",
        "awk '{print > \"src/out.txt\"}' f", "sed -n 'w src/o.txt' f", "awk '{print > \"/dev/null\"}' f",
        "awk 'BEGIN{\"date\" | getline d; print d}'", "awk 'BEGIN{while((getline l < \"list.txt\")>0) n++}'",
        "sed 'r list.txt' f",
    ]
    for c in onesti:
        r = a.chiama(a.pl("Bash", {"command": c}, sid=S_ALFA_LIBERA, aperta_in=pulita))
        prova(f"sedawk6: alfa, `{c[:58].splitlines()[0]}`: ammesso", r.ammesso, repr(r))
    # in una cartella condivisa
    cod = a.radice / "codice-condiviso-6"
    cod.mkdir(exist_ok=True)
    X = str(cod)
    a.togli_config()
    pulita = _alfa_pulita(a)
    cfg = _testo(a.dati / "config.json")
    a.scrivi_config(dict(json.loads(cfg), condivise=[X]))
    for c in ("sed -n 'w @@/f' f", "awk '{print > \"@@/f\"}' f", "sed 's/a/b/w @@/f' f",
              "awk 'BEGIN{system(\"touch @@/f\")}'", "sed 'e touch @@/f' f"):
        cmd = c.replace("@@", X)
        r = a.chiama(a.pl("Bash", {"command": cmd}, sid=S_ALFA_LIBERA, aperta_in=pulita))
        prova(f"sedawk6: alfa, condivisa, `{cmd[:58].replace(str(a.radice), '<R>')}`: negato "
              "(la cartella condivisa non si scrive)", r.negato and "condivisa" in r.motivo, repr(r))
    for c in ("sed 'r @@/f' f", "awk 'BEGIN{while((getline l < \"@@/f\")>0) print l}'"):
        cmd = c.replace("@@", X)
        r = a.chiama(a.pl("Bash", {"command": cmd}, sid=S_ALFA_LIBERA, aperta_in=pulita))
        prova(f"sedawk6: alfa, condivisa, `{cmd[:58].replace(str(a.radice), '<R>')}`: ammesso "
              "(lettura)", r.ammesso, repr(r))
    a.togli_config()


def _prove_condivise_6(prova, a: Ambiente):
    """Sesto giro, punto 2: condivise sicure. Una voce che e' la home, un antenato della
    cartella dei dati, di `<claude>/projects` o di `<claude>` (o sta dentro projects) e'
    ignorata con una nota (`plancia config condivise` la rifiuta); la ricerca che parte
    da una condivisa non entra mai nei dati ne' in projects; le scritture via git
    (`commit`, `add`, `fetch`, `branch`, `tag`, `config`, `gc`, `clone` dentro...), via
    `-t DIR`, `--target-directory`, `-o`, `--output` e un collegamento simbolico creato nello
    stesso comando sono scritture."""
    cod = a.radice / "codice-condiviso-6b"
    (cod / "sub").mkdir(parents=True, exist_ok=True)
    (cod / "README").write_text("x\n", "utf-8")
    (a.claude / "skills").mkdir(parents=True, exist_ok=True)
    (a.claude / "skills" / "s.md").write_text("una skill\n", "utf-8")
    X = str(cod)
    nota = str(a.comune / "nota.txt")
    a.togli_config()
    pulita = _alfa_pulita(a)
    base = json.loads(_testo(a.dati / "config.json"))

    def alfa(cmd, tool="Bash", ti=None):
        return a.chiama(a.pl(tool, ti or {"command": cmd}, sid=S_ALFA_LIBERA, aperta_in=pulita))

    def con(*voci):
        a.togli_config()
        try:
            (a.dati / "guardiano.condivise-nota").unlink()
        except OSError:
            pass
        a.scrivi_config(dict(base, condivise=list(voci)))

    # le voci che contengono i dati, projects o <claude>
    voci = {
        "la home": str(a.home), "la cartella di configurazione di Claude": str(a.claude),
        "<claude>/projects": str(a.claude / "projects"),
        "un antenato dei dati (e di tutto)": str(a.radice),
        "dentro projects": str(a.claude / "projects" / "x"),
        "la cartella dei dati": str(a.dati), "dentro i dati": str(a.dati / "sotto"),
    }
    for chi, voce in voci.items():
        con(voce, X)
        r = alfa(f"cat {nota}")
        righe = [x for x in a.registro() if x.get("esito") == "nota"]
        prova(f"cond6: la voce `{chi}` e' ignorata: il comune resta fuori dai permessi (negato)",
              r.negato, repr(r))
        prova(f"cond6: ...con una nota nel registro, e l'altra voce vale ({chi})",
              len(righe) == 1 and "condivise" in righe[0].get("motivo", "")
              and alfa(f"cat {X}/README").ammesso, str(righe))
    con(str(a.claude / "skills"))
    r = alfa(f"cat {a.claude}/skills/s.md")
    prova("cond6: una voce DENTRO <claude> ma non projects (le skill) e' accettata: si legge",
          r.ammesso and not [x for x in a.registro() if x.get("esito") == "nota"], repr(r))
    for cmd in (f"grep -rn x {a.radice}", f"rg x {a.home}", f"find {a.claude} -name x",
                f"ls -R {a.claude}/projects", f"grep -r x {a.dati}", f"tree {a.radice}"):
        con(str(a.radice), str(a.home), str(a.claude), X)
        r = alfa(cmd)
        prova(f"cond6: con voci antenate, `{cmd[:50].replace(str(a.radice), '<R>')}`: la ricerca "
              "non entra nei dati ne' in projects (negata)", r.negato, repr(r))
    for tool, ti in (("Grep", {"pattern": "x", "path": str(a.radice)}),
                     ("Glob", {"pattern": "**/*.json", "path": str(a.radice)}),
                     ("Grep", {"pattern": "x", "path": str(a.home)}),
                     ("Grep", {"pattern": "x", "path": str(a.dati)})):
        r = alfa("", tool, ti)
        prova(f"cond6: con voci antenate, {tool} da {ti['path'][-14:]}: negato", r.negato, repr(r))
    # il controllo non e' solo in caricamento: una condivisa che contenesse i dati (a mano,
    # fuori dal caricamento) non fa entrare una ricerca
    C = _importa_compartimenti()
    if C is not None:
        try:
            con(X)
            cfg = C.leggi_config(str(a.dati))
            finti = a.comune / "dati-finti"
            finti.mkdir(exist_ok=True)
            payload = a.pl("Bash", {"command": "ls"}, sid=S_ALFA_LIBERA, aperta_in=pulita)
            casi = []
            for nome, dati_dir, voce, cerca in (
                    ("una voce che contiene projects", str(a.dati), str(a.claude), str(a.claude)),
                    ("una voce che contiene i dati", str(finti), str(a.comune), str(a.comune))):
                amb = C.Ambito(cfg["compartimenti"], [], home=str(a.home), data_dir=dati_dir,
                               claude_dir=str(a.claude), condivise=[X])
                amb.condivise.append(voce)        # a mano, fuori dal controllo del caricamento
                chi = C.chiamante(payload, amb)
                v = C._percorso_nominato(cerca, chi, amb, "alfa", True, False)
                casi.append(bool(v))
                v2 = C._percorso_nominato(cerca, chi, amb, "alfa", None, False)
                casi.append(not v2)           # senza ricerca (non ricorsivo) una lettura si puo'
            prova("cond6: in-process, una condivisa (aggiunta a mano) che contiene projects o i "
                  "dati: la ricerca ricorsiva che parte da li' e' negata, un accesso semplice no",
                  all(casi), str(casi))
        except Exception as e:  # noqa: BLE001
            prova("cond6: in-process, una condivisa che contiene i dati: la ricerca e' negata",
                  False, repr(e))
    else:
        prova("cond6: in-process, una condivisa che contiene i dati: la ricerca e' negata",
              False, "compartimenti non si importa")
    # la CLI rifiuta le stesse voci
    env = dict(a.env())
    env["PYTHONPATH"] = str(RADICE)

    def plancia(*args):
        p = subprocess.run([sys.executable, str(RADICE / "bin" / "plancia"), *args], env=env,
                           cwd=str(RADICE), capture_output=True, timeout=120)
        return p.returncode, p.stdout.decode("utf-8", "replace") + p.stderr.decode("utf-8", "replace")

    a.togli_config()
    rc, out = plancia("config", "condivise", json.dumps([X]))
    prova("cond6: `plancia config condivise` accetta una cartella di codice", rc == 0 and X in out, out)
    for chi, voce in (("la home", str(a.home)), ("~", "~"), ("<claude>", str(a.claude)),
                      ("<claude>/projects", str(a.claude / "projects")),
                      ("un antenato dei dati", str(a.radice)), ("la radice /", "/"),
                      ("dentro projects", str(a.claude / "projects" / "x"))):
        rc, out = plancia("config", "condivise", json.dumps([voce]))
        prova(f"cond6: `plancia config condivise` rifiuta {chi} (uscita 2, config invariata)",
              rc == 2 and X in _testo(a.dati / "config.json")
              and voce not in json.loads(_testo(a.dati / "config.json")).get("condivise", []),
              out)
    rc, out = plancia("config", "condivise", json.dumps([str(a.claude / "skills")]))
    prova("cond6: ...e accetta una cartella dentro <claude> che non e' projects", rc == 0, out)
    # git, -t, -o, symlink
    a.togli_config()
    a.scrivi_config(dict(base, condivise=[X]))
    scrivono = [
        f"git -C {X} commit -m x", f"git -C {X} add .", f"git -C {X} fetch", f"git -C {X} branch newb",
        f"git -C {X} tag v1", f"git -C {X} config a b", f"git -C {X} gc", f"git -C {X} update-ref refs/x HEAD",
        f"git -C {X} remote add o u", f"git -C {X} init", f"git -C {X} notes add -m x",
        f"cd {X} && git add .", f"cd {X} && git commit -m x", f"cd {X} && git fetch",
        f"cd {X} && git tag v1", f"cd {X} && git config a b", f"cd {X} && git gc",
        f"git clone . {X}/new", f"git clone http://localhost/r.git {X}/r", f"git -C {X} push",
        f"git -C {X} stash", f"git -C {X} reset --hard", f"git -C {X} checkout -b nuovo",
        f"git -C {X} pull", f"git -C {X} branch -D x", f"git -C {X} tag -d v1",
        f"git -C {X} config --unset a", f"git -C {X} remote remove o", f"git -C {X} commit --amend",
        f"cp -t {X} f", f"cp -t {X} {pulita}/f", f"install -t {X} f", f"ln -t {X} f",
        f"cp --target-directory={X} f", f"mv -t {X} f", f"cp -rt {X} f", f"cp -t{X} f",
        f"cp -a -t {X} src", f"ln -s -t {X} f", f"mv --target-directory {X} f",
        f"gcc -o {X}/a.out x.c", f"pandoc -o {X}/o.pdf i.md", f"mytool --output {X}/o",
        f"mytool --output={X}/o", f"zip {X}/o.zip f", f"split f {X}/p", f"mktemp -p {X}",
        f"mkfifo {X}/p", f"xattr -w a b {X}/README", f"find . -fprint {X}/f",
        f"ffmpeg -i in.mp4 {X}/o.mp4", f"rsync --remove-source-files {X}/README dest/",
        f"sort -o {X}/f g", f"curl -o {X}/f http://localhost/x",
        f"ln -s {X} l && touch l/f", f"ln -s {X} {pulita}/l && touch {pulita}/l/f",
        f"ln -s {X} {pulita}/l && echo x > {pulita}/l/f", f"ln -s {X} l; cp f l/g",
        f"ln -sf {X} {pulita}/l && rm {pulita}/l/README", f"ln -s {X}/sub {pulita}/l && mkdir {pulita}/l/n",
        f"cd {pulita} && ln -s {X} l && touch l/f", f"ln -s ../codice-condiviso-6b {pulita}/l2 && touch {pulita}/l2/f",
    ]
    for c in scrivono:
        r = alfa(c)
        prova(f"cond6: alfa, `{c[:60].replace(str(a.radice), '<R>')}`: negato (scrive nella "
              "cartella condivisa)", r.negato and "condivisa" in r.motivo, repr(r))
    leggono = [
        f"git -C {X} log", f"git -C {X} status", f"git -C {X} branch", f"git -C {X} tag",
        f"git -C {X} config --get user.name", f"git -C {X} config user.name", f"git -C {X} remote -v",
        f"git -C {X} diff", f"git -C {X} show HEAD", f"git -C {X} rev-parse HEAD",
        f"git -C {X} config --list", f"git -C {X} branch -a", f"git -C {X} tag -l",
        f"git clone {X} {pulita}/copia", f"cd {X} && git log", f"cd {X} && git status",
        f"git -C {pulita} commit -m x", f"cd {pulita} && git add .", f"cd {pulita} && git fetch",
        f"git -C {pulita} branch nuovo", f"git -C {pulita} tag v1",
        f"cp {X}/README {pulita}/copia", f"cp -t {pulita}/src f", f"install -t {pulita} f",
        f"gcc -o {pulita}/a.out x.c", f"pandoc -o out.pdf in.md", f"mytool --output out.txt",
        f"zip out.zip f", f"split f p", f"grep -o foo f", "ssh -o StrictHostKeyChecking=no h true",
        "unzip -o a.zip", "tar -o -xf a.tar", "ls -o", f"ln -s {X} {pulita}/l && cat {pulita}/l/README",
        f"ln -s {X} {pulita}/l && ls {pulita}/l", f"ln -s {X}/README {pulita}/l3",
        f"ln -s {pulita}/src {pulita}/l5 && touch {pulita}/l5/n", f"ffmpeg -i {X}/a.mp4",
        f"rsync -a {X}/ {pulita}/copia2/", f"xattr -l {X}/README",
    ]
    for c in leggono:
        r = alfa(c)
        prova(f"cond6: alfa, `{c[:60].replace(str(a.radice), '<R>')}`: ammesso (lettura, o "
              "scrittura nei propri permessi)", r.ammesso, repr(r))
    # un collegamento a un file protetto, creato e scritto nello stesso comando
    D = str(a.dati)
    for chi, kw in (("predefinito", dict(sid=S_COMUNE, aperta_in=a.progetto)),
                    ("alfa", dict(sid=S_ALFA_LIBERA, aperta_in=pulita))):
        for c in (f"ln -s {D} {pulita}/ld && rm {pulita}/ld/config.json",
                  f"ln -s {D} {pulita}/ld && echo x > {pulita}/ld/config.json",
                  f"ln -s {D} {pulita}/ld && truncate -s0 {pulita}/ld/config.json"):
            r = a.chiama(a.pl("Bash", {"command": c}, **kw))
            prova(f"cond6: {chi}, `{c[:56].replace(str(a.radice), '<R>')}`: negato (il collegamento "
                  "porta ai dati)", r.negato, repr(r))
    a.togli_config()


def _prove_allarme_6(prova, a: Ambiente):
    """Sesto giro, punto 6: l'allarme dei due secondi. Per un nominato (o una sessione
    incerta) in `bloccante` l'hook NEGA con un motivo chiaro; per il predefinito ammette
    ma con il `systemMessage` OGNI volta; in `solo-registro` non nega. Anche il ramo
    dell'eccezione ordinaria avvisa per il predefinito."""
    a.togli_config()
    pulita = _alfa_pulita(a)
    seg_alfa = a.pl("Bash", {"command": f"cat {a.comune}/nota.txt"}, sid=S_ALFA_LIBERA, aperta_in=pulita)
    seg_pred = a.pl("Bash", {"command": f"cat {a.alfa1}/segreto.txt"}, sid=S_COMUNE, aperta_in=a.progetto)
    base = a.radice / "copia-hook-6"
    hook = _copia_checkout(a, base)
    wrapper = base / "bin" / "plancia-guardiano"
    testo = wrapper.read_text("utf-8")
    prova("allarme6: il wrapper ha `_TEMPO_MAX = 2.0` (la prova lo accorcia solo nella copia)",
          "_TEMPO_MAX = 2.0" in testo)
    wrapper.write_text(testo.replace("_TEMPO_MAX = 2.0", "_TEMPO_MAX = 1.0"), "utf-8")
    comp = base / "plancia" / "compartimenti.py"
    originale = comp.read_text("utf-8")
    comp.write_text(originale + "\n\ndef valuta(*args, **kw):\n    import time as _t\n"
                    "    _t.sleep(30)\n", "utf-8")
    cfg = _testo(a.dati / "config.json")

    def corri(payload):
        return _corri_copia(a, hook, payload, timeout=30)

    def messaggio(r):
        try:
            return json.loads(r.out).get("systemMessage", "")
        except (ValueError, AttributeError):
            return ""

    for modo in ("bloccante", "solo-registro"):
        a.scrivi_config(dict(json.loads(cfg), guardiano=modo))
        n0 = len(a.registro())
        r = corri(seg_alfa)
        nuove = a.registro()[n0:]
        if modo == "bloccante":
            prova("allarme6: bloccante, un NOMINATO al tempo scaduto: negato, con un motivo chiaro",
                  r is not None and r.negato and "troppo complesso" in r.motivo
                  and "spezzalo" in r.motivo, repr(r))
            prova("allarme6: ...e una riga `negato` nel registro",
                  len(nuove) == 1 and nuove[0]["esito"] == "negato"
                  and nuove[0]["compartimento"] == "alfa", str(nuove))
        else:
            prova("allarme6: solo-registro, un nominato al tempo scaduto: ammesso, con il "
                  "`systemMessage`, e una riga `avrebbe-negato`",
                  r is not None and r.rc == 0 and not r.negato and "troppo complesso" in messaggio(r)
                  and len(nuove) == 1 and nuove[0]["esito"] == "avrebbe-negato", f"{r!r} {nuove}")
        for volta in (1, 2, 3):
            n0 = len(a.registro())
            r = corri(seg_pred)
            nuove = a.registro()[n0:]
            prova(f"allarme6: {modo}, il PREDEFINITO al tempo scaduto (chiamata {volta}): ammesso "
                  "ma con il `systemMessage` ogni volta, e una riga nel registro",
                  r is not None and r.rc == 0 and not r.negato
                  and "troppo complesso" in messaggio(r) and len(nuove) == 1
                  and nuove[0]["esito"] == "tempo-scaduto", f"{r!r} {nuove}")
    # spento: niente
    a.scrivi_config(dict(json.loads(cfg), guardiano="spento"))
    n0 = len(a.registro())
    r = corri(seg_alfa)
    prova("allarme6: spento, al tempo scaduto: niente uscita, niente riga",
          r is not None and r.ammesso and len(a.registro()) == n0, repr(r))
    # settimo giro: l'allarme che scatta mentre il chiamante e' ANCORA DA STABILIRE (non si sa
    # a che compartimento appartiene la sessione) non e' "incerto": non nega nessuno, ammette
    # con il `systemMessage` e la riga `tempo-scaduto`, come per il predefinito. Il diniego
    # "spezzalo" resta per chi e' GIA' stabilito come nominato o incerto (segnali discordanti).
    comp.write_text(originale + "\n\ndef chiamante(*args, **kw):\n    import time as _t\n"
                    "    _t.sleep(30)\n", "utf-8")
    for modo in ("bloccante", "solo-registro"):
        a.scrivi_config(dict(json.loads(cfg), guardiano=modo))
        for chi_, seg_ in (("nominato", seg_alfa), ("predefinito", seg_pred)):
            for volta in (1, 2):
                n0 = len(a.registro())
                r = corri(seg_)
                nuove = a.registro()[n0:]
                prova(f"allarme7: {modo}, allarme con il chiamante ancora da stabilire, sessione "
                      f"{chi_} (chiamata {volta}): ammesso, con il `systemMessage`, senza nessun "
                      "diniego",
                      r is not None and r.rc == 0 and not r.negato and "deny" not in r.out
                      and "spezzalo" in messaggio(r), repr(r))
                prova(f"allarme7: ...e una riga `tempo-scaduto` senza compartimento nel registro "
                      f"({modo}, {chi_}, chiamata {volta})",
                      len(nuove) == 1 and nuove[0]["esito"] == "tempo-scaduto"
                      and nuove[0]["compartimento"] == "" and nuove[0]["modalita"] == modo,
                      str(nuove))
    a.scrivi_config(dict(json.loads(cfg), guardiano="spento"))
    n0 = len(a.registro())
    r = corri(seg_alfa)
    prova("allarme7: spento, allarme con il chiamante da stabilire: niente uscita, niente riga",
          r is not None and r.ammesso and len(a.registro()) == n0, repr(r))
    # ...mentre un chiamante GIA' stabilito come incerto (la stessa cartella data a due
    # nominati) al tempo scaduto in `bloccante` e' ancora negato con "spezzalo"
    comp.write_text(originale + "\n\ndef valuta(*args, **kw):\n    import time as _t\n"
                    "    _t.sleep(30)\n", "utf-8")
    cfg2 = json.loads(cfg)
    cfg2["compartimenti"]["beta"]["cartelle"].append(str(pulita))
    for modo in ("bloccante", "solo-registro"):
        a.scrivi_config(dict(cfg2, guardiano=modo))
        n0 = len(a.registro())
        r = corri(seg_alfa)
        nuove = a.registro()[n0:]
        if modo == "bloccante":
            prova("allarme7: bloccante, un chiamante gia' stabilito come INCERTO (due nominati "
                  "sulla stessa cartella) al tempo scaduto: negato con `spezzalo`",
                  r is not None and r.negato and "spezzalo" in r.motivo
                  and "alfa,beta" in r.motivo, repr(r))
            prova("allarme7: ...e una riga `negato` nel registro",
                  len(nuove) == 1 and nuove[0]["esito"] == "negato", str(nuove))
        else:
            prova("allarme7: solo-registro, l'INCERTO al tempo scaduto: ammesso, con la riga "
                  "`avrebbe-negato`",
                  r is not None and r.rc == 0 and not r.negato and "spezzalo" in messaggio(r)
                  and len(nuove) == 1 and nuove[0]["esito"] == "avrebbe-negato", f"{r!r} {nuove}")
    a.scrivi_config(dict(json.loads(cfg), guardiano="bloccante"))
    comp.write_text(originale + "\n\nimport time as _t2\n_t2.sleep(30)\n", "utf-8")
    # un allarme che scatta mentre il modulo si carica resta il guasto di prima (fail-open)
    a.scrivi_config(dict(json.loads(cfg), guardiano="bloccante"))
    marca = a.dati / "guardiano.non-parte"
    if marca.exists():
        marca.unlink()
    n0 = len(a.registro())
    r = corri(seg_alfa)
    nuove = [x for x in a.registro()[n0:] if x.get("esito") == "guardiano-non-parte"]
    prova("allarme6: un modulo che non si carica in tempo: `guardiano-non-parte`, ammesso, "
          "per tutti (il guasto e' un altro)",
          r is not None and r.rc == 0 and not r.negato and len(nuove) == 1, f"{r!r} {nuove}")
    comp.write_text(originale, "utf-8")
    if marca.exists():
        marca.unlink()
    # il caso vero: 32 `$(` annidati, circa 300 caratteri, fanno superare i due secondi
    a.scrivi_config(dict(json.loads(cfg), guardiano="bloccante"))
    pad = "echo " + "$(echo " * 34 + "x" + ")" * 34
    for chi, kw, ber in (("alfa", dict(sid=S_ALFA_LIBERA, aperta_in=pulita), f"{a.comune}/nota.txt"),
                         ("predefinito", dict(sid=S_COMUNE, aperta_in=a.progetto),
                          f"{a.alfa1}/segreto.txt")):
        pl = a.pl("Bash", {"command": f"cat {ber} ; {pad}"}, **kw)
        r1 = a.chiama(pl)
        r2 = a.chiama(pl)
        if chi == "alfa":
            prova("allarme6: il padding di 34 `$(` da un nominato: negato (prima passava)",
                  r1.negato and r2.negato, f"{r1!r} {r2!r}")
        else:
            prova("allarme6: il padding di 34 `$(` dal predefinito: ammesso con il `systemMessage` "
                  "la prima volta E la seconda",
                  all(x.rc == 0 and not x.negato and "troppo complesso" in messaggio(x)
                      for x in (r1, r2)), f"{r1!r} {r2!r}")
    # il ramo dell'eccezione ordinaria, in-process
    try:
        cm = importlib.import_module("plancia.compartimenti")
    except ImportError as e:
        prova("allarme6: plancia.compartimenti si importa", False, str(e))
        a.togli_config()
        return
    dati = Path(tempfile.mkdtemp(prefix="plancia-prova-guardiano-int6-"))
    orig = cm.valuta
    try:
        def guasta(*args, **kw):
            raise RuntimeError("guasto simulato")
        cm.valuta = guasta
        payload = {"session_id": "s9", "cwd": "/", "hook_event_name": "PreToolUse",
                   "transcript_path": str(dati / "p" / "-altra" / "s9.jsonl"),
                   "tool_name": "Read", "tool_input": {"file_path": "/etc/hosts"}}
        for modo in ("bloccante", "solo-registro"):
            (dati / "config.json").write_text(json.dumps({
                "guardiano": modo, "compartimenti": {"alfa": {"cartelle": [str(pulita)]}}}), "utf-8")
            out = cm.hook(json.dumps(payload), str(dati))
            prova(f"allarme6: errore interno, {modo}, predefinito: ammesso ma con il "
                  "`systemMessage` (non piu' in silenzio)",
                  "systemMessage" in out and "errore interno" in out and "deny" not in out, out[:200])
            righe = [json.loads(x) for x in (dati / "guardiano.log").read_text("utf-8").splitlines()
                     if x.strip()]
            prova(f"allarme6: ...e una riga `errore-interno` nel registro ({modo})",
                  righe and righe[-1].get("esito") == "errore-interno", str(righe[-1:]))
        (dati / "config.json").write_text(json.dumps({"guardiano": "spento"}), "utf-8")
        prova("allarme6: errore interno, spento: nessuna uscita",
              cm.hook(json.dumps(payload), str(dati)) == "")
    finally:
        cm.valuta = orig
        shutil.rmtree(dati, ignore_errors=True)
    a.togli_config()


def _prove_cd_scritture_7(prova, a: Ambiente):
    """Settimo giro, punto 2: dopo un `cd` con una destinazione che non si sa valutare
    (`cd $(mktemp -d)`, `cd -`) una scrittura con un NOME SEMPLICE (senza barra: `git init`,
    `git commit`, `git add .`, `touch f`, `echo x > f`, `mkdir x`, `tar xzf a.tgz`) e' ammessa
    per il PREDEFINITO, come dice il docstring (non si puo' dire dove porta, e negarla sarebbe
    il falso positivo di ogni script); una con una barra (`touch sub/f`) o il nome di un file
    del guardiano (`rm config.json`) resta negata. Il NOMINATO resta com'e': negato."""
    a.togli_config()
    pulita = _alfa_pulita(a)

    def pred(cmd):
        return a.chiama(a.pl("Bash", {"command": cmd}, sid=S_COMUNE, aperta_in=a.progetto))

    def alfa(cmd):
        return a.chiama(a.pl("Bash", {"command": cmd}, sid=S_ALFA_LIBERA, aperta_in=pulita))

    semplici = [
        "cd $(mktemp -d) && git init", "cd $(mktemp -d) && git commit -m x",
        "cd $(mktemp -d) && git clone https://example.org/x/y",
        "d=$(mktemp -d); cd $d && git init", "cd - && git add .",
        "cd $(mktemp -d) && touch f", "cd $(mktemp -d) && echo x > f",
        "cd $(mktemp -d) && mkdir x", "cd - && cp a b", "cd - && mv a b",
        "cd - && tee out.txt < in.txt", "cd $(cat lista) && rm nota.txt",
        "cd \"$X\" && git commit -am x", "cd - && touch *.txt", "cd - && git add . && git commit -m x",
    ]
    for c in semplici:
        r = pred(c)
        prova(f"cd7: predefinito, `{c}`: ammesso (un nome semplice dopo una cartella "
              "sconosciuta, come dice il docstring)", r.ammesso, repr(r))
        r = alfa(c)
        prova(f"cd7: alfa, `{c}`: negato (per il nominato non cambia)", r.negato, repr(r))
    con_barra = [
        "cd $(mktemp -d) && touch sub/f", "cd - && cp x sub/y", "cd - && echo x > sub/f",
        "cd $(mktemp -d) && mkdir ../x", "cd - && git clone https://example.org/x/y sub/y",
        "cd $(mktemp -d) && touch ..", "cd - && cp -r . ../x",
    ]
    for c in con_barra:
        r = pred(c)
        prova(f"cd7: predefinito, `{c}`: negato (un percorso relativo con una barra, o `..`, "
              "dopo una cartella sconosciuta)", r.negato and "non si sa dove porta" in r.motivo,
              repr(r))
    # una ricerca o una copia RICORSIVA da una cartella che non si sa resta negata (legge
    # tutto l'albero, che potrebbe essere di un nominato)
    for c in ("cd - && grep -r x .", "cd $(mktemp -d) && cp -r . x", "cd - && find . -name x",
              "cd - && rg x"):
        r = pred(c)
        prova(f"cd7: predefinito, `{c}`: negato (ricorsivo da una cartella sconosciuta)",
              r.negato, repr(r))
    # il nome di un file del guardiano resta negato anche senza barra
    for c in ("cd $(mktemp -d) && rm config.json", "cd - && tee guardiano.log < x",
              "cd $(cat lista) && truncate -s0 compartimenti.ultima-valida.json",
              "cd - && sed -i s/x/y/ config.json", "cd - && echo x > settings.json"):
        r = pred(c)
        prova(f"cd7: predefinito, `{c}`: negato (e' il nome di un file del guardiano)",
              r.negato and "non si sa dove porta" in r.motivo, repr(r))
    # le letture non cambiano, e una scrittura con un percorso assoluto si valuta per quello
    for c in ("cd $(mktemp -d) && ls", "cd - && cat nota.txt", "cd - && git status"):
        r = pred(c)
        prova(f"cd7: predefinito, `{c}`: ammesso", r.ammesso, repr(r))
    r = pred(f"cd - && touch {a.alfa1}/x")
    prova("cd7: predefinito, `cd - && touch <cartella di alfa>/x`: negato (il percorso assoluto "
          "vale)", r.negato, repr(r))
    a.togli_config()


def _prove_git_letture_7(prova, a: Ambiente):
    """Settimo giro, punto 3: in una cartella di codice CONDIVISA un nominato puo' LEGGERE
    con git (`log`, `show`, `diff`, `status`, `blame`, `rev-parse`, `branch` senza operandi o
    con `--contains`, `tag -l MODELLO`, `config --get`, `reflog`, `notes list`, `notes show`,
    `fetch --dry-run`, `stash list`, `worktree list`, `submodule status`): non sono scritture.
    Le scritture di git restano negate."""
    cod = a.radice / "codice-condiviso-7"
    cod.mkdir(parents=True, exist_ok=True)
    (cod / "README").write_text("x\n", "utf-8")
    X = str(cod)
    a.togli_config()
    pulita = _alfa_pulita(a)
    base = json.loads(_testo(a.dati / "config.json"))
    a.scrivi_config(dict(base, condivise=[X]))

    def alfa(cmd):
        return a.chiama(a.pl("Bash", {"command": cmd}, sid=S_ALFA_LIBERA, aperta_in=pulita))

    letture = [
        "log", "log --oneline -5", "show HEAD", "diff", "diff HEAD~1", "status", "blame README",
        "rev-parse HEAD", "branch", "branch -a", "branch -vv", "branch --list", "branch --list 'x*'",
        "branch --show-current", "branch --contains abc", "branch --no-contains abc",
        "branch --merged main", "branch --no-merged main", "branch --points-at HEAD",
        "branch -r --contains abc", "tag", "tag -l", "tag -l \"v*\"", "tag --list 'v*'", "tag -n",
        "tag -n5 -l 'v*'", "tag --contains abc", "tag --points-at HEAD", "tag --merged main",
        "tag -v v1", "config --get user.name", "config --list", "reflog", "reflog show",
        "reflog HEAD", "reflog -n 5", "reflog exists refs/heads/x", "notes", "notes list",
        "notes show HEAD", "notes --ref x list", "notes get-ref", "fetch --dry-run",
        "fetch --dry-run origin", "stash list", "stash show", "stash show -p",
        "worktree list", "submodule", "submodule status", "submodule summary", "remote -v",
        "ls-files", "ls-remote origin",
    ]
    for g in letture:
        for cmd in (f"git -C {X} {g}", f"cd {X} && git {g}"):
            r = alfa(cmd)
            prova(f"git7: alfa, `{cmd.replace(X, '<X>')}`: ammesso (una lettura in una cartella "
                  "condivisa)", r.ammesso, repr(r))
    scritture = [
        "commit -m x", "add .", "fetch", "fetch origin", "push", "branch nuovo", "branch -d x",
        "branch -D x", "branch -m a b", "branch nuovo abc", "tag v1", "tag -a v1 -m m",
        "tag -d v1", "tag -f v1", "tag -s v1", "notes add -m x", "notes append -m x",
        "notes remove", "notes edit", "notes merge x", "notes prune", "reflog expire --all",
        "reflog delete HEAD@{1}", "stash", "stash push", "stash pop", "stash drop", "stash apply",
        "worktree add ../x", "worktree remove x", "submodule update", "submodule add u p",
        "remote add o u", "config a b", "gc", "init", "checkout x", "reset --hard",
    ]
    for g in scritture:
        for cmd in (f"git -C {X} {g}", f"cd {X} && git {g}"):
            r = alfa(cmd)
            prova(f"git7: alfa, `{cmd.replace(X, '<X>')}`: negato (una scrittura in una cartella "
                  "condivisa)", r.negato, repr(r))
    a.togli_config()


def _prove_limiti_6(prova):
    """Sesto giro, punto 7: i limiti dichiarati, nel docstring del modulo e nel README
    (inglese e italiano): l'elenco onesto di cio' che il guardiano non vede e la frase
    che e' un guardiano di incidenti, non un confine di sicurezza."""
    C = _importa_compartimenti()
    doc = (C.__doc__ or "") if C is not None else ""
    prova("limiti6: il docstring di compartimenti.py ha la sezione LIMITI DICHIARATI",
          "LIMITI DICHIARATI" in doc, "manca la sezione")
    for voce in ("costruiti a runtime", "scaricato", "figli che si lanciano da soli", "MCP di terzi",
                 "non un confine di sicurezza"):
        prova(f"limiti6: il docstring elenca `{voce}`", voce in doc, "manca")
    for nome, frase in (("README.md", "not a security boundary"),
                        ("README.it.md", "non un confine di sicurezza")):
        testo = (RADICE / nome).read_text("utf-8")
        prova(f"limiti6: {nome} dice che e' un guardiano di incidenti e `{frase}`",
              frase in testo and ("incident" in testo.lower()), "manca")
        for voce in (("built at run time", "downloaded", "MCP") if nome == "README.md"
                     else ("costruiti a runtime", "scaricato", "MCP")):
            prova(f"limiti6: {nome} elenca `{voce}`", voce in testo, "manca")


def _prove_forma(prova):
    """Il file, la versione di Python, la privacy del repo pubblico."""
    attesi = [GUARDIANO, RADICE / "plancia" / "compartimenti.py", Path(__file__)]
    file_del_lotto = [f for f in attesi if f.exists()]
    prova("forma: bin/plancia-guardiano e plancia/compartimenti.py esistono",
          len(file_del_lotto) == 3, str(file_del_lotto))
    prova("forma: bin/plancia-guardiano e' eseguibile e ha lo shebang `env python3`",
          GUARDIANO.exists() and os.access(GUARDIANO, os.X_OK)
          and GUARDIANO.read_text("utf-8").splitlines()[0] == "#!/usr/bin/env python3")
    for f in attesi:
        try:
            ast.parse(f.read_text("utf-8"), filename=str(f), feature_version=(3, 9))
            ok = True
        except (SyntaxError, OSError) as e:
            ok = False
            print("   ", f, e)
        prova(f"forma: {f.name} esiste ed e' Python 3.9 valido (niente match, niente X | Y)", ok)
    # Il Python di sistema e' 3.9 sul Mac di sviluppo (Xcode), ma su un Linux
    # (ubuntu-latest) /usr/bin/python3 e' una versione piu' nuova: li' la 3.9 non
    # c'e' come Python di sistema e il controllo non si puo' fare. Il controllo
    # c'e' lo stesso e conta uno: se il Python di sistema e' > 3.9 passa con la
    # nota "saltato" (la sintassi 3.9 resta provata da `ast.parse(...,
    # feature_version=(3, 9))` qui sopra e dal job Python 3.9 della CI); se e' <= 3.9
    # o non si riesce a leggere la versione, si guarda davvero.
    v, nota = "True", ""
    if PYTHON == "/usr/bin/python3":
        try:
            lette = subprocess.run(
                [PYTHON, "-c", "import sys; print('%d.%d' % sys.version_info[:2])"],
                capture_output=True, timeout=60).stdout.decode().strip()
            maggiore, minore = (int(x) for x in lette.split("."))
            if (maggiore, minore) > (3, 9):
                nota = "saltato: il Python di sistema qui e' %s, non 3.9" % lette
            else:
                v = "True"
        except (OSError, ValueError, subprocess.SubprocessError):
            v = "illeggibile"
    prova("forma: le prove girano sul Python di sistema, che qui e' 3.9 "
          "(la versione minima da reggere; altrove passa e basta)", v == "True",
          nota or f"versione {v}")
    # config.py: le chiavi con i default giusti
    from plancia import config
    prova("config: DEFAULTS ha `guardiano` = spento e `compartimenti` = {}",
          config.DEFAULTS.get("guardiano") == "spento" and config.DEFAULTS.get("compartimenti") == {})
    # la posizione dei dati e' la stessa in config e nel guardiano
    codice = ("import os; from plancia import config, compartimenti as c;"
              "print(int(str(config.DATA_DIR) == c.percorso_dati()))")
    for env_extra in ({"PLANCIA_HOME": "/tmp/xx-plancia-prova"}, {}):
        e = dict(os.environ)
        e.pop("PLANCIA_HOME", None)
        e.update(env_extra)
        e["PYTHONPATH"] = str(RADICE)
        e["HOME"] = tempfile.gettempdir()
        p = subprocess.run([sys.executable, "-c", codice], env=e, cwd=str(RADICE),
                           capture_output=True)
        prova("config: la cartella dati del guardiano e' quella di plancia.config "
              + ("(PLANCIA_HOME)" if env_extra else "(~/.plancia)"),
              p.stdout.decode().strip() == "1", p.stderr.decode()[-200:])
    # privacy: il repo e' pubblico. I nomi sono spezzati apposta, cosi' questo
    # file non li contiene per intero.
    vietati = ["ant" + "onio", "rot" + "elli", "vesu" + "vius", "grow" + "patch",
               "g" + "p1", "g" + "p2", "1R6" + "Iog", "eug" + "enio", "ner" + "elli",
               "/Us" + "ers/", "Google" + "Drive"]
    rx = re.compile("|".join(re.escape(x) for x in vietati), re.I)
    trovati = []
    for f in file_del_lotto:
        for n, riga in enumerate(f.read_text("utf-8").splitlines(), 1):
            if rx.search(riga):
                trovati.append(f"{f.name}:{n}")
    prova("privacy: nessun nome vero ne' percorso reale nei file del guardiano (tutti e tre presenti)",
          len(file_del_lotto) == 3 and not trovati, str(trovati))
    for f in attesi:
        prova(f"forma: {f.name} esiste e non ha em dash",
              f.exists() and "\u2014" not in f.read_text("utf-8"))


def esegui(prova):
    _prove_forma(prova)
    _prove_errore_interno(prova)
    a = Ambiente()
    try:
        _prove_nominato(prova, a)
        _prove_predefinito(prova, a)
        _prove_subagenti(prova, a)
        _prove_sessioni_e_drive(prova, a)
        _prove_sessioni_app(prova, a)
        _prove_change_directory(prova, a)
        _prove_manifesto(prova, a)
        _prove_symlink(prova, a)
        _prove_modi(prova, a)
        _prove_config_malformata(prova, a)
        _prove_misura(prova, a)
        _prove_protezione(prova, a)
        _prove_relativi(prova, a)
        _prove_specchio(prova, a)
        _prove_autoprotezione_cli(prova, a)
        _prove_falsi_positivi_bash(prova, a)
        _prove_ricerca_trascrizioni(prova, a)
        _prove_tempo(prova, a)
        _prove_cli(prova, a)
        _prove_cli_config(prova, a)
        _prove_flusso_testo(prova, a)
        _prove_cd_variabili(prova, a)
        _prove_non_parte(prova, a)
        _prove_config_illeggibile(prova, a)
        _prove_settings(prova, a)
        _prove_interpreti_e_scritture(prova, a)
        _prove_annidati(prova, a)
        _prove_minori(prova, a)
        _prove_falsi_positivi_regex(prova, a)
        _prove_condivise(prova, a)
        _prove_gravi_5(prova, a)
        _prove_settings_5(prova, a)
        _prove_minori_5(prova, a)
        _prove_regressioni_6(prova, a)
        _prove_commenti_6(prova, a)
        _prove_prefissi_6(prova, a)
        _prove_sed_awk_6(prova, a)
        _prove_condivise_6(prova, a)
        _prove_allarme_6(prova, a)
        _prove_cd_scritture_7(prova, a)
        _prove_git_letture_7(prova, a)
        _prove_limiti_6(prova)
    finally:
        a.chiudi()
