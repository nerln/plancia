"""Propone, applica e annulla il riordino dei progetti: padri, stati, inglobamenti.

`slot.set_parent` sa assegnare un padre e rifiutarlo con un motivo; sa
`slot.annulla` disfare un batch. Quello che manca è la parte DECIDE (verdetto
§A, punto 7, "reversibilità come relazione"): calcolare *quale* padre proporre
per ogni progetto automatico senza uno, scriverlo in un file che l'utente può
leggere e correggere a mano, e solo dopo la sua occhiata applicarlo. Questo
modulo fa quella parte; non tocca `projects` finché non è `--applica`.

Il file di proposta
-------------------
Un JSON: una lista di righe, una per progetto, che `--proponi` scrive e che si
corregge a mano (o con un agente che ha studiato i progetti). Campi:

    chiave        obbligatorio. La chiave esatta del progetto (mai un nome
                  approssimato: un refuso viene rifiutato, non indovinato).
    nome, regola, path
                  informativi, li scrive `--proponi`; l'applicazione li ignora.
    padre         la chiave del padre (un progetto manuale, di profondità 0).
                  Vuoto = nessun padre proposto.
    stato         "attivo", "archiviato" o "concluso". Assente = lo stato non
                  si tocca.
    inglobato_in  la chiave del progetto dentro cui questo è confluito. Vale
                  come padre = quella chiave + stato "archiviato" + una nota
                  in coda al sommario del progetto, "Inglobato in <chiave>:
                  <motivo>". Se c'è anche `padre` deve essere la stessa chiave;
                  se c'è anche `stato` deve essere "archiviato". Se la
                  destinazione non può fare da padre (è un progetto automatico,
                  o è a sua volta figlio) il padre non si scrive, ma lo stato e
                  la nota sì: l'esito la conta fra gli «inglobati senza padre».
    motivo        il perché, in una frase. OBBLIGATORIO in ogni riga che ha
                  `stato` o `inglobato_in` (una riga senza viene rifiutata da
                  `--applica` e segnata "da correggere" da `--mostra`); per le
                  righe di solo padre lo scrive `--proponi`.

Esempio:

    [
      {"chiave": "prove-vecchie", "inglobato_in": "atlante",
       "motivo": "il codice vive ora nella cartella di atlante"},
      {"chiave": "bozza-tesi", "stato": "concluso",
       "motivo": "consegnata a giugno"},
      {"chiave": "field-notes-alpha", "padre": "field-notes", "regola": "prefisso",
       "motivo": "la chiave comincia con «field-notes-»"}
    ]

Regole di `--applica`
---------------------
- Un batch solo, col nome del file senza estensione. Ogni riga che cambia
  qualcosa scrive un evento `padre:<batch>` con i valori di PRIMA e di DOPO
  di padre, stato e sommario (`slot.riordina_progetto`).
- Tutto o niente per riga: se il padre viene rifiutato (padre automatico, già
  figlio, progetto con figli...) lo stato di quella riga non cambia. Le righe
  rifiutate non fermano le altre e tornano nell'esito con il motivo. Unica
  eccezione, l'inglobamento (vedi `inglobato_in`): il padre è facoltativo.
- Un progetto manuale (auto=0) si tocca solo se il file ha una riga che lo
  nomina con un `padre`, uno `stato` o un `inglobato_in`: una riga vuota su un
  manuale non lo sposta nemmeno con `--resto-in-cartelle-viste`. Un progetto
  che nel file non c'è non si tocca mai.
- Una riga di solo `stato` non finisce sotto `cartelle-viste`: quel resto vale
  solo per le righe senza padre e senza stato.
- Riapplicare lo stesso file non cambia niente (le righe tornano "invariate",
  anche quelle di solo padre) e non ripete la nota.
- Un file che non si legge (JSON non valido, non è una lista) è un errore
  detto in una riga (`FileNonValido`), non un traceback; una riga che non è un
  oggetto è rifiutata con un motivo. Il comando esce con 1 se una riga è stata
  rifiutata.

Regole di `--annulla`
---------------------
Rimette i valori di prima, campo per campo, in ordine inverso, e solo dove il
campo è ancora quello lasciato da quel batch: uno stato, un padre o un
sommario cambiati dopo (a mano o da un altro batch) non vengono scavalcati.
Si annulla passando il nome del batch o il file stesso.
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


class FileNonValido(ValueError):
    """Il file di riordino non si legge: JSON scritto male, o non è una lista."""


def carica(percorso):
    """Rilegge il JSON di `proponi` (magari corretto a mano dall'utente).

    Un file che non c'è alza `FileNotFoundError` come sempre; uno che c'è ma
    non è una lista di righe alza `FileNonValido` con il perché, in italiano.
    """
    percorso = Path(percorso).expanduser()
    testo = percorso.read_text(encoding="utf-8")
    try:
        dati = json.loads(testo)
    except ValueError as exc:
        raise FileNonValido(f"{percorso.name} non è un JSON valido: {exc}") from exc
    if not isinstance(dati, list):
        raise FileNonValido(f"{percorso.name} dovrebbe essere una lista di righe, "
                            f"è {type(dati).__name__}")
    return dati


def _t(valore):
    """Un valore di riga come testo da stampare, qualunque cosa ci sia scritta."""
    if valore is None:
        return ""
    return valore if isinstance(valore, str) else json.dumps(valore, ensure_ascii=False)


STATI_AMMESSI = slot.STATI_RIORDINO


def azione_riga(riga):
    """Cosa chiede una riga oltre al solo padre, senza toccare l'archivio.

    Torna `(azione, errore)`. `azione` è None se la riga è di solo padre (o
    vuota) e va per la strada di sempre, `slot.set_parent`; altrimenti un dict
    `{padre, stato, nota, inglobato}` da passare a `slot.riordina_progetto`.
    `errore` è il motivo di rifiuto detto in parole, oppure None. La stessa
    funzione serve a `applica` (per rifiutare) e a `tabella` (per segnare la
    riga "da correggere"), così le due non possono divergere.
    """
    if not isinstance(riga, dict):
        return None, "la riga non è un oggetto con «chiave»"
    chiave = riga.get("chiave")
    if not isinstance(chiave, str) or not chiave.strip():
        return None, "manca la chiave del progetto"
    campi = {c: riga.get(c) for c in ("padre", "stato", "inglobato_in", "motivo")}
    for nome, valore in campi.items():
        if valore is not None and not isinstance(valore, str):
            return None, f"il campo «{nome}» deve essere un testo"
    padre = (campi["padre"] or "").strip()
    stato = (campi["stato"] or "").strip()
    inglobato = (campi["inglobato_in"] or "").strip()
    if not stato and not inglobato:
        return None, None
    if stato and stato not in STATI_AMMESSI:
        return None, f"stato non valido: «{stato}». Ammessi: {', '.join(STATI_AMMESSI)}"
    motivo = " ".join((campi["motivo"] or "").split())
    if not motivo:
        return None, ("manca il motivo: ogni riga con «stato» o «inglobato_in» "
                      "deve dire perché")
    nota = ""
    if inglobato:
        if padre and padre != inglobato:
            return None, (f"la riga dice padre «{padre}» e inglobato in «{inglobato}»: "
                          "un progetto inglobato ha per padre la destinazione")
        if stato and stato != "archiviato":
            return None, (f"un progetto inglobato è archiviato, non «{stato}»: "
                          "togli lo stato o scrivi «archiviato»")
        if inglobato == chiave.strip():
            return None, "un progetto non può essere inglobato in sé stesso"
        padre, stato = inglobato, "archiviato"
        nota = f"Inglobato in {inglobato}: {motivo}"
    return {"padre": padre, "stato": stato, "nota": nota, "inglobato": bool(inglobato)}, None


def _e_manuale(conn, chiave):
    riga = conn.execute("SELECT auto FROM projects WHERE key=?", (chiave,)).fetchone()
    return bool(riga) and not riga["auto"]


def applica(conn, percorso, resto_in_cartelle_viste=False):
    """Applica il file: padri con `slot.set_parent`, righe con stato o
    inglobamento con `slot.riordina_progetto`. Le righe rifiutate non
    fermano le altre: tornano nel risultato, la CLI le stampa.

    Il batch è il nome del file senza estensione: è quello che `--annulla`
    dovrà ripassare a `slot.annulla`, quindi deve essere lo stesso.

    Torna `applicate` (righe che hanno cambiato qualcosa), `rifiutate`,
    `dettagli_rifiutate`, e per le righe con stato o inglobamento anche
    `stati` (stati cambiati), `inglobati` (inglobamenti riusciti) e
    `invariate` (già com'erano: non scrivono niente).
    """
    percorso = Path(percorso).expanduser()
    righe = carica(percorso)
    batch = percorso.stem

    if resto_in_cartelle_viste and any(
            isinstance(r, dict) and not r.get("padre") and not r.get("stato")
            and not r.get("inglobato_in") for r in righe):
        # Un bucket manuale come un altro: se non esiste ancora lo crea,
        # se esiste già _force=True non serve (auto/kind non sono nella
        # lista che upsert_project protegge da un ingest successivo).
        store.upsert_project(conn, CARTELLE_VISTE, "Cartelle viste", kind="infra", auto=0)
        conn.commit()

    applicate = 0
    stati = 0
    inglobati = 0
    invariate = 0
    rifiutate = []
    senza_padre = []
    for riga in righe:
        azione, errore = azione_riga(riga)
        if isinstance(riga, dict):
            chiave = riga.get("chiave")
            padre_scritto = _t(riga.get("inglobato_in") or riga.get("padre"))
        else:
            chiave, padre_scritto = None, ""
        if errore:
            rifiutate.append({"chiave": chiave, "motivo": errore, "padre": padre_scritto})
            continue
        if azione:
            esito = slot.riordina_progetto(
                conn, chiave, batch, padre_key=azione["padre"] or None,
                stato=azione["stato"] or None, nota=azione["nota"] or None,
                padre_facoltativo=azione["inglobato"])
            if not esito["ok"]:
                rifiutate.append({"chiave": chiave, "padre": azione["padre"],
                                  "motivo": esito["motivo"]})
            elif not esito["cambiato"]:
                invariate += 1
            else:
                applicate += 1
                if esito["stato_dopo"] != esito["stato_prima"]:
                    stati += 1
                if azione["inglobato"]:
                    inglobati += 1
                    if esito.get("padre_saltato"):
                        senza_padre.append({"chiave": chiave, "destinazione": azione["padre"],
                                            "motivo": esito["padre_saltato"]})
            continue
        padre = riga.get("padre") or ""
        if not padre:
            # Il resto vale per chi non ha proposto niente, mai per un manuale
            # che il file nomina senza dire cosa farne.
            if not resto_in_cartelle_viste or _e_manuale(conn, chiave):
                continue
            padre = CARTELLE_VISTE
        esito = slot.set_parent(conn, chiave, padre, batch)
        if esito["ok"] and esito.get("cambiato") is False:
            invariate += 1
        elif esito["ok"]:
            applicate += 1
        else:
            rifiutate.append({"chiave": chiave, "padre": padre, "motivo": esito["motivo"]})
    conn.commit()
    return {"applicate": applicate, "rifiutate": len(rifiutate),
            "dettagli_rifiutate": rifiutate, "stati": stati, "inglobati": inglobati,
            "invariate": invariate, "inglobati_senza_padre": senza_padre}


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
    chiave, le righe di solo stato dopo, e i "nessuna" (senza padre) in fondo.

    Se almeno una riga dice uno stato o un inglobamento, fra la regola e il
    motivo compare la colonna dello stato (`concluso`, `archiviato`,
    `inglobato`); senza, la tabella è quella di sempre. Una riga che
    `--applica` rifiuterebbe per come è scritta (manca il motivo, lo stato non
    esiste...) porta in coda «[DA CORREGGERE: ...]».

    Le colonne si allargano sulla riga più lunga davvero presente: una
    larghezza fissa (28/20, la versione precedente) va storta non appena una
    chiave la supera - e sul dato vero capita per un decimo delle chiavi.
    `.get("chiave", "")` invece di `r["chiave"]` perché una riga corretta a
    mano dall'utente senza quel campo non deve far fallire l'intera tabella
    con un KeyError: meglio una cella vuota.
    """
    # Una riga scritta male (non un oggetto, un campo che non e' un testo) non
    # deve far cadere la tabella: si normalizza a testo e si segna "da correggere"
    # (`azione_riga` guarda la riga ORIGINALE, quindi il difetto resta detto).
    originali = {}
    normalizzate = []
    for r in righe:
        if isinstance(r, dict):
            n = {k: (v if isinstance(v, str) else _t(v)) for k, v in r.items()
                 if k in ("chiave", "padre", "inglobato_in", "stato", "regola", "motivo")}
        else:
            n = {"chiave": "(riga non valida)", "motivo": _t(r)}
        originali[id(n)] = r
        normalizzate.append(n)
    righe = normalizzate

    def padre_di(r):
        return r.get("padre") or r.get("inglobato_in") or ""

    def stato_di(r):
        return "inglobato" if r.get("inglobato_in") else (r.get("stato") or "")

    con_padre = sorted((r for r in righe if padre_di(r)),
                       key=lambda r: (padre_di(r), r.get("chiave", "")))
    solo_stato = sorted((r for r in righe if not padre_di(r) and stato_di(r)),
                        key=lambda r: r.get("chiave", ""))
    senza_padre = sorted((r for r in righe if not padre_di(r) and not stato_di(r)),
                         key=lambda r: r.get("chiave", ""))
    tutte = con_padre + solo_stato + senza_padre
    con_stato = any(stato_di(r) for r in tutte)
    larghezza_chiave = max([len(r.get("chiave", "")) for r in tutte] + [_LARGHEZZA_MINIMA])
    larghezza_padre = max([len(padre_di(r) or "-") for r in tutte] + [_LARGHEZZA_MINIMA])

    def riga_fmt(r):
        testo = (f"{r.get('chiave', ''):<{larghezza_chiave}} "
                 f"{(padre_di(r) or '-'):<{larghezza_padre}} "
                 f"{r.get('regola', ''):<10} ")
        if con_stato:
            testo += f"{(stato_di(r) or '-'):<10} "
        testo += r.get("motivo", "") or ""
        _, errore = azione_riga(originali[id(r)])
        if errore:
            testo += f"  [DA CORREGGERE: {errore}]"
        return testo.rstrip()

    linee = [riga_fmt(r) for r in con_padre]
    for titolo, gruppo in (("solo stato:", solo_stato), ("nessuna:", senza_padre)):
        if gruppo:
            if linee:
                linee.append("")
            linee.append(titolo)
            linee.extend(riga_fmt(r) for r in gruppo)
    return "\n".join(linee)
