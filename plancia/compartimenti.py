"""Compartimenti: due (o piu') gruppi di lavoro sulla stessa macchina che non
si vedono. Qui sta la logica pura, senza effetti collaterali oltre al registro
e alla copia dell'ultima config valida; la usa `bin/plancia-guardiano` (l'hook
PreToolUse) e la userà il resto di Plancia quando filtrerà per compartimento.

Il modello, in breve:

- Un compartimento NOMINATO e' un elenco di PERMESSI: la sessione che gli
  appartiene vede solo le sue `cartelle` piu' un elenco neutro di binari e
  ambienti (`NEUTRI_FISSI`, `NEUTRI_HOME`), la propria cartella di lavoro
  temporaneo e la propria cartella in `~/.claude/projects`. Tutto il resto e'
  vietato.
- Il `predefinito` e' un elenco di DIVIETI: le cartelle di tutti i
  compartimenti nominati, piu' `divieti`, piu' ogni riga del file
  `manifesto_divieti` (uno per riga, `#` commenti, glob ammessi). Il manifesto
  e' la fonte unica dei percorsi del lavoro comune che sta ancora nell'albero
  del predefinito: non si riscrive a mano due volte.

Limiti da dire chiari (non sono difetti da correggere qui):

- E' un guardiano di INCIDENTI, non un confine di sicurezza. Ferma il
  comportamento ordinario di un agente, non uno che vuole aggirarlo: un
  percorso costruito a pezzi dentro uno script, un symlink creato apposta e poi
  letto da dentro un programma, un percorso scritto in un file e letto da un
  altro comando. Dentro lo stesso utente del sistema operativo non c'e' modo di
  farlo diventare un confine vero: quello serve un utente separato.
- L'estrazione dei percorsi da un comando Bash e' euristica (vedi
  `_candidati_comando`): token e sottostringhe che sembrano percorsi.
- Una ricerca RICORSIVA lanciata da Bash (`grep -r`, `rg`, `find`, `ls -R`,
  `tree`, `tar`, `zip`, `cp -r`, `rsync`, `git grep`) si riconosce dal nome del
  comando e vale come Grep: le cartelle nominate nel comando e la cwd sono
  trattate come radici di una ricerca, e una ricerca che include un percorso
  vietato e' negata. Il riconoscimento e' sul testo del comando: un programma
  che cammina l'albero per conto suo (uno script, `make`) non si vede. Grep e
  Glob si vedono sempre (partono da un `path` esplicito o dalla cwd).
- Un divieto scritto come modello di nome senza barre (`*.segreto`,
  `NOTA-X.md`) vale per un percorso solo quando il nome compare in quel
  percorso: la regola "la ricerca include un percorso vietato" non scatta mai
  per lui, perche' non ha una cartella da cui una ricerca possa partire.
- I token di shell con un glob (`cat cartella/*`) si espandono sul disco
  (fino a 200 voci per token) prima del confronto.
- Il confronto dei percorsi e' senza distinzione di maiuscole (APFS non le
  distingue): su un volume che le distingue puo' negare di piu', mai di meno.
- Gli strumenti che elencano o cercano senza un bersaglio esplicito
  (`search_files`, `list_sessions`, `ListAgents`, ...) non si possono valutare
  per il predefinito: passano, anche in `bloccante`. Per un nominato sono
  negati. Per `list_sessions` e `ListAgents`, quando esistono nominati, in
  `solo-registro` resta una riga `avrebbe-negato` (vedi `_misura`), per sapere
  quanto si usano: sono elenchi (titoli, cartelle di lavoro), non contenuti, ma
  chi accende E1 deve saperlo, perche' e' un canale aperto. Fa eccezione
  `search_session_transcripts`, che cerca nel CONTENUTO delle trascrizioni di
  tutte le sessioni: negato ai nominati sempre e al predefinito quando esistono
  nominati (`SESSIONI_RICERCA`).
- Gli strumenti di sessione ricevono l'id dell'app (`local_<uuid>`) o un nome
  (il titolo), non il `session_id` dell'hook: si risolvono leggendo il registro
  dell'app (`_voci_app`). Un id o un titolo che il registro e la tabella di
  Plancia non conoscono e' "sconosciuto" (negato a un nominato).
- Un `Artifact` con `files` come mappa e `root` si controlla sui valori
  (i sorgenti locali) e su `root`; un altro strumento MCP che legge un file
  con un nome di parametro nuovo no, finche' il nome non e' in `CHIAVI_PERCORSO`.
- I file del guardiano (config, copia, registro, manifesto, hook, questo
  modulo) non si modificano da nessuna sessione, e nemmeno le sue chiavi di
  config (`guardiano`, `compartimenti`, `strumenti_drive`) con la CLI di
  Plancia (`plancia config guardiano ...`, `python3 -m plancia.cli config ...`,
  `config.save_config` da un interprete): `_valuta_protetti`. Da Bash e'
  euristico (redirezioni, `tee`, `sed -i`, `cp`/`mv`/`install`/`rsync` verso il
  file, `rm`/`mv` del file o della cartella che lo contiene, codice di un
  interprete che nomina il file e scrive): un percorso costruito a pezzi dentro
  uno script non si vede. Vale solo in `bloccante`, come ogni diniego: chi vuole
  cambiare la config con l'aiuto di una sessione deve prima passare a
  `solo-registro`. NON protegge il `settings.json` che installa l'hook: togliere
  l'hook da li' spegne il guardiano (fuori dallo scopo di questo lotto).
- Trascrizioni e memoria di un compartimento nominato stanno sotto
  `<CLAUDE_CONFIG_DIR o ~/.claude>/projects/<cartella codificata>`: sono suo
  lavoro come le sue cartelle (`Ambito.proprietario_specchio`; E1 usa la stessa
  regola). Il predefinito non le legge, ne' cerca da `projects` o da un antenato
  (Grep, Glob, Bash ricorsivo). Il confine e' il trattino della codifica
  (`<enc>` e `<enc>-...`, non `<enc>altro`), ma la codifica perde la differenza
  fra `/` e `-`: una cartella sorella `alfa-2` di `alfa` risulta di alfa, e si
  nega per prudenza. Un `ls ~/.claude/projects` (non ricorsivo) mostra i nomi
  codificati delle cartelle, e un `ls` della cartella padre di un percorso
  vietato mostra i nomi dei suoi file: i contenuti no.
- Un percorso in `/tmp`, `/private/tmp`, `/var/folders` e simili non e' di
  nessun compartimento, ma un nominato non lo usa (e' un posto dove passarsi
  file: vedi il commento di `NEUTRI_FISSI`), e il motivo del diniego lo dice.
  `mktemp -d` da solo passa (nessun percorso nel testo) e cio' che si scrive
  li' non si vede: la separazione di `/tmp` e' di facciata contro un agente che
  la cerca. Un comando come `tar czf /tmp/x.tgz src` da un nominato e' negato per
  scelta: se si vuole ammettere `/tmp`, e' una riga in `NEUTRI_FISSI`.
- Le variabili di un comando (`cat $DIR/x`) si espandono con l'ambiente del
  payload, se ce n'e' uno (nessun hook di Claude Code lo manda, per quanto si e'
  visto), e poi con quello dell'hook; una variabile non definita si ignora (un
  percorso che non si sa ricostruire non si risolve sulla cwd). `echo` e `printf`
  stampano i loro argomenti e non toccano percorsi; il corpo di un heredoc e'
  testo, non un argomento (salvo che lo riceva una shell o un interprete, o
  contenga `$(...)` senza virgolette). Una `/` da sola non e' un percorso.
- La cwd di un nominato aperto fuori dalle sue cartelle (per id) vale per ogni
  comando Bash (vedi `valuta`); al contrario una sessione del predefinito che
  entra per errore in una cartella di un nominato (`cd` persistente) diventa
  quel nominato e perde il proprio lavoro: e' la scelta dichiarata in
  `chiamante` (la cwd puo' solo aggiungere un'appartenenza).
- Un here-string dato a `xargs` (`xargs cat <<< percorso`) non si vede.
- L'appartenenza dell'id Drive e' per id esatto, senza risalire agli antenati
  (la verifica degli antenati non e' affidabile da qui).

Leggero apposta: gira su OGNI strumento di OGNI sessione. Solo `json`, `os`,
`re` e `time` all'avvio; `shlex`, `fnmatch`, `sqlite3` solo quando servono.
Non importa `plancia.config`: quel modulo, all'import, costruisce decine di
oggetti `pathlib` e importa `secrets` (che tira dentro `hmac` e `hashlib`), un
costo che un hook globale non deve pagare a ogni strumento. La posizione della
cartella dati e' la stessa regola, ripetuta in `percorso_dati()`, e una prova
le confronta.
"""

import json
import os
import re
import time

PREDEFINITO = "predefinito"
MODI = ("spento", "solo-registro", "bloccante")
MODO_DEFAULT = "spento"

REGISTRO_MAX_BYTE = 5 * 1024 * 1024
# Una riga "config illeggibile" al massimo ogni tanto: senza questo limite
# ogni strumento di ogni sessione ne scriverebbe una, e il registro (che deve
# restare leggibile) sarebbe tutto li'.
NOTA_CONFIG_OGNI_SECONDI = 600

# --------------------------------------------------------------------------
# l'elenco neutro di un compartimento nominato
# --------------------------------------------------------------------------

# Binari e ambienti che ogni sessione deve poter leggere per lavorare, e che
# non portano lavoro di nessuno. Costante e commentata apposta: e' il punto in
# cui si decide cosa e' "di tutti".
#
# /tmp NON c'e' per i nominati: una cartella temporanea condivisa e' un posto
# dove un compartimento lascia un file e l'altro lo trova. Ogni nominato ha
# solo la propria cartella di sessione sotto `/private/tmp/claude-<uid>/`
# (vedi `_scratch_ok`). Anche `/var/folders` (la TMPDIR per utente di macOS)
# resta fuori, per lo stesso motivo.
NEUTRI_FISSI = (
    "/usr",                       # binari e librerie di sistema
    "/bin", "/sbin",
    "/etc",                       # configurazione di sistema, in sola lettura
    "/System",
    "/opt/homebrew",              # Homebrew su Apple Silicon
    "/Library/Developer",         # Command Line Tools
    "/Library/Frameworks",        # Python.framework e simili
    "/Applications/Xcode.app",
    # Dispositivi che i comandi nominano di continuo ("2>/dev/null"): non
    # portano contenuto di nessuno.
    "/dev/null", "/dev/zero", "/dev/random", "/dev/urandom",
    "/dev/stdin", "/dev/stdout", "/dev/stderr", "/dev/tty", "/dev/fd",
)
# Sotto la home di chi lancia l'hook.
NEUTRI_HOME = (
    ".local/bin",                 # comandi installati per l'utente
    ".pyenv",                     # ambienti Python
    "Library/Python",             # site-packages e binari utente di Python
)

# Strumenti MCP del Drive che un nominato puo' usare solo su id ammessi. Un
# altro nome si aggiunge con la chiave di config `strumenti_drive`.
STRUMENTI_DRIVE = (
    "read_file_content", "download_file_content", "search_files",
    "list_recent_files", "get_file_metadata", "get_file_permissions",
    "copy_file", "create_file", "update_file", "share_file", "trash_file",
)
# Quelli che elencano tutto il Drive: per un nominato non c'e' id che tenga.
STRUMENTI_DRIVE_ELENCO = ("search_files", "list_recent_files")
CHIAVI_ID_DRIVE = ("fileId", "file_id", "id", "parentId", "parent_id",
                   "folderId", "folder_id")

PREFISSO_SESSIONI = "mcp__ccd_session_mgmt__"
CHIAVI_ID_SESSIONE = ("session_id", "sessionId", "id", "target_session_id")
CHIAVI_LISTA_SESSIONI = ("session_ids", "sessionIds")
# Strumenti di sessione senza bersaglio che non guardano altre sessioni.
SESSIONI_SENZA_BERSAGLIO_OK = ("get_usage",)

# Chiavi di tool_input che portano un percorso (o una lista di percorsi).
CHIAVI_PERCORSO = ("file_path", "path", "notebook_path", "directory", "cwd",
                   "dir", "root")
CHIAVI_LISTA_PERCORSI = ("files", "paths", "file_paths")

MAX_PERCORSI_COMANDO = 300
MAX_ESPANSIONE_GLOB = 200

