"""Prove per L1-INGEST: `ingest.progetto_per_cartella()` cerca un padre
prima di creare una scheda nuova.

Si chiama `ingest.progetto_per_cartella()` direttamente invece di passare da
un transcript o da un hook finti: è la funzione che `sync_sessions()` chiama
attraverso `attribuisci()` per ogni cwd di sessione (ingest.py, vedi
`attribuisci()` subito sopra `progetto_per_cartella()`), quindi è "la
funzione chiamata da sync" più vicina alla realtà citata nel lotto, e la più
diretta da isolare: costruire un transcript jsonl finto per arrivarci
passando da `sync_sessions()` testerebbe anche `scan_session_file()` e
`radici_e_generiche()`, che non sono di questo lotto. Il tester manuale del
lotto (`./bin/plancia sync` con un hook finto in `queue/hooks.jsonl`) copre
un altro pezzo: `drain_queue()` (ingest.py, sotto "orchestrazione") usa gli
hook solo per scrivere eventi `SessionStart`/`SessionEnd` via
`resolve_path_project()`, che non crea mai un progetto nuovo: un hook da
solo non passa mai da `progetto_per_cartella()`. Chi rilancia il tester a
mano deve simulare una sessione vera (un file `.jsonl` sotto
`config.CLAUDE_PROJECTS` con `"cwd"` valorizzato) e lanciare `plancia sync`,
non limitarsi alla coda degli hook.

`keywords={}` in ogni chiamata: con una cwd non generica (non home, non
Drive, non `~/Documents/Codex`) `progetto_per_cartella()` non guarda mai
`keywords` (branch `generica` più sopra nella funzione), quindi un dizionario
vuoto non cambia l'esito di queste prove.

Perche' queste prove usano il prefisso del nome (regola 2 di
`slot.padre_per_path`) e non un `project_links` di kind `path` (regola 1),
diversamente dall'esempio del lotto ("vesuvius manuale collegato a
/x/vesuvius, cwd /x/vesuvius/op7"): `progetto_per_cartella()` chiama
`padre_per_path()` SOLO quando `resolve_path_project(conn, cwd)` ha già
risposto `None` (ingest.py, dentro `progetto_per_cartella()`), e
`resolve_path_project` guarda TUTTI i `project_links` di kind `path` di
OGNI progetto, manuali compresi: un sovrainsieme esatto delle righe che la
regola 1 di `padre_per_path` guarda. Se il path di un manuale è prefisso di
`cwd`, `resolve_path_project` lo trova per primo e restituisce l'id del
manuale stesso (la sessione è dentro la sua stessa cartella di lavoro: giusto
così, non deve nascere una scheda figlia per una sottocartella del progetto),
e la ricerca del padre non viene mai raggiunta. La regola 1 resta corretta e
già provata in isolamento da `tools/prove/slot.py::_prova_padre_per_path`
(fusa da L0-SCHEMA); qui, attraverso `progetto_per_cartella()`, è la regola 2
(prefisso del nome della cartella) l'unica che può davvero scattare, perché
non passa da `project_links` e quindi non viene mai intercettata prima da
`resolve_path_project`.

Prove in più (in `_prova_collisione_di_chiave`) coprono cosa succede quando
la chiave nuova (slug del basename della cwd) coincide con quella di una
scheda già in tavola (un manuale con lo stesso nome della cartella di
lavoro, una scheda nata da un'altra cartella con lo stesso basename, o il
caso speciale `cartelle-viste` stessa).

L1-INGEST-B: prima di questo lotto `progetto_per_cartella()` legava
comunque la cwd nuova alla scheda esistente (`upsert_project` restituisce
la riga esistente, non una nuova, quando la chiave collide): bug
riprodotto dal tester di L1-INGEST col caso `lumen`/`.../qualsiasi/lumen`
in `docs/lotti/LOTTO-L1-INGEST-B.md`. Da quel momento `resolve_path_project`
attribuiva alla scheda estranea (spesso un manuale) ogni sessione futura
sotto quella cartella incidentale, bypassando anche `cartelle-viste`. Ora,
se la scheda che ha la chiave non copre già questa cwd con un suo link path
(altrimenti `resolve_path_project` l'avrebbe già trovata prima e non
saremmo qui), non le si lega niente: nasce una SECONDA scheda con chiave
disambiguata (`<slug>-2`, poi `-3`, ...), e queste prove lo verificano sia
per un manuale (`_prova_collisione_di_chiave`, casi a/c) sia per una scheda
auto-creata da un'altra cartella con lo stesso basename (caso b), sia per lo
scenario `lumen` del lotto (`_prova_lumen_cartella_incidentale`), sia per il
caso "già coperto" che NON deve creare niente
(`_prova_caso_gia_coperto_non_crea_schede`). Il caso c0, su una connessione
fresca prima che `cartelle-viste` esista, esercita invece la guardia
`padre_id != trovato` per la scheda che diventerebbe padre di se stessa.
"""

