"""Il progetto su cui una sessione ha davvero lavorato.

Fino a qui una sessione finiva nel progetto della cartella da cui era stata
aperta. Per Codex funziona, perché Codex si apre dentro il progetto. Per Claude
Code no: misurato il 3 settembre 2026 su 903 sessioni, 235 erano aperte dalla
radice del Drive, 102 da ~/.plancia, 18 da ~/dev. Cartelle da cui si lavora a
tutto, e che quindi non dicono niente. Il catalogo ne usciva con un progetto
"dev" da 342 sessioni e un "Senza progetto" da 182: la metà dell'archivio in due
scatole che non sono progetti.

Quello che una sessione ha toccato invece sta scritto nei suoi `tool_use`: i file
letti e scritti, e i percorsi assoluti dentro i comandi Bash. La cartella che
compare più spesso dice il progetto molto meglio della cartella di apertura.

Qui dentro non si tocca il database: sono funzioni pure, così si possono provare
senza costruire un archivio. Chi le usa è `ingest`.
"""

import json
import os
import re
import ntpath

from . import config

# ---------------------------------------------------------------------------
# percorsi dentro i tool_use
# ---------------------------------------------------------------------------

#: Un percorso assoluto dentro un comando di shell finisce dove comincia la
#: sintassi della shell. Le graffe, gli asterischi e i due punti tagliano anche
#: `*.py` e `file.py:42`: quello che resta è la cartella, che è quello che serve.
_CORPO = r"[^\s'\"`;|&$()<>\\*?{}\[\]:,]*"
_INIZIO = r"(?:/Users/|/Volumes/)"
#: Windows: `C:\Users\x\progetto` o `C:/Users/x/progetto`, su qualsiasi unita'. Nel
#: corpo il rovescio e' un separatore, non una fuga come nella shell. La lettera
#: deve aprire un token: all'inizio del comando, dopo uno spazio, una virgoletta,
#: una parentesi, un `=` o un operatore. Non e' un disco `https://` (la lettera ne
#: segue un'altra) e non lo e' una lettera con i due punti in mezzo a
#: un'espressione: `sed 's/a:\/b\/c/x/'`.
_INIZIO_WIN = r"(?<![^\s'\"`(=;|&<>])[A-Za-z]:[\\/]"
#: UNC: `\\server\condivisione\...`, con il nome del server e quello della
#: condivisione. Anche dentro un comando.
_INIZIO_UNC = r"(?<![\\\w])\\\\(?=[^\s'\"\\/]+[\\/][^\s'\"\\/])"
_CORPO_WIN = r"[^\s'\"`;|&$()<>*?{}\[\]:,]*"
QUOTATO = re.compile(r"""['"]((?:""" + _INIZIO + "|" + _INIZIO_WIN + "|" + _INIZIO_UNC
                     + r""")[^'"]*)['"]""")
NUDO = re.compile(_INIZIO + _CORPO + "|" + _INIZIO_WIN + _CORPO_WIN
                  + "|" + _INIZIO_UNC + _CORPO_WIN)
#: Basta la testa di un percorso di Windows per sapere se un comando ne contiene.
NUDO_WIN_ANCHE = re.compile(_INIZIO_WIN + "|" + _INIZIO_UNC)
#: Un percorso assoluto di Windows (lettera e due punti, oppure UNC).
ASSOLUTO_WIN = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\)")
#: Un separatore, dell'una o dell'altra famiglia.
SEPARATORE = re.compile(r"[\\/]")
#: I glob cominciano a valere dal primo carattere speciale: sopra c'è la cartella.
GLOB = re.compile(r"[*?\[{]")
#: Le cartelle usa e getta dei collaudi, che nascono e muoiono ogni giro. Il
#: separatore e' l'uno o l'altro: `categoria` riceve il percorso normalizzato dal
#: sistema su cui si gira, e su Windows `/private/tmp/x` (il percorso di un
#: transcript di Mac) diventa `\private\tmp\x`.
TEMPORANEA = re.compile(
    r"^([\\/]private)?[\\/](tmp|var[\\/]folders)([\\/]|$)"
    r"|(^|[\\/])drift-[a-z0-9_]+([\\/]|$)"
    r"|[\\/](?i:AppData[\\/]Local[\\/]Temp)([\\/]|$)")

