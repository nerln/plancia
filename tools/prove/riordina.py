"""Prove per plancia/riordina.py: proponi, applica, annulla la mappa dei padri.

Come tools/prove/slot.py: ogni gruppo apre un archivio SQLite proprio in
memoria (mai il vero), coi suoi helper `_conn`/`_progetto` invece di
importare quelli privati di un altro modulo di prova (slot.py è di un altro
lotto: non si tocca, e importarne le funzioni con `_` davanti li accoppierebbe
per un dettaglio implementativo). `_scrivi_json` prende un `nome` distinto
per ogni chiamata: il batch (`slot.set_parent`/`slot.annulla`) scrive i suoi
eventi in `eventi.jsonl` sotto la PLANCIA_HOME di prova, condivisa da tutta
l'esecuzione di questo file (non dalla connessione in memoria, che è isolata
per gruppo) - due gruppi che scrivessero entrambi nel batch "mappa" (come
faceva la prima versione di questo file) leggerebbero gli eventi l'uno
dell'altro con `eventi.leggi(tipo="padre:mappa")`; se non se ne accorgono è
solo perché ogni `_progetto_esatto` cerca nella propria connessione e non
trova le chiavi nate nell'altro gruppo, non perché i nomi fossero davvero
distinti.
"""

import json
import sqlite3
import tempfile
from pathlib import Path


def _conn():
    from plancia import store
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    store.init_db(conn)
    return conn


def _progetto(conn, key, name=None, auto=0, **campi):
    from plancia import store
    pid = store.upsert_project(conn, key, name or key, auto=auto, _force=True, **campi)
    conn.commit()
    return pid


def _conta_progetti(conn):
    return conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]


def _scrivi_json(righe, nome="mappa"):
    dest = Path(tempfile.mkdtemp(prefix="plancia-prova-riordina-")) / f"{nome}.json"
    dest.write_text(json.dumps(righe, ensure_ascii=False, indent=2), encoding="utf-8")
    return dest


def _prova_proponi_prefisso_e_path(prova):
    """Il demo (tools/demo-data.py) non ha un manuale con figli auto a
    prefisso: qui se ne costruisce uno, come chiede il lotto (LOTTO-L1-RIORDINA
    §Prove)."""
    from plancia import riordina, store

    conn = _conn()
    manuale = _progetto(conn, "field-notes", auto=0)
    store.link_project(conn, manuale, "path", "/Users/e/dev/field-notes-agosto")
    _progetto(conn, "field-notes-alpha", auto=1)
    beta = _progetto(conn, "field-notes-beta", auto=1)
    store.link_project(conn, beta, "path", "/Users/e/dev/field-notes-agosto/beta")
    conn.commit()

    dest = Path(tempfile.mkdtemp(prefix="plancia-prova-riordina-")) / "proposta.json"
    percorso, righe = riordina.proponi(conn, dove=str(dest))
    prova("il file scritto esiste", percorso.exists(), str(percorso))

    per_chiave = {r["chiave"]: r for r in righe}
    prova("field-notes-alpha va sotto field-notes per prefisso (nessun link path)",
          per_chiave.get("field-notes-alpha", {}).get("padre") == "field-notes"
          and per_chiave["field-notes-alpha"]["regola"] == "prefisso",
          str(per_chiave.get("field-notes-alpha")))
    prova("field-notes-beta va sotto field-notes per path (ha un link sotto la sua cartella)",
          per_chiave.get("field-notes-beta", {}).get("padre") == "field-notes"
          and per_chiave["field-notes-beta"]["regola"] == "path",
          str(per_chiave.get("field-notes-beta")))
    prova("il manuale (field-notes) non compare fra le righe proposte: resta un padre",
          "field-notes" not in per_chiave, str(sorted(per_chiave)))

    # --proponi non scrive in projects: dump di id e parent_id prima e dopo.
    dump_prima = [dict(r) for r in
                 conn.execute("SELECT id, parent_id FROM projects ORDER BY id")]
    riordina.proponi(conn, dove=str(dest))
    dump_dopo = [dict(r) for r in
                conn.execute("SELECT id, parent_id FROM projects ORDER BY id")]
    prova("--proponi non scrive in projects (stesso dump prima e dopo)",
          dump_prima == dump_dopo, f"{dump_prima} -> {dump_dopo}")


def _prova_proponi_esclude_manuali_e_infra_speciale(prova):
    from plancia import riordina, store

    conn = _conn()
    _progetto(conn, "vesuvius", auto=0)
    store.upsert_project(conn, "plancia-interno", "Plancia (chiamate interne)",
                         kind="infra", hidden=1)
    conn.commit()

    _, righe = riordina.proponi(conn)
    chiavi = {r["chiave"] for r in righe}
    prova("un manuale (auto=0) non è mai candidato", "vesuvius" not in chiavi, str(chiavi))
    prova("il bucket infra speciale 'plancia-interno' non è mai candidato",
          "plancia-interno" not in chiavi, str(chiavi))


