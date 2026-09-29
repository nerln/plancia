"""Il registro: cosa è successo, in un formato che possono leggere anche gli altri.

Plancia sa quando un lavoro parte, quando finisce, quando un task si chiude,
quando un post esce. Queste cose servono anche fuori: all'agente che scrive i
post serve sapere cosa è stato spedito, a una scorciatoia serve sapere quando un
lancio è finito.

Invece di inventare una API per ogni consumatore, c'è un file solo, in append,
una riga per evento, con uno schema dichiarato. Chi legge tiene un segnalibro e
riparte da lì. È il formato più noioso possibile, ed è il motivo per cui
funzionerà anche fra due anni.

    ~/.plancia/eventi.jsonl

Ogni riga:

    {"schema":"plancia.evento/1","id":"...","ts":"...Z","tipo":"lavoro.completato",
     "titolo":"...","progetto":"scriba","origine":"cantiere","dati":{...}}

Il file non viene mai riscritto, solo accodato, e viene ruotato quando supera i
cinque megabyte. Le vecchie righe finiscono in `eventi.1.jsonl`.
"""

import json
import os
import secrets
import threading

from . import config, store

SCHEMA = "plancia.evento/1"
FILE = config.DATA_DIR / "eventi.jsonl"
MAX_BYTE = 5 * 1024 * 1024

# I tipi che Plancia emette. Chi legge dovrebbe ignorare quelli che non conosce
# invece di rompersi: l'elenco crescerà.
TIPI = (
    "lavoro.avviato",       # un agente è partito su un task
    "lavoro.completato",    # ha finito bene
    "lavoro.fallito",       # ha finito male
    "task.creato",
    "task.chiuso",
    "post.pubblicato",
    "progetto.archiviato",
    "progetto.aggiornato",
    "riepilogo.pronto",
)

_lucchetto = threading.Lock()


def scrivi(tipo: str, titolo: str = "", progetto=None, dati=None, origine="plancia") -> dict:
    """Accoda un evento. Non solleva mai: il registro non deve poter rompere
    il lavoro che sta registrando."""
    evento = {
        "schema": SCHEMA,
        "id": secrets.token_hex(8),
        "ts": store.now(),
        "tipo": tipo,
        "titolo": titolo or "",
        "progetto": progetto if isinstance(progetto, str) else None,
        "origine": origine,
        "dati": dati or {},
    }
    try:
        config.ensure_dirs()
        with _lucchetto:
            _ruota()
            with open(FILE, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(evento, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass
    return evento


def _ruota():
    try:
        if FILE.exists() and FILE.stat().st_size > MAX_BYTE:
            FILE.replace(FILE.with_suffix(".1.jsonl"))
    except Exception:
        pass


# Quanto si legge dal fondo prima di rassegnarsi a leggere tutto. A duecento
# byte per evento sono più di mille eventi: nessuno che tenga un segnalibro
# resta indietro di così tanto, e il pannello vocale chiede ogni sei secondi.
CODA = 256 * 1024


def _righe(path, solo_coda=True) -> list:
    """Le righe di un file, leggendo dal fondo quando basta."""
    fuori = []
    try:
        dimensione = path.stat().st_size
    except OSError:
        return fuori
    try:
        with open(path, "rb") as fh:
            if solo_coda and dimensione > CODA:
                fh.seek(dimensione - CODA)
                fh.readline()  # la prima riga è tagliata a metà
            for riga in fh:
                try:
                    fuori.append(json.loads(riga.decode("utf-8")))
                except Exception:
                    continue
    except OSError:
        pass
    return fuori


def leggi(dopo: str = None, tipo: str = None, limite: int = 100, filtro=None) -> list:
    """Gli eventi dopo un certo id, in ordine. Senza `dopo` torna gli ultimi.

    `dopo` è l'id dell'ultimo evento già visto: è il segnalibro del consumatore.

    `filtro` (una funzione evento -> bool) toglie gli eventi che non passano
    PRIMA del taglio agli ultimi `limite`: chi guarda un registro lungo da dentro
    un compartimento (vedi compartimenti_viste.py) trova i suoi anche se gli
    ultimi mille sono di altri. Se nella coda letta ne passano meno di `limite`
    si legge tutto, anche il file ruotato."""
    def selezione(righe):
        if dopo:
            for i, e in enumerate(righe):
                if e.get("id") == dopo:
                    righe = righe[i + 1:]
                    break
        if tipo:
            voluti = {t.strip() for t in tipo.split(",") if t.strip()}
            righe = [e for e in righe if e.get("tipo") in voluti]
        if filtro:
            righe = [e for e in righe if filtro(e)]
        if not dopo:
            righe = righe[-limite:]
        return righe[:limite]

    righe = _righe(FILE)
    trovato = any(e.get("id") == dopo for e in righe) if dopo else True
    scelte = selezione(righe) if trovato else None
    if not trovato or (not dopo and (len(righe) < limite or (
            filtro and len(scelte) < limite))):
        # il segnalibro è più indietro della coda: si legge tutto, anche il
        # file ruotato
        righe = _righe(FILE.with_suffix(".1.jsonl"), solo_coda=False) + \
            _righe(FILE, solo_coda=False)
        scelte = selezione(righe)
    return scelte


def ultimo_id() -> str:
    righe = leggi(limite=1)
    return righe[-1]["id"] if righe else ""


def stato() -> dict:
    n = 0
    try:
        with open(FILE, encoding="utf-8") as fh:
            n = sum(1 for _ in fh)
    except OSError:
        pass
    return {"file": str(FILE), "schema": SCHEMA, "eventi": n,
            "byte": FILE.stat().st_size if FILE.exists() else 0,
            "tipi": list(TIPI)}
