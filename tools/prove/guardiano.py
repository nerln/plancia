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
        e = {"HOME": str(self.home), "PLANCIA_HOME": str(self.dati),
             "CLAUDE_CONFIG_DIR": str(self.claude),
             "PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "C.UTF-8"}
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
    finally:
        a.chiudi()