CHIAVI_PERCORSO = ("file_path", "path", "notebook_path")
CHIAVI_GLOB = ("pattern", "glob")


def e_assoluto(valore) -> bool:
    """Un percorso assoluto POSIX (`/...`) o di Windows (`C:\\...`, `C:/...`, UNC).
    Si guarda la forma, non il sistema su cui si gira: il transcript di una
    sessione di Windows si puo' leggere anche altrove."""
    return isinstance(valore, str) and (
        valore.startswith("/") or bool(ASSOLUTO_WIN.match(valore)))


def senza_barra_finale(percorso: str) -> str:
    """Il percorso senza la barra finale: `/a/b/` diventa `/a/b`. Per un percorso di
    Windows si tolgono anche i rovesci (`C:\\a\\b\\` diventa `C:\\a\\b`), e la
    radice dell'unita' resta `C:\\`. Un percorso POSIX si tratta com'e' sempre."""
    if ASSOLUTO_WIN.match(percorso):
        resto = percorso.rstrip("\\/")
        return resto if len(resto) > 2 else percorso[:3]
    return percorso.rstrip("/")


def nome_cartella(percorso: str) -> str:
    """L'ultimo pezzo di un percorso, senza la barra finale: `/a/b/` da' `b`,
    `C:\\a\\b\\` pure. Con le regole della famiglia di percorsi a cui appartiene."""
    pulito = senza_barra_finale(percorso)
    if ASSOLUTO_WIN.match(pulito):
        return ntpath.basename(pulito)
    return os.path.basename(pulito)


def e_dentro(radice: str, percorso: str) -> bool:
    """`radice` e' `percorso` o una cartella che lo contiene, sui confini di
    cartella (`/a/bar` non sta sotto `/a/b`). Per i percorsi di Windows non contano
    le maiuscole ne' il tipo di barra; per gli altri e' il confronto di sempre."""
    if ASSOLUTO_WIN.match(radice) or ASSOLUTO_WIN.match(percorso):
        a = ntpath.normcase(ntpath.normpath(radice))
        b = ntpath.normcase(ntpath.normpath(percorso))
        return bool(a) and (b == a or b.startswith(a.rstrip("\\") + "\\"))
    return bool(radice) and (percorso == radice or percorso.startswith(radice + "/"))


def _pulisci(percorso: str) -> str:
    percorso = percorso.strip().rstrip(".,;:)]}'\"")
    if len(percorso) > 1:
        if ASSOLUTO_WIN.match(percorso):
            # `C:\` e `C:/` sono la radice dell'unita': la barra finale resta
            resto = percorso.rstrip("\\/")
            percorso = resto if len(resto) > 2 else percorso[:3]
        else:
            percorso = percorso.rstrip("/")
    return percorso


def _k(percorso: str) -> str:
    """Un percorso come si CONFRONTA: normalizzato e, dove il sistema non distingue
    le maiuscole (Windows), tutto minuscolo con una sola forma di separatore. Su
    macOS e Linux `normcase` non fa niente: e' `os.path.normpath` di sempre. Si
    confronta con questo e si restituisce la grafia originale."""
    return os.path.normcase(os.path.normpath(percorso))


def _dirname(percorso: str) -> str:
    """La cartella che contiene `percorso`, con le regole della famiglia di
    percorsi a cui appartiene."""
    if ASSOLUTO_WIN.match(percorso):
        return ntpath.dirname(percorso)
    return os.path.dirname(percorso)


def _livelli(percorso: str) -> int:
    """Quanti separatori ha un percorso (`/Users/x/p` ne ha 3, `C:\\Users\\x\\p`
    pure). Serve a scartare `/Users/x` da solo e simili: non e' ancora un progetto."""
    return len(SEPARATORE.findall(percorso)) if ASSOLUTO_WIN.match(percorso) \
        else percorso.count("/")


def base_di_glob(valore: str) -> str:
    """La cartella sopra il primo carattere di glob: `/a/b/*.py` → `/a/b`."""
    m = GLOB.search(valore)
    testa = valore[:m.start()] if m else valore
    if not m and not testa.endswith(("/", "\\") if ASSOLUTO_WIN.match(testa) else "/"):
        testa = _dirname(testa) or testa
    return _pulisci(testa)


