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
  modulo, `plancia/__init__.py`, `plancia/config.py`, e ogni `.py` in `bin/` e nella
  radice del checkout da cui gira l'hook) non si modificano da nessuna sessione,
  e nemmeno le sue chiavi di config (`guardiano`, `compartimenti`,
  `strumenti_drive`) con la CLI di Plancia (`plancia config guardiano ...`,
  `python3 -m plancia.cli config ...`, `$(which plancia) config ...`,
  `config.save_config` o `main([...])` da un interprete): `_valuta_protetti`. Da
  Bash e' euristico (redirezioni, `tee`, `sed -i`, `cp`/`mv`/`install`/`rsync`
  verso il file, `rm`/`mv` del file o della cartella che lo contiene,
  `find -delete`/`-exec rm`, `chmod -R`, `curl -o`, `wget -O`, `tar x -C`,
  `unzip -d`, `git checkout` nella cartella dei dati, codice di un interprete
  che nomina il file o `.plancia`+`config.json` e scrive): un percorso costruito
  a pezzi dentro uno script non si vede, ne' un `git checkout` nel checkout
  stesso, ne' una copia in massa nella radice del checkout. Vale solo in
  `bloccante`, come ogni diniego: chi vuole cambiare la config con l'aiuto di
  una sessione deve prima passare a `solo-registro`. Anche `plancia config <chiave>`
  rifiuta di riscrivere un config.json che non si legge (uscita 2).
