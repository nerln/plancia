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
        for d in (self.home, self.dati, self.claude / "projects", self.alfa1,
                  self.alfa2, self.alfa3, self.beta1, self.condiviso):
            d.mkdir(parents=True, exist_ok=True)
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
                            "divieti": [str(self.comune / "riservato")],
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
        e = {"HOME": str(self.home), "PLANCIA_HOME": str(self.dati),
             "CLAUDE_CONFIG_DIR": str(self.claude),
             "PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "C.UTF-8"}
        return e

    def esegui_testo(self, testo, interprete=None):
        t0 = time.time()
        p = subprocess.run([interprete or PYTHON, str(GUARDIANO)],
                           input=testo, capture_output=True, env=self.env(),
                           timeout=60)
        return Esito(p.returncode, p.stdout.decode("utf-8", "replace"),
                     p.stderr.decode("utf-8", "replace"), time.time() - t0)

    def chiama(self, payload):
        return self.esegui_testo(json.dumps(payload).encode("utf-8"))

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
        return {"session_id": sid, "cwd": str(cwd or aperta),
                "transcript_path": self.trascrizione(aperta, sid, madre,
                                                     workflows=workflows),
                "hook_event_name": "PreToolUse", "tool_name": tool,
                "tool_input": ti}

    def registro(self):
        p = self.dati / "guardiano.log"
        if not p.exists():
            return []
        return [json.loads(x) for x in p.read_text("utf-8").splitlines() if x.strip()]

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
    prova("1: il motivo dice il compartimento e a chi appartiene il percorso",
          "alfa" in r.motivo and fuori in r.motivo and "predefinito" in r.motivo, r.motivo)
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
    uid = os.getuid()
    scratch = f"/private/tmp/claude-{uid}/{_codifica(a.alfa1)}/{S_ALFA_LIBERA}/scratchpad/x.txt"
    altro_scratch = f"/private/tmp/claude-{uid}/{_codifica(a.alfa1)}/{S_COMUNE}/scratchpad/x.txt"
    prova("1: alfa, la propria cartella di sessione in /private/tmp/claude-<uid>: ammessa",
          alfa("Write", {"file_path": scratch, "content": "x"}).ammesso)
    prova("1: alfa, la cartella di sessione di un'ALTRA sessione: negata",
          alfa("Write", {"file_path": altro_scratch, "content": "x"}).negato)
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
    prova("1: alfa con la cwd fuori dai permessi: le parole senza barre (echo, ls) non sono percorsi",
          a.chiama(a.pl("Bash", {"command": "echo ciao && ls"}, sid=S_ALFA, aperta_in=a.comune)).ammesso)
    prova("1: alfa, Bash senza percorsi: ammesso",
          alfa("Bash", {"command": "echo ciao && python3 --version"}).ammesso)
    # id di sessione dichiarato: alfa anche se aperta altrove
    r = a.chiama(a.pl("Read", {"file_path": fuori}, sid=S_ALFA, aperta_in=a.comune))
    prova("1: una sessione in alfa.sessioni aperta nella cartella del predefinito e' "
          "comunque alfa: Read del file comune negato", r.negato, repr(r))
    prova("1: ...e la sua memoria (memory) resta ammessa",
          a.chiama(a.pl("Read", {"file_path": str(a.claude / "projects" / _codifica(a.comune) / "memory" / "M.md")},
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
    prova("modi: `spento` non scrive nemmeno la copia dell'ultima config valida",
          not (a.dati / "compartimenti.ultima-valida.json").exists())
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
    a.chiama(ammessa)
    prova("modi: una chiamata ammessa non scrive niente nel registro",
          len(a.registro()) == n)
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
    for modo in ("spento", "solo-registro", "bloccante"):
        a.scrivi_config(a.config(modo))
        for nome, dati in (("vuoto", b""), ("non JSON", b"non e' json {"),
                           ("JSON che non e' un oggetto", b"[1, 2]"),
                           ("byte non UTF-8", b"\xff\xfe\x00\xff"),
                           ("oggetto senza tool_name", b"{}"),
                           ("tool_input di tipo sbagliato",
                            b'{"tool_name":"Read","tool_input":["x"],"session_id":5}')):
            r = a.esegui_testo(dati)
            prova(f"modi: {modo}, stdin {nome}: exit 0 e nessuna uscita", r.ammesso, repr(r))
    prova("modi: gli stdin rotti non hanno scritto niente nel registro",
          len(a.registro()) == righe_prima)

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
            prova(f"errore interno: {modo}, nominato: "
                  + ("negato per prudenza" if atteso_nominato else "ammesso, nessuna uscita"),
                  ("errore interno" in nom) if atteso_nominato else nom == "", nom[:150])
            pre = cm.hook(json.dumps(altro), str(dati))
            prova(f"errore interno: {modo}, predefinito: ammesso, nessuna uscita", pre == "", pre[:150])
    finally:
        cm.valuta = originale
        shutil.rmtree(dati, ignore_errors=True)
        shutil.rmtree(cartella, ignore_errors=True)


def _prove_tempo(prova, a: Ambiente):
    a.scrivi_config(a.config("bloccante"))
    bash = a.pl("Bash", {"command": f"cat {a.alfa1}/segreto.txt | head; ls {a.alfa2} 2>/dev/null"},
                sid=S_ALFA_LIBERA, aperta_in=a.alfa1)
    leggi = a.pl("Read", {"file_path": str(a.comune / "nota.txt")}, sid=S_COMUNE)
    for _ in range(3):  # riscalda i .pyc e la cache del disco
        a.chiama(bash)
    tempi = []
    for i in range(20):
        tempi.append(a.chiama(bash if i % 2 else leggi).secondi * 1000)
    tempi.sort()
    med, mx = tempi[len(tempi) // 2], tempi[-1]
    t0 = time.time()
    subprocess.run([PYTHON, "-c", "pass"], env=a.env(), capture_output=True)
    base = (time.time() - t0) * 1000
    prova(f"tempo: per chiamata mediana {med:.0f} ms, massimo {mx:.0f} ms "
          f"(avvio di Python a vuoto {base:.0f} ms); soglia 150 ms",
          med < 150, f"mediana {med:.0f} ms")
    a.scrivi_config(a.config("spento"))
    for _ in range(3):
        a.chiama(bash)
    tempi = sorted(a.chiama(bash).secondi * 1000 for _ in range(10))
    prova(f"tempo: `spento` mediana {tempi[5]:.0f} ms", tempi[5] < 150, f"{tempi[5]:.0f} ms")


def _prove_cli(prova, a: Ambiente):
    a.togli_config()
    a.scrivi_config(a.config("solo-registro"))
    a.chiama(a.pl("Read", {"file_path": str(a.comune / "nota.txt")}, sid=S_ALFA_LIBERA,
                  aperta_in=a.alfa1))
    a.chiama(a.pl("Read", {"file_path": str(a.alfa1 / "segreto.txt")}, sid=S_COMUNE))
    env = dict(a.env())
    env["PYTHONPATH"] = str(RADICE)

    def plancia(*args):
        p = subprocess.run([sys.executable, str(RADICE / "bin" / "plancia"), "guardiano", *args],
                           env=env, cwd=str(RADICE), capture_output=True, timeout=60)
        return p.returncode, p.stdout.decode("utf-8", "replace") + p.stderr.decode("utf-8", "replace")

    rc, out = plancia("--stato")
    prova("cli: `plancia guardiano --stato` dice modalita', compartimenti e righe recenti",
          rc == 0 and "solo-registro" in out and "alfa: 3 cartelle" in out
          and "beta: 1 cartelle" in out and "predefinito:" in out
          and "2 righe" in out and "2 avrebbe-negato" in out, out)
    prova("cli: --stato NON stampa i percorsi delle cartelle",
          str(a.radice) not in out and "alfa-uno" not in out, out)
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
    # e non scrive niente
    prova("cli: il sottocomando non crea ne' scrive config.json, copia o registro",
          not any((a.dati / f).exists() for f in
                  ("config.json", "compartimenti.ultima-valida.json", "guardiano.log")))


def _prove_forma(prova):
    """Il file, la versione di Python, la privacy del repo pubblico."""
    file_del_lotto = [f for f in (GUARDIANO, RADICE / "plancia" / "compartimenti.py",
                                  Path(__file__)) if f.exists()]
    prova("forma: bin/plancia-guardiano e plancia/compartimenti.py esistono",
          len(file_del_lotto) == 3, str(file_del_lotto))
    prova("forma: bin/plancia-guardiano e' eseguibile e ha lo shebang `env python3`",
          GUARDIANO.exists() and os.access(GUARDIANO, os.X_OK)
          and GUARDIANO.read_text("utf-8").splitlines()[0] == "#!/usr/bin/env python3")
    for f in file_del_lotto:
        try:
            ast.parse(f.read_text("utf-8"), filename=str(f), feature_version=(3, 9))
            ok = True
        except SyntaxError as e:
            ok = False
            print("   ", f, e)
        prova(f"forma: {f.name} e' Python 3.9 valido (niente match, niente X | Y)", ok)
    v = "True"
    if PYTHON == "/usr/bin/python3":
        v = subprocess.run([PYTHON, "-c", "import sys; print(sys.version_info[:2] <= (3, 9))"],
                           capture_output=True).stdout.decode().strip()
    prova("forma: le prove girano sul Python di sistema, che qui e' 3.9 "
          "(la versione minima da reggere; altrove passa e basta)", v == "True",
          f"versione {v}")
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
    prova("privacy: nessun nome vero ne' percorso reale nei file del guardiano", not trovati,
          str(trovati))
    for f in file_del_lotto:
        prova(f"forma: niente em dash in {f.name}", "\u2014" not in f.read_text("utf-8"))


def esegui(prova):
    _prove_forma(prova)
    _prove_errore_interno(prova)
    a = Ambiente()
    try:
        _prove_nominato(prova, a)
        _prove_predefinito(prova, a)
        _prove_subagenti(prova, a)
        _prove_sessioni_e_drive(prova, a)
        _prove_change_directory(prova, a)
        _prove_manifesto(prova, a)
        _prove_symlink(prova, a)
        _prove_modi(prova, a)
        _prove_config_malformata(prova, a)
        _prove_tempo(prova, a)
        _prove_cli(prova, a)
    finally:
        a.chiudi()