def _prova_applica_annulla(prova):
    """--applica poi --annulla riportano parent_id a NULL per tutti quelli
    toccati; il numero di righe in projects non cambia mai (LOTTO §Prove)."""
    from plancia import riordina

    conn = _conn()
    manuale = _progetto(conn, "field-notes", auto=0)
    _progetto(conn, "field-notes-alpha", auto=1)
    _progetto(conn, "quasar", auto=1)  # candidato a fare da padre più sotto, ma è auto
    _progetto(conn, "un-altro", auto=1)
    prima_n = _conta_progetti(conn)  # tutti i progetti già esistono: da qui non deve cambiare

    righe = [
        {"chiave": "field-notes-alpha", "nome": "field-notes-alpha", "padre": "field-notes",
         "regola": "prefisso", "motivo": "test", "path": []},
    ]
    dest = _scrivi_json(righe, nome="prova-applica-annulla")
    esito = riordina.applica(conn, dest)
    prova("--applica non cambia il numero di righe in projects",
          prima_n == _conta_progetti(conn), f"{prima_n} -> {_conta_progetti(conn)}")
    prova("field-notes-alpha applicata", esito["applicate"] == 1, str(esito))

    riga = conn.execute(
        "SELECT parent_id FROM projects WHERE key='field-notes-alpha'").fetchone()
    prova("field-notes-alpha ha preso field-notes come padre",
          riga["parent_id"] == manuale, str(dict(riga)))

    # Una riga con un padre che non esiste viene rifiutata e riportata, senza
    # sollevare eccezioni e senza bloccare le altre righe.
    r2 = [
        {"chiave": "quasar", "nome": "quasar", "padre": "atlas-inesistente",
         "regola": "nessuna", "motivo": "chiave inesistente", "path": []},
    ]
    dest2 = _scrivi_json(r2, nome="prova-applica-annulla-inesistente")
    esito2 = riordina.applica(conn, dest2)
    prova("un padre inesistente viene rifiutato e riportato, senza sollevare eccezioni",
          esito2["applicate"] == 0 and esito2["rifiutate"] == 1
          and esito2["dettagli_rifiutate"][0]["chiave"] == "quasar",
          str(esito2))

    # Una riga con padre automatico (auto=1) viene rifiutata allo stesso modo:
    # 'quasar' è auto=1, e slot.set_parent lo scarta come padre a prescindere
    # da chi si propone come suo figlio.
    r3 = [
        {"chiave": "un-altro", "nome": "un-altro", "padre": "quasar",
         "regola": "nessuna", "motivo": "padre automatico, va rifiutato", "path": []},
    ]
    dest3 = _scrivi_json(r3, nome="prova-applica-annulla-auto")
    esito3 = riordina.applica(conn, dest3)
    prova("una riga con padre automatico viene rifiutata e riportata nell'esito",
          esito3["applicate"] == 0 and esito3["rifiutate"] == 1
          and "automatico" in esito3["dettagli_rifiutate"][0]["motivo"],
          str(esito3))

    n = riordina.annulla(conn, dest.stem)
    riga = conn.execute(
        "SELECT parent_id FROM projects WHERE key='field-notes-alpha'").fetchone()
    prova("--annulla riporta parent_id a NULL per la riga applicata",
          n == 1 and riga["parent_id"] is None, f"n={n} riga={dict(riga)}")

    prova("--annulla non cambia il numero di righe in projects",
          prima_n == _conta_progetti(conn), f"{prima_n} -> {_conta_progetti(conn)}")


def _prova_resto_in_cartelle_viste(prova):
    from plancia import riordina

    conn = _conn()
    _progetto(conn, "senza-padre-alcuno", auto=1)
    righe = [
        {"chiave": "senza-padre-alcuno", "nome": "senza-padre-alcuno", "padre": "",
         "regola": "nessuna", "motivo": "nessuna regola ha trovato un padre", "path": []},
    ]
    dest = _scrivi_json(righe, nome="prova-resto-in-cartelle-viste")

    esito = riordina.applica(conn, dest)
    riga = conn.execute(
        "SELECT parent_id FROM projects WHERE key='senza-padre-alcuno'").fetchone()
    prova("di default una riga senza padre non tocca il progetto",
          esito["applicate"] == 0 and esito["rifiutate"] == 0 and riga["parent_id"] is None,
          str(esito))

    esito2 = riordina.applica(conn, dest, resto_in_cartelle_viste=True)
    riga2 = conn.execute(
        "SELECT p.parent_id, c.key AS chiave_padre FROM projects p "
        "JOIN projects c ON c.id = p.parent_id WHERE p.key='senza-padre-alcuno'"
    ).fetchone()
    prova("con --resto-in-cartelle-viste finisce sotto 'cartelle-viste'",
          esito2["applicate"] == 1 and riga2 is not None
          and riga2["chiave_padre"] == "cartelle-viste",
          f"{esito2} riga={dict(riga2) if riga2 else None}")