# Le sessioni "misurate": strumenti dell'app che cercano o elencano fra TUTTE
# le sessioni, senza un bersaglio. Per il predefinito non si possono negare
# (limite dichiarato), ma in `solo-registro` se ne scrive una riga, per sapere
# quanto si usano prima di decidere cosa farne.
SESSIONI_DA_MISURARE = ("list_sessions",)
# Strumenti che cercano nel CONTENUTO delle trascrizioni di tutte le sessioni:
# negati ai nominati sempre e al predefinito quando esistono nominati (non c'e'
# un id che li renda ammissibili: cercano dappertutto).
SESSIONI_RICERCA = ("search_session_transcripts",)

# Strumenti che scrivono un file con `file_path`/`notebook_path`.
STRUMENTI_SCRITTURA = ("Write", "Edit", "MultiEdit", "NotebookEdit")

# Il registro dell'app: `<home>/Library/Application Support/Claude/
# claude-code-sessions/*/*/local_<uuid>.json`, con `sessionId` (l'id `local_`
# che gli strumenti di sessione ricevono), `cliSessionId` (il `session_id`
# dell'hook: e' il nome del .jsonl), `cwd`, `originCwd` e `title`.
_RX_LOCAL = re.compile(r"^local_[0-9A-Za-z-]{1,80}$")
MAX_FILE_REGISTRO_APP = 5000

_UUID = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


# --------------------------------------------------------------------------
# percorsi
# --------------------------------------------------------------------------

def percorso_dati(env=None) -> str:
    """La cartella dati di Plancia: la stessa regola di `config.DATA_DIR`
    (PLANCIA_HOME, altrimenti ~/.plancia), senza importare `config`."""
    env = os.environ if env is None else env
    return env.get("PLANCIA_HOME") or os.path.join(os.path.expanduser("~"), ".plancia")


def _norm(p, base=None) -> str:
    """Percorso assoluto, con i symlink risolti fino in fondo. Funziona anche
    su un percorso che non esiste (risolve i pezzi iniziali che esistono).
    Stringa vuota se non e' un percorso usabile."""
    if not isinstance(p, str) or not p or "\x00" in p:
        return ""
    try:
        p = os.path.expanduser(p)
        if not os.path.isabs(p):
            p = os.path.join(base or os.getcwd(), p)
        r = os.path.realpath(p)
    except (OSError, ValueError):
        return ""
    return r.rstrip("/") or "/"


def _codifica(p: str) -> str:
    """Come Claude Code trasforma una cartella nel nome che le da' sotto
    `~/.claude/projects`: ogni carattere non `[A-Za-z0-9]` diventa un trattino,
    uno per uno (stessa regola di `plancia/esclusi.py:_codifica`, ripetuta:
    quella sta in un modulo che importa il database)."""
    return re.sub(r"[^A-Za-z0-9]", "-", p)


def _dentro(p: str, radice: str) -> bool:
    """`p` e' `radice` o sta sotto. Senza distinzione di maiuscole (vedi i
    limiti nel docstring del modulo)."""
    if not p or not radice:
        return False
    a, b = p.lower(), radice.lower().rstrip("/")
    if b == "":
        return True
    return a == b or a.startswith(b + "/")


def _ha_glob(s: str) -> bool:
    return any(c in s for c in "*?[")


# --------------------------------------------------------------------------
# il registro dell'app: da un id `local_...` (o da un titolo) alla sessione
# --------------------------------------------------------------------------

def _leggi_voce_app(percorso: str):
    try:
        if os.path.getsize(percorso) > 4 * 1024 * 1024:
            return None
        with open(percorso, "r", encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError, UnicodeDecodeError, RecursionError):
        return None
    if not isinstance(d, dict):
        return None

    def testo(k):
        v = d.get(k)
        return v if isinstance(v, str) else ""
    return {"local": testo("sessionId"), "cli": testo("cliSessionId"),
            "cwd": testo("cwd"), "origine": testo("originCwd"),
            "titolo": testo("title")}


def _voci_app(home: str, chiave=None, titolo=None) -> list:
    """Le sessioni del registro dell'app che corrispondono a un id `local_`
    (`chiave`) o a un titolo (senza distinzione di maiuscole). Il titolo
    costringe a leggere tutti i file del registro (poche centinaia): si fa
    solo per gli strumenti di sessione che ricevono un nome. Un id `local_`
    e' un solo file."""
    import glob
    base = os.path.join(glob.escape(home), "Library", "Application Support",
                        "Claude", "claude-code-sessions", "*", "*")
    if chiave is not None:
        if not _RX_LOCAL.match(chiave):
            return []
        pattern = os.path.join(base, chiave + ".json")
    else:
        pattern = os.path.join(base, "local_*.json")
    voci = []
    try:
        trovati = sorted(glob.glob(pattern))
    except OSError:
        return []
    for percorso in trovati[:MAX_FILE_REGISTRO_APP]:
        v = _leggi_voce_app(percorso)
        if not v:
            continue
        if titolo is not None and v["titolo"].lower() != titolo.lower():
            continue
        if not v["local"] and chiave:
            v["local"] = chiave
        voci.append(v)
    return voci


# --------------------------------------------------------------------------
# config: lettura, validazione, copia dell'ultima valida
# --------------------------------------------------------------------------

def _lista_str(v, nome):
    if v is None:
        return []
    if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
        raise ValueError(f"{nome} non e' una lista di stringhe")
    return list(v)


def valida_compartimenti(raw):
    """`compartimenti` di config.json, controllato. Torna la stessa struttura
    con le liste sempre presenti, o solleva ValueError con il motivo. Un
    tipo sbagliato in qualunque punto rende TUTTA la sezione inaffidabile
    (fail-closed: vedi `carica()`)."""
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("compartimenti non e' un oggetto")
    out = {}
    for nome, c in raw.items():
        if not isinstance(nome, str) or not nome:
            raise ValueError("nome di compartimento non valido")
        if not isinstance(c, dict):
            raise ValueError(f"compartimento {nome!r} non e' un oggetto")
        if nome == PREDEFINITO:
            man = c.get("manifesto_divieti")
            if man is not None and not isinstance(man, str):
                raise ValueError("manifesto_divieti non e' una stringa")
            out[nome] = {
                "manifesto_divieti": man or "",
                "divieti": _lista_str(c.get("divieti"), "divieti"),
                "comandi_vietati": _lista_str(c.get("comandi_vietati"),
                                              "comandi_vietati"),
            }
        else:
            out[nome] = {
                "cartelle": _lista_str(c.get("cartelle"), "cartelle"),
                "sessioni": _lista_str(c.get("sessioni"), "sessioni"),
                "drive_ids": _lista_str(c.get("drive_ids"), "drive_ids"),
            }
    return out


def _da_json(letta, solo_modo=False):
    """(modo, compartimenti, strumenti_drive) da un oggetto gia' letto, o
    ValueError. Con `solo_modo` e modo `spento` non si guarda altro: uno
    spento con un resto scritto male e' comunque spento (l'hook spento non
    legge niente oltre il modo)."""
    if not isinstance(letta, dict):
        raise ValueError("config.json non e' un oggetto")
    modo = letta.get("guardiano", MODO_DEFAULT)
    if not isinstance(modo, str) or modo.strip().lower() not in MODI:
        raise ValueError("guardiano: modo sconosciuto")
    modo = modo.strip().lower()
    if solo_modo and modo == "spento":
        return modo, {}, []
    comp = valida_compartimenti(letta.get("compartimenti"))
    drive = _lista_str(letta.get("strumenti_drive"), "strumenti_drive")
    return modo, comp, drive


def leggi_config(data_dir: str, rapida: bool = False) -> dict:
    """Legge `config.json` SENZA scriverlo e senza creare cartelle. Con
    `rapida` (l'hook) un `guardiano: "spento"` non valida il resto.

    Torna `{"stato": "assente"|"ok"|"rotta", "modo", "compartimenti",
    "strumenti_drive", "errore"}`. `assente`: il file non c'e' (guardiano
    spento, come da default)."""
    r = {"stato": "ok", "modo": MODO_DEFAULT, "compartimenti": {},
         "strumenti_drive": [], "errore": None}
    percorso = os.path.join(data_dir, "config.json")
    try:
        with open(percorso, "r", encoding="utf-8") as f:
            testo = f.read()
    except FileNotFoundError:
        r["stato"] = "assente"
        return r
    except (OSError, UnicodeDecodeError) as exc:
        r["stato"], r["errore"] = "rotta", f"config.json non leggibile: {exc}"
        return r
    try:
        r["modo"], r["compartimenti"], r["strumenti_drive"] = _da_json(
            json.loads(testo), rapida)
    except (ValueError, RecursionError) as exc:
        r["stato"], r["errore"] = "rotta", f"config.json non valido: {exc}"
    return r


def _percorso_copia(data_dir: str) -> str:
    return os.path.join(data_dir, "compartimenti.ultima-valida.json")


def _leggi_copia(data_dir: str):
    """L'ultima config valida salvata, o None (assente, illeggibile, non piu'
    valida)."""
    try:
        with open(_percorso_copia(data_dir), "r", encoding="utf-8") as f:
            modo, comp, drive = _da_json(json.load(f))
    except (OSError, ValueError, UnicodeDecodeError, RecursionError):
        return None
    return {"modo": modo, "compartimenti": comp, "strumenti_drive": drive}


def _salva_copia_se_diversa(data_dir: str, cfg: dict) -> None:
    """Scrive la copia solo se cambia: una scrittura a ogni strumento sarebbe
    rumore e usura. Scrittura atomica (file temporaneo + rename): un hook
    interrotto a meta' non deve lasciare una copia tagliata."""
    nuovo = json.dumps({"guardiano": cfg["modo"],
                        "compartimenti": cfg["compartimenti"],
                        "strumenti_drive": cfg["strumenti_drive"]},
                       indent=2, sort_keys=True, ensure_ascii=False)
    dest = _percorso_copia(data_dir)
    try:
        with open(dest, "r", encoding="utf-8") as f:
            if f.read() == nuovo:
                return
    except OSError:
        pass
    try:
        os.makedirs(data_dir, exist_ok=True)
        tmp = f"{dest}.{os.getpid()}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(nuovo)
        os.replace(tmp, dest)
    except OSError:
        pass


def carica(data_dir: str) -> dict:
    """La configurazione EFFETTIVA del guardiano, con le regole di guasto.

    - config assente o `guardiano: "spento"`: spento, non si legge altro
      (se esiste la copia dell'ultima valida la si riscrive come spento).
    - config valida: si usa, e (se non spento) se ne tiene la copia.
    - config rotta CON copia valida: si usa la copia, modo compreso: un
      nominato resta confinato (fail-closed per i nominati).
    - config rotta SENZA copia: `solo-registro` per tutti, con una riga
      "config illeggibile" (limitata nel tempo). Il predefinito non viene mai
      bloccato per un errore di config.

    Torna `{"modo", "compartimenti", "strumenti_drive", "stato", "nota"}`.
    `nota` e' il testo della riga di registro da scrivere, o None."""
    c = leggi_config(data_dir, rapida=True)
    if c["stato"] == "ok" and c["modo"] == "spento":
        # `spento` e' una config valida come le altre: se c'e' una copia
        # dell'ultima valida la si aggiorna, altrimenti una virgola in piu' in
        # config.json (a mano, il file e' condiviso con il resto di Plancia)
        # rimetterebbe in piedi il vecchio `bloccante` che l'utente aveva
        # spento. Senza copia non se ne crea una: spento non scrive niente.
        if os.path.exists(_percorso_copia(data_dir)):
            _salva_copia_se_diversa(data_dir, {
                "modo": "spento", "compartimenti": {}, "strumenti_drive": []})
        return {"modo": "spento", "compartimenti": {}, "strumenti_drive": [],
                "stato": "ok", "nota": None}
    if c["stato"] == "assente":
        return {"modo": "spento", "compartimenti": {}, "strumenti_drive": [],
                "stato": c["stato"], "nota": None}
    if c["stato"] == "ok":
        _salva_copia_se_diversa(data_dir, c)
        return {"modo": c["modo"], "compartimenti": c["compartimenti"],
                "strumenti_drive": c["strumenti_drive"], "stato": "ok",
                "nota": None}
    copia = _leggi_copia(data_dir)
    if copia is not None:
        return {"modo": copia["modo"], "compartimenti": copia["compartimenti"],
                "strumenti_drive": copia["strumenti_drive"],
                "stato": "copia",
                "nota": "config illeggibile (%s): uso l'ultima valida"
                        % (c["errore"],)}
    return {"modo": "solo-registro", "compartimenti": {}, "strumenti_drive": [],
            "stato": "rotta",
            "nota": "config illeggibile (%s): nessuna copia valida, "
                    "solo-registro per tutti" % (c["errore"],)}


# --------------------------------------------------------------------------
# registro
# --------------------------------------------------------------------------