def percorsi_da_comando(comando: str) -> list:
    """I percorsi assoluti dentro un comando di shell, virgolette comprese.

    Le virgolette si guardano per prime e poi si cancellano: dentro ci stanno gli
    spazi, e la radice del Drive si chiama «Il mio Drive». Cercando prima i
    token nudi, quella diventerebbe tre percorsi diversi e nessuno buono.
    """
    if not comando or ("/Users/" not in comando and "/Volumes/" not in comando
                       and not NUDO_WIN_ANCHE.search(comando)):
        return []
    fuori, resto = [], []
    fine = 0
    for m in QUOTATO.finditer(comando):
        fuori.append(_pulisci(m.group(1)))
        resto.append(comando[fine:m.start()])
        fine = m.end()
    resto.append(comando[fine:])
    for m in NUDO.finditer(" ".join(resto)):
        fuori.append(_pulisci(m.group(0)))
    # `/Users/nome` da solo non è un posto: sotto ai tre livelli non
    # c'è ancora nessun progetto.
    return [p for p in fuori if _livelli(p) >= 3]


def percorsi_da_tool_use(blocco: dict) -> list:
    """I percorsi assoluti che un singolo `tool_use` dichiara di toccare."""
    dentro = blocco.get("input")
    if not isinstance(dentro, dict):
        return []
    fuori = []
    for chiave in CHIAVI_PERCORSO:
        valore = dentro.get(chiave)
        if e_assoluto(valore):
            fuori.append(_pulisci(valore))
    for chiave in CHIAVI_GLOB:
        valore = dentro.get(chiave)
        if e_assoluto(valore):
            base = base_di_glob(valore)
            if _livelli(base) >= 2:
                fuori.append(base)
    comando = dentro.get("command")
    if isinstance(comando, str):
        fuori.extend(percorsi_da_comando(comando))
    return [p for p in fuori if p]


# ---------------------------------------------------------------------------
# le radici note
# ---------------------------------------------------------------------------

def radici_generiche(home=None, drive=None) -> set:
    """Le cartelle da cui si lavora a tutto: non identificano un progetto."""
    home = str(home or config.HOME)
    fuori = {
        os.path.normpath(home),
        os.path.normpath(os.path.join(home, "dev")),
        os.path.normpath(os.path.join(home, "Siti")),
        os.path.normpath(os.path.join(home, "dev/siti")),
        os.path.normpath(os.path.join(home, "Documents/Codex")),
        os.path.normpath(str(config.DATA_DIR)),
    }
    fuori.update(contenitori_extra())
    if drive:
        fuori.add(os.path.normpath(str(drive)))
        fuori.add(os.path.normpath(os.path.join(str(drive), "Lavoro")))
        fuori.add(os.path.normpath(os.path.join(str(drive), "Personale")))
    return fuori


def contenitori_extra() -> list:
    """I contenitori scritti a mano in config.json (chiave `contenitori`, una lista
    di percorsi): un disco esterno, un'altra cartella dei progetti. Nessun percorso
    di nessuna macchina sta nel codice. Una chiave scritta male vale come assente."""
    try:
        dati = json.loads(config.CONFIG_FILE.read_text("utf-8"))
    except Exception:
        return []
    voci = dati.get("contenitori") if isinstance(dati, dict) else None
    if not isinstance(voci, list):
        return []
    return [os.path.normpath(os.path.expanduser(v)) for v in voci
            if isinstance(v, str) and v.strip()]


#: Le cartelle sotto cui ogni sottocartella immediata è un progetto a sé.
def contenitori(home=None, drive=None) -> list:
    home = str(home or config.HOME)
    fuori = [os.path.join(home, "dev"), os.path.join(home, "Siti"),
             os.path.join(home, "dev/siti")]
    if drive:
        fuori += [os.path.join(str(drive), "Lavoro"), os.path.join(str(drive), "Personale")]
    fuori += contenitori_extra()
    return [os.path.normpath(p) for p in fuori]