import os
import sqlite3


def _conn():
    from plancia import store
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    store.init_db(conn)
    return conn


def _manuale(conn, key, path=None):
    from plancia import store
    pid = store.upsert_project(conn, key, key, auto=0, _force=True)
    if path:
        store.link_project(conn, pid, "path", path)
    conn.commit()
    return pid


def _riga(conn, pid):
    return conn.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()


def _prova_figlio_di_manuale(prova):
    """Una cwd nuova il cui nome ha il prefisso di un manuale produce una
    scheda con parent_id = id del manuale (slot.padre_per_path, regola 2:
    vedi il docstring del modulo sul perché non si usa la regola 1/path)."""
    from plancia import ingest

    conn = _conn()
    vesuvius = _manuale(conn, "vesuvius", path="/x/vesuvius")

    pid = ingest.progetto_per_cartella(conn, "/altrove/vesuvius-op7", {})
    riga = _riga(conn, pid)
    prova("la scheda nuova nasce con parent_id = vesuvius",
          riga["parent_id"] == vesuvius, str(dict(riga)))
    prova("la scheda nuova non è essa stessa 'vesuvius'",
          riga["key"] != "vesuvius", riga["key"])


def _prova_senza_manuale_va_sotto_cartelle_viste(prova):
    """cwd /y/zzz senza nessun manuale che combaci."""
    from plancia import ingest

    conn = _conn()
    # un manuale che esiste ma non c'entra niente con /y/zzz (ne' per path,
    # ne' per prefisso del nome della cartella)
    _manuale(conn, "vesuvius", path="/x/vesuvius")

    pid = ingest.progetto_per_cartella(conn, "/y/zzz", {})
    riga = _riga(conn, pid)
    cv = conn.execute("SELECT * FROM projects WHERE key='cartelle-viste'").fetchone()
    prova("cartelle-viste esiste dopo la prima cwd orfana", cv is not None, "")
    prova("la scheda nuova nasce figlia di cartelle-viste",
          cv is not None and riga["parent_id"] == cv["id"], str(dict(riga)))
    prova("cartelle-viste è kind infra, hidden=0, auto=0, status attivo",
          cv is not None and (cv["kind"], cv["hidden"], cv["auto"], cv["status"])
          == ("infra", 0, 0, "attivo"),
          str(dict(cv)) if cv is not None else "cartelle-viste non esiste")

    # una seconda cwd orfana diversa: cartelle-viste non si duplica
    pid2 = ingest.progetto_per_cartella(conn, "/y/www", {})
    riga2 = _riga(conn, pid2)
    conteggio = conn.execute(
        "SELECT COUNT(*) FROM projects WHERE key='cartelle-viste'"
    ).fetchone()[0]
    prova("cartelle-viste viene creata una volta sola", conteggio == 1, str(conteggio))
    prova("anche la seconda cwd orfana finisce sotto cartelle-viste",
          cv is not None and riga2["parent_id"] == cv["id"], str(dict(riga2)))