def _prova_regola_path_non_da_motivo_falso_su_prefisso_cartella(prova):
    """Correzione del critico (finding 2): `slot.padre_per_path` applica due
    regole indipendenti (contenimento vero, e "il nome della cartella
    comincia con <chiave manuale>-"); `_regola_path` non deve più
    etichettarle entrambe "path" con lo stesso motivo "sta dentro", perché
    la seconda non è un contenimento. Caso del critico: manuale `vesuvius`
    con path `/x/dev/vesuvius`, auto `op6-causal` con path
    `/x/dev/vesuvius-op6` (non sta dentro, comincia solo per lo stesso
    nome)."""
    from plancia import riordina, store

    conn = _conn()
    vesuvius = _progetto(conn, "vesuvius", auto=0)
    store.link_project(conn, vesuvius, "path", "/x/dev/vesuvius")
    _progetto(conn, "op6-causal", auto=1)
    op6 = conn.execute("SELECT id FROM projects WHERE key='op6-causal'").fetchone()["id"]
    store.link_project(conn, op6, "path", "/x/dev/vesuvius-op6")

    # Contenimento vero, per contrasto nello stesso giro: la regola "path"
    # deve continuare a funzionare quando è davvero un contenimento.
    atlante = _progetto(conn, "atlante", auto=0)
    store.link_project(conn, atlante, "path", "/y/dev/atlante")
    _progetto(conn, "modulo-x", auto=1)
    modulo = conn.execute("SELECT id FROM projects WHERE key='modulo-x'").fetchone()["id"]
    store.link_project(conn, modulo, "path", "/y/dev/atlante/sub")
    conn.commit()

    _, righe = riordina.proponi(conn)
    per_chiave = {r["chiave"]: r for r in righe}

    r = per_chiave.get("op6-causal")
    prova("op6-causal (nome di cartella, non contenimento) non prende la regola 'path'",
          r is not None and r["regola"] != "path", str(r))
    prova("op6-causal prende 'prefisso', con padre risolto a vesuvius",
          r is not None and r["regola"] == "prefisso" and r["padre"] == "vesuvius", str(r))
    prova("il motivo non dice 'sta dentro' (non è un contenimento vero)",
          r is not None and "sta dentro" not in r["motivo"], str(r))
    prova("il motivo dice che è la CARTELLA a cominciare con vesuvius-",
          r is not None and "vesuvius-op6" in r["motivo"] and "comincia con" in r["motivo"],
          str(r))

    r2 = per_chiave.get("modulo-x")
    prova("modulo-x (davvero dentro /y/dev/atlante) prende la regola 'path'",
          r2 is not None and r2["regola"] == "path" and r2["padre"] == "atlante", str(r2))
    prova("qui il motivo dice davvero 'sta dentro'",
          r2 is not None and "sta dentro" in r2["motivo"], str(r2))


def _prova_regola_repo_checkout_locale(prova):
    """Correzione del critico (finding 1): `project_links` ha
    `UNIQUE(kind, value)`, quindi un manuale e un progetto candidato non
    possono mai condividere lo stesso VALORE di link `repo` (il vecchio
    confronto non poteva mai scattare). Il match vero: la chiave del
    candidato, o il basename di un suo link `path`, coincide col nome del
    repository che un manuale radice rivendica con un proprio link `repo`.
    Caso del critico: manuale `wedding-invite` con link repo
    `wedding-invite-starter-kit` e nessun link path; auto
    `wedding-invite-starter-kit` con path
    `/Users/e/Siti/wedding-invite-starter-kit`."""
    from plancia import riordina, store

    conn = _conn()
    manuale = _progetto(conn, "wedding-invite", auto=0)
    store.link_project(conn, manuale, "repo", "wedding-invite-starter-kit")
    _progetto(conn, "wedding-invite-starter-kit", auto=1)
    candidato = conn.execute(
        "SELECT id FROM projects WHERE key='wedding-invite-starter-kit'").fetchone()["id"]
    store.link_project(conn, candidato, "path",
                       "/Users/e/Siti/wedding-invite-starter-kit")
    conn.commit()

    _, righe = riordina.proponi(conn)
    per_chiave = {r["chiave"]: r for r in righe}
    r = per_chiave.get("wedding-invite-starter-kit")
    prova("wedding-invite-starter-kit va sotto wedding-invite per 'repo' "
          "(è il checkout locale del repository che il manuale rivendica)",
          r is not None and r["padre"] == "wedding-invite" and r["regola"] == "repo",
          str(r))

    # Il rinforzo con `repos.local_path`: se la tabella repos dice che il
    # checkout vero sta altrove, il nome da solo non deve più bastare.
    conn2 = _conn()
    atlas = _progetto(conn2, "atlas", auto=0)
    store.link_project(conn2, atlas, "repo", "shared-name")
    _progetto(conn2, "shared-name", auto=1)
    altro = conn2.execute("SELECT id FROM projects WHERE key='shared-name'").fetchone()["id"]
    store.link_project(conn2, altro, "path", "/altrove/shared-name")
    conn2.execute(
        "INSERT INTO repos(name, project_id, local_path) VALUES (?,?,?)",
        ("shared-name", atlas, "/unico/checkout/vero/shared-name"),
    )
    conn2.commit()

    _, righe2 = riordina.proponi(conn2)
    r2 = {row["chiave"]: row for row in righe2}.get("shared-name")
    prova("con repos.local_path noto e diverso, il solo nome non basta più: nessuna regola",
          r2 is not None and r2["regola"] == "nessuna" and not r2["padre"], str(r2))