def contenitori_avviso(home=None, drive=None) -> list:
    """I contenitori per l'avviso di `bin/plancia-hook` ("questa sessione e' aperta
    in una cartella contenitore"): quelli di `contenitori()` piu' la radice del
    Drive, che non e' un progetto e nemmeno la casa di uno. L'hook non importa il
    pacchetto e ricalcola la stessa lista da solo: una prova li confronta."""
    fuori = ([os.path.normpath(str(drive))] if drive else []) + contenitori(home, drive)
    visti, elenco = set(), []
    for p in fuori:
        if p not in visti:
            visti.add(p)
            elenco.append(p)
    return elenco


def radici_note(conn=None, home=None, drive=None) -> set:
    """Tutte le cartelle che valgono come progetto.

    Due fonti: quelle che Plancia già conosce (i link dei progetti e i repo
    locali) e le sottocartelle immediate dei contenitori. Le radici generiche
    restano fuori anche se qualcuno le ha legate a un progetto: `~/dev` è legata
    al progetto "dev", ed è per questo che quel progetto si è mangiato tutte le
    cartelle sotto.
    """
    generiche = radici_generiche(home, drive)
    # La macchina di Claude non e' un progetto. Le skill, i transcript e i file
    # di memoria li tocca ogni sessione: misurato il 3 settembre 2026, tenerli
    # dentro attribuiva a «.claude» trentatre sessioni, fra cui otto «X account
    # daily check» che avevano solo letto la skill, e un lavoro sul paper di
    # Taekwondo vinto per un percorso di scarto su ventuno.
    fuori_sempre = (os.path.normpath(str(config.CLAUDE_DIR)),
                    os.path.normpath(str(config.DATA_DIR)))
    fuori = set()
    if conn is not None:
        for tabella, colonna in (("project_links", "value"), ("repos", "local_path")):
            try:
                righe = conn.execute(
                    f"SELECT {colonna} AS v FROM {tabella} "
                    + ("WHERE kind='path'" if tabella == "project_links" else
                       "WHERE local_path IS NOT NULL AND local_path <> ''")).fetchall()
            except Exception:
                continue
            for riga in righe:
                if riga["v"]:
                    fuori.add(os.path.normpath(riga["v"]))
    for base in contenitori(home, drive):
        try:
            voci = os.scandir(base)
        except OSError:
            continue
        with voci:
            for voce in voci:
                if voce.is_dir() and not voce.name.startswith("."):
                    fuori.add(os.path.normpath(voce.path))
    generiche_k = {_k(g) for g in generiche}
    fuori_sempre_k = [_k(b) for b in fuori_sempre]
    return {r for r in fuori
            if r and r != os.sep and _k(r) not in generiche_k
            and not any(_k(r) == b or _k(r).startswith(b + os.sep) for b in fuori_sempre_k)}


# ---------------------------------------------------------------------------
# la decisione
# ---------------------------------------------------------------------------

def categoria(cwd: str, interne=None) -> str:
    """`interna` per le chiamate che Plancia fa a sé, `temporanea` per i collaudi."""
    if not cwd:
        return "progetto"
    normale = os.path.normpath(cwd)
    interne = interne if interne is not None else {os.path.normpath(str(config.DATA_DIR))}
    confronto = _k(normale)
    for base in interne:
        base = _k(base) if base else base
        if base and (confronto == base or confronto.startswith(base + os.sep)):
            return "interna"
    if TEMPORANEA.search(normale):
        return "temporanea"
    return "progetto"


def radice_di(percorso: str, radici_ordinate) -> str:
    """La radice nota più profonda che contiene questo percorso."""
    if not percorso:
        return None
    normale = _k(percorso)
    for radice in radici_ordinate:
        r = _k(radice)
        if normale == r or normale.startswith(r + os.sep):
            return radice
    return None


def _uniche(radici) -> list:
    """Le radici normalizzate, una sola per ogni modo di scriverla (dove le
    maiuscole non contano) e nella grafia della prima incontrata."""
    viste = {}
    for r in radici:
        if r:
            viste.setdefault(_k(r), os.path.normpath(r))
    return list(viste.values())