def _prova_secondo_passaggio_stessa_cwd(prova):
    """Un secondo sync sulla stessa cwd non crea doppioni ne' cambia il padre."""
    from plancia import ingest

    conn = _conn()
    vesuvius = _manuale(conn, "vesuvius")

    prima_conteggio = conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
    pid1 = ingest.progetto_per_cartella(conn, "/altrove/vesuvius-op7", {})
    dopo_primo = conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
    prova("il primo passaggio crea esattamente una scheda in più",
          dopo_primo == prima_conteggio + 1, f"{prima_conteggio} -> {dopo_primo}")

    pid2 = ingest.progetto_per_cartella(conn, "/altrove/vesuvius-op7", {})
    dopo_secondo = conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
    prova("il secondo passaggio non aggiunge righe",
          dopo_secondo == dopo_primo, f"{dopo_primo} -> {dopo_secondo}")
    prova("il secondo passaggio torna la stessa scheda", pid1 == pid2, f"{pid1} vs {pid2}")

    riga = _riga(conn, pid2)
    prova("il padre resta vesuvius dopo il secondo passaggio",
          riga["parent_id"] == vesuvius, str(dict(riga)))


def _prova_parent_manuale_non_riassegnato(prova):
    """Un progetto con parent_id gia' valorizzato a mano non viene toccato
    da un sync successivo sulla stessa cwd."""
    from plancia import ingest

    conn = _conn()
    vesuvius = _manuale(conn, "vesuvius")
    altro_padre = _manuale(conn, "altro-padre")

    # una prima cwd crea la scheda figlia di vesuvius per regola...
    pid = ingest.progetto_per_cartella(conn, "/altrove/vesuvius-op7", {})
    riga = _riga(conn, pid)
    prova("setup: la scheda nasce sotto vesuvius", riga["parent_id"] == vesuvius, str(dict(riga)))

    # ...poi una persona la riassegna a mano (simulato con un UPDATE diretto,
    # come farebbe slot.set_parent senza passare da qui)
    conn.execute("UPDATE projects SET parent_id=? WHERE id=?", (altro_padre, pid))
    conn.commit()

    pid2 = ingest.progetto_per_cartella(conn, "/altrove/vesuvius-op7", {})
    riga2 = _riga(conn, pid2)
    prova("un sync successivo sulla stessa cwd non riassegna il padre scelto a mano",
          pid2 == pid and riga2["parent_id"] == altro_padre, str(dict(riga2)))


def _prova_casi_speciali_non_ricevono_padre(prova):
    """I casi speciali gia' esistenti (plancia-interno, temporanee,
    drive-workspace) non cambiano e non ricevono mai un padre."""
    from plancia import config, ingest

    conn = _conn()
    _manuale(conn, "vesuvius")  # presente ma irrilevante per questi cwd

    pid_interno = ingest.progetto_per_cartella(conn, str(config.DATA_DIR), {})
    riga_interno = _riga(conn, pid_interno)
    prova("plancia-interno non riceve un padre",
          riga_interno["parent_id"] is None, str(dict(riga_interno)))

    # SCRATCH_RE (ingest.py) matcha "/private/tmp/..." o "tmp/...", non
    # "/tmp/..." nudo (manca lo "/" prima del gruppo nel pattern): su macOS
    # /tmp è comunque un symlink a /private/tmp, quindi un cwd reale finisce
    # sempre già risolto così.
    pid_scratch = ingest.progetto_per_cartella(conn, "/private/tmp/qualcosa-di-temporaneo", {})
    riga_scratch = _riga(conn, pid_scratch)
    prova("una cartella scratch (temporanee) non riceve un padre",
          riga_scratch["parent_id"] is None, str(dict(riga_scratch)))

    pid_home = ingest.progetto_per_cartella(conn, str(config.HOME), {})
    riga_home = _riga(conn, pid_home)
    prova("la home (radice generica -> drive-workspace) non riceve un padre",
          riga_home["parent_id"] is None, str(dict(riga_home)))


