"""Propone, applica e annulla la mappa dei padri (verdetto §A, L1-RIORDINA).

`slot.set_parent` sa assegnare un padre e rifiutarlo con un motivo; sa
`slot.annulla` disfare un batch. Quello che manca è la parte DECIDE (verdetto
§A, punto 7, "reversibilità come relazione"): calcolare *quale* padre proporre
per ogni progetto automatico senza uno, scriverlo in un file che Eugenio può
leggere e correggere a mano, e solo dopo la sua occhiata applicarlo. Questo
modulo fa quella parte; non tocca `projects` finché non è `--applica`.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from . import attribuzione, config, slot, store

# I tre progetti "infra" che plancia/ingest.py:progetto_per_cartella crea da
# solo per lavoro che non è un progetto vero (chiamate interne di Plancia,
# sessioni temporanee, cartelle senza nome riconoscibile). Sono auto=1 come
# qualunque scheda automatica, ma proporgli un padre non ha senso: non sono
# lavoro da riordinare sotto un filone, sono lo scarico del sistema. Le chiavi
# sono copiate da ingest.py; se là cambiano, vanno cambiate anche qui.
INFRA_SPECIALI = {"plancia-interno", "temporanee", "drive-workspace"}

# Dove finiscono, con --resto-in-cartelle-viste, i progetti a cui nessuna
# regola ha trovato un padre: un bucket manuale (auto=0) come un altro, non
# uno dei tre sopra (quelli restano invisibili, questo va visto).
CARTELLE_VISTE = "cartelle-viste"


def _candidati(conn):
    """I progetti a cui la mappa può proporre un padre.

    Un manuale (auto=0) resta sempre un padre possibile, mai un figlio:
    lo dice il verdetto (§A) e lo controlla comunque `slot.set_parent`, ma
    filtrarlo qui evita che compaia tra i "nessuna" di `--mostra`, dove
    sembrerebbe un progetto dimenticato invece che una radice per scelta.
    Un progetto che ha già dei figli (auto o no: vedi sotto) resta fuori per
    lo stesso motivo dei manuali: diventerebbe lui un figlio, e i suoi figli
    dei nipoti, cosa che `set_parent` rifiuta comunque ma che qui è meglio
    non proporre nemmeno.
    """
    figli_di = {
        r["parent_id"] for r in
        conn.execute("SELECT DISTINCT parent_id FROM projects WHERE parent_id IS NOT NULL")
    }
    righe = conn.execute(
        "SELECT * FROM projects WHERE parent_id IS NULL AND auto=1"
    ).fetchall()
    return [
        r for r in righe
        if r["id"] not in figli_di
        and not (r["kind"] == "infra" and r["key"] in INFRA_SPECIALI)
    ]


def _links(conn, project_id, kind):
    return [
        r["value"] for r in conn.execute(
            "SELECT value FROM project_links WHERE project_id=? AND kind=?",
            (project_id, kind),
        ).fetchall()
    ]


def _dentro(link_valore, valore):
    """`link_valore` è prefisso di `valore` sui confini di cartella. Stessa
    regola di `slot._prefisso_path`, ripetuta qui invece di importare un
    nome privato di un altro file (slot.py non è di proprietà di questo
    lotto: non lo si tocca, e non ci si aggancia ai suoi dettagli interni)."""
    link_valore = attribuzione.senza_barra_finale(link_valore)
    valore = attribuzione.senza_barra_finale(valore)
    return attribuzione.e_dentro(link_valore, valore)


def _radice(conn, manuale):
    """Se `manuale` è a sua volta figlio di una radice, torna la riga della
    radice; altrimenti torna `manuale` stesso. Un padre proposto è sempre
    di profondità 0: `slot.set_parent` rifiuta un padre che ha già un
    padre, quindi proporre un figlio come padre sarebbe solo un rifiuto
    rimandato a `--applica`."""
    if not manuale["parent_id"]:
        return manuale
    riga = conn.execute("SELECT * FROM projects WHERE id=?", (manuale["parent_id"],)).fetchone()
    return riga or manuale


def _regola_path(conn, progetto):
    """Un link `path` del progetto sta davvero dentro il link path di un
    manuale (radice, o figlio: in quel caso si risale alla radice).

    Il contenimento è verificato qui, non con `slot.padre_per_path`:
    quella funzione applica *due* regole indipendenti sulla stessa cwd, il
    contenimento del percorso e "il nome della cartella comincia con
    <chiave manuale>-" (slot.py, docstring di padre_per_path, regola 2).
    Chiamarla e etichettare qualunque suo esito come "path" scriveva un
    motivo falso ("sta dentro") per i casi presi dalla seconda regola, che
    è un indizio più debole (una somiglianza di nome, non un contenimento):
    quei casi finiscono sotto la regola "prefisso" (vedi `_regola_prefisso`),
    con un motivo che dice cosa è successo davvero.
    """
    manuali = conn.execute("SELECT * FROM projects WHERE auto=0").fetchall()
    for valore in _links(conn, progetto["id"], "path"):
        migliore, punteggio = None, -1
        for m in manuali:
            for link_valore in _links(conn, m["id"], "path"):
                if _dentro(link_valore, valore) and len(
                        attribuzione.senza_barra_finale(link_valore)) > punteggio:
                    migliore, punteggio = m, len(attribuzione.senza_barra_finale(link_valore))
        if migliore is None:
            continue
        radice = _radice(conn, migliore)
        if radice["key"] != progetto["key"]:
            return radice["key"], f"il percorso «{valore}» sta dentro quello di «{radice['key']}»"
    return None, ""


def _regola_repo(conn, progetto):
    """Il progetto è la cartella locale di un repository che un manuale
    radice rivendica con un proprio link `repo`.

    `project_links` ha `UNIQUE(kind, value)` (store.py:45): un valore di
    link `repo` appartiene quindi a un solo progetto per volta, e non può
    esistere un manuale *e* un progetto candidato con lo stesso link `repo`
    da confrontare (`store.link_project` sposterebbe il link su uno dei
    due, mai copiarlo su entrambi). Il match vero è un altro: la chiave del
    candidato, o il basename di un suo link `path` (la cartella dove sta il
    checkout), coincide col NOME del repository che il manuale rivendica -
    cioè col valore che il manuale tiene come link `repo`. È il caso di due
    cartelle sullo stesso computer che si chiamano come il repository:
    `wedding-invite-starter-kit` (chiave e cartella) è il checkout del repo
    `wedding-invite-starter-kit` che il manuale `wedding-invite` rivendica,
    pur non avendo lui stesso nessun link `path`.

    Quando la tabella `repos` sa dov'è il checkout (`local_path`) e a chi
    appartiene (`project_id` = proprio quel manuale), si chiede in più che
    un link `path` del candidato stia sotto quel `local_path`: così, se in
    futuro esistessero due checkout diversi con lo stesso nome di repo (due
    macchine, due fork), il nome da solo non basta più a decidere. Se
    `repos` non sa niente del checkout, il nome resta l'unico segnale
    disponibile.
    """
    manuali = conn.execute(
        "SELECT * FROM projects WHERE auto=0 AND parent_id IS NULL"
    ).fetchall()
    link_path = _links(conn, progetto["id"], "path")
    basenames = {attribuzione.nome_cartella(v) for v in link_path}
    nomi_candidato = {progetto["key"]} | basenames
    for m in manuali:
        for repo_valore in _links(conn, m["id"], "repo"):
            if repo_valore not in nomi_candidato:
                continue
            riga_repo = conn.execute(
                "SELECT local_path FROM repos WHERE name=? AND project_id=?",
                (repo_valore, m["id"]),
            ).fetchone()
            if riga_repo and riga_repo["local_path"]:
                if not any(_dentro(riga_repo["local_path"], v) for v in link_path):
                    continue
            if progetto["key"] == repo_valore:
                motivo = f"la chiave coincide col repository «{repo_valore}» di «{m['key']}»"
            else:
                motivo = f"la cartella «{repo_valore}» è il repository collegato a «{m['key']}»"
            return m["key"], motivo
    return None, ""


def _regola_prefisso(conn, progetto):
    """La chiave del progetto, o il nome della cartella di un suo link
    `path` (basename), comincia con `<chiave manuale>-`.

    La stessa seconda regola di `slot.padre_per_path` (vedi il commento in
    `_regola_path`), applicata sia alla chiave sia, quando esiste, al nome
    della cartella: la chiave e il nome della cartella possono divergere
    (`op6-causal` con cartella `vesuvius-op6`), e in quel caso solo il nome
    della cartella porta il segnale. Considera anche i manuali figli e
    risale alla radice, come `padre_per_path`: un padre proposto è sempre
    di profondità 0.
    """
    manuali = conn.execute("SELECT * FROM projects WHERE auto=0").fetchall()
    nomi = [progetto["key"]] + [
        attribuzione.nome_cartella(v) for v in _links(conn, progetto["id"], "path")
    ]
    migliore, punteggio, nome_usato = None, -1, None
    for m in manuali:
        if m["key"] == progetto["key"]:
            continue
        for nome in nomi:
            if nome != m["key"] and nome.startswith(m["key"] + "-") and len(m["key"]) > punteggio:
                migliore, punteggio, nome_usato = m, len(m["key"]), nome
    if migliore is None:
        return None, ""
    radice = _radice(conn, migliore)
    if nome_usato == progetto["key"]:
        motivo = f"la chiave comincia con «{migliore['key']}-»"
    else:
        motivo = f"la cartella «{nome_usato}» comincia con «{migliore['key']}-»"
    return radice["key"], motivo


def _proponi_riga(conn, progetto):
    """Prova le regole in ordine (path, repo, prefisso): la prima che trova
    un padre vince. L'ordine non è arbitrario: un link path o repo è una
    prova che qualcuno ha collegato quel progetto a un posto preciso, un
    prefisso nel nome è solo una somiglianza testuale."""
    for regola, funzione in (("path", _regola_path), ("repo", _regola_repo),
                             ("prefisso", _regola_prefisso)):
        padre, motivo = funzione(conn, progetto)
        if padre:
            return padre, regola, motivo
    return "", "nessuna", "nessuna regola ha trovato un padre"


def proponi(conn, dove=None):
    """Calcola la mappa e la scrive in un JSON leggibile. Non tocca `projects`.

    Torna `(percorso, righe)`: il chiamante (la CLI) stampa il riepilogo, i
    test confrontano le righe senza dover riaprire il file.
    """
    righe = []
    for progetto in sorted(_candidati(conn), key=lambda r: r["key"]):
        padre, regola, motivo = _proponi_riga(conn, progetto)
        righe.append({
            "chiave": progetto["key"],
            "nome": progetto["name"],
            "padre": padre,
            "regola": regola,
            "motivo": motivo,
            "path": _links(conn, progetto["id"], "path"),
        })

    if dove:
        percorso = Path(dove).expanduser()
    else:
        oggi = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        percorso = config.DATA_DIR / "riordino" / f"{oggi}.json"
    percorso.parent.mkdir(parents=True, exist_ok=True)
    percorso.write_text(json.dumps(righe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return percorso, righe


def carica(percorso):
    """Rilegge il JSON di `proponi` (magari corretto a mano da Eugenio)."""
    return json.loads(Path(percorso).expanduser().read_text(encoding="utf-8"))


def applica(conn, percorso, resto_in_cartelle_viste=False):
    """Chiama `slot.set_parent` per ogni riga con un padre. Le righe rifiutate
    non fermano le altre: tornano nel risultato, la CLI le stampa.

    Il batch è il nome del file senza estensione: è quello che `--annulla`
    dovrà ripassare a `slot.annulla`, quindi deve essere lo stesso.
    """
    percorso = Path(percorso).expanduser()
    righe = carica(percorso)
    batch = percorso.stem

    if resto_in_cartelle_viste and any(not r.get("padre") for r in righe):
        # Un bucket manuale come un altro: se non esiste ancora lo crea,
        # se esiste già _force=True non serve (auto/kind non sono nella
        # lista che upsert_project protegge da un ingest successivo).
        store.upsert_project(conn, CARTELLE_VISTE, "Cartelle viste", kind="infra", auto=0)
        conn.commit()

    applicate = 0
    rifiutate = []
    for riga in righe:
        chiave = riga.get("chiave")
        padre = riga.get("padre") or ""
        if not padre:
            if not resto_in_cartelle_viste:
                continue
            padre = CARTELLE_VISTE
        esito = slot.set_parent(conn, chiave, padre, batch)
        if esito["ok"]:
            applicate += 1
        else:
            rifiutate.append({"chiave": chiave, "padre": padre, "motivo": esito["motivo"]})
    conn.commit()
    return {"applicate": applicate, "rifiutate": len(rifiutate), "dettagli_rifiutate": rifiutate}


def annulla(conn, batch):
    """Un solo punto d'ingresso nel modulo per la CLI: dentro è `slot.annulla`,
    che già sa non scavalcare un batch più recente sullo stesso progetto."""
    return slot.annulla(conn, batch)


# Larghezza minima delle colonne chiave/padre quando le righe reali sono
# tutte più corte: solo per non stringere la tabella in modo ridicolo su
# una mappa piccola, non un tetto (una chiave più lunga allarga la colonna).
_LARGHEZZA_MINIMA = 10


def tabella(righe):
    """Il testo di `--mostra`: chiave, padre, regola, motivo; per padre poi
    chiave, e i "nessuna" (senza padre) in fondo, come chiede il lotto.

    Le colonne chiave e padre si allargano sulla riga più lunga davvero
    presente: una larghezza fissa (28/20, la versione precedente) va storta
    non appena una chiave la supera - e sul dato vero capita per un decimo
    delle chiavi. `.get("chiave", "")` invece di `r["chiave"]` perché una
    riga corretta a mano da Eugenio senza quel campo non deve far fallire
    l'intera tabella con un KeyError: meglio una cella vuota.
    """
    con_padre = sorted((r for r in righe if r.get("padre")),
                       key=lambda r: (r["padre"], r.get("chiave", "")))
    senza_padre = sorted((r for r in righe if not r.get("padre")),
                        key=lambda r: r.get("chiave", ""))
    tutte = con_padre + senza_padre
    larghezza_chiave = max([len(r.get("chiave", "")) for r in tutte] + [_LARGHEZZA_MINIMA])
    larghezza_padre = max([len(r.get("padre") or "-") for r in tutte] + [_LARGHEZZA_MINIMA])

    def riga_fmt(r):
        return (f"{r.get('chiave', ''):<{larghezza_chiave}} "
                f"{(r.get('padre') or '-'):<{larghezza_padre}} "
                f"{r.get('regola', ''):<10} {r.get('motivo', '')}")

    linee = [riga_fmt(r) for r in con_padre]
    if senza_padre:
        if linee:
            linee.append("")
        linee.append("nessuna:")
        linee.extend(riga_fmt(r) for r in senza_padre)
    return "\n".join(linee)