def _prova_mostra_larghezze_dinamiche(prova):
    """Correzione del critico (finding 3): colonne a larghezza fissa (28,
    20) vanno storte non appena una chiave le supera. Una mappa con una
    chiave molto più lunga della larghezza fissa di prima e una cortissima:
    la colonna padre deve iniziare allo stesso offset in entrambe le
    righe."""
    from plancia import riordina

    chiave_lunga = "chiave-decisamente-piu-lunga-di-ventotto-caratteri"
    righe = [
        {"chiave": chiave_lunga, "nome": "L", "padre": "radice", "regola": "path",
         "motivo": "m1", "path": []},
        {"chiave": "corta", "nome": "C", "padre": "radice", "regola": "prefisso",
         "motivo": "m2", "path": []},
    ]
    testo = riordina.tabella(righe)
    linee = {l.split()[0]: l for l in testo.split("\n") if l.strip()}
    pos_lunga = linee[chiave_lunga].index("radice")
    pos_corta = linee["corta"].index("radice")
    prova("la colonna padre inizia allo stesso offset per la chiave lunga e per quella corta",
          pos_lunga == pos_corta, f"lunga={pos_lunga} corta={pos_corta}\n{testo}")

    # Una riga corretta a mano senza 'chiave' non deve sollevare KeyError.
    senza_chiave = [{"padre": "radice", "regola": "path", "motivo": "m3", "path": []}]
    try:
        riordina.tabella(senza_chiave)
        ok = True
    except KeyError as e:
        ok = False
    prova("una riga senza il campo 'chiave' non solleva KeyError", ok, "")


def _prova_mostra(prova):
    from plancia import riordina

    righe = [
        {"chiave": "b-progetto", "nome": "B", "padre": "vesuvius", "regola": "path",
         "motivo": "m1", "path": []},
        {"chiave": "a-progetto", "nome": "A", "padre": "vesuvius", "regola": "prefisso",
         "motivo": "m2", "path": []},
        {"chiave": "delta", "nome": "D", "padre": "atlante", "regola": "repo",
         "motivo": "m4", "path": []},
        {"chiave": "z-orfano", "nome": "Z", "padre": "", "regola": "nessuna",
         "motivo": "m3", "path": []},
    ]
    testo = riordina.tabella(righe)
    pos = {chiave: testo.index(chiave) for chiave in
          ("a-progetto", "b-progetto", "delta", "z-orfano")}
    prova("ordinata per padre: 'atlante' (delta) prima di 'vesuvius'",
          pos["delta"] < pos["a-progetto"], str(pos))
    prova("a parità di padre, per chiave: a-progetto prima di b-progetto",
          pos["a-progetto"] < pos["b-progetto"], str(pos))
    prova("le righe senza padre (nessuna) vanno in fondo",
          pos["z-orfano"] > pos["a-progetto"] and pos["z-orfano"] > pos["delta"], str(pos))


def _riga_progetto(conn, chiave):
    return dict(conn.execute("SELECT * FROM projects WHERE key=?", (chiave,)).fetchone())


def _stato_completo(conn):
    """Stato, padre e nota di ogni progetto: quello che --annulla deve
    rimettere esattamente."""
    return [(r["key"], r["status"], r["parent_id"], r["summary"]) for r in
            conn.execute("SELECT key, status, parent_id, summary FROM projects ORDER BY key")]