def _prova_collisione_di_chiave(prova):
    """La chiave della cwd nuova (slug del basename) può coincidere con
    quella di una scheda esistente. Se quella scheda non ha già un link
    path che copra questa cwd (altrimenti `resolve_path_project` l'avrebbe
    già trovata, e non saremmo in questa funzione), non le si lega niente:
    nasce una SECONDA scheda con chiave disambiguata (L1-INGEST-B). Vedi il
    docstring del modulo e quello di `ingest.progetto_per_cartella`."""
    from plancia import ingest

    # (c0) cwd il cui basename e' letteralmente 'cartelle-viste', su una
    # connessione fresca, vista PRIMA che il contenitore esista: ricade nel
    # ramo esisteva=None (caso 2 del docstring di progetto_per_cartella,
    # non toccato da questo lotto), quindi la chiave 'cartelle-viste' nasce
    # come questa stessa scheda. slot.padre_per_path non trova nessun
    # manuale e ricade su _cartella_vista(conn), che ora trova la riga
    # appena inserita da questa stessa chiamata: senza la guardia
    # `padre_id != trovato` diventerebbe padre di se stessa.
    conn0 = _conn()
    pid_cv0 = ingest.progetto_per_cartella(conn0, "/q/cartelle-viste", {})
    riga_cv0 = _riga(conn0, pid_cv0)
    prova("cwd 'cartelle-viste' vista per prima non diventa padre di se stessa",
          riga_cv0["key"] == "cartelle-viste" and riga_cv0["parent_id"] is None,
          str(dict(riga_cv0)))

    conn = _conn()

    # (a) manuale 'vesuvius' (senza link path): una cwd DIVERSA il cui
    # basename e' letteralmente 'vesuvius' collide con la chiave del
    # manuale, ma il manuale non ha nessun link path che copra questa cwd:
    # nasce 'vesuvius-2', il manuale non riceve niente.
    vesuvius = _manuale(conn, "vesuvius")
    pid = ingest.progetto_per_cartella(conn, "/altrove/vesuvius", {})
    riga = _riga(conn, pid)
    prova("cwd che collide col nome di un manuale senza link path: non torna il manuale",
          pid != vesuvius, f"pid={pid} vesuvius={vesuvius}")
    prova("la scheda nuova ha chiave disambiguata vesuvius-2",
          riga["key"] == "vesuvius-2", riga["key"])
    riga_vesuvius = _riga(conn, vesuvius)
    prova("il manuale resta senza padre (non diventa padre di se stesso)",
          riga_vesuvius["parent_id"] is None, str(dict(riga_vesuvius)))
    link_manuale = conn.execute(
        "SELECT 1 FROM project_links WHERE project_id=? AND kind='path'", (vesuvius,)
    ).fetchone()
    prova("il manuale non riceve nessun link path dalla cartella incidentale",
          link_manuale is None, "")

    # (b) scheda 'op7' nata da una prima cwd, poi riassegnata a mano a un
    # altro padre. Una seconda cwd con lo STESSO basename ma path DIVERSO
    # non e' coperta dal (unico) link path di op7: nasce 'op7-2', e il
    # padre assegnato a mano a op7 non viene toccato.
    altro_padre = _manuale(conn, "altro-padre")
    pid_op7 = ingest.progetto_per_cartella(conn, "/a/op7", {})
    conn.execute("UPDATE projects SET parent_id=? WHERE id=?", (altro_padre, pid_op7))
    conn.commit()
    pid_op7_bis = ingest.progetto_per_cartella(conn, "/b/op7", {})
    riga_op7_bis = _riga(conn, pid_op7_bis)
    prova("una cwd con lo stesso basename ma path diverso produce una scheda nuova",
          pid_op7_bis != pid_op7, f"{pid_op7_bis} vs {pid_op7}")
    prova("la scheda nuova ha chiave disambiguata op7-2",
          riga_op7_bis["key"] == "op7-2", riga_op7_bis["key"])
    riga_op7 = _riga(conn, pid_op7)
    prova("il padre assegnato a mano a op7 non viene toccato dal basename ripetuto",
          riga_op7["parent_id"] == altro_padre, str(dict(riga_op7)))

    # (c) cwd il cui basename e' letteralmente 'cartelle-viste', DOPO che
    # cartelle-viste esiste gia' (creata sopra, in (a): 'vesuvius'.startswith
    # ('vesuvius-') e' falso, quindi (a) non trova nessun padre per prefisso
    # e ricade su cartelle-viste, creandola):
    # stesso trattamento, chiave disambiguata 'cartelle-viste-2', figlia di
    # 'cartelle-viste' stessa (padre_per_path non trova altro: ricade su
    # _cartella_vista, che trova la riga esistente, non la crea).
    cv = conn.execute("SELECT id FROM projects WHERE key='cartelle-viste'").fetchone()
    prova("setup: cartelle-viste esiste gia' prima di (c)", cv is not None, "")
    pid_cv = ingest.progetto_per_cartella(conn, "/q/cartelle-viste", {})
    riga_cv = _riga(conn, pid_cv)
    prova("una cwd chiamata come 'cartelle-viste' non torna 'cartelle-viste' stessa",
          pid_cv != cv["id"], f"pid_cv={pid_cv} cartelle-viste={cv['id']}")
    prova("la scheda nuova ha chiave disambiguata cartelle-viste-2",
          riga_cv["key"] == "cartelle-viste-2", riga_cv["key"])
    prova("la scheda nuova nasce figlia di 'cartelle-viste', non di se stessa",
          riga_cv["parent_id"] == cv["id"], str(dict(riga_cv)))