def _percorso_registro(data_dir: str) -> str:
    return os.path.join(data_dir, "guardiano.log")


def scrivi_registro(data_dir: str, riga: dict) -> None:
    """Una riga JSON in `guardiano.log`. Rotazione semplice: oltre 5 MB il
    file diventa `.1` (sostituendo l'eventuale `.1` precedente). Non solleva
    mai: un registro che non si scrive non deve fermare un hook."""
    try:
        os.makedirs(data_dir, exist_ok=True)
        p = _percorso_registro(data_dir)
        try:
            if os.path.getsize(p) > REGISTRO_MAX_BYTE:
                os.replace(p, p + ".1")
        except OSError:
            pass
        riga = dict(riga)
        riga.setdefault("ts", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        dati = (json.dumps(riga, ensure_ascii=False) + "\n").encode("utf-8")
        fd = os.open(p, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            os.write(fd, dati)
        finally:
            os.close(fd)
    except (OSError, ValueError):
        pass


def _nota_config_dovuta(data_dir: str) -> bool:
    """Vero se e' ora di scrivere di nuovo la riga "config illeggibile"."""
    marca = os.path.join(data_dir, "guardiano.config-illeggibile")
    try:
        if time.time() - os.path.getmtime(marca) < NOTA_CONFIG_OGNI_SECONDI:
            return False
    except OSError:
        pass
    try:
        os.makedirs(data_dir, exist_ok=True)
        with open(marca, "w") as f:
            f.write("")
    except OSError:
        pass
    return True


def leggi_registro(data_dir: str, n: int = 20) -> list:
    """Le ultime `n` righe del registro, come dizionari (le righe rotte si
    saltano)."""
    try:
        with open(_percorso_registro(data_dir), "rb") as f:
            f.seek(0, os.SEEK_END)
            dim = f.tell()
            f.seek(max(0, dim - 2 * 1024 * 1024))
            testo = f.read().decode("utf-8", "replace")
    except OSError:
        return []
    righe = []
    for linea in testo.splitlines():
        try:
            d = json.loads(linea)
        except ValueError:
            continue
        if isinstance(d, dict):
            righe.append(d)
    return righe[-n:] if n > 0 else []


def _epoch(ts) -> float:
    import calendar
    return calendar.timegm(time.strptime(ts, "%Y-%m-%dT%H:%M:%SZ"))


def stato(data_dir: str) -> dict:
    """Modo, compartimenti (nomi e numero di cartelle, MAI i percorsi) e
    righe di registro nelle ultime 24 ore. Sola lettura."""
    c = leggi_config(data_dir)
    copia = _leggi_copia(data_dir) if c["stato"] == "rotta" else None
    if c["stato"] == "ok":
        comp, modo = c["compartimenti"], c["modo"]
    elif copia:
        comp, modo = copia["compartimenti"], copia["modo"]
    else:
        comp = {}
        modo = MODO_DEFAULT if c["stato"] == "assente" else "solo-registro"
    elenco = []
    for nome, v in sorted(comp.items()):
        if nome == PREDEFINITO:
            elenco.append({"nome": nome, "divieti": len(v["divieti"]),
                           "comandi_vietati": len(v["comandi_vietati"]),
                           "manifesto": bool(v["manifesto_divieti"])})
        else:
            elenco.append({"nome": nome, "cartelle": len(v["cartelle"]),
                           "sessioni": len(v["sessioni"]),
                           "drive_ids": len(v["drive_ids"])})
    soglia = time.time() - 24 * 3600
    recenti = {"negato": 0, "avrebbe-negato": 0, "altro": 0}
    for d in leggi_registro(data_dir, 100000):
        try:
            t = _epoch(d.get("ts"))
        except (ValueError, TypeError):
            continue
        if t < soglia:
            continue
        e = d.get("esito")
        recenti[e if e in recenti else "altro"] += 1
    return {"modo": modo, "config": c["stato"], "errore": c["errore"],
            "usa_copia": bool(copia), "compartimenti": elenco,
            "registro_24h": recenti}


# --------------------------------------------------------------------------
# l'insieme dei compartimenti, pronto per decidere
# --------------------------------------------------------------------------

class Ambito:
    """I compartimenti di una config, con i percorsi gia' risolti."""

    def __init__(self, comp: dict, strumenti_drive=None, home=None, uid=None,
                 data_dir=None, claude_dir=None):
        self.home = home or os.path.expanduser("~")
        self.uid = os.getuid() if uid is None else uid
        self.data_dir = data_dir or ""
        # `<CLAUDE_CONFIG_DIR o ~/.claude>/projects`: dove Claude Code tiene
        # trascrizioni e memoria di ogni cartella (vedi `proprietario_specchio`).
        self.claude_dir = claude_dir or cartella_claude(home=self.home)
        self.progetti = _norm(os.path.join(self.claude_dir, "projects"))
        self.strumenti_drive = set(STRUMENTI_DRIVE) | set(strumenti_drive or [])
        self.nominati = {}
        for nome, c in comp.items():
            if nome == PREDEFINITO:
                continue
            cartelle, codifiche = [], set()
            for raw in c["cartelle"]:
                n = _norm(raw)
                if not n:
                    continue
                cartelle.append(n)
                # La codifica si prova sia sulla grafia scritta sia su quella
                # risolta: Claude Code codifica la cwd com'e' stata aperta.
                codifiche.add(_codifica(os.path.expanduser(raw)).lower())
                codifiche.add(_codifica(n).lower())
            # `sessioni` accetta il `session_id` dell'hook (il nome del .jsonl)
            # e l'id `local_<uuid>` dell'app: questo si traduce nel
            # `cliSessionId` leggendo il registro dell'app, cosi' chi chiama
            # (che ha solo il session_id) si riconosce in tutti e due i modi.
            sessioni = set(c["sessioni"])
            for s in c["sessioni"]:
                if s.startswith("local_"):
                    for v in _voci_app(self.home, chiave=s):
                        if v["cli"]:
                            sessioni.add(v["cli"])
            self.nominati[nome] = {
                "cartelle": cartelle, "codifiche": codifiche,
                "sessioni": sessioni,
                "drive_ids": set(c["drive_ids"]),
            }
        pred = comp.get(PREDEFINITO) or {}
        self.divieti_raw = list(pred.get("divieti") or [])
        self.manifesto = pred.get("manifesto_divieti") or ""
        self.comandi_vietati = [s for s in (pred.get("comandi_vietati") or []) if s]
        self._divieti = None
        self._neutri = None

    def neutri(self):
        """L'elenco neutro, risolto una volta per chiamata."""
        if self._neutri is None:
            elenco = [_norm(p) for p in NEUTRI_FISSI]
            elenco += [_norm(os.path.join(self.home, p)) for p in NEUTRI_HOME]
            self._neutri = [p for p in elenco if p]
        return self._neutri

    def divieti(self):
        """Lista di `(letterale, glob)`: `glob` e' None per un percorso
        letterale (gia' risolto), altrimenti il modello. Si costruisce una
        volta per chiamata e solo se serve (il manifesto e' un file da
        leggere)."""
        if self._divieti is not None:
            return self._divieti
        # Ogni riga con la cartella rispetto a cui si risolve se e' relativa
        # con una barra: quella dei dati per `divieti`, quella del manifesto per
        # le sue righe. Mai la cwd dell'hook: cambia da una sessione all'altra e
        # un divieto relativo colpirebbe posti diversi a seconda di dove si e'.
        righe = [(r, self.data_dir) for r in self.divieti_raw]
        if self.manifesto:
            man = os.path.expanduser(self.manifesto)
            try:
                with open(man, "r", encoding="utf-8") as f:
                    for linea in f.read().splitlines():
                        linea = linea.strip()
                        if linea and not linea.startswith("#"):
                            righe.append((linea, os.path.dirname(
                                os.path.abspath(man))))
            except (OSError, UnicodeDecodeError):
                # Un manifesto illeggibile non blocca il predefinito (vedi
                # `carica`): perde solo quelle righe, e la prova del
                # manifesto e' li' apposta per accorgersene.
                pass
        out = []
        for riga, base in righe:
            riga = os.path.expanduser(riga)
            if base and "/" in riga and not os.path.isabs(riga):
                riga = os.path.join(base, riga)
            if _ha_glob(riga):
                out.append((_prefisso_letterale(riga), _norm_glob(riga)))
            else:
                n = _norm(riga) if "/" in riga else riga
                if n:
                    out.append((n, None))
        self._divieti = out
        return out

    def proprietario_percorso(self, p: str):
        """Il nome del nominato che possiede `p`, o None."""
        for nome, c in self.nominati.items():
            if any(_dentro(p, f) for f in c["cartelle"]):
                return nome
        return None

    def proprietario_specchio(self, p: str):
        """Il nome del nominato a cui appartiene `p` come SPECCHIO di una sua
        cartella sotto `<claude>/projects`: le trascrizioni, la memoria, le
        cartelle di sessione e dei subagenti di una cartella di X e delle sue
        discendenti sono lavoro di X. None se `p` non e' li' sotto o non e' di
        nessun nominato. Il confine e' il trattino: `<enc>` e `<enc>-...`
        (una discendente), non `<enc>altro` (una sorella con lo stesso inizio).
        Ma la codifica perde la differenza fra `/` e `-`, quindi una sorella
        `alfa-2` di `alfa` risulta di alfa: in dubbio si nega (vedi
        `_codifica_di_x`)."""
        if not p or not self.progetti or not _dentro(p, self.progetti):
            return None
        resto = p[len(self.progetti):].strip("/")
        if not resto:
            return None
        primo = resto.split("/")[0].lower()
        for nome, c in self.nominati.items():
            if any(primo == e or primo.startswith(e + "-") for e in c["codifiche"]):
                return nome
        return None

    def specchio_incluso(self, p: str):
        """Il nome di un nominato (con almeno una cartella) il cui specchio in
        `<claude>/projects` sta dentro `p` o e' `p` stessa: una ricerca ricorsiva
        che parte da `p` (`projects`, `~/.claude`, `~`) lo leggerebbe. None se
        non ce n'e'."""
        if not p or not self.progetti or not _dentro(self.progetti, p):
            return None
        for nome, c in self.nominati.items():
            if c["codifiche"]:
                return nome
        return None


def cartella_claude(env=None, home=None) -> str:
    """La cartella di configurazione di Claude Code: `CLAUDE_CONFIG_DIR`, se
    c'e', altrimenti `~/.claude`."""
    env = os.environ if env is None else env
    return env.get("CLAUDE_CONFIG_DIR") or os.path.join(
        home or os.path.expanduser("~"), ".claude")


def proprietario_specchio(p: str, ambito: "Ambito"):
    """Il nominato a cui appartiene `p` come trascrizione, memoria o cartella
    di sessione sotto `<claude>/projects` (o None). `p` deve essere gia'
    risolto con `_norm`. E' la regola che il richiamo di Plancia (E1) usa per
    non leggere il lavoro di un compartimento nominato nelle trascrizioni."""
    return ambito.proprietario_specchio(p)


def _prefisso_letterale(pattern: str) -> str:
    """La parte di `pattern` prima del primo componente con un glob, risolta.
    `/a/b/*.txt` -> `/a/b`. Senza barre (un modello di nome): stringa vuota."""
    if "/" not in pattern or not os.path.isabs(pattern):
        return ""
    fisso = []
    for z in pattern.split("/"):
        if _ha_glob(z):
            break
        fisso.append(z)
    return _norm("/".join(fisso) or "/")


def _norm_glob(pattern: str) -> str:
    """Il modello con il prefisso letterale risolto (`/tmp` e' un symlink a
    `/private/tmp`: un modello scritto con l'uno deve valere per l'altro)."""
    if "/" not in pattern or not os.path.isabs(pattern):
        return pattern
    pezzi = pattern.split("/")
    fisso = []
    for z in pezzi:
        if _ha_glob(z):
            break
        fisso.append(z)
    coda = pezzi[len(fisso):]
    base = _norm("/".join(fisso) or "/")
    return (base.rstrip("/") + "/" + "/".join(coda)) if coda else base


def _combacia_glob(modello: str, p: str) -> bool:
    """Un divieto con glob contro un percorso.

    Con una barra e' un modello di percorso: vale per `p` e per ogni suo
    antenato (negare una cartella nega tutto quello che sta sotto). Il `*`
    attraversa le barre (`fnmatch`): piu' largo, quindi piu' prudente. Senza
    barra e' un modello di NOME: vale se combacia un componente qualsiasi."""
    import fnmatch
    m, q = modello.lower(), p.lower()
    if "/" in m:
        parti = q.split("/")
        for i in range(2, len(parti) + 1):
            if fnmatch.fnmatchcase("/".join(parti[:i]) or "/", m):
                return True
        return False
    return any(fnmatch.fnmatchcase(c, m) for c in q.split("/") if c)


# --------------------------------------------------------------------------
# chi chiama
# --------------------------------------------------------------------------

def _da_trascrizione(tp):
    """`(id_madre, cartella_codificata, cartella_progetto)` da un
    `transcript_path`.

    Una sessione: `<progetti>/<codificata>/<id>.jsonl`. Un subagente:
    `<progetti>/<codificata>/<id madre>/subagents/[workflows/<x>/]agent-...
    .jsonl`: l'id della madre e' il componente che precede `subagents`."""
    if not isinstance(tp, str) or not tp:
        return "", "", ""
    parti = tp.replace("\\", "/").split("/")
    if "subagents" in parti:
        i = parti.index("subagents")
        madre = parti[i - 1] if i >= 1 else ""
        codificata = parti[i - 2] if i >= 2 else ""
        progetto = "/".join(parti[:i - 1]) if i >= 2 else ""
        return madre, codificata, progetto
    nome = parti[-1]
    madre = nome[:-6] if nome.endswith(".jsonl") else nome
    codificata = parti[-2] if len(parti) >= 2 else ""
    return madre, codificata, "/".join(parti[:-1])


def _codifica_di_x(cod: str, c: dict) -> bool:
    """La cartella di apertura (codificata) e' una cartella di X o una sua
    discendente. `startswith(e + "-")` prende anche una cartella sorella con
    lo stesso prefisso ("/x/alfa-2" per "/x/alfa"): la codifica perde la
    distinzione fra "/" e "-", e in dubbio si confina."""
    return bool(cod) and any(cod == e or cod.startswith(e + "-")
                             for e in c["codifiche"])


def _nomi_da_segnali(ambito: Ambito, ids=(), cwds=(), codifiche=()) -> list:
    """I nomi dei compartimenti nominati a cui puntano i segnali: un id in
    `sessioni`, una cwd dentro le cartelle, una cartella di apertura
    codificata. Ne basta uno per compartimento (prudenza)."""
    ids = {x for x in ids if x}
    codifiche = [c.lower() for c in codifiche if c]
    nomi = []
    for nome in sorted(ambito.nominati):
        c = ambito.nominati[nome]
        if (ids & c["sessioni"]
                or any(_codifica_di_x(cod, c) for cod in codifiche)
                or any(cw and _dentro(cw, f) for cw in cwds
                       for f in c["cartelle"])):
            nomi.append(nome)
    return nomi


def chiamante(payload: dict, ambito: Ambito) -> dict:
    """A quali compartimenti appartiene la sessione che chiama.

    Tre segnali, e ne basta UNO (prudenza: una sessione che sembra di due
    compartimenti deve rispettare i permessi di entrambi):

    1. l'id di sessione, o l'id della sessione MADRE se chi chiama e' un
       subagente (ricavato dal `transcript_path`), e' in `X.sessioni`;
    2. la cartella in cui la sessione e' stata APERTA, ricavata dal
       `transcript_path` (la cartella codificata sotto `~/.claude/projects`),
       e' una cartella di X o una sua discendente;
    3. il `cwd` del payload sta dentro una cartella di X.

    Il `cwd` da solo NON basta come segnale di appartenenza: un `cd` (e ogni
    strumento che cambia directory) lo sposta, quindi un nominato che esce
    dalla sua cartella con un `cd` sembrerebbe di colpo predefinito e
    uscirebbe dal confinamento. Per questo gli altri due segnali (id e
    cartella di apertura) non si muovono mai. Il `cwd` puo' solo AGGIUNGERE
    un'appartenenza, mai toglierla.

    Torna `{"nomi": [...], "sessione", "madre", "codificata",
    "cartella_progetto", "cwd", "subagente"}`. `nomi` vuoto = predefinito."""
    sid = payload.get("session_id")
    sid = sid if isinstance(sid, str) else ""
    madre, codificata, progetto = _da_trascrizione(payload.get("transcript_path"))
    cwd_raw = payload.get("cwd")
    cwd = _norm(cwd_raw) if isinstance(cwd_raw, str) and cwd_raw else ""
    nomi = _nomi_da_segnali(ambito, (sid, madre), (cwd,), (codificata,))
    tp = payload.get("transcript_path")
    subagente = bool(payload.get("agent_id")) or (
        isinstance(tp, str) and "/subagents/" in tp.replace("\\", "/"))
    return {"nomi": nomi, "sessione": sid or madre, "madre": madre,
            "codificata": codificata, "cartella_progetto": progetto,
            "cwd": cwd, "subagente": subagente}


def _scratch_ok(p: str, chi: dict, ambito: Ambito) -> bool:
    """La cartella di lavoro temporaneo di QUESTA sessione:
    `/private/tmp/claude-<uid>/<qualcosa>/<id di sessione>/...`."""
    base = _norm("/private/tmp/claude-%s" % ambito.uid)
    if not _dentro(p, base):
        return False
    resto = p[len(base):].strip("/").split("/")
    ids = {x for x in (chi["sessione"], chi["madre"]) if x}
    return len(resto) >= 2 and resto[1] in ids


def _progetto_ok(p: str, chi: dict, dalla_cartella: bool) -> bool:
    """La propria cartella sotto `~/.claude/projects`. Se la sessione e' li'
    perche' la sua cartella di apertura e' di X, e' tutta sua. Se invece e'
    di X solo per id (aperta in una cartella normale che condivide con altre
    sessioni), solo la propria trascrizione e la propria cartella di
    sessione: le trascrizioni degli altri non sono sue, e neanche `memory`.
    `memory` e' la memoria di TUTTE le sessioni del predefinito aperte in quella
    cartella: leggerla mostrerebbe i loro ricordi al nominato, e scriverci
    metterebbe i suoi in un `MEMORY.md` che Claude Code carica da solo in ogni
    sessione del predefinito (il canale 7 della specifica, nei due sensi)."""
    prog = _norm(chi["cartella_progetto"]) if chi["cartella_progetto"] else ""
    if not prog:
        return False
    if dalla_cartella:
        return _dentro(p, prog)
    for x in (chi["sessione"], chi["madre"]):
        if x and (_dentro(p, os.path.join(prog, x))
                  or p.lower() == os.path.join(prog, x + ".jsonl").lower()):
            return True
    return False


# --------------------------------------------------------------------------
# percorsi dagli strumenti e dai comandi Bash
# --------------------------------------------------------------------------

_RX_URL = re.compile(r"\b[A-Za-z][A-Za-z0-9+.-]*://\S+")
# Un percorso assoluto dentro un testo qualsiasi (codice passato a un
# interprete): preceduto da inizio riga, spazio, virgolette, `=`, `(`, `,`, ...
# ma non da una lettera, un punto, `$`, `}`, `:` o `/` (cosi' `s/a/b/` di sed e
# `https://x/y` non si scambiano per percorsi). Almeno un carattere dopo la
# barra: una `/` da sola (`os.listdir('/')`, una divisione) non e' un percorso.
_RX_ASSOLUTO = re.compile(r"""(?<![\w.$}:/])((?:~|)/[^\s'"`;|&<>()\\]+)""")
_RX_VAR = re.compile(r"\$(?:\{([A-Za-z_]\w*)\}|([A-Za-z_]\w*))")

# Comandi che eseguono CODICE dato come testo (`python3 -c "..."`, un heredoc
# passato a `python3 -`): dentro le stringhe ci sono percorsi che il comando
# aprira' davvero, quindi si cercano con l'espressione regolare. Gli altri
# comandi non interpretano i loro argomenti come codice.
_RX_INTERPRETE = re.compile(
    r"^(?:python[\d.]*|node|nodejs|deno|bun|ruby|perl|php|osascript|lua|rscript"
    r"|swift)$", re.I)
# Le shell: il testo di `sh -c '...'` e il corpo di un heredoc dato a `bash` SONO
# comandi, e si analizzano come tali.
_SHELL = ("sh", "bash", "zsh", "dash", "ksh", "fish")
# Comandi che stampano i loro argomenti: `echo $HOME` non tocca nessun percorso.
# Restano le redirezioni (`echo x > file` scrive un file) e le sostituzioni di
# comando dentro gli argomenti (`echo $(cat file)`, che si analizzano a parte).
_MUTI = ("echo", "printf")
_PUNTEGGIATURA = frozenset("();<>|&")


def _e_interprete(nome: str) -> bool:
    return bool(_RX_INTERPRETE.match(nome or ""))


def _punt(t: str) -> bool:
    """Un token di punteggiatura della shell (`>`, `>>`, `<<`, `2>&1` a pezzi)."""
    return bool(t) and all(c in _PUNTEGGIATURA for c in t)


def _prefisso_glob_dir(pattern: str) -> str:
    """La cartella letterale in cui cade un modello di Glob."""
    tagliato = re.split(r"[*?\[{]", pattern, 1)[0]
    if tagliato == pattern:
        return pattern
    return tagliato.rsplit("/", 1)[0] if "/" in tagliato else ""


# --- il comando Bash, a pezzi ----------------------------------------------
#
# EURISTICO, dichiarato: ferma gli incidenti, non chi vuole aggirarlo. Il
# comando si scompone cosi': (1) via i corpi degli heredoc (sono dati, non
# argomenti: restano solo se il comando che li riceve li interpreta, cioe' una
# shell o un interprete di codice); (2) segmenti separati da `;`, `&&`, `||`,
# `|`, a capo, parentesi (con le virgolette rispettate); (3) ogni segmento in
# token con `shlex`; (4) le sostituzioni `$(...)` e `` `...` `` e il testo di
# `sh -c` si analizzano di nuovo, a parte. Se le virgolette non tornano si
# ripiega su uno split per spazi.

_RX_HEREDOC = re.compile(
    r"<<(-?)[ \t]*(?:'([^'\n]*)'|\"([^\"\n]*)\"|\\?([A-Za-z_][A-Za-z_0-9.-]*))")
_CACHE_ANALISI = {}


def _token(seg: str) -> list:
    import shlex
    try:
        lex = shlex.shlex(seg, posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        lex.commenters = ""
        return list(lex)
    except ValueError:
        return [t.strip("'\"") for t in seg.split()]


_PREFISSI_COMANDO = ("sudo", "time", "nice", "env", "command", "xargs", "exec",
                     "nohup")


def _nome_e_args(tok) -> tuple:
    """Il nome del comando (senza cartella) e i suoi argomenti, dopo i
    prefissi (`sudo`, `env`, `VAR=x`, opzioni dei prefissi...)."""
    t = list(tok)
    while t and (t[0] in _PREFISSI_COMANDO or re.match(r"^\w+=", t[0])
                 or (t[0].startswith("-") and len(t) > 1)
                 or _punt(t[0])):
        t = t[1:]
    if not t:
        return "", []
    return os.path.basename(t[0]), t[1:]


def _tipo_ricevente(fatto: str) -> str:
    """Chi riceve un heredoc, dal testo del comando scritto fin qui: `shell`
    (il corpo e' una serie di comandi), `codice` (un interprete: il corpo e'
    codice con percorsi veri) o `dati` (`cat`, `tee`, `git`: il corpo e' testo)."""
    coda = re.split(r"[;&|\n()]", fatto)[-1]
    nome, _ = _nome_e_args(_token(coda))
    if nome in _SHELL:
        return "shell"
    if _e_interprete(nome):
        return "codice"
    return "dati"


def _togli_heredoc(cmd: str):
    """`(testo senza i corpi da scartare, [corpi di codice])`. Il corpo di un
    heredoc dato a una shell resta nel testo (sono comandi), quello dato a un
    interprete va nell'elenco dei corpi di codice, tutti gli altri si scartano:
    `cat <<'EOF'`, `git commit -m "$(cat <<'EOF' ... EOF)"` non hanno percorsi
    da negare nel loro testo."""
    if "<<" not in cmd:
        return cmd, []
    out, corpi, attesa = [], [], []
    q, i, n = None, 0, len(cmd)
    while i < n:
        c = cmd[i]
        if q:
            out.append(c)
            if q == '"' and c == "\\" and i + 1 < n:
                out.append(cmd[i + 1])
                i += 2
                continue
            if c == q:
                q = None
            i += 1
            continue
        if c == "\\" and i + 1 < n:
            out.append(c + cmd[i + 1])
            i += 2
            continue
        if c in "'\"":
            q = c
            out.append(c)
            i += 1
            continue
        if c == "\n" and attesa:
            out.append("\n")
            i += 1
            for delim, tipo, quotato in attesa:
                righe = []
                while i < n:
                    j = cmd.find("\n", i)
                    j = n if j == -1 else j
                    riga = cmd[i:j]
                    i = j + 1
                    if riga.strip() == delim:
                        break
                    righe.append(riga)
                corpo = "\n".join(righe)
                if tipo == "shell":
                    out.append(corpo + "\n")
                elif tipo == "codice":
                    corpi.append(corpo)
                elif not quotato:
                    # Un heredoc senza virgolette espande `$(...)` e gli apici
                    # inversi del suo corpo: quei comandi girano davvero.
                    for interno in _sostituzioni(corpo):
                        out.append(interno + "\n")
            attesa = []
            continue
        if c == "<" and cmd.startswith("<<", i) and not cmd.startswith("<<<", i):
            m = _RX_HEREDOC.match(cmd, i)
            if m:
                delim = next((g for g in m.group(2, 3, 4) if g is not None), "")
                quotato = m.group(2) is not None or m.group(3) is not None or (
                    "\\" in m.group(0))
                attesa.append((delim, _tipo_ricevente("".join(out)), quotato))
                out.append(m.group(0))
                i = m.end()
                continue
        out.append(c)
        i += 1
    return "".join(out), corpi


def _dividi_segmenti(t: str) -> list:
    """Il testo diviso ai `;`, `&&`, `||`, `|`, a capo e alle parentesi che non
    sono dentro virgolette, `$(...)` o apici inversi. `>&`, `&>` e `>|` non
    dividono."""
    out, cur = [], []
    q, sub, bt, i, n = None, 0, False, 0, len(t)
    while i < n:
        c = t[i]
        if q:
            cur.append(c)
            if q == '"' and c == "\\" and i + 1 < n:
                cur.append(t[i + 1])
                i += 2
                continue
            if c == q:
                q = None
            i += 1
            continue
        if c == "\\" and i + 1 < n:
            cur.append(c + t[i + 1])
            i += 2
            continue
        if c in "'\"":
            q = c
            cur.append(c)
            i += 1
            continue
        if c == "`":
            bt = not bt
            cur.append(c)
            i += 1
            continue
        if bt:
            cur.append(c)
            i += 1
            continue
        if c == "$" and t[i + 1:i + 2] == "(":
            sub += 1
            cur.append("$(")
            i += 2
            continue
        if sub:
            sub += 1 if c == "(" else -1 if c == ")" else 0
            cur.append(c)
            i += 1
            continue
        prec = t[i - 1] if i else ""
        succ = t[i + 1] if i + 1 < n else ""
        sep = c in ";\n()" or (c == "|" and prec != ">") or (
            c == "&" and prec not in "<>" and succ != ">")
        if sep:
            out.append("".join(cur))
            cur = []
        else:
            cur.append(c)
        i += 1
    out.append("".join(cur))
    return [s.strip() for s in out if s.strip()]


def _sostituzioni(t: str) -> list:
    """I testi dentro `$(...)`, `` `...` `` e `<(...)` (non quelli fra apici
    singoli): sono comandi da analizzare a parte."""
    out, sq, dq, i, n = [], False, False, 0, len(t)
    while i < n:
        c = t[i]
        if c == "\\":
            i += 2
            continue
        if c == '"' and not sq:
            dq = not dq
        elif c == "'" and not dq:
            sq = not sq
        elif not sq:
            if c in "$<>" and t[i + 1:i + 2] == "(" and (c == "$" or not dq):
                j, prof = i + 2, 1
                while j < n and prof:
                    prof += 1 if t[j] == "(" else -1 if t[j] == ")" else 0
                    j += 1
                out.append(t[i + 2:j - 1 if prof == 0 else j])
                i += 2
                continue
            if c == "`":
                k = t.find("`", i + 1)
                if k != -1:
                    out.append(t[i + 1:k])
                    i = k + 1
                    continue
        i += 1
    return out


def _analizza(cmd: str, prof: int = 0) -> dict:
    """`{"segmenti": [{"nome", "args", "token", "testo"}, ...], "corpi": [...]}`
    del comando e di tutto quello che contiene (sostituzioni, `sh -c`)."""
    if prof == 0 and cmd in _CACHE_ANALISI:
        return _CACHE_ANALISI[cmd]
    ris = {"segmenti": [], "corpi": []}
    if cmd and prof <= 3:
        testo, corpi = _togli_heredoc(cmd)
        ris["corpi"].extend(corpi)
        for seg in _dividi_segmenti(testo):
            tok = _token(seg)
            nome, args = _nome_e_args(tok)
            ris["segmenti"].append({"nome": nome, "args": args, "token": tok,
                                    "testo": seg})
            interni = list(_sostituzioni(seg))
            if nome in _SHELL:
                for k, a in enumerate(args):
                    if re.match(r"^-[A-Za-z]*c[A-Za-z]*$", a) and k + 1 < len(args):
                        interni.append(args[k + 1])
                        break
            elif nome == "eval":
                interni.append(" ".join(args))
            for interno in interni:
                r = _analizza(interno, prof + 1)
                ris["segmenti"].extend(r["segmenti"])
                ris["corpi"].extend(r["corpi"])
    if prof == 0:
        if len(_CACHE_ANALISI) > 64:
            _CACHE_ANALISI.clear()
        _CACHE_ANALISI[cmd] = ris
    return ris


def _parole_segmento(s: dict) -> list:
    """I token di un segmento che possono essere percorsi o nomi: senza la
    punteggiatura, senza la parola che segue un heredoc o una here-string (e'
    un delimitatore o un testo), e per `echo`/`printf` solo i bersagli delle
    redirezioni (gli altri argomenti si stampano e basta)."""
    muto = s["nome"] in _MUTI
    out, prec = [], ""
    for t in s["token"]:
        if _punt(t):
            prec = t
            continue
        heredoc = "<<" in prec
        redirezione = (">" in prec or "<" in prec) and not heredoc
        prec = ""
        if heredoc or (muto and not redirezione):
            continue
        out.append(t)
    return out


def _espandi_var(c: str, env=None):
    """`c` con le variabili `$VAR` e `${VAR}` espanse con l'ambiente del payload
    (se c'e') e poi con quello dell'hook. `None` se ne resta una non definita
    (o un `$` di altro genere: `$1`, `$?`): un percorso che non si sa
    ricostruire si ignora, invece di risolverlo sulla cwd come se `$X` fosse un
    nome di cartella."""
    if "$" not in c:
        return c
    mancante = []

    def sost(m):
        nome = m.group(1) or m.group(2)
        v = (env or {}).get(nome)
        if not isinstance(v, str):
            v = os.environ.get(nome)
        if v is None:
            mancante.append(nome)
            return ""
        return v
    r = _RX_VAR.sub(sost, c)
    return None if mancante or "$" in r else r


def _varianti_token(t: str, env=None):
    """Da un token di shell: se stesso e la parte dopo il primo `=`
    (`--dir=/x`). Torna `(percorsi, nomi_semplici)`: i primi sembrano un
    percorso (iniziano con `/`, `~`, `./`, `../` o contengono `/`), i secondi
    sono nomi senza barre (`cd cartella`, `git -C cartella`), che hanno senso
    solo risolti sulla cwd (vedi `_percorsi_da_comando`)."""
    if not t or (t.startswith("-") and "=" not in t):
        return [], []
    cand = [t]
    if "=" in t:
        cand.append(t.split("=", 1)[1])
    perc, nomi = [], []
    for c in cand:
        c = c.lstrip("<>&|(").strip()
        if not c or "$(" in c or "`" in c or "\n" in c or len(c) > 4096:
            continue
        if _RX_URL.match(c):
            continue
        c = _espandi_var(c, env)
        if not c:
            continue
        if c == ".." or c.startswith(("/", "~", "./", "../")) or "/" in c:
            perc.append(c)
        elif not c.startswith("-") and len(c) <= 255 and not any(x.isspace() for x in c):
            nomi.append(c)
    return perc, nomi


def _trova_percorsi_in_testo(testo: str) -> list:
    out = []
    for m in _RX_ASSOLUTO.finditer(_RX_URL.sub(" ", testo)):
        c = m.group(1)
        out.append(c)
        if c.rstrip(".,:") != c:
            out.append(c.rstrip(".,:"))
    return out


def _candidati_comando(cmd: str, env=None):
    """Percorsi e nomi che un comando Bash potrebbe toccare: i token dei suoi
    segmenti (vedi sopra) e, per i comandi che eseguono codice (`python3 -c`,
    un heredoc dato a `python3 -`), i percorsi assoluti cercati dentro il testo
    del codice."""
    an = _analizza(cmd)
    trovati, nomi = [], []
    for s in an["segmenti"]:
        for t in _parole_segmento(s):
            perc, semplici = _varianti_token(t, env)
            trovati.extend(perc)
            nomi.extend(semplici)
        if _e_interprete(s["nome"]):
            for t in s["args"]:
                trovati.extend(_trova_percorsi_in_testo(t))
    for corpo in an["corpi"]:
        trovati.extend(_trova_percorsi_in_testo(corpo))
    visti, out = set(), []
    for c in trovati:
        if c and c not in visti:
            visti.add(c)
            out.append(c)
    return out, nomi


def _espandi_glob(c: str, cwd) -> list:
    """Le voci del disco che un token con un glob di shell (`cartella/*`,
    `PR-?.md`) espanderebbe, rispetto alla cwd. Vuoto se non c'e' glob o non
    combacia niente: il token letterale si controlla comunque."""
    if not _ha_glob(c):
        return []
    import glob
    modello = os.path.expanduser(c)
    if not os.path.isabs(modello):
        modello = os.path.join(cwd or os.getcwd(), modello)
    try:
        return sorted(glob.glob(modello))[:MAX_ESPANSIONE_GLOB]
    except (OSError, ValueError):
        return []


def _percorsi_da_comando(cmd: str, cwd, nomi_semplici=False, env=None):
    """I percorsi di un comando Bash, risolti. Con `nomi_semplici` anche i
    token senza barre (`cd cartella`) risolti sulla cwd: solo per il
    predefinito, dove servono a vedere `cd cartella-di-un-nominato` da una
    cwd che sta sopra. Non per un nominato: con la cwd fuori dai suoi permessi
    ogni parola (`echo`, `ls`) risolverebbe fuori (ma vedi `valuta`: per un
    nominato la cwd stessa e' un percorso toccato da ogni comando). I token con
    un glob si espandono sul disco (`cat cartella/*`)."""
    out, visti = [], set()
    perc, nomi = _candidati_comando(cmd, env)

    def aggiungi(testo, n):
        if n and n not in visti:
            visti.add(n)
            out.append((testo, n))

    for c in perc + (nomi if nomi_semplici else []):
        aggiungi(c, _norm(c, cwd))
        for e in _espandi_glob(c, cwd):
            aggiungi(e, _norm(e, cwd))
        if len(out) >= MAX_PERCORSI_COMANDO:
            break
    return out


# I comandi che camminano un albero intero. Riconosciuti dal NOME del comando
# (il primo token di ogni segmento, dopo i prefissi `sudo`, `xargs`,
# `VAR=x`...), non da una parola qualsiasi nel testo: `echo find` non e' una
# ricerca.
_RICORSIVI_SEMPRE = ("rg", "ag", "ack", "fd", "find", "tree", "tar", "zip",
                     "rsync")


def _comando_ricorsivo(cmd: str) -> bool:
    """Vero se la riga contiene un comando che cerca o copia ricorsivamente
    (grep -r, rg, find, ls -R, tree, tar, zip, cp -r, rsync, git grep)."""
    for s in _analizza(cmd)["segmenti"]:
        nome, args = s["nome"], s["args"]
        if not nome:
            continue
        if nome in _RICORSIVI_SEMPRE:
            return True
        if nome in ("grep", "egrep", "fgrep"):
            if any(re.match(r"^-[A-Za-z]*[rR][A-Za-z]*$", a) or a in (
                    "--recursive", "--dereference-recursive",
                    "--directories=recurse") for a in args):
                return True
            if "-d" in args and "recurse" in args:
                return True
        elif nome == "ls":
            if any(re.match(r"^-[A-Za-z]*R", a) or a == "--recursive"
                   for a in args):
                return True
        elif nome == "cp":
            if any(re.match(r"^-[A-Za-z]*[rRa][A-Za-z]*$", a) or a in (
                    "--recursive", "--archive") for a in args):
                return True
        elif nome == "git":
            salta = False
            for a in args:
                if salta:
                    salta = False
                elif a in ("-C", "-c", "--git-dir", "--work-tree"):
                    salta = True
                elif not a.startswith("-"):
                    if a == "grep":
                        return True
                    break
    return False


def percorsi_richiesti(nome: str, ti: dict, cwd, nomi_semplici=False, env=None):
    """Tutti i percorsi che una chiamata di strumento vuole toccare, come
    `(testo, percorso_risolto, ricorsivo)`. `ricorsivo` e' vero per Grep e
    Glob: una ricerca che parte da una cartella entra in tutto quello che ci
    sta sotto, compresa una cartella vietata. Grep senza `path` cerca nella
    cwd. `env` e' l'ambiente del payload (se c'e'), per le variabili dei
    comandi Bash."""
    out = []
    corto = _nome_corto(nome)
    ricerca = corto in ("Grep", "Glob")

    # `Artifact` risolve i file sorgente rispetto a `root`, se c'e'.
    root = ti.get("root")
    base_file = _norm(root, cwd) if isinstance(root, str) and root else None

    def aggiungi(testo, ricorsivo=False, base=None):
        n = _norm(testo, base or cwd)
        if n:
            out.append((testo, n, ricorsivo))

    for k in CHIAVI_PERCORSO:
        v = ti.get(k)
        if isinstance(v, str) and v:
            aggiungi(v, ricerca and k == "path")
    for k in CHIAVI_LISTA_PERCORSI:
        v = ti.get(k)
        if isinstance(v, list):
            for x in v:
                if isinstance(x, str) and x:
                    aggiungi(x, base=base_file)
                elif isinstance(x, dict):
                    for kk in CHIAVI_PERCORSO:
                        if isinstance(x.get(kk), str) and x[kk]:
                            aggiungi(x[kk], base=base_file)
    # `files` come mappa {percorso pubblicato: sorgente} (Artifact): il valore
    # e' il file locale, stringa o {"from": ...}. Il percorso pubblicato (la
    # chiave) non e' un file locale. Un valore {"artifact", "path"} copia da
    # un altro artifact e non tocca il disco.
    fm = ti.get("files")
    if isinstance(fm, dict):
        for val in fm.values():
            src = val if isinstance(val, str) else (
                val.get("from") if isinstance(val, dict) else None)
            if isinstance(src, str) and src:
                aggiungi(src, base=base_file)
    if ricerca:
        pth = ti.get("path")
        base = pth if isinstance(pth, str) and pth else (cwd or os.getcwd())
        if not (isinstance(pth, str) and pth):
            aggiungi(base, True)
        pat = ti.get("pattern") if corto == "Glob" else None
        if isinstance(pat, str) and pat:
            if pat.startswith(("/", "~")):
                d = _prefisso_glob_dir(os.path.expanduser(pat))
                if d:
                    aggiungi(d, _ha_glob(pat))
            else:
                d = _prefisso_glob_dir(pat)
                if d:
                    aggiungi(os.path.join(os.path.expanduser(base), d), True)
    cmd = ti.get("command")
    if isinstance(cmd, str) and cmd:
        ric = _comando_ricorsivo(cmd)
        trovati = _percorsi_da_comando(cmd, cwd, nomi_semplici, env)
        for testo, n in trovati:
            # Una `/` da sola non e' un percorso da negare (`ls /`), salvo che
            # una ricerca ricorsiva parta proprio da li' (`find / -name x`).
            if n == "/" and not ric:
                continue
            out.append((testo, n, ric))
        if ric and cwd and not any(os.path.exists(n) for _, n in trovati):
            # Una ricerca senza una cartella o un file operando che esista
            # (`rg x`, `git grep x`) parte dalla cwd. Con un operando che
            # esiste (`grep -r x progetto`) parte da li', e la cwd non c'entra.
            # (`x`, il modello, non e' un percorso che esiste: risolto sulla
            # cwd non combacia con niente.)
            n = _norm(cwd)
            if n:
                out.append((cwd, n, True))
    return out


# --------------------------------------------------------------------------
# sessioni: da id a compartimento
# --------------------------------------------------------------------------

def _gruppo(nomi) -> list:
    return list(nomi) or [PREDEFINITO]


def _gruppo_da_tabella(chiave: str, ambito: Ambito, data_dir: str) -> list:
    """I gruppi di compartimenti delle sessioni che la tabella `sessions` di
    Plancia conosce sotto `chiave` (un `session_id` o un titolo), uno per
    sessione. Sola lettura (`mode=ro`), aperta solo qui per non pagare sqlite
    a ogni strumento. Un database bloccato o assente e' "nessuna riga"."""
    db = os.path.join(data_dir, "plancia.db")
    if not os.path.exists(db):
        return []
    try:
        import sqlite3
        from urllib.parse import quote
        try:
            conn = sqlite3.connect("file:%s?mode=ro" % quote(db), uri=True,
                                   timeout=0.3)
            conn.execute("SELECT 1 FROM sessions LIMIT 1")
        except sqlite3.OperationalError:
            # Misurato: con un database in WAL chiuso pulito (nessun file
            # -wal/-shm, cioe' Plancia non e' in esecuzione) un SQLite recente
            # non apre in `mode=ro` ("unable to open database file"). Senza un
            # -wal da leggere tutto e' nel file principale, e `immutable=1` e'
            # sicuro; con un -wal presente NON si ripiega (si perderebbero le
            # ultime scritture): la sessione resta "sconosciuta".
            if os.path.exists(db + "-wal"):
                raise
            conn = sqlite3.connect("file:%s?mode=ro&immutable=1" % quote(db),
                                   uri=True, timeout=0.3)
        try:
            righe = conn.execute(
                "SELECT cwd, file FROM sessions WHERE session_id=? LIMIT 1",
                (chiave,)).fetchall()
            if not righe and not _UUID.match(chiave):
                righe = conn.execute(
                    "SELECT cwd, file FROM sessions WHERE lower(title)=lower(?) "
                    "LIMIT 20", (chiave,)).fetchall()
        finally:
            conn.close()
    except Exception:  # noqa: BLE001 - un db illeggibile e' "nessuna riga"
        return []
    gruppi = []
    for cwd_raw, file_ in righe:
        cwd = _norm(cwd_raw) if cwd_raw else ""
        gruppi.append(_gruppo(_nomi_da_segnali(
            ambito, (), (cwd,), (_da_trascrizione(file_)[1],))))
    return gruppi


def compartimenti_sessione(chiave: str, ambito: Ambito, data_dir: str):
    """I compartimenti della sessione (o delle sessioni) che `chiave` indica:
    una lista di GRUPPI, uno per sessione trovata, ciascuno la lista dei nomi
    nominati a cui la sessione appartiene (`[PREDEFINITO]` se la conosce solo
    Plancia). `None` se non se ne trova nessuna (sconosciuta).

    `chiave` e' quello che gli strumenti veri mandano: un id `local_<uuid>`
    dell'app, un nome (il titolo della sessione), oppure un `session_id`
    dell'hook. Le fonti, tutte:

    1. `X.sessioni` (per `session_id` o per id `local_` come scritto);
    2. il registro dell'app (`_voci_app`): un id `local_` si traduce nel
       `cliSessionId`, e la cwd e la cartella di apertura di quella sessione
       danno l'appartenenza per cartella; un nome si cerca fra i titoli;
    3. la tabella `sessions` di Plancia (cwd e file della sessione), per un
       `session_id` o un titolo. Un id `local_` non ci compare mai.

    Con piu' sessioni dello stesso titolo valgono tutte: chi decide le vuole
    tutte compatibili."""
    gruppi = []
    diretto = _nomi_da_segnali(ambito, (chiave,))
    if diretto:
        gruppi.append(diretto)
    if chiave.startswith("local_"):
        voci = _voci_app(ambito.home, chiave=chiave)
    elif not _UUID.match(chiave):
        voci = _voci_app(ambito.home, titolo=chiave)
    else:
        voci = []
    for v in voci:
        gruppi.append(_gruppo(_nomi_da_segnali(
            ambito, (v["local"], v["cli"], chiave),
            (_norm(v["cwd"]), _norm(v["origine"])),
            (_codifica(os.path.expanduser(v["cwd"])) if v["cwd"] else "",
             _codifica(os.path.expanduser(v["origine"])) if v["origine"] else ""))))
    if not chiave.startswith("local_"):
        gruppi += _gruppo_da_tabella(chiave, ambito, data_dir)
    return gruppi or None


def _e_proprio(chiave: str, chi: dict, ambito: Ambito) -> bool:
    """`chiave` indica la sessione che chiama (o la sua madre).

    Oltre agli id dell'hook: `self`, che gli strumenti di sessione accettano
    per "questa sessione"; `main`, che un subagente usa per parlare alla
    sessione che l'ha lanciato (e' il modo documentato di SendMessage); e un id
    `local_` il cui `cliSessionId` e' quello di chi chiama."""
    mie = (chi["sessione"], chi["madre"])
    if chiave in mie or chiave == "self":
        return True
    if chiave == "main" and chi["subagente"]:
        return True
    if chiave.startswith("local_"):
        return any(v["cli"] and v["cli"] in mie
                   for v in _voci_app(ambito.home, chiave=chiave))
    return False


def _agente_proprio(chiave: str, chi: dict) -> bool:
    """`chiave` e' un subagente della sessione che chiama (un file
    `<madre>/subagents/agent-<chiave>.jsonl`): un nominato deve poter scrivere
    ai propri subagenti."""
    prog, madre = chi["cartella_progetto"], chi["madre"]
    if not (prog and madre) or "/" in chiave or chiave in ("", ".", ".."):
        return False
    pieno = chiave if chiave.startswith("agent-") else "agent-" + chiave
    return os.path.exists(os.path.join(prog, madre, "subagents", pieno + ".jsonl"))


# --------------------------------------------------------------------------
# la decisione
# --------------------------------------------------------------------------

def _stringhe(ti, chiavi):
    return [ti[k] for k in chiavi if isinstance(ti.get(k), str) and ti[k]]


def _nome_corto(tool: str) -> str:
    return tool.split("__")[-1] if tool.startswith("mcp__") else tool


def _env_payload(payload: dict):
    """L'ambiente del payload, se l'hook ne riceve uno (un dizionario di
    stringhe): serve a espandere le variabili di un comando Bash. Nessun hook
    di Claude Code lo manda, per quanto si e' visto: senza, le variabili si
    espandono con l'ambiente dell'hook e una non definita si ignora."""
    e = payload.get("env")
    if not isinstance(e, dict):
        return None
    return {k: v for k, v in e.items() if isinstance(k, str) and isinstance(v, str)}


def valuta(payload: dict, ambito: Ambito, chi: dict, data_dir: str):
    """La prima violazione di una chiamata, o None se e' ammessa. Torna
    `{"bersaglio", "motivo", "proprietario"}`."""
    nome = payload.get("tool_name")
    ti = payload.get("tool_input")
    if not isinstance(nome, str) or not nome:
        return None
    if not isinstance(ti, dict):
        ti = {}
    nominato = bool(chi["nomi"])
    mio = ",".join(chi["nomi"]) if nominato else PREDEFINITO

    # 0) i file del guardiano stesso: nessuna sessione li modifica
    v = _valuta_protetti(nome, ti, ambito, chi, data_dir, mio, _env_payload(payload))
    if v:
        return v
    # 1) sessioni: strumenti dell'app che leggono o scrivono altre sessioni
    v = _valuta_sessioni(nome, ti, ambito, chi, data_dir, mio)
    if v:
        return v
    # 2) Drive
    v = _valuta_drive(nome, ti, ambito, chi, mio)
    if v:
        return v
    # 3) comandi vietati (predefinito): rami git condivisi e simili
    cmd = ti.get("command")
    if not nominato and isinstance(cmd, str):
        for s in ambito.comandi_vietati:
            if s in cmd:
                return {"bersaglio": s, "proprietario": "un compartimento nominato",
                        "motivo": "compartimento %s: il comando nomina %r, che "
                                  "appartiene a un compartimento nominato" % (mio, s)}
    # 3b) un nominato con la cwd fuori dai suoi permessi: ogni comando parte da
    # li' e legge la cwd con parole senza barre (`cat nota.txt`, `ls`,
    # `grep -r x .`, `head *`) che l'estrazione dei percorsi non vede. La cwd e'
    # quindi un percorso toccato da ogni comando: se sta fuori, il comando si
    # nega e si dice come rientrare. (Una sessione e' di un nominato "solo per
    # id" proprio quando e' aperta fuori dalle sue cartelle: e' il caso normale.)
    if nominato and isinstance(cmd, str) and chi["cwd"]:
        v = _percorso_nominato(chi["cwd"], chi, ambito, mio)
        if v:
            cartelle = [f for n in chi["nomi"] for f in ambito.nominati[n]["cartelle"]]
            return {"bersaglio": chi["cwd"], "proprietario": v["proprietario"],
                    "motivo": "compartimento %s: la cartella di lavoro %s e' fuori "
                              "dai permessi di %s, e un comando da li' leggerebbe "
                              "file fuori dai permessi: sposta la sessione con "
                              "change_directory in una cartella del compartimento "
                              "(%s)" % (mio, chi["cwd"], mio,
                                        ", ".join(cartelle) or "nessuna configurata")}
    # 4) percorsi
    for testo, p, ricorsivo in percorsi_richiesti(nome, ti, chi["cwd"] or None,
                                                  nomi_semplici=not nominato,
                                                  env=_env_payload(payload)):
        if nominato:
            v = _percorso_nominato(p, chi, ambito, mio)
        else:
            v = _percorso_predefinito(p, ricorsivo, ambito, mio)
        if v:
            return v
    return None


# Le chiavi di config.json che tengono acceso o configurano il guardiano.
CHIAVI_GUARDIANO = ("guardiano", "compartimenti", "strumenti_drive")

# Scritture "per altre vie" dentro il codice di un interprete
# (`python3 -c "open(f, 'w')"`, `Path(f).write_text`, `os.remove`, `shutil`,
# `fs.writeFileSync`, `config.save_config`, ...): se il testo nomina un file del
# guardiano E ha uno di questi segni, e' una scrittura. `json.load(open(f))` no.
_RX_CODICE_SCRIVE = re.compile(
    r"write|dump\(|os\.(?:replace|rename|remove|unlink|truncate|link|symlink)"
    r"|unlink|rmtree|shutil|truncate|save_config|appendFile|File\.open"
    r"""|open\([^)]*,\s*['"][wax+]|mode\s*=\s*['"][wax+]""", re.I)
_RX_SED_SUL_POSTO = re.compile(r"^(?:-[A-Za-z]*i|--in-place)")

_MOTIVO_A_MANO = ("le impostazioni del guardiano le cambia il proprietario della "
                  "macchina a mano, fuori da una sessione")


def _protetti(ambito: Ambito, data_dir: str) -> list:
    """I file che tengono in piedi il guardiano: la config, la copia
    dell'ultima valida, il registro, il manifesto dei divieti, l'hook e questo
    modulo. Un agente fermato dal guardiano non deve poterlo spegnere da solo."""
    qui = os.path.realpath(__file__)
    elenco = [os.path.join(data_dir, "config.json"), _percorso_copia(data_dir),
              _percorso_registro(data_dir), _percorso_registro(data_dir) + ".1",
              os.path.join(os.path.dirname(os.path.dirname(qui)), "bin",
                           "plancia-guardiano"),
              qui]
    if ambito.manifesto:
        elenco.append(os.path.expanduser(ambito.manifesto))
    return [n for n in (_norm(p) for p in elenco) if n]


def _operandi(s: dict) -> list:
    """Gli argomenti di un segmento che non sono opzioni, redirezioni ne' i
    loro bersagli (i file su cui il comando opera)."""
    out, prec = [], ""
    for t in s["token"][1:] if s["token"] and s["token"][0] == s["nome"] else s["args"]:
        if _punt(t):
            prec = t
            continue
        redir = bool(prec)
        prec = ""
        if redir or not t or (t.startswith("-") and len(t) > 1):
            continue
        out.append(t)
    return out


def _cli_config_guardiano(s: dict):
    """La chiave del guardiano che un segmento imposta con la CLI di Plancia
    (`plancia config guardiano spento`, `python3 -m plancia.cli config ...`,
    `python3 bin/plancia config ...`), o None. Senza un valore e' una lettura."""
    nome, args = s["nome"], s["args"]
    resto = None
    if nome == "plancia":
        resto = args
    elif _e_interprete(nome):
        for k, a in enumerate(args):
            if a == "-m" and k + 1 < len(args) and args[k + 1] in (
                    "plancia.cli", "plancia", "plancia.__main__"):
                resto = args[k + 2:]
                break
            if not a.startswith("-"):
                base = os.path.basename(a)
                if base == "plancia" or (base == "cli.py" and os.path.basename(
                        os.path.dirname(a)) == "plancia"):
                    resto = args[k + 1:]
                break
    if resto is None:
        return None
    parole = [a for a in resto if not _punt(a) and not a.startswith("-")]
    if len(parole) >= 3 and parole[0] == "config" and parole[1] in CHIAVI_GUARDIANO:
        return parole[1]
    return None


def _scrive_un_protetto(cmd: str, cwd, protetti: set, env=None):
    """`(bersaglio, come)` se il comando Bash scrive, cancella o sposta un file
    del guardiano, o imposta una sua chiave con la CLI; altrimenti None.

    EURISTICO, dichiarato: chi vuole aggirarlo ci riesce (un percorso costruito a
    pezzi dentro uno script). Chiude il caso ordinario: `plancia config guardiano
    spento`, `sed -i`, `tee`, una redirezione, `cp x config.json`, `python3 -c`
    che scrive il file, `rm`/`mv` del file o della cartella che lo contiene. La
    lettura e' ammessa."""
    an = _analizza(cmd)

    def protetto(x):
        """Il file protetto a cui punta `x` (anche con un glob di shell), o None."""
        x = _espandi_var(x, env)
        if not x:
            return None
        for cand in [x] + _espandi_glob(x, cwd):
            n = _norm(cand, cwd)
            if n and n.lower() in protetti:
                return n
        return None

    def contiene(x):
        """Un file protetto che sta dentro la cartella `x` (o e' `x`)."""
        x = _espandi_var(x, env)
        n = _norm(x, cwd) if x else ""
        return n if n and any(_dentro(p, n) for p in protetti) else None

    def destinazione(operandi):
        """Il file protetto che un `cp`/`mv`/`install`/`rsync` scrive: l'ultimo
        operando, o (se e' una cartella) la cartella piu' il nome di ogni sorgente."""
        if not operandi:
            return None
        ultimo = operandi[-1]
        v = protetto(ultimo)
        if v:
            return v
        u = _espandi_var(ultimo, env)
        dest = _norm(u, cwd) if u else ""
        if len(operandi) >= 2 and dest and (ultimo.endswith("/") or os.path.isdir(dest)):
            for src in operandi[:-1]:
                n = _norm(os.path.join(dest, os.path.basename(src.rstrip("/"))))
                if n and n.lower() in protetti:
                    return n
        return None

    codice = False
    for s in an["segmenti"]:
        nome = s["nome"]
        # 1) la CLI di Plancia
        chiave = _cli_config_guardiano(s)
        if chiave:
            return chiave, "cli"
        if _e_interprete(nome):
            codice = True
        # 2) redirezioni: `> file`, `>> file`, `>| file`
        prec = ""
        for t in s["token"]:
            if _punt(t):
                prec = t
                continue
            if ">" in prec and "<" not in prec and not prec.endswith("&"):
                v = protetto(t)
                if v:
                    return v, "scrive"
            prec = ""
        op = _operandi(s)
        n = nome.lower()
        if n in ("tee", "truncate", "rm", "chmod", "chown", "ed", "ex", "vi", "vim",
                 "nano", "emacs", "sponge", "unlink", "shred", "mv"):
            for x in op:
                v = protetto(x)
                if v:
                    return v, "scrive"
            if n == "mv":
                v = destinazione(op)
                if v:
                    return v, "scrive"
            if n in ("rm", "mv", "unlink", "shred"):
                for x in op[:-1] if n == "mv" else op:
                    v = contiene(x)
                    if v:
                        return v, "scrive"
        elif n in ("sed", "perl") and any(_RX_SED_SUL_POSTO.match(a) for a in s["args"]):
            for x in op:
                v = protetto(x)
                if v:
                    return v, "scrive"
        elif n in ("cp", "install", "rsync", "ln"):
            v = destinazione(op)
            if v:
                return v, "scrive"
        elif n == "dd":
            for a in s["args"]:
                if a.startswith("of="):
                    v = protetto(a[3:])
                    if v:
                        return v, "scrive"
    # 3) codice dato a un interprete: nomina un file del guardiano E scrive
    if codice:
        testi = [t for s in an["segmenti"] if _e_interprete(s["nome"]) for t in s["args"]]
        testi += an["corpi"]
        if "save_config" in cmd:
            return "config.save_config", "cli"
        for t in testi:
            if _RX_CODICE_SCRIVE.search(t):
                for c in _trova_percorsi_in_testo(t):
                    v = protetto(c)
                    if v:
                        return v, "scrive"
    return None


def _valuta_protetti(nome, ti, ambito, chi, data_dir, mio, env=None):
    """Scrivere (o cancellare, o spostare) un file del guardiano, o cambiarne le
    impostazioni con la CLI di Plancia (`plancia config guardiano ...`), e'
    negato a TUTTE le sessioni, predefinito compreso. Leggere resta ammesso. Con
    Bash e' euristico (vedi `_scrive_un_protetto`). Vale solo in `bloccante`,
    come ogni diniego: chi vuole cambiare la config con l'aiuto di una sessione
    deve prima passare a `solo-registro`, o cambiarla a mano."""
    corto = _nome_corto(nome)
    cwd = chi["cwd"] or None
    cmd = ti.get("command")
    scrittura = corto in STRUMENTI_SCRITTURA
    if not scrittura and not (isinstance(cmd, str) and cmd):
        return None     # nessuno strumento che scrive e nessun comando: niente da guardare
    protetti = {p.lower() for p in _protetti(ambito, data_dir)}
    if scrittura:
        for k in ("file_path", "notebook_path", "path"):
            if isinstance(ti.get(k), str):
                n = _norm(ti[k], cwd)
                if n and n.lower() in protetti:
                    return {"bersaglio": n, "proprietario": "il guardiano",
                            "motivo": "compartimento %s: %s e' un file del guardiano "
                                      "dei compartimenti: %s" % (mio, n, _MOTIVO_A_MANO)}
        return None
    r = _scrive_un_protetto(cmd, cwd, protetti, env)
    if not r:
        return None
    bersaglio, come = r
    if come == "cli":
        return {"bersaglio": bersaglio, "proprietario": "il guardiano",
                "motivo": "compartimento %s: il comando imposta la chiave %r di "
                          "config.json, che governa il guardiano dei compartimenti: %s"
                          % (mio, bersaglio, _MOTIVO_A_MANO)}
    return {"bersaglio": bersaglio, "proprietario": "il guardiano",
            "motivo": "compartimento %s: %s e' un file del guardiano dei "
                      "compartimenti: %s" % (mio, bersaglio, _MOTIVO_A_MANO)}


def _percorso_nominato(p, chi, ambito, mio):
    """Un percorso contro i permessi di TUTTI i compartimenti della sessione
    (di solito uno)."""
    for nome in chi["nomi"]:
        c = ambito.nominati[nome]
        if any(_dentro(p, f) for f in c["cartelle"]):
            continue
        if any(_dentro(p, n) for n in ambito.neutri()):
            continue
        if _scratch_ok(p, chi, ambito):
            continue
        if _progetto_ok(p, chi, _codifica_di_x(chi["codificata"].lower(), c)):
            continue
        prop = ambito.proprietario_percorso(p) or ambito.proprietario_specchio(p)
        if prop is None and _e_temporaneo(p, ambito):
            return {"bersaglio": p, "proprietario": "nessuno",
                    "motivo": "compartimento %s: %s e' nella cartella temporanea "
                              "condivisa, che non e' di nessun compartimento ma che "
                              "un compartimento nominato non usa (e' un posto dove "
                              "passarsi file): usa la sua cartella di sessione in "
                              "/private/tmp/claude-%s/ (fuori dai permessi di %s)"
                              % (mio, p, ambito.uid, nome)}
        if prop is None and p == "/":
            return {"bersaglio": p, "proprietario": "nessuno",
                    "motivo": "compartimento %s: la radice del disco non e' di nessun "
                              "compartimento ma e' fuori dai permessi di %s"
                              % (mio, nome)}
        prop = prop or PREDEFINITO
        return {"bersaglio": p, "proprietario": prop,
                "motivo": "compartimento %s: %s appartiene a %s (fuori dai "
                          "permessi di %s)" % (mio, p, prop, nome)}
    return None


_TEMPORANEI = ("/tmp", "/private/tmp", "/var/tmp", "/private/var/tmp",
               "/var/folders", "/private/var/folders")


def _e_temporaneo(p: str, ambito: Ambito) -> bool:
    """`p` sta in una cartella temporanea condivisa (`/tmp` e la TMPDIR per
    utente di macOS): non e' di nessun compartimento."""
    return any(_dentro(p, t) or _dentro(p, _norm(t)) for t in _TEMPORANEI)


def _divieto(p, mio, extra=""):
    return {"bersaglio": p, "proprietario": "un compartimento nominato",
            "motivo": "compartimento %s: %s appartiene a un compartimento "
                      "nominato%s" % (mio, p, (" (" + extra + ")") if extra else "")}


_RICERCA_INCLUDE = "la ricerca include un percorso vietato: restringi il percorso"


def _percorso_predefinito(p, ricorsivo, ambito, mio):
    """Un percorso contro i divieti del predefinito. Una ricerca ricorsiva che
    parte da un antenato di un percorso vietato lo include: negata."""
    for nome, c in ambito.nominati.items():
        for f in c["cartelle"]:
            if _dentro(p, f):
                return {"bersaglio": p, "proprietario": nome,
                        "motivo": "compartimento %s: %s appartiene a %s"
                                  % (mio, p, nome)}
            if ricorsivo and _dentro(f, p):
                return {"bersaglio": p, "proprietario": nome,
                        "motivo": "compartimento %s: la ricerca in %s include %s, "
                                  "che appartiene a %s: restringi il percorso"
                                  % (mio, p, f, nome)}
    # Lo specchio delle cartelle dei nominati in `<claude>/projects`:
    # trascrizioni, memoria, cartelle di sessione e dei subagenti. E' lavoro
    # loro (i canali 5 e 7 della specifica) come le cartelle stesse.
    prop = ambito.proprietario_specchio(p)
    if prop:
        return {"bersaglio": p, "proprietario": prop,
                "motivo": "compartimento %s: %s (trascrizioni e memoria) appartiene "
                          "a %s" % (mio, p, prop)}
    if ricorsivo:
        prop = ambito.specchio_incluso(p)
        if prop:
            return {"bersaglio": p, "proprietario": prop,
                    "motivo": "compartimento %s: la ricerca in %s include le "
                              "trascrizioni e la memoria di %s sotto %s: restringi "
                              "il percorso" % (mio, p, prop, ambito.progetti)}
    for letterale, glob in ambito.divieti():
        if glob is None and "/" not in letterale:
            # un nome semplice (senza barre): vale come modello di nome
            if _combacia_glob(letterale, p):
                return _divieto(p, mio)
        elif glob is None:
            if _dentro(p, letterale):
                return _divieto(p, mio)
            if ricorsivo and _dentro(letterale, p):
                return _divieto(p, mio, _RICERCA_INCLUDE)
        else:
            if _combacia_glob(glob, p):
                return _divieto(p, mio)
            # Una ricerca che parte proprio dal prefisso letterale del modello
            # (`<cartella>/PR-*`, ricerca in `<cartella>`) include i file che
            # combaciano: negata anche con p == letterale.
            if ricorsivo and letterale and _dentro(letterale, p):
                return _divieto(p, mio, _RICERCA_INCLUDE)
    return None


def _valuta_sessioni(nome, ti, ambito, chi, data_dir, mio):
    nominato = bool(chi["nomi"])
    if nome == "ListAgents":
        if nominato:
            return {"bersaglio": "ListAgents", "proprietario": "altri compartimenti",
                    "motivo": "compartimento %s: ListAgents elenca sessioni di altri "
                              "compartimenti" % mio}
        return _misura(ambito, "ListAgents", mio)
    if nome == "SendMessage":
        a = ti.get("to")
        if not isinstance(a, str) or not a:
            if not nominato:
                return None
            return {"bersaglio": "SendMessage", "proprietario": "sconosciuto",
                    "motivo": "compartimento %s: SendMessage senza un destinatario "
                              "verificabile" % mio}
        return _sessione_bersaglio(
            a, ambito, chi, data_dir, mio,
            proprio=_e_proprio(a, chi, ambito) or _agente_proprio(a, chi))
    if not nome.startswith(PREFISSO_SESSIONI):
        return None
    corto = _nome_corto(nome)
    if corto in SESSIONI_RICERCA and ambito.nominati:
        # Anche con un filtro di sessione nel tool_input: la ricerca e' nel
        # contenuto delle trascrizioni, che sono lavoro dei compartimenti.
        return {"bersaglio": corto, "proprietario": "altri compartimenti",
                "motivo": "compartimento %s: %s cerca nelle trascrizioni di tutte "
                          "le sessioni, anche di un compartimento nominato" % (mio, corto)}
    ids = _stringhe(ti, CHIAVI_ID_SESSIONE)
    for k in CHIAVI_LISTA_SESSIONI:
        if isinstance(ti.get(k), list):
            ids += [x for x in ti[k] if isinstance(x, str) and x]
    if not ids:
        if nominato and corto not in SESSIONI_SENZA_BERSAGLIO_OK:
            return {"bersaglio": corto, "proprietario": "altri compartimenti",
                    "motivo": "compartimento %s: %s senza una sessione bersaglio "
                              "elenca o cerca fra sessioni di altri compartimenti"
                              % (mio, corto)}
        if corto in SESSIONI_DA_MISURARE:
            return _misura(ambito, corto, mio)
        return None
    for i in ids:
        v = _sessione_bersaglio(i, ambito, chi, data_dir, mio,
                                proprio=_e_proprio(i, chi, ambito))
        if v:
            return v
    return None


def _misura(ambito, strumento, mio):
    """Una chiamata che il predefinito puo' fare senza un bersaglio
    (`list_sessions`, `search_session_transcripts`, `ListAgents`): non si puo'
    negare (limite dichiarato nel docstring), ma se esistono compartimenti
    nominati si fa scrivere una riga in `solo-registro`, per sapere quanto si
    usa prima di decidere. Non nega mai, nemmeno in `bloccante`."""
    if not ambito.nominati:
        return None
    return {"bersaglio": strumento, "proprietario": "un compartimento nominato",
            "solo_misura": True,
            "motivo": "compartimento %s: %s cerca o elenca fra tutte le sessioni, "
                      "anche di un compartimento nominato (solo misura, non si "
                      "nega)" % (mio, strumento)}


def _sessione_bersaglio(chiave, ambito, chi, data_dir, mio, proprio):
    """La sessione `chiave` e' raggiungibile da chi chiama?

    Un nominato raggiunge solo sessioni che sono almeno dei suoi stessi
    compartimenti; una sessione sconosciuta e' negata. Il predefinito
    raggiunge le sessioni predefinite e quelle sconosciute (id sconosciuto:
    ammesso, come da specifica), non quelle di un nominato. `chiave` puo'
    indicare piu' sessioni (titolo ripetuto): tutte devono essere raggiungibili."""
    if proprio:
        return None
    nominato = bool(chi["nomi"])
    gruppi = compartimenti_sessione(chiave, ambito, data_dir)
    if gruppi is None:
        if not nominato:
            return None
        return {"bersaglio": chiave, "proprietario": "sconosciuto",
                "motivo": "compartimento %s: la sessione %s e' sconosciuta a un "
                          "compartimento nominato" % (mio, chiave)}
    for comp in gruppi:
        ok = set(chi["nomi"]) <= set(comp) if nominato else comp == [PREDEFINITO]
        if not ok:
            return {"bersaglio": chiave, "proprietario": ",".join(comp),
                    "motivo": "compartimento %s: la sessione %s appartiene a %s"
                              % (mio, chiave, ",".join(comp))}
    return None


def _valuta_drive(nome, ti, ambito, chi, mio):
    corto = _nome_corto(nome)
    if not nome.startswith("mcp__") or (
            corto not in ambito.strumenti_drive and nome not in ambito.strumenti_drive):
        return None
    ids = _stringhe(ti, CHIAVI_ID_DRIVE)
    for k in ("fileIds", "file_ids"):
        if isinstance(ti.get(k), list):
            ids += [x for x in ti[k] if isinstance(x, str) and x]
    if chi["nomi"]:
        if corto in STRUMENTI_DRIVE_ELENCO:
            return {"bersaglio": corto, "proprietario": "altri compartimenti",
                    "motivo": "compartimento %s: %s elenca tutto il Drive"
                              % (mio, corto)}
        if not ids:
            return {"bersaglio": corto, "proprietario": "sconosciuto",
                    "motivo": "compartimento %s: %s senza un id Drive verificabile"
                              % (mio, corto)}
        for i in ids:
            for n in chi["nomi"]:
                if i not in ambito.nominati[n]["drive_ids"]:
                    prop = next((k for k, c in ambito.nominati.items()
                                 if i in c["drive_ids"]), PREDEFINITO)
                    return {"bersaglio": i, "proprietario": prop,
                            "motivo": "compartimento %s: l'id Drive %s appartiene a "
                                      "%s (non e' fra i drive_ids di %s)"
                                      % (mio, i, prop, n)}
        return None
    for i in ids:
        for n, c in ambito.nominati.items():
            if i in c["drive_ids"]:
                return {"bersaglio": i, "proprietario": n,
                        "motivo": "compartimento %s: l'id Drive %s appartiene a %s"
                                  % (mio, i, n)}
    return None


# --------------------------------------------------------------------------
# l'hook
# --------------------------------------------------------------------------

def uscita_negata(motivo: str) -> str:
    """Il diniego di un PreToolUse, come JSON su stdout con uscita 0.

    Formato scelto: `hookSpecificOutput` con `hookEventName: "PreToolUse"`,
    `permissionDecision: "deny"` e `permissionDecisionReason`, l'uscita JSON
    strutturata dei PreToolUse di Claude Code: il motivo arriva a Claude come
    spiegazione del rifiuto. Il ripiego piu' vecchio (uscita 2 con il motivo
    su stderr) non serve: gli altri hook PreToolUse gia' in uso su questa
    macchina rifiutano con questo stesso formato JSON. NON e' stato provato
    dentro un Claude Code vero da questo lotto (la documentazione non era
    raggiungibile): le prove lanciano l'hook come sottoprocesso e leggono lo
    stdout."""
    return json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": motivo}}, ensure_ascii=False)


def hook(testo: str, data_dir: str) -> str:
    """Decide una chiamata di strumento. `testo` e' lo stdin dell'hook.
    Torna lo stdout da scrivere ("" = nessuna uscita = ammessa). Non solleva
    mai.

    Regola dei guasti: stdin vuoto o non JSON = ammessa. In `spento` e
    `solo-registro` qualunque eccezione = ammessa, niente output. In
    `bloccante` un'eccezione DOPO aver capito che chi chiama e' un nominato
    nega per prudenza (fail-closed per i nominati); prima di saperlo, o per il
    predefinito, ammette."""
    try:
        payload = json.loads(testo)
    except (ValueError, RecursionError, TypeError):
        return ""
    if not isinstance(payload, dict):
        return ""
    ev = payload.get("hook_event_name")
    if isinstance(ev, str) and ev and ev != "PreToolUse":
        return ""
    modo, chi, v = "spento", None, None
    try:
        cfg = carica(data_dir)
        modo = cfg["modo"]
        if modo == "spento":
            return ""
        if cfg["nota"] and _nota_config_dovuta(data_dir):
            sid = payload.get("session_id")
            scrivi_registro(data_dir, {
                "modalita": modo, "sessione": sid if isinstance(sid, str) else "",
                "compartimento": "", "strumento": "", "bersaglio": "",
                "motivo": cfg["nota"], "esito": "nota"})
        if not cfg["compartimenti"]:
            return ""
        ambito = Ambito(cfg["compartimenti"], cfg["strumenti_drive"],
                        data_dir=data_dir)
        chi = chiamante(payload, ambito)
        v = valuta(payload, ambito, chi, data_dir)
    except Exception as exc:  # noqa: BLE001 - un hook globale non rompe niente
        if modo == "bloccante" and chi is not None and chi["nomi"]:
            v = {"bersaglio": "", "proprietario": "",
                 "motivo": "compartimento %s: errore interno del guardiano (%s), "
                           "negato per prudenza" % (",".join(chi["nomi"]),
                                                    type(exc).__name__)}
        else:
            return ""
    if not v:
        return ""
    if v.get("solo_misura") and modo != "solo-registro":
        return ""
    blocca = modo == "bloccante" and not v.get("solo_misura")
    sid = payload.get("session_id")
    scrivi_registro(data_dir, {
        "modalita": modo, "sessione": sid if isinstance(sid, str) else "",
        "compartimento": ",".join(chi["nomi"]) if chi and chi["nomi"] else PREDEFINITO,
        "strumento": str(payload.get("tool_name") or ""),
        "bersaglio": v["bersaglio"], "motivo": v["motivo"],
        "esito": "negato" if blocca else "avrebbe-negato"})
    return uscita_negata(v["motivo"]) if blocca else ""