- I file `settings.json` e `settings.local.json` di Claude Code (di `~`, di
  `CLAUDE_CONFIG_DIR` e dei progetti, cioe' sotto una cartella `.claude`) sono
  protetti in modo MIRATO: Write/Edit/MultiEdit passano solo se il contenuto
  risultante non ha `disableAllHooks` a vero e, quando il file ha oggi la voce
  PreToolUse di `plancia-guardiano`, la ha ancora (lo stesso comando); Bash che
  li scrive e' negato con l'invito a usare Edit. Dedotto, non visto: l'effetto
  di `disableAllHooks` in un settings di progetto. Non coperti: `managed
  settings`, le variabili d'ambiente, l'app (`mcp__ccd_settings__*`), un
  `settings.json` cambiato prima che il guardiano fosse acceso.
- Il guardiano che non parte (il pacchetto non si importa, l'hook solleva) resta
  fail-open ma lascia una riga `guardiano-non-parte` nel registro e un
  `systemMessage` per l'utente (`bin/plancia-guardiano`); il pacchetto si carica
  senza mettere `bin/` ne' la radice sul `sys.path`.
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
- Le variabili di un comando (`cat $DIR/x`) si espandono con quelle assegnate
  nello stesso comando (`VAR=x; cat $VAR/f`, `export VAR=x`), poi con
  l'ambiente del payload, se ce n'e' uno (nessun hook di Claude Code lo manda,
  per quanto si e' visto), poi con quello dell'hook; una variabile non definita
  si ignora (un percorso che non si sa ricostruire non si risolve sulla cwd).
  Una `/` da sola non e' un percorso.
- La cartella si SIMULA lungo il comando: `cd X && cat f`, `cd X; cat f`,
  `pushd`, `popd`, una subshell fra parentesi (`(cd X; cat f)` non sposta niente
  dopo), e i percorsi relativi dei segmenti successivi si risolvono li'. Un `cd`
  relativo verso una cartella che non c'e' fallisce e non sposta (`cd comune;
  grep -r x .` cerca dove era); un `cd -`, un `cd` con una variabile non definita
  o dopo un `||` lasciano la cartella SCONOSCIUTA: un percorso relativo dopo si
  nega per prudenza (un nome semplice senza barre per il predefinito no: non si
  puo' dire se e' un file). Dedotto, non provato su una shell vera: un `cd` che
  fallisce in un `&&`.
- `echo` e `printf` stampano i loro argomenti e non toccano percorsi, MA solo se
  il testo non arriva a un comando che lo usa: fuori da una pipe, fuori da una
  sostituzione (`$(...)`, apici inversi: `f=$(echo x); cat $f`), e se scritto in
  un file non e' poi dato a un esecutore nello stesso comando (`echo 'cat x' >
  run.sh && bash run.sh`, `echo x > lista; xargs cat < lista`). Il corpo di un
  heredoc e' testo solo se lo riceve un comando che non esegue (`cat` verso un
  file o `git commit -F -`, anche dentro `git commit -m "$(cat <<EOF ...)"`); se
  lo riceve una shell, un interprete, `eval`, `source`, `xargs`, `ssh`, o se il
  comando che lo riceve manda l'output a una pipe verso un esecutore o a una
  sostituzione (`eval "$(cat <<EOF ...)"`), il suo contenuto si controlla come
  comando. Lo stesso vale per una here-string. Due comandi dati in due chiamate
  separate (uno scrive lo script, l'altro lo esegue) non si vedono.
- La cwd di un nominato aperto fuori dalle sue cartelle (per id) vale per ogni
  comando Bash (vedi `valuta`); al contrario una sessione del predefinito che
  entra per errore in una cartella di un nominato (`cd` persistente) diventa
  quel nominato e perde il proprio lavoro: e' la scelta dichiarata in
  `chiamante` (la cwd puo' solo aggiungere un'appartenenza).
- Cartelle ANNIDATE fra compartimenti (alfa in `/w/alfa`, beta in `/w/alfa/beta`):
  un percorso, una cwd, una cartella di apertura sono del nominato piu'
  SPECIFICO (per componenti, indipendentemente dall'ordine della config; la
  stessa regola di boa). Due nominati sulla STESSA cartella sono incerti: la
  sessione li' ha i permessi di entrambi (nessuno) e il percorso e' negato a
  tutti, con il motivo "assegnata a piu' di un compartimento". L'id della
  madre di un subagente, ricavato dal percorso del suo transcript, conta solo
  se quel file esiste davvero sotto `<claude>/projects` e la madre ha il suo
  transcript (dedotto: che a ogni chiamata di un subagente il file esista
  gia').
- Una ricerca ricorsiva con limite di profondita' (`find -maxdepth N`, `tree -L N`,
  `rg --max-depth N`, `fd -d N`) include una cartella vietata solo se ci arriva:
  `find . -maxdepth 1` non e' una ricerca illimitata. `du` (senza `-a`) non conta
  i nomi che un glob espande. Un url `file:` (WebFetch, i browser, `curl`) e' un
  percorso. Glob con un modello assoluto e senza `path` non usa la cwd.
- Gli strumenti di sessione senza id (`set_session_title`, `clear_session`, ...)
  restano negati a un nominato: lo schema non dice che senza id agiscano su di
  lei (solo `get_usage` lo dice); il motivo suggerisce `session_id: "self"`.
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
# Chiavi che portano un url: un `file:` e' un percorso (WebFetch, i browser).
CHIAVI_URL = ("url", "uri")

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


def _voci_app(home: str, chiave=None, titolo=None, cli=None) -> list:
    """Le sessioni del registro dell'app che corrispondono a un id `local_`
    (`chiave`) o a un titolo (senza distinzione di maiuscole). Il titolo
    costringe a leggere tutti i file del registro (poche centinaia): si fa
    solo per gli strumenti di sessione che ricevono un nome. Un id `local_`
    e' un solo file. Con `cli` (un `session_id` crudo, un uuid: il nome del
    `.jsonl`) si cerca il `cliSessionId`, e anche questo legge tutto il registro."""
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
        if cli is not None and v["cli"] != cli:
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
    non_parte = {"righe": 0, "ultima": None}
    for d in leggi_registro(data_dir, 100000):
        try:
            t = _epoch(d.get("ts"))
        except (ValueError, TypeError):
            continue
        if t < soglia:
            continue
        e = d.get("esito")
        if e == "guardiano-non-parte":
            # scritta da `bin/plancia-guardiano` quando il pacchetto non si
            # importa o l'hook solleva: il guardiano e' spento per tutti
            non_parte["righe"] += 1
            non_parte["ultima"] = {"ts": d.get("ts"), "motivo": d.get("motivo")}
            continue
        recenti[e if e in recenti else "altro"] += 1
    return {"modo": modo, "config": c["stato"], "errore": c["errore"],
            "usa_copia": bool(copia), "compartimenti": elenco,
            "registro_24h": recenti, "non_parte": non_parte}


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

    def proprietari_percorso(self, p: str) -> list:
        """I nomi dei nominati che possiedono `p`, col criterio del PIU'
        SPECIFICO: se le cartelle sono annidate (alfa in `/w/alfa`, beta in
        `/w/alfa/beta`) un percorso e' del nominato la cui cartella lo contiene
        con piu' componenti (per componenti, non per prefisso di stringa),
        qualunque sia l'ordine della config. Due nominati sulla STESSA cartella
        (config sbagliata) sono due nomi: chi decide tratta il percorso come
        incerto. Lista vuota se non e' di nessuno."""
        migliore, nomi = -1, []
        for nome, c in self.nominati.items():
            for f in c["cartelle"]:
                if _dentro(p, f):
                    d = _n_componenti(f)
                    if d > migliore:
                        migliore, nomi = d, [nome]
                    elif d == migliore and nome not in nomi:
                        nomi.append(nome)
        return nomi

    def proprietario_percorso(self, p: str):
        """Il nome del nominato che possiede `p` (il piu' specifico), o None. Con
        un percorso ambiguo (due nominati sulla stessa cartella) il primo:
        serve a dare un nome al diniego, non a decidere."""
        nomi = self.proprietari_percorso(p)
        return nomi[0] if nomi else None

    def proprietari_codifica(self, cod: str) -> list:
        """I nominati a cui appartiene una cartella di apertura CODIFICATA sotto
        `<claude>/projects` (`<enc>` o `<enc>-...`), col criterio del piu'
        specifico: vince la codifica piu' lunga. La codifica perde la differenza
        fra `/` e `-`, quindi `alfa-2` (sorella di `alfa`) risulta di alfa, e
        `alfa-beta` di un nominato che ha `alfa/beta`: in dubbio si confina. Due
        nominati con la stessa codifica sono due nomi."""
        cod = (cod or "").lower()
        migliore, nomi = -1, []
        if not cod:
            return nomi
        for nome, c in self.nominati.items():
            for e in c["codifiche"]:
                if cod == e or cod.startswith(e + "-"):
                    if len(e) > migliore:
                        migliore, nomi = len(e), [nome]
                    elif len(e) == migliore and nome not in nomi:
                        nomi.append(nome)
        return nomi

    def proprietario_specchio(self, p: str):
        """Il nome del nominato a cui appartiene `p` come SPECCHIO di una sua
        cartella sotto `<claude>/projects`: le trascrizioni, la memoria, le
        cartelle di sessione e dei subagenti di una cartella di X e delle sue
        discendenti sono lavoro di X. None se `p` non e' li' sotto o non e' di
        nessun nominato. Il confine e' il trattino: `<enc>` e `<enc>-...`
        (una discendente), non `<enc>altro` (una sorella con lo stesso inizio).
        Ma la codifica perde la differenza fra `/` e `-`, quindi una sorella
        `alfa-2` di `alfa` risulta di alfa: in dubbio si nega (vedi
        `proprietari_codifica`)."""
        if not p or not self.progetti or not _dentro(p, self.progetti):
            return None
        resto = p[len(self.progetti):].strip("/")
        if not resto:
            return None
        nomi = self.proprietari_codifica(resto.split("/")[0])
        return nomi[0] if nomi else None

    def specchio_incluso(self, p: str, ric=True):
        """Il nome di un nominato (con almeno una cartella) il cui specchio in
        `<claude>/projects` sta dentro `p` o e' `p` stessa: una ricerca ricorsiva
        che parte da `p` (`projects`, `~/.claude`, `~`) lo leggerebbe. `ric` e'
        il limite di profondita' della ricerca (True: nessuno). None se non ce
        n'e'."""
        if not p or not self.progetti or not _dentro(self.progetti, p):
            return None
        # la cartella di un nominato sta un livello sotto `projects`
        if not _ric(ric, _prof(self.progetti, p) + 1):
            return None
        for nome, c in self.nominati.items():
            if c["codifiche"]:
                return nome
        return None


def _n_componenti(p: str) -> int:
    return len([x for x in p.split("/") if x])


def _prof(f: str, p: str) -> int:
    """Quanti livelli sotto `p` sta `f` (0 se e' `p`); `f` deve stare dentro `p`."""
    return _n_componenti(f) - _n_componenti(p)


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

def _da_trascrizione(tp, claude_dir=None):
    """`(id_madre, cartella_codificata, cartella_progetto)` da un
    `transcript_path`.

    Una sessione: `<progetti>/<codificata>/<id>.jsonl`. Un subagente:
    `<progetti>/<codificata>/<id madre>/subagents/[workflows/<x>/]agent-...
    .jsonl`: l'id della madre e' il componente che precede `subagents`. Un id
    ricavato da un percorso e' una AFFERMAZIONE di chi lo scrive, non un fatto:
    per un subagente conta solo se il file esiste davvero (realpath) dentro
    `<claude>/projects`, nella forma `<codificata>/<madre>/subagents/...`, e
    se esiste anche la trascrizione della madre (`<codificata>/<madre>.jsonl`)
    (`_madre_verificata`, stessa regola di boa). Senza `claude_dir` non si
    verifica (le funzioni che leggono una riga della tabella di Plancia)."""
    if not isinstance(tp, str) or not tp:
        return "", "", ""
    parti = tp.replace("\\", "/").split("/")
    if "subagents" in parti:
        i = parti.index("subagents")
        madre = parti[i - 1] if i >= 1 else ""
        codificata = parti[i - 2] if i >= 2 else ""
        progetto = "/".join(parti[:i - 1]) if i >= 2 else ""
        if claude_dir is not None and not _madre_verificata(tp, claude_dir):
            madre = ""
        return madre, codificata, progetto
    nome = parti[-1]
    madre = nome[:-6] if nome.endswith(".jsonl") else nome
    codificata = parti[-2] if len(parti) >= 2 else ""
    return madre, codificata, "/".join(parti[:-1])


def _madre_verificata(tp: str, claude_dir: str) -> bool:
    """Il transcript di un subagente esiste davvero sotto `<claude>/projects`
    e la madre ha il suo transcript."""
    try:
        reale = os.path.realpath(tp)
        if not os.path.isfile(reale):
            return False
        base = os.path.realpath(os.path.join(claude_dir, "projects"))
        if not reale.startswith(base + os.sep):
            return False
        rel = reale[len(base) + 1:].split(os.sep)
        if len(rel) < 4 or not rel[0] or not rel[1] or rel[2] != "subagents":
            return False
        return os.path.isfile(os.path.join(base, rel[0], rel[1] + ".jsonl"))
    except (OSError, ValueError):
        return False


def _nomi_da_segnali(ambito: Ambito, ids=(), cwds=(), codifiche=()) -> list:
    """I nomi dei compartimenti nominati a cui puntano i segnali: un id in
    `sessioni`, una cwd dentro le cartelle, una cartella di apertura
    codificata. Ne basta uno per compartimento (prudenza). Fra le cartelle
    annidate un segnale di cartella (cwd o codifica) vale per il nominato piu'
    specifico, non per quelli che la contengono soltanto: una sessione in
    `/w/alfa/beta/x` e' di beta, una in `/w/alfa/y` e' di alfa. Due nominati che
    elencano la stessa cartella sono tutti e due: la sessione e' incerta e ha i
    permessi di entrambi, cioe' quasi nessuno."""
    ids = {x for x in ids if x}
    nomi = set()
    for nome, c in ambito.nominati.items():
        if ids & c["sessioni"]:
            nomi.add(nome)
    for cw in cwds:
        if cw:
            nomi.update(ambito.proprietari_percorso(cw))
    for cod in codifiche:
        if cod:
            nomi.update(ambito.proprietari_codifica(cod))
    return sorted(nomi)


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

    Con cartelle ANNIDATE fra compartimenti (alfa in `/w/alfa`, beta in
    `/w/alfa/beta`) i segnali 2 e 3 valgono per il nominato piu' SPECIFICO, per
    componenti di percorso e indipendentemente dall'ordine della config (la
    stessa regola di boa); due nominati sulla stessa cartella valgono tutti e
    due (la sessione e' incerta: ha i permessi di entrambi, cioe' quasi
    nessuno). L'id della madre ricavato dal percorso di un subagente conta solo
    se il suo transcript esiste davvero sotto `projects` e la madre ha il suo
    (`_madre_verificata`): un percorso inventato non e' un id.

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
    madre, codificata, progetto = _da_trascrizione(payload.get("transcript_path"),
                                                   ambito.claude_dir)
    cwd_raw = payload.get("cwd")
    cwd = _norm(cwd_raw) if isinstance(cwd_raw, str) and cwd_raw else ""
    nomi = _nomi_da_segnali(ambito, (sid, madre), (cwd,), (codificata,))
    tp = payload.get("transcript_path")
    subagente = bool(payload.get("agent_id")) or (
        isinstance(tp, str) and "/subagents/" in tp.replace("\\", "/"))
    return {"nomi": nomi, "sessione": sid or madre, "madre": madre,
            "codificata": codificata, "cartella_progetto": progetto,
            "da_codifica": ambito.proprietari_codifica(codificata),
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
# ATTENZIONE: l'eccezione vale SOLO se il loro testo non arriva a un altro
# comando (una pipe, una sostituzione, un file che poi si esegue): vedi
# `_analizza`.
_MUTI = ("echo", "printf")
_PUNTEGGIATURA = frozenset("();<>|&")
# Chi riceve un testo (un heredoc, una pipe) e lo USA: una shell, un
# interprete, un comando che ne legge i percorsi (`xargs`, `read`), una parola
# chiave di ciclo. Il testo che arriva a uno di questi si controlla come comando.
_ESECUTORI = frozenset(_SHELL + (
    "eval", "source", ".", "ssh", "parallel", "while", "for", "until", "do",
    "done", "then", "else", "elif", "if", "read", "mapfile", "readarray", "exec",
    "watch", "script", "{", "case", "select", "coproc"))
# Interpreti di codice che si danno ANCHE come heredoc (`awk -f - <<EOF`,
# `sqlite3 <<EOF`): non si cercano nei loro argomenti (`awk '/x/'` non ha
# percorsi), ma il corpo di un heredoc si.
_RX_CODICE_HD = re.compile(r"^(?:awk|gawk|mawk|nawk|sqlite3?|psql|expect|tclsh)$", re.I)
# La cartella di un segmento quando non si sa (un `cd -`, una destinazione con
# una variabile non definita): un percorso relativo li' non si sa dove porta.
_IGNOTA = "\x00cwd-ignota"


def _e_interprete(nome: str) -> bool:
    return bool(_RX_INTERPRETE.match(nome or ""))


def _e_codice(nome: str) -> bool:
    return _e_interprete(nome) or bool(_RX_CODICE_HD.match(nome or ""))


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
# comando si scompone cosi': (1) i corpi degli heredoc si tolgono dal testo e si
# tengono a parte, legati al comando che li riceve (un segnaposto `<<\x01N\x01`
# al posto del delimitatore); (2) segmenti separati da `;`, `&&`, `||`, `|`, a
# capo, parentesi (con le virgolette rispettate), ognuno con il separatore che
# lo segue; (3) ogni segmento in token con `shlex`; (4) lungo i segmenti si
# SIMULANO la cartella (`cd`, `pushd`, `popd`, subshell fra parentesi) e le
# variabili (`VAR=x`, `export VAR=x`), cosi' un percorso relativo si risolve
# dove il comando lo leggerebbe davvero; (5) le sostituzioni `$(...)` e `` `...` ``,
# il testo di `sh -c` e di `eval`, e i testi che arrivano a un esecutore (un
# heredoc dato a una shell, un `echo ... | sh`) si analizzano di nuovo, a parte.
# Se le virgolette non tornano si ripiega su uno split per spazi.
#
# Il testo di `echo`/`printf` e il corpo di un heredoc sono INERTI (non si
# guardano) solo se non arrivano a un comando che li usa: `echo $HOME`,
# `cat <<EOF > file`, `git commit -m "$(cat <<EOF ...)"`. Se escono in una pipe,
# o in una sostituzione, o li riceve una shell o un interprete, si controllano
# come comandi. Un testo scritto in un file (`echo ... > f`) e poi dato a un
# esecutore nello stesso comando (`bash f`, `xargs cat < f`, `. f`) si controlla.

_RX_HEREDOC = re.compile(
    r"<<(-?)[ \t]*(?:'([^'\n]*)'|\"([^\"\n]*)\"|\\?([A-Za-z_][A-Za-z_0-9.-]*))")
_RX_MARCA_HD = re.compile(r"^\x01(\d+)\x01$")
_RX_WHICH = re.compile(
    r"\$\(\s*(?:which|command\s+-v|type\s+-p|whence)\s+([A-Za-z0-9_./-]+)\s*\)"
    r"|`\s*(?:which|command\s+-v)\s+([A-Za-z0-9_./-]+)\s*`")
_CACHE_ANALISI = {}
_CONTATORE = [0]


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
_RX_ASSEGNA = re.compile(r"^[A-Za-z_]\w*=")


def _spezza(tok):
    """`(prefissi, assegnazioni, primo_token, nome, argomenti)` di un segmento,
    dopo i prefissi (`sudo`, `env`, `xargs`, `VAR=x`, opzioni dei prefissi...).
    `nome` e' senza cartella; vuoto se il segmento e' solo assegnazioni."""
    t = list(tok)
    pre, ass = [], []
    while t and (t[0] in _PREFISSI_COMANDO or re.match(r"^\w+=", t[0])
                 or (t[0].startswith("-") and len(t) > 1)
                 or _punt(t[0])):
        if t[0] in _PREFISSI_COMANDO:
            pre.append(t[0])
        elif _RX_ASSEGNA.match(t[0]):
            ass.append(t[0])
        t = t[1:]
    if not t:
        return pre, ass, "", "", []
    return pre, ass, t[0], os.path.basename(t[0]), t[1:]


def _nome_e_args(tok) -> tuple:
    """Il nome del comando (senza cartella) e i suoi argomenti."""
    _, _, _, nome, args = _spezza(tok)
    return nome, args


def _togli_heredoc(cmd: str, hd=None):
    """`(testo, heredoc)`. Il corpo di ogni heredoc si toglie dal testo e si
    tiene in `heredoc[N]` (`{"corpo", "quotato"}`); il delimitatore diventa il
    segnaposto `\\x01N\\x01`, cosi' `_analizza` lo lega al segmento che lo
    riceve. Non si decide qui se e' testo o comandi: dipende da chi lo riceve."""
    hd = [] if hd is None else hd
    if "<<" not in cmd:
        return cmd, hd
    out, attesa = [], []
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
            for idx, delim in attesa:
                righe = []
                while i < n:
                    j = cmd.find("\n", i)
                    j = n if j == -1 else j
                    riga = cmd[i:j]
                    i = j + 1
                    if riga.strip() == delim:
                        break
                    righe.append(riga)
                hd[idx]["corpo"] = "\n".join(righe)
            attesa = []
            continue
        if c == "<" and cmd.startswith("<<", i) and not cmd.startswith("<<<", i):
            m = _RX_HEREDOC.match(cmd, i)
            if m:
                delim = next((g for g in m.group(2, 3, 4) if g is not None), "")
                quotato = m.group(2) is not None or m.group(3) is not None or (
                    "\\" in m.group(0))
                hd.append({"corpo": "", "quotato": quotato})
                attesa.append((len(hd) - 1, delim))
                out.append("<<\x01%d\x01" % (len(hd) - 1))
                i = m.end()
                continue
        out.append(c)
        i += 1
    return "".join(out), hd


def _dividi_segmenti(t: str) -> list:
    """Il testo diviso ai `;`, `&&`, `||`, `|`, `|&`, `&`, a capo e alle
    parentesi che non sono dentro virgolette, `$(...)` o apici inversi. `>&`,
    `&>` e `>|` non dividono. Torna `("seg", testo, separatore_dopo)` (il
    separatore e' "" alla fine) e `("(",)` / `(")",)` per le parentesi."""
    out, cur = [], []
    q, sub, bt, i, n = None, 0, False, 0, len(t)

    def chiudi(dopo):
        s = "".join(cur).strip()
        del cur[:]
        if s:
            out.append(("seg", s, dopo))
        elif dopo and out and out[-1][0] == "seg" and out[-1][2] in ("", "\n", ";"):
            # un separatore piu' forte dopo uno debole (`a\n| b`): vale il forte
            out[-1] = ("seg", out[-1][1], dopo)

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
        if c == "(":
            chiudi("")
            out.append(("(",))
        elif c == ")":
            chiudi("")
            out.append((")",))
        elif c in ";\n":
            chiudi(c)
        elif c == "|" and prec != ">":
            if succ == "|":
                chiudi("||")
                i += 1
            elif succ == "&":
                chiudi("|&")
                i += 1
            else:
                chiudi("|")
        elif c == "&" and prec not in "<>" and succ != ">":
            if succ == "&":
                chiudi("&&")
                i += 1
            else:
                chiudi("&")
        else:
            cur.append(c)
        i += 1
    chiudi("")
    return out


def _scansiona_sost(t: str) -> list:
    """Le sostituzioni di comando di un testo come `(inizio, fine, interno)`:
    `$(...)`, `` `...` `` e `<(...)` (non quelle fra apici singoli). Anche quelle
    annidate."""
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
                out.append((i, j, t[i + 2:j - 1 if prof == 0 else j]))
                i += 2
                continue
            if c == "`":
                k = t.find("`", i + 1)
                if k != -1:
                    out.append((i, k + 1, t[i + 1:k]))
                    i = k + 1
                    continue
        i += 1
    return out


def _sostituzioni(t: str) -> list:
    """I testi dentro `$(...)`, `` `...` `` e `<(...)`: sono comandi da
    analizzare a parte."""
    return [x[2] for x in _scansiona_sost(t)]


def _maschera(t: str) -> str:
    """`t` con ogni sostituzione (le piu' esterne) sostituita da un solo
    carattere `\\x02`: cosi' `shlex` non spezza un `$(cat x)` ai suoi spazi e un
    `VAR=$(...)` resta un'assegnazione sola."""
    res, pos = [], 0
    for a, b, _ in sorted(_scansiona_sost(t)):
        if a < pos:
            continue
        res.append(t[pos:a])
        res.append("\x02")
        pos = b
    res.append(t[pos:])
    return "".join(res)


def _espandi_var(c: str, env=None, locali=None):
    """`c` con le variabili `$VAR` e `${VAR}` espanse: prima le variabili
    assegnate nello stesso comando (`locali`), poi l'ambiente del payload (se
    c'e'), poi quello dell'hook. `None` se ne resta una non definita (o un `$`
    di altro genere: `$1`, `$?`): un percorso che non si sa ricostruire si
    ignora, invece di risolverlo sulla cwd come se `$X` fosse un nome di
    cartella."""
    if "$" not in c:
        return c
    mancante = []

    def sost(m):
        nome = m.group(1) or m.group(2)
        if locali is not None and nome in locali:
            v = locali[nome]
        else:
            v = (env or {}).get(nome)
            if not isinstance(v, str):
                v = os.environ.get(nome)
        if not isinstance(v, str):
            mancante.append(nome)
            return ""
        return v
    r = _RX_VAR.sub(sost, c)
    return None if mancante or "$" in r else r


def _valore_var(v: str, env, locali):
    """Il valore che una assegnazione `VAR=v` da' alla variabile, o None se
    non si sa (una sostituzione di comando, una variabile non definita)."""
    if "$(" in v or "`" in v or "\x02" in v:
        return None
    e = _espandi_var(v, env, locali)
    if e is None:
        return None
    return os.path.expanduser(e) if e.startswith("~") else e


def _operandi_cd(args):
    out, prec, fine = [], "", False
    for a in args:
        if _punt(a):
            prec = a
            continue
        if prec:
            prec = ""
            continue
        if not fine and a == "--":
            fine = True
            continue
        if not fine and a.startswith("-") and a != "-":
            continue
        out.append(a)
    return out


def _risolvi_cd(target: str, cwd, locali, env):
    """La cartella in cui porta `cd target` da `cwd`, o `_IGNOTA`."""
    e = _espandi_var(target, env, locali)
    if not e:
        return _IGNOTA
    if _ha_glob(e):
        base = cwd if cwd and cwd != _IGNOTA else None
        if not (e.startswith(("/", "~")) or base):
            return _IGNOTA
        veri = [x for x in _espandi_glob(e, base) if os.path.isdir(x)]
        if len(veri) != 1:
            return _IGNOTA
        e = veri[0]
    if cwd == _IGNOTA and not e.startswith(("/", "~")):
        return _IGNOTA
    n = _norm(e, cwd if cwd != _IGNOTA else None)
    if not n:
        return _IGNOTA
    if not os.path.isdir(n) and not e.startswith(("/", "~")):
        # un `cd` relativo verso una cartella che non c'e' fallisce e la cartella
        # resta quella di prima (`cd comune; grep -rn x .` cerca dove era);
        # uno assoluto si segue: puo' essere creata dallo stesso comando
        return cwd if cwd is not None else (_norm(".") or _IGNOTA)
    return n


def _nuova_cwd(nome, args, cwd, dirs, locali, env, prima, dopo):
    """`(cwd, dirs)` dopo un `cd`, `pushd` o `popd`. Un `cd -`, una destinazione
    che non si sa risolvere, un `cd` dopo un `||` (forse non e' stato eseguito)
    danno `_IGNOTA`: piu' avanti un percorso relativo non si sa dove porta, e si
    nega per prudenza. Un comando in background o in una pipe gira in una
    sottoshell: non sposta niente."""
    if dopo in ("&", "|", "|&"):
        return cwd, dirs
    nuova = cwd
    if nome == "cd":
        op = _operandi_cd(args)
        if not op:
            nuova = os.path.expanduser("~")
        elif op[0] == "-":
            nuova = _IGNOTA
        else:
            nuova = _risolvi_cd(op[0], cwd, locali, env)
    elif nome == "pushd":
        op = _operandi_cd(args)
        if not op or op[0].startswith(("+", "-")):
            nuova = _IGNOTA
        else:
            nuova = _risolvi_cd(op[0], cwd, locali, env)
            dirs = dirs + [cwd]
    elif nome == "popd":
        if dirs:
            nuova, dirs = dirs[-1], dirs[:-1]
        else:
            nuova = _IGNOTA
    if prima == "||":
        nuova = _IGNOTA
    return nuova, dirs


def _uscite(tok) -> list:
    """I bersagli delle redirezioni di uscita (`> f`, `>> f`, `>| f`)."""
    out, prec = [], ""
    for t in tok:
        if _punt(t):
            prec = t
            continue
        if ">" in prec and "<" not in prec and not prec.endswith("&"):
            out.append(t)
        prec = ""
    return out


def _fase_a(testo: str, st: dict, env):
    """I segmenti di `testo` con la cartella e le variabili di quando partono."""
    cwd, vs, dirs = st["cwd"], st["vars"], list(st["dirs"])
    pila, segs, prima = [], [], ""
    for it in _dividi_segmenti(testo):
        if it[0] == "(":
            pila.append((cwd, vs, list(dirs)))
            continue
        if it[0] == ")":
            if pila:
                cwd, vs, dirs = pila.pop()
            continue
        _, seg, dopo = it
        tok = _token(_maschera(_RX_WHICH.sub(lambda m: m.group(1) or m.group(2), seg)))
        pre, ass, cmd0, nome, args = _spezza(tok)
        if cmd0.startswith("$") and cmd0 not in ("$", "$(") and "(" not in cmd0:
            e = _espandi_var(cmd0, env, vs)
            if e:
                nome = os.path.basename(e)
        s = {"nome": nome, "args": args, "token": tok, "testo": seg, "pre": pre,
             "cwd": cwd, "vars": vs, "prima": prima, "dopo": dopo,
             "hd": [int(m.group(1)) for m in (_RX_MARCA_HD.match(t) for t in tok) if m]}
        segs.append(s)
        # effetti sullo stato, DOPO aver fissato quello con cui il segmento parte
        if nome == "" and ass:
            vs = dict(vs)
            for a in ass:
                k, v = a.split("=", 1)
                vs[k] = _valore_var(v, env, vs)
        elif nome in ("export", "declare", "typeset", "local", "readonly"):
            vs = dict(vs)
            for a in args:
                if _RX_ASSEGNA.match(a):
                    k, v = a.split("=", 1)
                    vs[k] = _valore_var(v, env, vs)
        elif nome == "unset":
            vs = {k: v for k, v in vs.items() if k not in args}
        elif nome in ("cd", "pushd", "popd"):
            cwd, dirs = _nuova_cwd(nome, args, cwd, dirs, vs, env, prima, dopo)
        prima = dopo
    return segs


def _e_esecutore(s: dict) -> bool:
    """Il segmento USA il testo che riceve: una shell, un interprete, `xargs`..."""
    return (s["nome"] in _ESECUTORI or "xargs" in s["pre"]
            or _e_codice(s["nome"]))


def _consumo_testo(c) -> bool:
    """Il comando che consuma una sostituzione la usa come TESTO (il messaggio di
    `git commit -m "$(cat <<EOF ...)"`), non come percorso o come comando."""
    if not c or c["nome"] not in ("git", "gh"):
        return False
    return not any(a in ("-F", "--file", "--body-file", "-f") or a.startswith("-F")
                   for a in c["args"])


def _testo_echo(s: dict) -> str:
    """Il testo che `echo`/`printf` stampano: gli argomenti che non sono opzioni
    ne' redirezioni."""
    out, prec = [], ""
    for t in s["token"][1:]:
        if _punt(t):
            prec = t
            continue
        if prec:
            prec = ""
            continue
        if t.startswith("-") and not out and len(t) <= 3:
            continue
        out.append(t)
    return " ".join(out)


def _copia_stato(s: dict) -> dict:
    return {"cwd": s["cwd"], "vars": s["vars"], "dirs": []}


def _analizza(cmd: str, cwd0=None, env=None, prof: int = 0, st=None, cons=None,
              hd=None) -> dict:
    """`{"segmenti": [{"nome", "args", "token", "testo", "pre", "cwd", "vars",
    "prima", "dopo", "hd", "muto", "aqui", "catena"}, ...], "corpi": [...]}`
    del comando e di tutto quello che contiene (sostituzioni, `sh -c`, `eval`,
    heredoc e testi che arrivano a un esecutore). `cwd` e' la cartella in cui il
    segmento parte (simulata lungo i `cd`), o `_IGNOTA`. `corpi` sono testi di
    codice in cui cercare percorsi assoluti."""
    chiave = None
    if prof == 0:
        chiave = (cmd, cwd0, tuple(sorted(env.items())) if env else None)
        if chiave in _CACHE_ANALISI:
            return _CACHE_ANALISI[chiave]
    ris = {"segmenti": [], "corpi": []}
    if cmd and prof <= 4:
        # anche nei testi delle sostituzioni: un heredoc dentro `"$(...)"` non
        # si vede finche' il testo non e' estratto dalle virgolette
        testo, hd = _togli_heredoc(cmd, hd)
        if st is None:
            st = {"cwd": cwd0, "vars": {}, "dirs": []}
        segs = _fase_a(testo, st, env)
        _fase_b(segs, ris, cwd0, env, prof, cons, hd)
    if prof == 0:
        if len(_CACHE_ANALISI) > 64:
            _CACHE_ANALISI.clear()
        _CACHE_ANALISI[chiave] = ris
    return ris


def _sotto(ris: dict, testo: str, s: dict, cwd0, env, prof, hd, cons=None):
    """Analizza `testo` (una sostituzione, un `sh -c`, un heredoc) con la
    cartella e le variabili del segmento `s`, e ne aggiunge i segmenti."""
    r = _analizza(testo, cwd0, env, prof + 1, _copia_stato(s), cons, hd)
    ris["segmenti"].extend(r["segmenti"])
    ris["corpi"].extend(r["corpi"])


def _fase_b(segs: list, ris: dict, cwd0, env, prof: int, cons, hd: list) -> None:
    # le catene: segmenti collegati da pipe
    catena = None
    for k, s in enumerate(segs):
        if catena is None or segs[k - 1]["dopo"] not in ("|", "|&"):
            _CONTATORE[0] += 1
            catena = _CONTATORE[0]
        s["catena"] = catena
    differiti = []
    for k, s in enumerate(segs):
        nome = s["nome"]
        pipe_out = s["dopo"] in ("|", "|&")
        # il testo di questo segmento arriva a un esecutore lungo la pipe?
        j, pipe_esec = k, False
        while j < len(segs) and segs[j]["dopo"] in ("|", "|&"):
            j += 1
            if j < len(segs) and _e_esecutore(segs[j]):
                pipe_esec = True
        catturato = cons is not None
        # echo/printf: inerti solo se stampano su un terminale o in un file,
        # senza pipe e fuori da una sostituzione (la regola e' quella)
        s["muto"] = nome in _MUTI and not pipe_out and not catturato
        flusso = (pipe_out and pipe_esec) or (catturato and not _consumo_testo(cons))
        esec = _e_esecutore(s)
        s["aqui"] = esec or flusso or nome == "read"
        s["aqui_testo"] = []
        ris["segmenti"].append(s)
        # sostituzioni (il loro output e' consumato da questo segmento), `sh -c`
        for interno in _sostituzioni(s["testo"]):
            r = _analizza(interno, cwd0, env, prof + 1, _copia_stato(s), s, hd)
            ris["segmenti"].extend(r["segmenti"])
            ris["corpi"].extend(r["corpi"])
        if nome in _SHELL:
            for i, a in enumerate(s["args"]):
                if re.match(r"^-[A-Za-z]*c[A-Za-z]*$", a) and i + 1 < len(s["args"]):
                    _sotto(ris, s["args"][i + 1], s, cwd0, env, prof, hd)
                    break
        if nome == "eval":
            _sotto(ris, " ".join(s["args"]), s, cwd0, env, prof, hd)
        # il testo di echo/printf che una pipe porta a un esecutore e' un
        # comando (`echo "cat /x" | sh`): si analizza come tale
        if nome in _MUTI and pipe_out and pipe_esec:
            testo_e = _testo_echo(s)
            _sotto(ris, testo_e, s, cwd0, env, prof, hd)
            ris["corpi"].append((testo_e, s["cwd"]))
        # here-string: `read f <<< testo`, `sh <<< 'cmd'`
        prec = ""
        for t in s["token"]:
            if _punt(t):
                prec = t
                continue
            if prec == "<<<" and s["aqui"]:
                s["aqui_testo"].append(t)
                ris["corpi"].append((t, s["cwd"]))
                if nome in _SHELL or nome == "eval":
                    _sotto(ris, t, s, cwd0, env, prof, hd)
            prec = ""
        # heredoc
        uscite = _uscite(s["token"])
        for hid in s["hd"]:
            if hid >= len(hd):
                continue
            corpo, quotato = hd[hid]["corpo"], hd[hid]["quotato"]
            if esec or flusso:
                _sotto(ris, corpo, s, cwd0, env, prof, hd)
                ris["corpi"].append((corpo, s["cwd"]))
            elif _e_codice(nome):
                ris["corpi"].append((corpo, s["cwd"]))
            else:
                if not quotato:
                    # un heredoc senza virgolette espande `$(...)` e gli apici
                    # inversi del suo corpo: quei comandi girano davvero
                    for interno in _sostituzioni(corpo):
                        _sotto(ris, interno, s, cwd0, env, prof, hd)
                if uscite:
                    differiti.append((k, corpo, uscite[0]))
        if s["muto"] and uscite:
            differiti.append((k, _testo_echo(s), uscite[0]))
    # un testo scritto in un file e poi dato a un esecutore nello stesso comando
    for k, testo, dest in differiti:
        d = _espandi_var(dest, env, segs[k]["vars"])
        dn = _norm(d, segs[k]["cwd"] if segs[k]["cwd"] != _IGNOTA else None) if d else ""
        if not dn:
            continue
        for s2 in segs[k + 1:]:
            if not _e_esecutore(s2):
                continue
            usa = False
            for t in s2["token"]:
                if _punt(t) or t.startswith("-"):
                    continue
                e = _espandi_var(t, env, s2["vars"])
                if e and _norm(e, s2["cwd"] if s2["cwd"] != _IGNOTA else None).lower() == dn.lower():
                    usa = True
                    break
            if usa:
                _sotto(ris, testo, s2, cwd0, env, prof, hd)
                ris["corpi"].append((testo, s2["cwd"]))
                break


def _parole_segmento(s: dict) -> list:
    """I token di un segmento che possono essere percorsi o nomi: senza la
    punteggiatura, senza la parola che segue un heredoc (e' il segnaposto del
    delimitatore), senza il testo di una here-string che nessuno usa, e per
    `echo`/`printf` inerti solo i bersagli delle redirezioni (gli altri
    argomenti si stampano e basta)."""
    muto = s.get("muto")
    out, prec = [], ""
    for t in s["token"]:
        if _punt(t):
            prec = t
            continue
        heredoc = "<<" in prec and "<<<" not in prec
        aqui = "<<<" in prec
        redirezione = (">" in prec or "<" in prec) and not heredoc and not aqui
        prec = ""
        if heredoc or _RX_MARCA_HD.match(t):
            continue
        if aqui and not s.get("aqui"):
            continue
        if muto and not redirezione:
            continue
        out.append(t)
    return out


def _file_url(u: str):
    """Il percorso di un url `file:`, o None se non lo e' (o e' di un altro host)."""
    if not isinstance(u, str) or not u[:5].lower() == "file:":
        return None
    from urllib.parse import unquote, urlparse
    try:
        p = urlparse(u)
    except ValueError:
        return None
    if p.netloc not in ("", "localhost"):
        return None
    return unquote(p.path) or None


def _varianti_token(t: str, env=None, locali=None):
    """Da un token di shell: se stesso e la parte dopo il primo `=`
    (`--dir=/x`). Torna `(percorsi, nomi_semplici)`: i primi sembrano un
    percorso (iniziano con `/`, `~`, `./`, `../` o contengono `/`), i secondi
    sono nomi senza barre (`cd cartella`, `git -C cartella`), che hanno senso
    solo risolti sulla cwd (vedi `_percorsi_da_comando`). Un url `file:` e' un
    percorso."""
    if not t:
        return [], []
    if t.startswith("-") and "=" not in t:
        # un'opzione (`-rf`), salvo che porti un percorso: `-I/usr/include`,
        # `-o/dest` (il percorso attaccato), o sia un nome che comincia con `-`
        # con una barra (le cartelle codificate di `~/.claude/projects` sono cosi':
        # `cat -Users-x-dir/memory/f`)
        if "/" not in t or t.startswith("--"):
            return [], []
        cand = [t]
        if len(t) > 2 and t[1].isalpha() and t[2] in "/~.":
            cand.append(t[2:])
    else:
        cand = [t]
        if "=" in t:
            cand.append(t.split("=", 1)[1])
    perc, nomi = [], []
    for c in cand:
        c = c.lstrip("<>&|(").strip()
        if not c or "$(" in c or "`" in c or "\x02" in c or "\n" in c or len(c) > 4096:
            continue
        f = _file_url(c)
        if f:
            perc.append(f)
            continue
        if _RX_URL.match(c):
            continue
        c = _espandi_var(c, env, locali)
        if not c:
            continue
        if c == ".." or c.startswith(("/", "~", "./", "../")) or "/" in c:
            perc.append(c)
        elif not c.startswith("-") and len(c) <= 255 and not any(x.isspace() for x in c):
            nomi.append(c)
    return perc, nomi


def _trova_percorsi_in_testo(testo: str) -> list:
    out = []
    for m in re.finditer(r"""file:[^\s'"`;|&<>()\\]+""", testo, re.I):
        f = _file_url(m.group(0))
        if f:
            out.append(f)
    for m in _RX_ASSOLUTO.finditer(_RX_URL.sub(" ", testo)):
        c = m.group(1)
        out.append(c)
        if c.rstrip(".,:") != c:
            out.append(c.rstrip(".,:"))
    return out


_RX_RELATIVO_STR = re.compile(r"""['"]([^'"\s/~$][^'"\s]*/[^'"\s]*)['"]""")


def _trova_relativi_in_testo(testo: str) -> list:
    """Le stringhe fra virgolette che sembrano un percorso RELATIVO (`'a/b.txt'`)
    dentro il codice di un interprete: si risolvono sulla cartella del comando."""
    return [m.group(1) for m in _RX_RELATIVO_STR.finditer(testo)
            if "://" not in m.group(1) and "\x02" not in m.group(1)]


def _candidati_an(an: dict, env=None) -> list:
    """Percorsi e nomi che un comando Bash potrebbe toccare, come
    `(testo, tipo, cwd, segmento)`: `tipo` e' `p` (sembra un percorso) o `n` (un
    nome semplice), `cwd` la cartella in cui il segmento lo legge (simulata
    lungo i `cd`), `segmento` il dizionario di `_analizza` (None per il testo di
    un codice, dove si cercano solo percorsi assoluti)."""
    trovati = []
    for s in an["segmenti"]:
        for t in _parole_segmento(s):
            perc, semplici = _varianti_token(t, env, s["vars"])
            trovati.extend((c, "p", s["cwd"], s) for c in perc)
            trovati.extend((c, "n", s["cwd"], s) for c in semplici)
        if _e_interprete(s["nome"]):
            for t in s["args"]:
                trovati.extend((c, "p", None, s) for c in _trova_percorsi_in_testo(t))
                trovati.extend((c, "p", s["cwd"], s) for c in _trova_relativi_in_testo(t))
        for t in s.get("aqui_testo") or ():
            trovati.extend((c, "p", None, s) for c in _trova_percorsi_in_testo(t))
    for corpo, cw in an["corpi"]:
        trovati.extend((c, "p", None, None) for c in _trova_percorsi_in_testo(corpo))
        trovati.extend((c, "p", cw, None) for c in _trova_relativi_in_testo(corpo))
    visti, out = set(), []
    for c, tipo, cw, s in trovati:
        k = (c, tipo, cw, id(s))
        if c and k not in visti:
            visti.add(k)
            out.append((c, tipo, cw, s))
    return out


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
    """I percorsi di un comando Bash, risolti, come `(testo, percorso,
    segmento)`. Ogni percorso relativo si risolve sulla cartella in cui il suo
    segmento parte (simulata lungo i `cd`); se quella non si sa
    (`cd -`, una variabile non definita) il percorso relativo vale `_IGNOTA`.
    Con `nomi_semplici` anche i token senza barre (`cd cartella`) risolti sulla
    cwd: solo per il predefinito, dove servono a vedere `cd cartella-di-un-nominato`
    da una cwd che sta sopra. Non per un nominato: con la cwd fuori dai suoi
    permessi ogni parola (`echo`, `ls`) risolverebbe fuori (ma vedi `valuta`: per
    un nominato la cwd stessa e' un percorso toccato da ogni comando). I token
    con un glob si espandono sul disco (`cat cartella/*`)."""
    an = _analizza(cmd, cwd, env)
    out, visti = [], set()

    def aggiungi(testo, n, s):
        k = (n, id(s))
        if n and k not in visti:
            visti.add(k)
            out.append((testo, n, s))

    for c, tipo, cw, s in _candidati_an(an, env):
        if tipo == "n" and not nomi_semplici:
            continue
        base = cw if cw is not None else cwd
        if base == _IGNOTA and not c.startswith(("/", "~")):
            if tipo == "p":
                aggiungi(c, _IGNOTA, s)
            continue
        aggiungi(c, _norm(c, base), s)
        if s is not None and s["nome"] == "du" and not any(
                re.match(r"^-[A-Za-z]*a", a) or a == "--all" for a in s["args"]):
            # `du -sh *` da una cartella che ha sotto una vietata mostra solo
            # dimensioni, non nomi ne' contenuti (con -a i nomi si vedono)
            continue
        for e in _espandi_glob(c, base):
            aggiungi(e, _norm(e, base), s)
        if len(out) >= MAX_PERCORSI_COMANDO:
            break
    return out


# I comandi che camminano un albero intero. Riconosciuti dal NOME del comando
# (il primo token di ogni segmento, dopo i prefissi `sudo`, `xargs`,
# `VAR=x`...), non da una parola qualsiasi nel testo: `echo find` non e' una
# ricerca.
_RICORSIVI_SEMPRE = ("ag", "ack", "zip", "rsync", "tar")


def _num_dopo(args, opzioni):
    for k, a in enumerate(args):
        for o in opzioni:
            if a == o and k + 1 < len(args) and args[k + 1].isdigit():
                return int(args[k + 1])
            if a.startswith(o + "=") and a.split("=", 1)[1].isdigit():
                return int(a.split("=", 1)[1])
            if len(o) == 2 and a.startswith(o) and a[2:].isdigit():
                return int(a[2:])
    return None


def _ricorsivita(s: dict):
    """Se il segmento cerca o copia ricorsivamente: `None` (no), `True` (senza
    limite) o un intero, la profondita' massima a cui puo' arrivare una cartella
    vietata perche' i suoi file siano letti (`find . -maxdepth 1`: nessuna;
    `tree -L 2`: le cartelle direttamente sotto la radice). Riconosce grep -r, rg,
    find, ls -R, tree, tar, zip, cp -r, rsync, git grep."""
    nome, args = s["nome"], s["args"]
    if not nome:
        return None
    if nome == "find":
        n = _num_dopo(args, ("-maxdepth",))
        if n is None:
            return True
        esegue = any(a in ("-exec", "-execdir", "-ok", "-okdir") for a in args)
        return n if esegue else n - 1
    if nome == "tree":
        n = _num_dopo(args, ("-L",))
        return True if n is None else n - 1
    if nome in ("rg", "fd"):
        n = _num_dopo(args, ("--max-depth", "-d"))
        if n is None:
            return True
        if nome == "fd" and not any(a in ("-x", "--exec", "-X", "--exec-batch")
                                    for a in args):
            return n - 1
        return n
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
        if any(re.match(r"^-[A-Za-z]*R", a) or a == "--recursive" for a in args):
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
    return None


def _ric_attiva(r) -> bool:
    """Una ricerca che entra in almeno una cartella."""
    return r is True or (isinstance(r, int) and not isinstance(r, bool) and r > 0)


def _ric(r, prof: int) -> bool:
    """La ricerca `r` (None, True o un limite) arriva a un percorso `prof`
    livelli sotto la sua radice?"""
    return r is True or (isinstance(r, int) and not isinstance(r, bool)
                         and 0 < prof <= r)


def _max_ric(a, b):
    if a is True or b is True:
        return True
    if a is None:
        return b
    if b is None:
        return a
    return max(a, b)


def _ric_catene(an: dict) -> dict:
    """Per ogni catena di pipe di un comando, la ricerca piu' larga che contiene."""
    d = {}
    for s in an["segmenti"]:
        r = _ricorsivita(s)
        if r is not None:
            d[s["catena"]] = _max_ric(d.get(s["catena"]), r)
    return d


def percorsi_richiesti(nome: str, ti: dict, cwd, nomi_semplici=False, env=None):
    """Tutti i percorsi che una chiamata di strumento vuole toccare, come
    `(testo, percorso_risolto, ricorsivo)`. `ricorsivo` e' `None` (no), `True`
    (una ricerca che entra in tutto quello che sta sotto) o un intero (una
    ricerca a profondita' limitata): Grep e Glob sono ricerche, e una ricerca che
    parte da una cartella entra in tutto quello che ci sta sotto, compresa una
    cartella vietata. Grep senza `path` cerca nella cwd; Glob senza `path` con un
    modello assoluto no. `env` e' l'ambiente del payload (se c'e'), per le
    variabili dei comandi Bash. Il percorso `_IGNOTA` vale "un percorso relativo
    che non si sa dove porta"."""
    out = []
    corto = _nome_corto(nome)
    ricerca = corto in ("Grep", "Glob")

    # `Artifact` risolve i file sorgente rispetto a `root`, se c'e'.
    root = ti.get("root")
    base_file = _norm(root, cwd) if isinstance(root, str) and root else None

    def aggiungi(testo, ricorsivo=None, base=None):
        n = _norm(testo, base or cwd)
        if n:
            out.append((testo, n, ricorsivo))

    for k in CHIAVI_PERCORSO:
        v = ti.get(k)
        if isinstance(v, str) and v:
            aggiungi(v, True if ricerca and k == "path" else None)
    for k in CHIAVI_URL:
        f = _file_url(ti.get(k))
        if f:
            aggiungi(f)
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
        pat = ti.get("pattern") if corto == "Glob" else None
        assoluto = (isinstance(pat, str) and pat.startswith(("/", "~")))
        if not (isinstance(pth, str) and pth) and not assoluto:
            aggiungi(base, True)
        if isinstance(pat, str) and pat:
            if pat.startswith(("/", "~")):
                d = _prefisso_glob_dir(os.path.expanduser(pat))
                if d:
                    aggiungi(d, True if _ha_glob(pat) else None)
            else:
                d = _prefisso_glob_dir(pat)
                if d:
                    aggiungi(os.path.join(os.path.expanduser(base), d), True)
    cmd = ti.get("command")
    if isinstance(cmd, str) and cmd:
        an = _analizza(cmd, cwd, env)
        ric_c = _ric_catene(an)
        trovati = _percorsi_da_comando(cmd, cwd, nomi_semplici, env)
        for testo, n, s in trovati:
            r = ric_c.get(s["catena"]) if s is not None else None
            # Una `/` da sola non e' un percorso da negare (`ls /`), salvo che
            # una ricerca ricorsiva parta proprio da li' (`find / -name x`).
            if n == "/" and not _ric_attiva(r):
                continue
            out.append((testo, n, r))
        for s in an["segmenti"]:
            r = _ricorsivita(s)
            if r is None:
                continue
            # Una ricerca senza una cartella o un file operando che esista
            # (`rg x`, `git grep x`) parte dalla cartella del suo segmento. Con
            # un operando che esiste (`grep -r x progetto`) parte da li', e la
            # cartella non c'entra. (`x`, il modello, non e' un percorso che
            # esiste: risolto sulla cartella non combacia con niente.)
            mie = [n for _, n, ss in trovati if ss is s]
            if any(n != _IGNOTA and os.path.exists(n) for n in mie):
                continue
            base = s["cwd"] if s["cwd"] is not None else cwd
            if base == _IGNOTA:
                out.append((base, _IGNOTA, r))
            elif base:
                n = _norm(base)
                if n:
                    out.append((base, n, r))
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
        # un `session_id` crudo: la sessione e' nel registro dell'app col suo
        # `cliSessionId`, anche se non e' in nessuna lista `sessioni`
        voci = _voci_app(ambito.home, cli=chiave)
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
    # La cwd e' quella SIMULATA lungo il comando (`cd dentro && ls` parte da
    # dentro), e un `cd` da solo non legge niente: il suo bersaglio si controlla
    # fra i percorsi.
    if nominato and isinstance(cmd, str) and cmd:
        v = _valuta_cwd_nominato(cmd, chi, ambito, mio, _env_payload(payload))
        if v:
            return v
    # 4) percorsi
    for testo, p, ricorsivo in percorsi_richiesti(nome, ti, chi["cwd"] or None,
                                                  nomi_semplici=not nominato,
                                                  env=_env_payload(payload)):
        if p == _IGNOTA:
            return {"bersaglio": testo, "proprietario": "sconosciuto",
                    "motivo": "compartimento %s: il comando cambia cartella con una "
                              "destinazione che non si sa determinare (`cd -`, una "
                              "variabile non definita) e poi usa un percorso "
                              "relativo: scrivi percorsi assoluti" % mio}
        if nominato:
            v = _percorso_nominato(p, chi, ambito, mio, ricorsivo)
        else:
            v = _percorso_predefinito(p, ricorsivo, ambito, mio)
        if v:
            return v
    return None


def _valuta_cwd_nominato(cmd, chi, ambito, mio, env):
    """Per un nominato: la cartella da cui parte ogni segmento del comando (la
    cwd simulata) deve stare nei suoi permessi. Un segmento `cd`/`pushd`/`popd`
    o di sole assegnazioni non legge la cartella."""
    for s in _analizza(cmd, chi["cwd"] or None, env)["segmenti"]:
        if not s["nome"] or s["nome"] in ("cd", "pushd", "popd"):
            continue
        cw = s["cwd"] if s["cwd"] is not None else (chi["cwd"] or None)
        if not cw:
            continue
        if cw == _IGNOTA:
            return {"bersaglio": s["nome"], "proprietario": "sconosciuto",
                    "motivo": "compartimento %s: il comando cambia cartella con una "
                              "destinazione che non si sa determinare (`cd -`, una "
                              "variabile non definita) e poi lancia `%s` da li': "
                              "scrivi percorsi assoluti" % (mio, s["nome"])}
        v = _percorso_nominato(cw, chi, ambito, mio)
        if v:
            cartelle = [f for n in chi["nomi"] for f in ambito.nominati[n]["cartelle"]]
            return {"bersaglio": cw, "proprietario": v["proprietario"],
                    "motivo": "compartimento %s: la cartella di lavoro %s e' fuori "
                              "dai permessi di %s, e un comando da li' leggerebbe "
                              "file fuori dai permessi: sposta la sessione con "
                              "change_directory in una cartella del compartimento "
                              "(%s)" % (mio, cw, mio,
                                        ", ".join(cartelle) or "nessuna configurata")}
    return None


# Le chiavi di config.json che tengono acceso o configurano il guardiano.
CHIAVI_GUARDIANO = ("guardiano", "compartimenti", "strumenti_drive")

# Scritture "per altre vie" dentro il codice di un interprete
# (`python3 -c "open(f, 'w')"`, `Path(f).write_text`, `os.remove`, `shutil`,
# `fs.writeFileSync`, `File.write`, `open(F, ">...")` di perl, `config.save_config`,
# ...): se il testo nomina un file del guardiano E ha uno di questi segni, e' una
# scrittura. `json.load(open(f))` no.
_RX_CODICE_SCRIVE = re.compile(
    r"write|dump\(|os\.(?:replace|rename|remove|unlink|truncate|link|symlink)"
    r"|unlink|rmtree|shutil|truncate|save_config|appendFile|File\.open|File\.delete"
    r"|File\.rename|FileUtils|\bmv\b|\bcopyfile|\bcopy2?\("
    r"""|open\([^)]*,\s*['"][wax+]|mode\s*=\s*['"][wax+]|open\s*\(?[^;\n]*['"]\s*\+?>""",
    re.I)
_RX_SED_SUL_POSTO = re.compile(r"^(?:-[A-Za-z]*i|--in-place)")
# Il pacchetto di Plancia importato da un interprete, e cio' che lo usa per
# cambiare la config: `main([...])` della CLI, `save_config`, `sys.argv`.
_RX_PKG_PLANCIA = re.compile(
    r"\bfrom\s+plancia\b|\bimport\s+plancia\b|plancia\.(?:cli|config|compartimenti)\b"
    r"""|require\(\s*['"][^'"]*plancia""")
_RX_USA_CLI = re.compile(r"\bmain\s*\(|save_config|\bsys\.argv\b")
# La cartella dei dati di Plancia nominata per NOME (`os.environ['HOME'] + '/.plancia'`,
# `PLANCIA_HOME`), senza un percorso assoluto che l'espressione regolare dei
# percorsi possa vedere, insieme a uno dei file o delle chiavi del guardiano.
_RX_DATI_NOMINATI = re.compile(r"\.plancia\b|PLANCIA_HOME")
_RX_DATI_FILE = re.compile(r"config\.json|compartimenti|guardiano", re.I)

_MOTIVO_A_MANO = ("le impostazioni del guardiano le cambia il proprietario della "
                  "macchina a mano, fuori da una sessione")
_MOTIVO_SETTINGS = ("il file di impostazioni di Claude Code tiene acceso il guardiano: "
                    "si modifica con Edit o Write (che controllano che la voce "
                    "PreToolUse di plancia-guardiano resti e che non ci sia "
                    "disableAllHooks), non da Bash")
# Comandi di `find -exec` che non scrivono.
_LETTURA_ESEC = frozenset((
    "cat", "grep", "egrep", "fgrep", "head", "tail", "wc", "ls", "stat", "file", "md5",
    "md5sum", "shasum", "sha256sum", "du", "echo", "less", "more", "jq", "basename",
    "dirname", "readlink", "realpath", "printf", "test", "[", "true"))
# Sottocomandi di git che riscrivono l'albero di lavoro.
_GIT_SCRIVE = frozenset((
    "checkout", "restore", "reset", "clean", "stash", "switch", "merge", "rebase",
    "pull", "apply", "am", "cherry-pick", "revert", "rm", "mv", "checkout-index",
    "read-tree", "worktree", "submodule"))


class _Protetti:
    """Cio' che tiene in piedi il guardiano, e che nessuna sessione tocca:

    - i file di stato: la config, la copia dell'ultima valida, il registro, il
      manifesto dei divieti;
    - il codice dell'hook: `bin/plancia-guardiano`, `plancia/__init__.py`,
      `plancia/compartimenti.py`, `plancia/config.py`, e ogni file `.py` (o
      modulo caricabile) in `bin/` e nella radice del checkout da cui gira
      l'hook: sono sul `sys.path` dell'hook, e un `json.py` li' gli
      toglierebbe il modulo di sistema (il wrapper si difende, ma non si lascia
      la porta aperta);
    - i file di impostazioni di Claude Code (`settings.json`,
      `settings.local.json`, ovunque stiano sotto una cartella `.claude`, e
      nella cartella di configurazione): qui la protezione e' MIRATA, non un
      divieto in blocco (`_controlla_settings`)."""

    def __init__(self, ambito: Ambito, data_dir: str):
        qui = os.path.realpath(__file__)
        self.radice = os.path.dirname(os.path.dirname(qui))
        self.bin = os.path.join(self.radice, "bin")
        self.dati = _norm(data_dir)
        elenco = [os.path.join(data_dir, "config.json"), _percorso_copia(data_dir),
                  _percorso_registro(data_dir), _percorso_registro(data_dir) + ".1",
                  os.path.join(data_dir, "guardiano.non-parte"),
                  os.path.join(self.bin, "plancia-guardiano"), qui,
                  os.path.join(self.radice, "plancia", "__init__.py"),
                  os.path.join(self.radice, "plancia", "config.py")]
        if ambito.manifesto:
            elenco.append(os.path.expanduser(ambito.manifesto))
        self.esatti = {n.lower() for n in (_norm(p) for p in elenco) if n}
        self.settings_utente = {
            n.lower() for n in (_norm(os.path.join(d, f))
                                for d in {ambito.claude_dir,
                                          os.path.join(ambito.home, ".claude")}
                                for f in ("settings.json", "settings.local.json")) if n}
        # le cartelle che li contengono: scriverci dentro "in massa" (find
        # -delete, un `cp -r` su tutta la cartella, un `tar x`) li tocca
        self.cartelle = {os.path.dirname(p) for p in self.esatti | self.settings_utente}
        self.radice_l = self.radice.lower()
        self.bin_l = self.bin.lower()

    def tag(self, n: str):
        """`file` (protetto del tutto), `settings` (protetto in modo mirato) o
        None, per un percorso gia' risolto."""
        low = n.lower()
        if low in self.esatti:
            return "file"
        d = os.path.dirname(low)
        if d in (self.radice_l, self.bin_l) and low.endswith((".py", ".pyc", ".so", ".pth")):
            return "file"
        if (os.path.basename(low) == "__init__.py" and os.path.dirname(d) == self.radice_l
                and os.path.basename(d) != "plancia"):
            return "file"       # un pacchetto nuovo nella radice: `json/__init__.py`
        if low in self.settings_utente or (
                os.path.basename(low) in ("settings.json", "settings.local.json")
                and os.path.basename(d) == ".claude"):
            return "settings"
        return None

    def contiene(self, n: str):
        """`(percorso, tag)` di un file protetto dentro la cartella `n` (o `n`
        stesso), o None."""
        for p in sorted(self.esatti | self.settings_utente):
            if _dentro(p, n):
                return p, self.tag(p) or "file"
        return None

    def cartella_stato(self, n: str) -> bool:
        """`n` e' una cartella che contiene direttamente file protetti."""
        return n.lower().rstrip("/") in self.cartelle


def _voci_guardiano(testo: str):
    """I comandi delle voci PreToolUse di un settings che nominano
    `plancia-guardiano`, o None se il testo non e' JSON."""
    try:
        d = json.loads(testo)
    except (ValueError, RecursionError):
        return None
    out = set()
    hooks = d.get("hooks") if isinstance(d, dict) else None
    pre = hooks.get("PreToolUse") if isinstance(hooks, dict) else None
    for voce in pre if isinstance(pre, list) else ():
        for h in (voce.get("hooks") if isinstance(voce, dict) else None) or ():
            c = h.get("command") if isinstance(h, dict) else None
            if isinstance(c, str) and "plancia-guardiano" in c:
                out.add(c)
    return out


def _testo_dopo_scrittura(corto: str, ti: dict, attuale: str):
    """Il contenuto che il file avra' dopo lo strumento di scrittura, o None se
    non si sa (parametri strani, un `old_string` che non c'e': lo strumento
    stesso fallira')."""
    if corto == "Write":
        c = ti.get("content")
        return c if isinstance(c, str) else None
    modifiche = []
    if corto == "Edit":
        modifiche = [ti]
    elif corto == "MultiEdit" and isinstance(ti.get("edits"), list):
        modifiche = [e for e in ti["edits"] if isinstance(e, dict)]
    else:
        return None
    testo = attuale
    for e in modifiche:
        vecchio, nuovo = e.get("old_string"), e.get("new_string")
        if not isinstance(vecchio, str) or not isinstance(nuovo, str) or vecchio not in testo:
            return None
        testo = testo.replace(vecchio, nuovo) if e.get("replace_all") else testo.replace(vecchio, nuovo, 1)
    return testo


def _controlla_settings(n: str, corto: str, ti: dict, P: _Protetti):
    """Il motivo per cui una scrittura su un file di impostazioni di Claude
    Code e' negata, o None. Ammessa SOLO se il contenuto risultante non ha
    `disableAllHooks` a vero e, quando il file ha oggi la voce PreToolUse del
    guardiano (lo stesso comando), la ha ancora: chi modifica settings.json per
    altri motivi non inciampa. Da Bash la scrittura si nega in blocco (non se ne
    vede il risultato)."""
    try:
        with open(n, "r", encoding="utf-8") as f:
            attuale = f.read()
    except (OSError, UnicodeDecodeError):
        attuale = ""
    nuovo = _testo_dopo_scrittura(corto, ti, attuale)
    if nuovo is None:
        return None
    try:
        d = json.loads(nuovo)
        spento = isinstance(d, dict) and d.get("disableAllHooks") in (True, "true")
    except (ValueError, RecursionError):
        spento = bool(re.search(r'"disableAllHooks"\s*:\s*"?true', nuovo))
    if spento:
        return ("scrive `disableAllHooks` a vero: spegnerebbe tutti gli hook, "
                "guardiano compreso")
    prima = _voci_guardiano(attuale)
    if prima:
        dopo = _voci_guardiano(nuovo)
        if dopo is None:
            ok = all(json.dumps(c)[1:-1] in nuovo or c in nuovo for c in prima)
        else:
            ok = prima <= dopo
        if not ok:
            return ("toglie o cambia la voce PreToolUse di plancia-guardiano: "
                    "spegnerebbe il guardiano")
    return None


def _protetti(ambito: Ambito, data_dir: str) -> list:
    """I file di stato e di codice del guardiano (elenco esatto, senza le zone)."""
    return sorted(_Protetti(ambito, data_dir).esatti)


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
        if redir or not t or (t.startswith("-") and len(t) > 1) or _RX_MARCA_HD.match(t):
            continue
        out.append(t)
    return out


def _cli_config_guardiano(s: dict):
    """La chiave del guardiano che un segmento imposta con la CLI di Plancia
    (`plancia config guardiano spento`, `python3 -m plancia.cli config ...`,
    `python3 bin/plancia config ...`, `$(which plancia) config ...`), o None.
    Senza un valore e' una lettura."""
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


def _tar_estrae(args) -> bool:
    """`tar` estrae (`x`): con l'opzione lunga o corta, o nel gruppo all'antica
    (`tar xzf a.tgz`, `tar -xzf a.tgz`)."""
    if any(a in ("-x", "--extract", "--get") for a in args):
        return True
    if args and re.match(r"^-?[A-Za-z]+$", args[0]) and "x" in args[0]:
        return True
    return any(re.match(r"^-[A-Za-z]*x[A-Za-z]*$", a) for a in args)


def _scrive_un_protetto(cmd: str, cwd, P: _Protetti, env=None):
    """`(bersaglio, come)` se il comando Bash scrive, cancella o sposta un file
    del guardiano, o imposta una sua chiave con la CLI; altrimenti None. `come`
    e' `cli`, `scrive`, `settings` (un file di impostazioni di Claude Code) o
    `ignota` (una scrittura relativa dopo un `cd` che non si sa dove porta).

    EURISTICO, dichiarato: chi vuole aggirarlo ci riesce (un percorso costruito a
    pezzi dentro uno script). Chiude il caso ordinario: `plancia config guardiano
    spento`, `sed -i`, `tee`, una redirezione, `cp x config.json`, `python3 -c`
    che scrive il file, `rm`/`mv` del file o della cartella che lo contiene,
    `find -delete`, `curl -o`, `tar x -C`, `git checkout` nella cartella dei
    dati. I percorsi relativi si risolvono sulla cartella SIMULATA del segmento
    (`cd cartella-dati && sed -i ... config.json`). La lettura e' ammessa."""
    an = _analizza(cmd, cwd, env)

    def base(s):
        return s["cwd"] if s["cwd"] is not None else cwd

    def risolvi(x, s):
        """I percorsi risolti a cui punta `x` (anche con un glob di shell), o
        None se `x` e' relativo e la cartella non si sa."""
        x = _espandi_var(x, env, s["vars"])
        if not x:
            return []
        b = base(s)
        if b == _IGNOTA and not x.startswith(("/", "~")):
            return None
        return [n for n in (_norm(c, b) for c in [x] + _espandi_glob(x, b)) if n]

    def protetto(x, s):
        r = risolvi(x, s)
        if r is None:
            return x, "ignota"
        for n in r:
            t = P.tag(n)
            if t:
                return n, ("settings" if t == "settings" else "scrive")
        return None

    def contiene(x, s):
        r = risolvi(x, s)
        if r is None:
            return x, "ignota"
        for n in r:
            c = P.contiene(n)
            if c:
                return c[0], ("settings" if c[1] == "settings" else "scrive")
        return None

    def stato(x, s):
        """`x` e' una cartella che contiene direttamente file protetti."""
        r = risolvi(x, s)
        if r is None:
            return x, "ignota"
        for n in r:
            if P.cartella_stato(n):
                return n, "scrive"
        return None

    def destinazione(operandi, s):
        """Il file protetto che un `cp`/`mv`/`install`/`rsync` scrive: l'ultimo
        operando, o (se e' una cartella) la cartella piu' il nome di ogni sorgente."""
        if not operandi:
            return None
        v = protetto(operandi[-1], s)
        if v:
            return v
        r = risolvi(operandi[-1], s) or []
        if len(operandi) >= 2 and r and (operandi[-1].endswith("/") or os.path.isdir(r[0])):
            for src in operandi[:-1]:
                n = _norm(os.path.join(r[0], os.path.basename(src.rstrip("/"))))
                t = P.tag(n) if n else None
                if t:
                    return n, ("settings" if t == "settings" else "scrive")
        return None

    def valore_opzione(args, brevi, lunghe):
        """Il valore di un'opzione (`-o x`, `-ox`, `--output x`, `--output=x`)."""
        for i, a in enumerate(args):
            for o in brevi:
                if a == o and i + 1 < len(args):
                    return args[i + 1]
                if a.startswith(o) and len(a) > len(o) and not a.startswith("--"):
                    return a[len(o):]
            for o in lunghe:
                if a == o and i + 1 < len(args):
                    return args[i + 1]
                if a.startswith(o + "="):
                    return a.split("=", 1)[1]
        return None

    codice = False
    for s in an["segmenti"]:
        nome, args = s["nome"], s["args"]
        n = nome.lower()
        # 1) la CLI di Plancia
        chiave = _cli_config_guardiano(s)
        if chiave:
            return chiave, "cli"
        if _e_interprete(nome):
            codice = True
        # 2) redirezioni: `> file`, `>> file`, `>| file`
        for t in _uscite(s["token"]):
            v = protetto(t, s)
            if v:
                return v
        op = _operandi(s)
        if n in ("tee", "truncate", "rm", "chmod", "chown", "ed", "ex", "vi", "vim",
                 "nano", "emacs", "sponge", "unlink", "shred", "mv", "touch"):
            for x in op:
                v = protetto(x, s)
                if v:
                    return v
            if n == "mv":
                v = destinazione(op, s)
                if v:
                    return v
            if n in ("rm", "mv", "unlink", "shred"):
                for x in op[:-1] if n == "mv" else op:
                    v = contiene(x, s)
                    if v:
                        return v
            if n in ("chmod", "chown") and any(
                    re.match(r"^-[A-Za-z]*R", a) or a == "--recursive" for a in args):
                for x in op:
                    v = contiene(x, s)
                    if v:
                        return v
        elif n in ("sed", "perl") and any(_RX_SED_SUL_POSTO.match(a) for a in args):
            for x in op:
                v = protetto(x, s)
                if v:
                    return v
        elif n in ("cp", "install", "rsync", "ln"):
            v = destinazione(op, s)
            if v:
                return v
            ricorsivo = n == "rsync" or any(
                re.match(r"^-[A-Za-z]*[rRa]", a) or a in ("--recursive", "--archive")
                for a in args)
            if ricorsivo and n != "ln" and op:
                # una copia ricorsiva dentro la cartella dei file protetti li puo'
                # sovrascrivere (`cp -r x/. ~/.plancia/`, `rsync -a x/ ~/.plancia/`)
                v = stato(op[-1], s)
                if v:
                    return v
        elif n == "dd":
            for a in args:
                if a.startswith("of="):
                    v = protetto(a[3:], s)
                    if v:
                        return v
        elif n == "find":
            radici = []
            for a in args:
                if a.startswith(("-", "(", "!")):
                    break
                radici.append(a)
            esegue = next((os.path.basename(args[i + 1]) for i, a in enumerate(args)
                           if a in ("-exec", "-execdir", "-ok", "-okdir")
                           and i + 1 < len(args)), None)
            if "-delete" in args or (esegue is not None and esegue not in _LETTURA_ESEC):
                for x in radici or ["."]:
                    v = stato(x, s) or protetto(x, s)
                    if v:
                        return v
        elif n == "curl":
            dest = valore_opzione(args, ("-o",), ("--output",))
            if dest:
                v = protetto(dest, s)
                if v:
                    return v
            if any(a in ("-O", "--remote-name", "--remote-name-all") for a in args) or any(
                    re.match(r"^-[A-Za-z]*O[A-Za-z]*$", a) for a in args):
                cartella = valore_opzione(args, (), ("--output-dir",)) or "."
                v = stato(cartella, s)
                if v:
                    return v
                for a in args:
                    if _RX_URL.match(a):
                        nome_file = os.path.basename(a.split("?", 1)[0].rstrip("/"))
                        v = protetto(os.path.join(cartella, nome_file), s)
                        if v:
                            return v
        elif n == "wget":
            dest = valore_opzione(args, ("-O",), ("--output-document",))
            if dest:
                v = protetto(dest, s)
                if v:
                    return v
            cartella = valore_opzione(args, ("-P",), ("--directory-prefix",)) or "."
            urls = [a for a in args if _RX_URL.match(a)]
            if urls:
                v = stato(cartella, s)
                if v:
                    return v
                for a in urls:
                    nome_file = os.path.basename(a.split("?", 1)[0].rstrip("/"))
                    v = protetto(os.path.join(cartella, nome_file), s)
                    if v:
                        return v
        elif n == "tar":
            estrae = _tar_estrae(args)
            cartella = valore_opzione(args, ("-C",), ("--directory",))
            if estrae:
                v = stato(cartella or ".", s)
                if v:
                    return v
            else:
                dest = valore_opzione(args, (), ("--file",))
                if dest is None and args and re.match(r"^-?[A-Za-z]*f[A-Za-z]*$", args[0]):
                    dest = args[1] if len(args) > 1 else None
                if dest:
                    v = protetto(dest, s)
                    if v:
                        return v
        elif n == "unzip":
            if not any(a in ("-l", "-p", "-t", "-v", "-Z", "-z") for a in args):
                v = stato(valore_opzione(args, ("-d",), ()) or ".", s)
                if v:
                    return v
        elif n == "git":
            salta, dir_git, sotto = False, None, None
            for i, a in enumerate(args):
                if salta:
                    salta = False
                elif a == "-C" and i + 1 < len(args):
                    dir_git = args[i + 1]
                    salta = True
                elif a in ("-c", "--git-dir", "--work-tree"):
                    salta = True
                elif not a.startswith("-"):
                    sotto = a
                    break
            if sotto in _GIT_SCRIVE:
                v = stato(dir_git or ".", s)
                if v:
                    return v
    # 3) codice dato a un interprete: usa la CLI o il pacchetto di Plancia per
    # cambiare la config, oppure nomina un file del guardiano (con un percorso
    # assoluto, o per nome: `.plancia` e `config.json`) E scrive
    if codice:
        testi = [t for s in an["segmenti"] if _e_interprete(s["nome"]) for t in s["args"]]
        testi += [t for t, _ in an["corpi"]]
        for t in testi:
            scrive = bool(_RX_CODICE_SCRIVE.search(t))
            if _RX_PKG_PLANCIA.search(t):
                if "save_config" in t:
                    return "config.save_config", "cli"
                if re.search(r"\bmain\s*\(|\bsys\.argv\b", t):
                    return "plancia.cli", "cli"
                if "CONFIG_FILE" in t and scrive:
                    return "CONFIG_FILE", "scrive"
            if scrive:
                if _RX_DATI_NOMINATI.search(t) and _RX_DATI_FILE.search(t):
                    return "config.json", "scrive"
                for c in _trova_percorsi_in_testo(t):
                    for n in [_norm(c, cwd)]:
                        if n and P.tag(n):
                            return n, "settings" if P.tag(n) == "settings" else "scrive"
    if "save_config" in cmd and codice:
        return "config.save_config", "cli"
    return None


def _valuta_protetti(nome, ti, ambito, chi, data_dir, mio, env=None):
    """Scrivere (o cancellare, o spostare) un file del guardiano, o cambiarne le
    impostazioni con la CLI di Plancia (`plancia config guardiano ...`), e'
    negato a TUTTE le sessioni, predefinito compreso. Leggere resta ammesso. Con
    Bash e' euristico (vedi `_scrive_un_protetto`). Vale solo in `bloccante`,
    come ogni diniego: chi vuole cambiare la config con l'aiuto di una sessione
    deve prima passare a `solo-registro`, o cambiarla a mano. Il file di
    impostazioni di Claude Code (settings.json, settings.local.json) e' protetto
    in modo MIRATO: Write/Edit/MultiEdit passano se il risultato ha ancora la
    voce del guardiano (vedi `_controlla_settings`), Bash no."""
    corto = _nome_corto(nome)
    cwd = chi["cwd"] or None
    cmd = ti.get("command")
    scrittura = corto in STRUMENTI_SCRITTURA
    if not scrittura and not (isinstance(cmd, str) and cmd):
        return None     # nessuno strumento che scrive e nessun comando: niente da guardare
    P = _Protetti(ambito, data_dir)
    if scrittura:
        for k in ("file_path", "notebook_path", "path"):
            if isinstance(ti.get(k), str):
                n = _norm(ti[k], cwd)
                t = P.tag(n) if n else None
                if t == "file":
                    return {"bersaglio": n, "proprietario": "il guardiano",
                            "motivo": "compartimento %s: %s e' un file del guardiano "
                                      "dei compartimenti: %s" % (mio, n, _MOTIVO_A_MANO)}
                if t == "settings":
                    perche = _controlla_settings(n, corto, ti, P)
                    if perche:
                        return {"bersaglio": n, "proprietario": "il guardiano",
                                "motivo": "compartimento %s: la modifica di %s %s"
                                          % (mio, n, perche)}
        return None
    r = _scrive_un_protetto(cmd, cwd, P, env)
    if not r:
        return None
    bersaglio, come = r
    if come == "cli":
        return {"bersaglio": bersaglio, "proprietario": "il guardiano",
                "motivo": "compartimento %s: il comando imposta la chiave %r di "
                          "config.json, che governa il guardiano dei compartimenti: %s"
                          % (mio, bersaglio, _MOTIVO_A_MANO)}
    if come == "settings":
        return {"bersaglio": bersaglio, "proprietario": "il guardiano",
                "motivo": "compartimento %s: il comando scrive %s: %s"
                          % (mio, bersaglio, _MOTIVO_SETTINGS)}
    if come == "ignota":
        return {"bersaglio": bersaglio, "proprietario": "il guardiano",
                "motivo": "compartimento %s: il comando scrive %s dopo un `cd` che non "
                          "si sa dove porta: scrivi percorsi assoluti" % (mio, bersaglio)}
    return {"bersaglio": bersaglio, "proprietario": "il guardiano",
            "motivo": "compartimento %s: %s e' un file del guardiano dei "
                      "compartimenti: %s" % (mio, bersaglio, _MOTIVO_A_MANO)}


def _percorso_nominato(p, chi, ambito, mio, ricorsivo=None):
    """Un percorso contro i permessi di TUTTI i compartimenti della sessione
    (di solito uno). Una cartella e' del nominato piu' specifico che la
    contiene: dentro `/w/alfa/beta` alfa non entra, anche se ha `/w/alfa`."""
    for nome in chi["nomi"]:
        c = ambito.nominati[nome]
        prop = ambito.proprietari_percorso(p)
        if prop == [nome]:
            # una ricerca che parte da qui entra anche nelle cartelle annidate
            # di un altro nominato
            for altro, ca in ambito.nominati.items():
                if altro == nome:
                    continue
                for f in ca["cartelle"]:
                    if _dentro(f, p) and _ric(ricorsivo, _prof(f, p)):
                        return {"bersaglio": p, "proprietario": altro,
                                "motivo": "compartimento %s: la ricerca in %s include "
                                          "%s, che appartiene a %s: restringi il "
                                          "percorso" % (mio, p, f, altro)}
            continue
        if len(prop) > 1 and nome in prop:
            return {"bersaglio": p, "proprietario": ",".join(prop),
                    "motivo": "compartimento %s: %s e' assegnata a piu' di un "
                              "compartimento (%s) dalla configurazione: incerta, "
                              "negata finche' non si ripara" % (mio, p, ",".join(prop))}
        if prop:
            return {"bersaglio": p, "proprietario": prop[0],
                    "motivo": "compartimento %s: %s appartiene a %s (fuori dai "
                              "permessi di %s)" % (mio, p, prop[0], nome)}
        if any(_dentro(p, n) for n in ambito.neutri()):
            continue
        if _scratch_ok(p, chi, ambito):
            continue
        if _progetto_ok(p, chi, nome in chi["da_codifica"]):
            continue
        prop = ambito.proprietario_specchio(p)
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
    parte da un antenato di un percorso vietato lo include: negata (se e'
    a profondita' limitata, solo se arriva fin li': `find . -maxdepth 1` no)."""
    for nome in ambito.proprietari_percorso(p)[:1]:
        return {"bersaglio": p, "proprietario": nome,
                "motivo": "compartimento %s: %s appartiene a %s" % (mio, p, nome)}
    for nome, c in ambito.nominati.items():
        for f in c["cartelle"]:
            if _dentro(f, p) and _ric(ricorsivo, _prof(f, p)):
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
    prop = ambito.specchio_incluso(p, ricorsivo)
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
            if _dentro(letterale, p) and _ric(ricorsivo, _prof(letterale, p)):
                return _divieto(p, mio, _RICERCA_INCLUDE)
        else:
            if _combacia_glob(glob, p):
                return _divieto(p, mio)
            # Una ricerca che parte proprio dal prefisso letterale del modello
            # (`<cartella>/PR-*`, ricerca in `<cartella>`) include i file che
            # combaciano: negata anche con p == letterale.
            if letterale and _dentro(letterale, p) and _ric(ricorsivo, _prof(letterale, p)):
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
                              "elenca o cerca fra sessioni di altri compartimenti "
                              "(per questa sessione passa session_id \"self\": senza "
                              "un id non e' certo che lo strumento agisca su di lei)"
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