def _prova_lumen_cartella_incidentale(prova):
    """Lo scenario del lotto L1-INGEST-B: un manuale (`lumen`) senza link
    path e una cartella incidentale con lo stesso nome altrove. La cwd
    incidentale non si fonde nel manuale; una sottocartella della stessa
    cartella incidentale segue la scheda disambiguata appena creata (che
    ORA ha il suo link path); una seconda cartella incidentale diversa
    produce una terza chiave."""
    from plancia import ingest

    conn = _conn()
    lumen = _manuale(conn, "lumen")  # auto=0, senza link path

    prima = conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
    pid1 = ingest.progetto_per_cartella(conn, "/altrove/lumen", {})
    riga1 = _riga(conn, pid1)
    prova("la cartella incidentale '/altrove/lumen' non si fonde nel manuale lumen",
          pid1 != lumen, f"pid1={pid1} lumen={lumen}")
    prova("la scheda nuova ha chiave lumen-2, nome lumen, auto=1, kind progetto",
          (riga1["key"], riga1["name"], riga1["auto"], riga1["kind"])
          == ("lumen-2", "lumen", 1, "progetto"), str(dict(riga1)))

    cv = conn.execute("SELECT id FROM projects WHERE key='cartelle-viste'").fetchone()
    prova("lumen-2 nasce figlia di cartelle-viste (nessun padre per path o prefisso)",
          cv is not None and riga1["parent_id"] == cv["id"], str(dict(riga1)))

    riga_lumen = _riga(conn, lumen)
    prova("il manuale lumen resta senza link path e senza padre",
          riga_lumen["parent_id"] is None, str(dict(riga_lumen)))
    prova("project_links NON ha (lumen, path, /altrove/lumen)",
          conn.execute(
              "SELECT 1 FROM project_links WHERE project_id=? AND kind='path' AND value=?",
              (lumen, os.path.normpath("/altrove/lumen"))).fetchone() is None, "")
    prova("project_links HA (lumen-2, path, /altrove/lumen)",
          pid1 != lumen and conn.execute(
              "SELECT 1 FROM project_links WHERE project_id=? AND kind='path' AND value=?",
              (pid1, os.path.normpath("/altrove/lumen"))).fetchone() is not None, "")

    # una sessione sotto la stessa cartella incidentale: lumen-2 ha ORA un
    # link path che la copre, quindi resolve_path_project la trova prima e
    # non nasce una terza scheda.
    pid_sub = ingest.progetto_per_cartella(conn, "/altrove/lumen/sub", {})
    prova("una sottocartella della cartella incidentale finisce su lumen-2, non su lumen",
          pid_sub == pid1 and pid_sub != lumen, f"{pid_sub} vs lumen={lumen} lumen-2={pid1}")

    # una seconda collisione, path diverso: lumen-3, non di nuovo lumen-2.
    pid2 = ingest.progetto_per_cartella(conn, "/altrove2/lumen", {})
    riga2 = _riga(conn, pid2)
    prova("una seconda cartella incidentale diversa produce lumen-3",
          riga2["key"] == "lumen-3", riga2["key"])
    prova("lumen-2 e lumen-3 sono due schede diverse",
          pid1 != pid2, f"{pid1} vs {pid2}")

    dopo = conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
    prova("in tutto nascono 3 schede in piu' (cartelle-viste, lumen-2, lumen-3)",
          dopo == prima + 3, f"{prima} -> {dopo}")