def _prova_stato_e_inglobato_applica(prova):
    from plancia import riordina

    conn = _conn()
    atlante = _progetto(conn, "atlante", auto=0)
    _progetto(conn, "vecchio-esperimento", auto=1, summary="Prime prove.")
    _progetto(conn, "bozza-chiusa", auto=1)
    _progetto(conn, "riaperto", auto=1, status="archiviato")
    prima = _stato_completo(conn)
    n = _conta_progetti(conn)

    righe = [
        {"chiave": "vecchio-esperimento", "padre": "", "regola": "nessuna",
         "inglobato_in": "atlante", "motivo": "il codice vive ora dentro atlante"},
        {"chiave": "bozza-chiusa", "stato": "concluso", "motivo": "consegnato a giugno"},
        {"chiave": "riaperto", "stato": "attivo", "motivo": "si riprende a ottobre"},
    ]
    dest = _scrivi_json(righe, nome="prova-stato-inglobato")
    esito = riordina.applica(conn, dest)
    prova("applica: tre righe applicate, nessuna rifiutata",
          esito["applicate"] == 3 and esito["rifiutate"] == 0, str(esito))

    v = _riga_progetto(conn, "vecchio-esperimento")
    prova("inglobato: padre = atlante, stato archiviato",
          v["parent_id"] == atlante and v["status"] == "archiviato", str(v))
    prova("inglobato: la nota 'Inglobato in atlante' con il motivo e in coda al sommario",
          v["summary"] == "Prime prove.\nInglobato in atlante: il codice vive ora dentro atlante",
          repr(v["summary"]))
    prova("stato concluso scritto, il padre non si muove",
          _riga_progetto(conn, "bozza-chiusa")["status"] == "concluso"
          and _riga_progetto(conn, "bozza-chiusa")["parent_id"] is None, "")
    prova("stato attivo rimette in vita un archiviato",
          _riga_progetto(conn, "riaperto")["status"] == "attivo", "")
    prova("applica non crea ne toglie progetti", _conta_progetti(conn) == n, "")

    # Un secondo --applica dello stesso file non cambia niente e non raddoppia la nota
    esito2 = riordina.applica(conn, dest)
    prova("secondo applica: niente di nuovo, la nota non si ripete",
          esito2["applicate"] == 0 and esito2.get("invariate") == 3
          and _riga_progetto(conn, "vecchio-esperimento")["summary"].count("Inglobato") == 1,
          str(esito2))

    k = riordina.annulla(conn, dest.stem)
    prova("annulla: rimette stato, padre e nota di tutti e tre esattamente",
          k == 3 and _stato_completo(conn) == prima, f"k={k}\n{_stato_completo(conn)}\n{prima}")


def _prova_motivo_obbligatorio_e_rifiuti(prova):
    from plancia import riordina

    conn = _conn()
    _progetto(conn, "atlante", auto=0)
    _progetto(conn, "a", auto=1)
    _progetto(conn, "b", auto=1)
    _progetto(conn, "c", auto=1)
    _progetto(conn, "d", auto=1)
    _progetto(conn, "e", auto=1)
    prima = _stato_completo(conn)

    righe = [
        {"chiave": "a", "stato": "archiviato"},
        {"chiave": "b", "stato": "archiviato", "motivo": "   "},
        {"chiave": "c", "stato": "dimenticato", "motivo": "stato inventato"},
        {"chiave": "d", "inglobato_in": "atlante", "stato": "concluso", "motivo": "incoerente"},
        {"chiave": "e", "inglobato_in": "atlante", "padre": "altro", "motivo": "due padri"},
        {"chiave": "a", "inglobato_in": "non-esiste", "motivo": "destinazione assente"},
    ]
    esito = riordina.applica(conn, _scrivi_json(righe, nome="prova-rifiuti-stato"))
    motivi = [d["motivo"] for d in esito["dettagli_rifiutate"]]
    prova("sei righe sbagliate: tutte rifiutate, nessuna applicata",
          esito["applicate"] == 0 and esito["rifiutate"] == 6, str(esito))
    prova("senza motivo o con motivo vuoto: il rifiuto dice 'motivo'",
          "motivo" in motivi[0] and "motivo" in motivi[1], str(motivi))
    prova("stato inventato: il rifiuto elenca gli stati ammessi",
          "archiviato" in motivi[2] and "concluso" in motivi[2], str(motivi))
    prova("inglobato con stato diverso da archiviato e contraddizione rifiutata",
          "archiviato" in motivi[3], str(motivi))
    prova("inglobato con un altro padre e contraddizione rifiutata",
          "atlante" in motivi[4] and "altro" in motivi[4], str(motivi))
    prova("inglobato in un progetto che non esiste e rifiutato",
          "non-esiste" in motivi[5], str(motivi))
    prova("le righe rifiutate non toccano niente (nemmeno lo stato)",
          _stato_completo(conn) == prima, "")

    # tutto o niente sulla riga: padre rifiutato = stato invariato
    conn2 = _conn()
    _progetto(conn2, "auto-padre", auto=1)
    _progetto(conn2, "figlio", auto=1)
    prima2 = _stato_completo(conn2)
    # Un PADRE esplicito rifiutato resta tutto o niente. (Un inglobamento in un
    # automatico non e' piu' un rifiuto: archivia e annota senza scrivere il
    # padre, vedi tools/prove/riprendi-riparazione.py.)
    esito2 = riordina.applica(conn2, _scrivi_json(
        [{"chiave": "figlio", "padre": "auto-padre", "stato": "archiviato",
          "motivo": "padre automatico"}],
        nome="prova-tutto-o-niente"))
    prova("padre rifiutato da set_parent: anche lo stato resta com'era",
          esito2["rifiutate"] == 1 and _stato_completo(conn2) == prima2, str(esito2))


