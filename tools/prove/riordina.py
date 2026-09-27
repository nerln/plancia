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


def esegui(prova) -> None:
    _prova_proponi_prefisso_e_path(prova)
    _prova_proponi_esclude_manuali_e_infra_speciale(prova)
    _prova_regola_path_non_da_motivo_falso_su_prefisso_cartella(prova)
    _prova_regola_repo_checkout_locale(prova)
    _prova_applica_annulla(prova)
    _prova_resto_in_cartelle_viste(prova)
    _prova_mostra(prova)
    _prova_mostra_larghezze_dinamiche(prova)


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