def conta(percorsi, radici) -> dict:
    """Quante volte ogni radice è stata toccata, e a che punto la prima volta.

    L'ordine serve solo a rompere i pareggi: fra due cartelle toccate lo stesso
    numero di volte vince quella toccata per prima, che è quasi sempre quella da
    cui si è partiti.
    """
    ordinate = sorted(_uniche(radici), key=len, reverse=True)
    fuori = {}
    for i, percorso in enumerate(percorsi):
        radice = radice_di(percorso, ordinate)
        if not radice:
            continue
        voce = fuori.get(radice)
        if voce is None:
            fuori[radice] = [1, i]
        else:
            voce[0] += 1
    return fuori


def dominante(conteggi: dict):
    """(radice, quante, totale) della cartella toccata di più."""
    if not conteggi:
        return None, 0, 0
    totale = sum(v[0] for v in conteggi.values())
    radice = min(conteggi.items(), key=lambda kv: (-kv[1][0], kv[1][1]))[0]
    return radice, conteggi[radice][0], totale


#: Quanto deve pesare una cartella diversa per scavalcare una cwd che è già un
#: progetto vero. Sotto questa soglia si tiene la cwd: aprire una sessione in un
#: progetto e leggere due file di un altro è normale, e non cambia di chi è il
#: lavoro.
SOGLIA_SCAVALCO = 0.70


def decidi(cwd, percorsi, radici, generiche=None, interne=None) -> dict:
    """Su quale cartella ha lavorato questa sessione, e come si è deciso.

    `percorsi` sono i percorsi assoluti toccati, nell'ordine in cui compaiono.
    Torna `dir`, `da` ('cwd', 'percorsi' o 'nessuno'), `n` (quanti percorsi hanno
    contato) e `categoria`.
    """
    generiche = generiche if generiche is not None else radici_generiche()
    generiche = {_k(g) for g in generiche if g}
    cwd_n = os.path.normpath(cwd) if cwd else ""
    cat = categoria(cwd_n, interne)
    conteggi = conta(percorsi or [], radici)
    radice, quante, totale = dominante(conteggi)
    esito = {"dir": None, "da": "nessuno", "n": totale, "categoria": cat}

    if cat != "progetto":
        # una cartella temporanea o una chiamata interna resta quello che è:
        # non è un progetto e non deve diventarlo
        esito["dir"] = cwd_n or None
        esito["da"] = "cwd" if cwd_n else "nessuno"
        return esito

    ordinate = sorted(_uniche(radici), key=len, reverse=True)
    cwd_radice = radice_di(cwd_n, ordinate) if cwd_n else None
    cwd_nota = bool(cwd_radice) and _k(cwd_n) not in generiche

    if not cwd_nota:
        if radice:
            esito["dir"], esito["da"] = radice, "percorsi"
        return esito

    esito["dir"], esito["da"] = cwd_radice, "cwd"
    if radice and _k(radice) != _k(cwd_radice) and totale and quante / totale >= SOGLIA_SCAVALCO:
        esito["dir"], esito["da"] = radice, "percorsi"
    return esito


# ---------------------------------------------------------------------------
# memoria fra un sync e l'altro
# ---------------------------------------------------------------------------

def fondi(vecchi: dict, nuovi: dict) -> dict:
    """I conteggi di prima più quelli dei byte appena letti.

    Il sync incrementale legge solo la coda del transcript: senza sommare, una
    sessione lunga verrebbe attribuita in base al suo ultimo pezzo.
    """
    fuori = {k: list(v) for k, v in (vecchi or {}).items()}
    salto = max((v[1] for v in fuori.values()), default=-1) + 1
    for radice, valore in (nuovi or {}).items():
        n, primo = (valore if isinstance(valore, (list, tuple)) else (valore, 0))
        if radice in fuori:
            fuori[radice][0] += n
        else:
            fuori[radice] = [n, salto + primo]
    return fuori


def percorsi_finti(conteggi: dict) -> list:
    """Rimette in fila dei percorsi coerenti con dei conteggi già salvati.

    Serve a far passare `decidi` anche quando i percorsi veri non ci sono più,
    perché sono stati letti in un sync di ieri.
    """
    ordinate = sorted(conteggi.items(), key=lambda kv: kv[1][1])
    fuori = []
    for radice, (n, _) in ordinate:
        fuori.extend([radice] * n)
    return fuori