def _prova_caso_gia_coperto_non_crea_schede(prova):
    """Il caso gia' coperto (manuale con un link path prefisso della cwd)
    non passa da qui: `resolve_path_project` lo trova prima e attribuisce
    al manuale, senza che nasca nessuna scheda. Non e' un comportamento di
    questo lotto (non cambia), ma va provato perche' e' l'altra faccia
    della stessa medaglia del caso 3 del docstring."""
    from plancia import ingest

    conn = _conn()
    # il link e' scritto come lo scrive il sistema (su Windows `\\casa\\lumen`): il codice lo confronta
    # con la cwd normalizzata
    lumen = _manuale(conn, "lumen", path=os.path.normpath("/casa/lumen"))

    prima = conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
    pid = ingest.progetto_per_cartella(conn, "/casa/lumen/sotto", {})
    dopo = conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
    prova("la cwd gia' coperta dal link path del manuale torna il manuale stesso",
          pid == lumen, f"pid={pid} lumen={lumen}")
    prova("non nasce nessuna scheda nuova", dopo == prima, f"{prima} -> {dopo}")


def esegui(prova) -> None:
    _prova_figlio_di_manuale(prova)
    _prova_senza_manuale_va_sotto_cartelle_viste(prova)
    _prova_secondo_passaggio_stessa_cwd(prova)
    _prova_parent_manuale_non_riassegnato(prova)
    _prova_casi_speciali_non_ricevono_padre(prova)
    _prova_collisione_di_chiave(prova)
    _prova_lumen_cartella_incidentale(prova)
    _prova_caso_gia_coperto_non_crea_schede(prova)


if __name__ == "__main__":
    import os
    import sys
    import tempfile
    from pathlib import Path

    RADICE = Path(__file__).resolve().parent.parent.parent
    sys.path.insert(0, str(RADICE))

    CASA = Path(tempfile.mkdtemp(prefix="plancia-prova-ingest-padre-"))
    os.environ["PLANCIA_HOME"] = str(CASA)

    falliti = []
    passati = 0

    def prova(nome, condizione, dettaglio=""):
        global passati
        if condizione:
            passati += 1
            print(f"  ok   {nome}")
        else:
            falliti.append(nome)
            print(f"  NO   {nome} {dettaglio}")

    print(f"archivio di prova: {CASA}\n")
    esegui(prova)
    print(f"\n{passati} passate, {len(falliti)} fallite")
    if falliti:
        for f in falliti:
            print(f"  - {f}")
        sys.exit(1)