def _prova_manuale_solo_con_riga_esplicita(prova):
    from plancia import riordina

    conn = _conn()
    _progetto(conn, "tesi", auto=0)
    _progetto(conn, "atlante", auto=0)
    _progetto(conn, "figlio-auto", auto=1)
    prima = _stato_completo(conn)

    # Una riga senza padre ne stato su un manuale non lo tocca, nemmeno col resto
    righe = [{"chiave": "tesi", "padre": "", "regola": "nessuna", "motivo": "x", "path": []}]
    dest = _scrivi_json(righe, nome="prova-manuale-implicito")
    esito = riordina.applica(conn, dest, resto_in_cartelle_viste=True)
    creati = conn.execute("SELECT 1 FROM projects WHERE key='cartelle-viste'").fetchone()
    parent_tesi = conn.execute("SELECT parent_id FROM projects WHERE key='tesi'").fetchone()[0]
    prova("una riga vuota su un manuale non lo sposta in cartelle-viste",
          esito["applicate"] == 0 and parent_tesi is None, str(esito))

    # Una riga di solo stato non viene spostata in cartelle-viste dal resto
    riordina.applica(conn, _scrivi_json(
        [{"chiave": "figlio-auto", "stato": "archiviato", "motivo": "fermo"},
         {"chiave": "atlante", "padre": "", "regola": "nessuna", "motivo": "x", "path": []}],
        nome="prova-solo-stato-resto"), resto_in_cartelle_viste=True)
    prova("una riga di solo stato non finisce in cartelle-viste col resto",
          _riga_progetto(conn, "figlio-auto")["parent_id"] is None
          and _riga_progetto(conn, "figlio-auto")["status"] == "archiviato", "")
    prova("un manuale con riga vuota non finisce in cartelle-viste nemmeno cosi",
          _riga_progetto(conn, "atlante")["parent_id"] is None, "")
    conn.execute("UPDATE projects SET status='attivo' WHERE key='figlio-auto'")
    conn.commit()

    # Un progetto che non e' nel file non si tocca: solo le righe scritte contano
    riordina.applica(conn, _scrivi_json(
        [{"chiave": "figlio-auto", "stato": "concluso", "motivo": "finito"}],
        nome="prova-manuale-fuori-file"))
    prova("i manuali che non sono nel file restano identici",
          [r for r in _stato_completo(conn) if r[0] in ("tesi", "atlante")]
          == [r for r in prima if r[0] in ("tesi", "atlante")], "")

    # Una riga esplicita sul manuale lo cambia (e --annulla lo rimette)
    esplicita = _scrivi_json(
        [{"chiave": "tesi", "stato": "concluso", "motivo": "discussa"}], nome="prova-manuale-esplicito")
    esito3 = riordina.applica(conn, esplicita)
    prova("una riga esplicita sul manuale cambia il suo stato",
          esito3["applicate"] == 1 and _riga_progetto(conn, "tesi")["status"] == "concluso",
          str(esito3))
    riordina.annulla(conn, esplicita.stem)
    prova("annulla rimette lo stato del manuale",
          _riga_progetto(conn, "tesi")["status"] == "attivo", "")


