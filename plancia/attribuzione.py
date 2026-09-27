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

import os
import re

from . import config

# ---------------------------------------------------------------------------
# percorsi dentro i tool_use
# ---------------------------------------------------------------------------

#: Un percorso assoluto dentro un comando di shell finisce dove comincia la
#: sintassi della shell. Le graffe, gli asterischi e i due punti tagliano anche
#: `*.py` e `file.py:42`: quello che resta è la cartella, che è quello che serve.
_CORPO = r"[^\s'\"`;|&$()<>\\*?{}\[\]:,]*"
_INIZIO = r"(?:/Users/|/Volumes/)"
QUOTATO = re.compile(r"""['"](""" + _INIZIO + r"""[^'"]*)['"]""")
NUDO = re.compile(_INIZIO + _CORPO)
#: I glob cominciano a valere dal primo carattere speciale: sopra c'è la cartella.
GLOB = re.compile(r"[*?\[{]")
#: Le cartelle usa e getta dei collaudi, che nascono e muoiono ogni giro.
TEMPORANEA = re.compile(
    r"^(/private)?/(tmp|var/folders)(/|$)|(^|/)drift-[a-z0-9_]+(/|$)")

CHIAVI_PERCORSO = ("file_path", "path", "notebook_path")
CHIAVI_GLOB = ("pattern", "glob")


def _pulisci(percorso: str) -> str:
    percorso = percorso.strip().rstrip(".,;:)]}'\"")
    if len(percorso) > 1:
        percorso = percorso.rstrip("/")
    return percorso


def base_di_glob(valore: str) -> str:
    """La cartella sopra il primo carattere di glob: `/a/b/*.py` → `/a/b`."""
    m = GLOB.search(valore)
    testa = valore[:m.start()] if m else valore
    if not m and not testa.endswith("/"):
        testa = os.path.dirname(testa) or testa
    return _pulisci(testa)


def percorsi_da_comando(comando: str) -> list:
    """I percorsi assoluti dentro un comando di shell, virgolette comprese.

    Le virgolette si guardano per prime e poi si cancellano: dentro ci stanno gli
    spazi, e la radice del Drive si chiama «Il mio Drive». Cercando prima i
    token nudi, quella diventerebbe tre percorsi diversi e nessuno buono.
    """
    if not comando or "/Users/" not in comando and "/Volumes/" not in comando:
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
    # `/Users/eugenionerelli` da solo non è un posto: sotto ai tre livelli non
    # c'è ancora nessun progetto.
    return [p for p in fuori if p.count("/") >= 3]


def percorsi_da_tool_use(blocco: dict) -> list:
    """I percorsi assoluti che un singolo `tool_use` dichiara di toccare."""
    dentro = blocco.get("input")
    if not isinstance(dentro, dict):
        return []
    fuori = []
    for chiave in CHIAVI_PERCORSO:
        valore = dentro.get(chiave)
        if isinstance(valore, str) and valore.startswith("/"):
            fuori.append(_pulisci(valore))
    for chiave in CHIAVI_GLOB:
        valore = dentro.get(chiave)
        if isinstance(valore, str) and valore.startswith("/"):
            base = base_di_glob(valore)
            if base.count("/") >= 2:
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
        "/Volumes/AppsAndFiles/dev",
    }
    if drive:
        fuori.add(os.path.normpath(str(drive)))
        fuori.add(os.path.normpath(os.path.join(str(drive), "Lavoro")))
        fuori.add(os.path.normpath(os.path.join(str(drive), "Personale")))
    return fuori


#: Le cartelle sotto cui ogni sottocartella immediata è un progetto a sé.
def contenitori(home=None, drive=None) -> list:
    home = str(home or config.HOME)
    fuori = [os.path.join(home, "dev"), os.path.join(home, "Siti"),
             os.path.join(home, "dev/siti"), "/Volumes/AppsAndFiles/dev"]
    if drive:
        fuori += [os.path.join(str(drive), "Lavoro"), os.path.join(str(drive), "Personale")]
    return [os.path.normpath(p) for p in fuori]


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
    return {r for r in fuori
            if r and r != os.sep and r not in generiche
            and not any(r == b or r.startswith(b + os.sep) for b in fuori_sempre)}


# ---------------------------------------------------------------------------
# la decisione
# ---------------------------------------------------------------------------

def categoria(cwd: str, interne=None) -> str:
    """`interna` per le chiamate che Plancia fa a sé, `temporanea` per i collaudi."""
    if not cwd:
        return "progetto"
    normale = os.path.normpath(cwd)
    interne = interne if interne is not None else {os.path.normpath(str(config.DATA_DIR))}
    for base in interne:
        if base and (normale == base or normale.startswith(base + os.sep)):
            return "interna"
    if TEMPORANEA.search(normale):
        return "temporanea"
    return "progetto"


def radice_di(percorso: str, radici_ordinate) -> str:
    """La radice nota più profonda che contiene questo percorso."""
    if not percorso:
        return None
    normale = os.path.normpath(percorso)
    for radice in radici_ordinate:
        if normale == radice or normale.startswith(radice + os.sep):
            return radice
    return None


def conta(percorsi, radici) -> dict:
    """Quante volte ogni radice è stata toccata, e a che punto la prima volta.

    L'ordine serve solo a rompere i pareggi: fra due cartelle toccate lo stesso
    numero di volte vince quella toccata per prima, che è quasi sempre quella da
    cui si è partiti.
    """
    ordinate = sorted({os.path.normpath(r) for r in radici if r}, key=len, reverse=True)
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
    generiche = {os.path.normpath(g) for g in generiche if g}
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

    ordinate = sorted({os.path.normpath(r) for r in radici if r}, key=len, reverse=True)
    cwd_radice = radice_di(cwd_n, ordinate) if cwd_n else None
    cwd_nota = bool(cwd_radice) and cwd_n not in generiche

    if not cwd_nota:
        if radice:
            esito["dir"], esito["da"] = radice, "percorsi"
        return esito

    esito["dir"], esito["da"] = cwd_radice, "cwd"
    if radice and radice != cwd_radice and totale and quante / totale >= SOGLIA_SCAVALCO:
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