def _prova_annulla_dopo_modifiche_successive(prova):
    """Annulla un batch dopo che altro e' cambiato: si rimette solo quello che
    il batch aveva lasciato ancora com'era, campo per campo."""
    from plancia import riordina, slot

    conn = _conn()
    atlante = _progetto(conn, "atlante", auto=0)
    _progetto(conn, "x", auto=1, summary="Nota originale.")
    _progetto(conn, "y", auto=1)
    _progetto(conn, "z", auto=1)
    prima = _stato_completo(conn)

    a = _scrivi_json([
        {"chiave": "x", "inglobato_in": "atlante", "motivo": "primo giro"},
        {"chiave": "y", "stato": "archiviato", "motivo": "primo giro"},
        {"chiave": "z", "stato": "archiviato", "motivo": "primo giro"},
    ], nome="prova-successive-a")
    riordina.applica(conn, a)
    dopo_a = _stato_completo(conn)

    # Dopo il batch A: x viene riaperto a mano (stato), y passa a concluso in un
    # batch B, z non si tocca.
    conn.execute("UPDATE projects SET status='attivo' WHERE key='x'")
    conn.commit()
    b = _scrivi_json([{"chiave": "y", "stato": "concluso", "motivo": "secondo giro"}],
                     nome="prova-successive-b")
    riordina.applica(conn, b)

    k = riordina.annulla(conn, a.stem)
    x = _riga_progetto(conn, "x")
    prova("annulla A: x, riaperto a mano, resta attivo ma torna senza padre e senza nota",
          x["status"] == "attivo" and x["parent_id"] is None and x["summary"] == "Nota originale.",
          str(x))
    prova("annulla A: y, portato a concluso da B, non e' scavalcato",
          _riga_progetto(conn, "y")["status"] == "concluso", "")
    prova("annulla A: z torna com'era", _riga_progetto(conn, "z")["status"] == "attivo", "")
    prova("annulla A conta i progetti davvero toccati (x e z)", k == 2, f"k={k}")

    # Annullando B, y torna a archiviato (lo lascio' A); poi annullando ancora A, attivo.
    riordina.annulla(conn, b.stem)
    prova("annulla B rimette archiviato", _riga_progetto(conn, "y")["status"] == "archiviato", "")
    riordina.annulla(conn, a.stem)
    prova("annulla A dopo B: y torna attivo", _riga_progetto(conn, "y")["status"] == "attivo", "")
    prova("alla fine e' tutto com'era all'inizio", _stato_completo(conn) == prima,
          f"{_stato_completo(conn)}\n{prima}")

    # Una nota modificata a mano dopo il batch non viene cancellata
    conn2 = _conn()
    _progetto(conn2, "atlante", auto=0)
    _progetto(conn2, "w", auto=1, summary="Base.")
    c = _scrivi_json([{"chiave": "w", "inglobato_in": "atlante", "motivo": "m"}],
                     nome="prova-successive-nota")
    riordina.applica(conn2, c)
    conn2.execute("UPDATE projects SET summary=summary || ' Aggiunta a mano.' WHERE key='w'")
    conn2.commit()
    riordina.annulla(conn2, c.stem)
    w = _riga_progetto(conn2, "w")
    prova("una nota modificata a mano dopo il batch non viene cancellata dall'annulla",
          "Aggiunta a mano." in w["summary"] and w["parent_id"] is None
          and w["status"] == "attivo", str(w))


def _prova_annulla_compatibile_con_eventi_vecchi(prova):
    """Un batch scritto da set_parent (senza stato ne nota) si annulla come
    prima, e non tocca lo stato."""
    from plancia import riordina, slot

    conn = _conn()
    atlante = _progetto(conn, "atlante", auto=0)
    _progetto(conn, "f", auto=1)
    esito = slot.set_parent(conn, "f", "atlante", "prova-vecchio-formato")
    conn.execute("UPDATE projects SET status='concluso' WHERE key='f'")
    conn.commit()
    k = riordina.annulla(conn, "prova-vecchio-formato")
    f = _riga_progetto(conn, "f")
    prova("evento del formato vecchio: rimette il padre e non tocca lo stato",
          esito["ok"] and k == 1 and f["parent_id"] is None and f["status"] == "concluso", str(f))


def _prova_mostra_stato_e_inglobato(prova):
    from plancia import riordina

    righe = [
        {"chiave": "vecchio", "nome": "V", "padre": "atlante", "regola": "nessuna",
         "inglobato_in": "atlante", "motivo": "confluito in atlante", "path": []},
        {"chiave": "chiuso", "nome": "C", "padre": "", "regola": "nessuna",
         "stato": "concluso", "motivo": "consegnato", "path": []},
        {"chiave": "figlio", "nome": "F", "padre": "atlante", "regola": "prefisso",
         "motivo": "somiglianza-nel-nome", "path": []},
        {"chiave": "orfano", "nome": "O", "padre": "", "regola": "nessuna",
         "motivo": "nessuna regola", "path": []},
        {"chiave": "senza-motivo", "nome": "S", "padre": "", "regola": "nessuna",
         "stato": "archiviato", "path": []},
    ]
    testo = riordina.tabella(righe)
    per_chiave = {l.split()[0]: l for l in testo.split("\n") if l.strip() and l[0] != " "}
    prova("la tabella mostra lo stato scritto in una riga",
          "concluso" in per_chiave["chiuso"] and "consegnato" in per_chiave["chiuso"], testo)
    prova("la tabella mostra l'inglobamento con destinazione e motivo",
          "inglobato" in per_chiave["vecchio"] and "atlante" in per_chiave["vecchio"]
          and "confluito in atlante" in per_chiave["vecchio"], testo)
    prova("una riga senza motivo e segnalata nella tabella",
          "motivo" in per_chiave["senza-motivo"].lower()
          and "da correggere" in per_chiave["senza-motivo"].lower(), testo)
    prova("le righe di solo stato non finiscono fra le 'nessuna'",
          testo.index("chiuso") < testo.index("nessuna:") < testo.index("orfano"), testo)
    prova("le colonne restano allineate: il motivo comincia allo stesso offset",
          per_chiave["vecchio"].index("confluito in atlante")
          == per_chiave["figlio"].index("somiglianza-nel-nome")
          == per_chiave["chiuso"].index("consegnato"), testo)

    # Senza righe con stato la tabella e' quella di prima (nessuna colonna in piu')
    solo_padri = [{"chiave": "a", "nome": "A", "padre": "p", "regola": "path", "motivo": "m1",
                   "path": []}]
    prova("senza stato ne inglobamenti la tabella non cambia formato",
          riordina.tabella(solo_padri).split() == ["a", "p", "path", "m1"],
          riordina.tabella(solo_padri))


def _prova_cli_stato_e_inglobato(prova):
    """Il giro intero da riga di comando su un archivio di prova, per
    --mostra, --applica, --annulla."""
    import os
    import subprocess
    import sys

    radice = Path(__file__).resolve().parent.parent.parent
    casa = Path(tempfile.mkdtemp(prefix="plancia-prova-riordina-cli-"))
    env = dict(os.environ, PLANCIA_HOME=str(casa), HOME=str(casa),
               CLAUDE_CONFIG_DIR=str(casa / "claude"), CODEX_HOME=str(casa / "codex"),
               PYTHONPATH=str(radice))
    (casa / "claude").mkdir()
    (casa / "codex").mkdir()
    # Un archivio con due progetti, scritto direttamente nel database di prova
    import sqlite3
    from plancia import store
    conn = sqlite3.connect(str(casa / "plancia.db"))
    conn.row_factory = sqlite3.Row
    store.init_db(conn)
    store.upsert_project(conn, "atlante", "Atlante", auto=0, _force=True)
    store.upsert_project(conn, "vecchio", "Vecchio", auto=1, summary="Base.")
    conn.commit()
    conn.close()
    file = casa / "mappa.json"
    file.write_text(json.dumps([{"chiave": "vecchio", "inglobato_in": "atlante",
                                 "motivo": "confluito"}]), encoding="utf-8")

    def lancia(*argv):
        return subprocess.run([sys.executable, str(radice / "bin" / "plancia"), "riordina", *argv],
                              cwd=str(radice), env=env, capture_output=True, text=True,
                              timeout=60)

    r = lancia("--mostra", str(file))
    prova("cli --mostra: tabella con l'inglobamento",
          r.returncode == 0 and "inglobato" in r.stdout and "confluito" in r.stdout,
          r.stdout + r.stderr)
    r = lancia("--applica", str(file))
    prova("cli --applica: dice quante applicate e quanti stati/inglobati",
          r.returncode == 0 and "applicate: 1" in r.stdout and "inglobati: 1" in r.stdout,
          r.stdout + r.stderr)
    conn = sqlite3.connect(str(casa / "plancia.db"))
    conn.row_factory = sqlite3.Row
    v = dict(conn.execute("SELECT * FROM projects WHERE key='vecchio'").fetchone())
    prova("cli --applica: archiviato, sotto atlante, con la nota",
          v["status"] == "archiviato" and v["parent_id"] is not None
          and "Inglobato in atlante: confluito" in v["summary"], str(v))
    conn.close()
    r = lancia("--annulla", "mappa")
    conn = sqlite3.connect(str(casa / "plancia.db"))
    conn.row_factory = sqlite3.Row
    v = dict(conn.execute("SELECT * FROM projects WHERE key='vecchio'").fetchone())
    prova("cli --annulla: stato, padre e nota di prima",
          r.returncode == 0 and "rimesse: 1" in r.stdout and v["status"] == "attivo"
          and v["parent_id"] is None and v["summary"] == "Base.", r.stdout + r.stderr + str(v))
    conn.close()
    import shutil
    shutil.rmtree(casa, ignore_errors=True)


def esegui(prova) -> None:
    _prova_proponi_prefisso_e_path(prova)
    _prova_proponi_esclude_manuali_e_infra_speciale(prova)
    _prova_regola_path_non_da_motivo_falso_su_prefisso_cartella(prova)
    _prova_regola_repo_checkout_locale(prova)
    _prova_applica_annulla(prova)
    _prova_resto_in_cartelle_viste(prova)
    _prova_mostra(prova)
    _prova_mostra_larghezze_dinamiche(prova)
    _prova_stato_e_inglobato_applica(prova)
    _prova_motivo_obbligatorio_e_rifiuti(prova)
    _prova_manuale_solo_con_riga_esplicita(prova)
    _prova_annulla_dopo_modifiche_successive(prova)
    _prova_annulla_compatibile_con_eventi_vecchi(prova)
    _prova_mostra_stato_e_inglobato(prova)
    _prova_cli_stato_e_inglobato(prova)


if __name__ == "__main__":
    import os
    import sys

    RADICE = Path(__file__).resolve().parent.parent.parent
    sys.path.insert(0, str(RADICE))

    CASA = Path(tempfile.mkdtemp(prefix="plancia-prova-riordina-home-"))
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
