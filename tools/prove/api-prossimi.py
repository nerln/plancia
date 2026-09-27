"""Prove per LOTTO-L2-VISTA, lato API: /api/prossimi raggruppato per area,
/api/projects?albero=1, e /api/tasks?dopo=1 per il cassetto "Dopo".

Vero server HTTP (api.Handler), non solo le funzioni Python: quello che si
può rompere qui è l'instradamento delle query string (?albero=1, ?dopo=1) e
il raggruppamento in plancia.api.prossimi_raggruppati, non la logica di
slot.py (già provata da tools/prove/slot.py, non di questo lotto) né quella
di actions.tasks_list (idem). Stesso schema di tools/prove/esporta-font.py:
un server vero su una porta scelta dal sistema operativo (0), così non
litiga con quello che tools/prova.py apre sulla 7791 né con quelli degli
altri lotti in corso.

Usa PLANCIA_HOME, il database di prova che tools/prova.py ha già aperto
(mai ~/.plancia, il vero archivio di Eugenio): api.Handler chiama sempre
store.connect(), quindi non si può passare un archivio in memoria a parte.
Per non sporcare i dati di un altro file sotto tools/prove/, ogni chiave qui
è prefissata 'vista-' (verificato con grep: nessun altro file del repo la
usa).
"""

import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer


def _progetto(conn, key, **campi):
    from plancia import store
    pid = store.upsert_project(conn, key, campi.pop("name", key),
                                auto=campi.pop("auto", 0), _force=True, **campi)
    conn.commit()
    return pid


def _get(porta, percorso):
    with urllib.request.urlopen(f"http://127.0.0.1:{porta}{percorso}", timeout=10) as r:
        return json.loads(r.read())


def esegui(prova) -> None:
    from plancia import api, slot, store

    conn = store.connect()

    # Due aree (due padri), ognuno con un figlio attivo: la geometria minima
    # per il raggruppamento di /api/prossimi e per l'annidamento di
    # ?albero=1 nello stesso giro.
    _progetto(conn, "vista-area-uno", status="attivo")
    figlio_uno = _progetto(conn, "vista-figlio-uno", status="attivo")
    _progetto(conn, "vista-area-due", status="attivo")
    figlio_due = _progetto(conn, "vista-figlio-due", status="attivo",
                            next_action="fai qualcosa")

    r = slot.set_parent(conn, "vista-figlio-uno", "vista-area-uno", "vista-batch")
    prova("setup: vista-figlio-uno sotto vista-area-uno", r["ok"], str(r))
    r = slot.set_parent(conn, "vista-figlio-due", "vista-area-due", "vista-batch")
    prova("setup: vista-figlio-due sotto vista-area-due", r["ok"], str(r))
    # last_activity dei due padri, diversa e in ordine opposto rispetto
    # all'ordine (per scadenza) dei figli: cosi' un raggruppamento che
    # aprisse il gruppo dalla riga del padre invece che da quella del figlio
    # (come farebbe con una slot.prossimi() che rimescola l'ordine) sposta
    # davvero l'ordine dei gruppi, e non solo per una coincidenza di sole
    # due righe identiche.
    conn.execute("UPDATE projects SET last_activity=? WHERE key='vista-area-uno'", ("2025-01-01T00:00:00",))
    conn.execute("UPDATE projects SET last_activity=? WHERE key='vista-area-due'", ("2025-06-01T00:00:00",))
    conn.commit()

    ts = store.now()
    # Due scadenze diverse, su due aree diverse: vista-figlio-due ('2026-01-01',
    # la minore) e vista-figlio-uno ('2026-02-01', vedi sotto). Se il
    # raggruppamento rimescolasse l'ordine di slot.prossimi() (che le mette
    # già ordinate, scadenza minore prima), la riga con la scadenza minore
    # non sarebbe più la prima dell'intera risposta appiattita.
    conn.execute(
        "INSERT INTO tasks(title, status, due, project_id, created_at, updated_at) "
        "VALUES('vista task con scadenza', 'aperto', '2026-01-01', ?, ?, ?)",
        (figlio_due, ts, ts),
    )
    # Tre task aperti sul figlio-uno: slot.prossimi() ne userebbe uno solo
    # come "cosa" (il primo nell'ordine di actions.tasks_list), gliene
    # restano due per il cassetto Dopo. Il primo (i=0) porta una scadenza
    # ('2026-02-01', successiva a quella del figlio-due) cosi' diventa lui
    # il "cosa" del gruppo vista-area-uno, con una seconda scadenza distinta
    # da quella del figlio-due.
    for i in range(3):
        conn.execute(
            "INSERT INTO tasks(title, status, due, project_id, created_at, updated_at) "
            "VALUES(?, 'aperto', ?, ?, ?, ?)",
            (f"vista task {i}", "2026-02-01" if i == 0 else None, figlio_uno, ts, ts),
        )
    conn.commit()

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), api.Handler)
    porta = httpd.server_address[1]
    filo = threading.Thread(target=httpd.serve_forever, daemon=True)
    filo.start()
    try:
        # ------------------------------------------------------- /api/prossimi
        d = _get(porta, "/api/prossimi")
        prova("/api/prossimi risponde con 'aree' e 'senza_area'",
              isinstance(d.get("aree"), list) and isinstance(d.get("senza_area"), list),
              str(d)[:300])

        chiavi_nostre = {"vista-area-uno", "vista-figlio-uno", "vista-area-due", "vista-figlio-due"}
        righe_nostre = []
        for a in d["aree"]:
            righe_nostre += [r for r in a["righe"] if r["key"] in chiavi_nostre]
        righe_nostre += [r for r in d["senza_area"] if r["key"] in chiavi_nostre]
        prova("una riga per ciascuno dei nostri 4 progetti attivi",
              {r["key"] for r in righe_nostre} == chiavi_nostre, str(righe_nostre))
        # Un set non vede una riga doppia (due righe con la stessa chiave
        # collasserebbero in un solo elemento nel controllo sopra).
        prova("nessuna riga doppia tra le nostre quattro", len(righe_nostre) == 4, str(righe_nostre))

        aree_nostre = {a["key"]: a for a in d["aree"] if a["key"] in ("vista-area-uno", "vista-area-due")}
        prova("le due aree compaiono come gruppi propri (non 'senza area')",
              set(aree_nostre) == {"vista-area-uno", "vista-area-due"}, str(list(aree_nostre)))

        prova("vista-figlio-uno è nel gruppo di vista-area-uno",
              any(r["key"] == "vista-figlio-uno" for r in aree_nostre["vista-area-uno"]["righe"]),
              str(aree_nostre.get("vista-area-uno")))
        prova("vista-figlio-due è nel gruppo di vista-area-due",
              any(r["key"] == "vista-figlio-due" for r in aree_nostre["vista-area-due"]["righe"]),
              str(aree_nostre.get("vista-area-due")))

        # Appiattimento nell'ordine in cui il front lo legge (panelloProssimi,
        # web/app.js): le aree nel loro ordine, le righe di ciascuna nel loro
        # ordine, poi senza_area. Con due scadenze vere (vista-figlio-due,
        # la minore, e vista-figlio-uno, in un'altra area) un raggruppamento
        # che riordinasse i gruppi invece di limitarsi a raccoglierli
        # tradisce l'invariante sotto anche se le righe dentro ogni gruppo
        # restano nell'ordine giusto: il mutante "lista rovesciata" (scadenza
        # per ultima) la fa fallire di certo, un riordino dei gruppi per nome
        # o per conteggio la fa fallire se sposta in testa un gruppo la cui
        # riga con scadenza non è la minore assoluta.
        piatta_tutta = [r for a in d["aree"] for r in a["righe"]] + d["senza_area"]
        scadenze_presenti = [r["scadenza"] for r in piatta_tutta if r["scadenza"]]
        prova("la prima riga dell'intera risposta appiattita ha la scadenza minore tra "
              "tutte quelle presenti nella risposta (anche con i dati di altri moduli)",
              bool(piatta_tutta) and bool(piatta_tutta[0]["scadenza"])
              and piatta_tutta[0]["scadenza"] == min(scadenze_presenti),
              str(piatta_tutta[:3]))

        indice = {r["key"]: i for i, r in enumerate(piatta_tutta)}
        prova("nell'appiattimento vista-figlio-due (scadenza minore) viene prima di vista-figlio-uno",
              indice.get("vista-figlio-due", -1) >= 0
              and indice.get("vista-figlio-uno", -1) >= 0
              and indice["vista-figlio-due"] < indice["vista-figlio-uno"],
              str((indice.get("vista-figlio-due"), indice.get("vista-figlio-uno"))))

        # ------------------------------------------------------------ ?albero=1
        piatto = next(p for p in _get(porta, "/api/projects") if p["key"] == "vista-area-uno")
        prova("senza albero=1, /api/projects torna la riga piatta (senza 'figli')",
              "figli" not in piatto, str(piatto))

        annidato = _get(porta, "/api/projects?albero=1")
        padre = next((n for n in annidato if n["key"] == "vista-area-uno"), None)
        prova("?albero=1 annida vista-figlio-uno sotto vista-area-uno",
              padre is not None and any(f["key"] == "vista-figlio-uno" for f in padre["figli"]),
              str(padre))

        # ---------------------------------------------------------------- dopo
        senza = _get(porta, "/api/tasks?project=vista-figlio-uno&status=aperti")
        prova("setup: vista-figlio-uno ha 3 task aperti", len(senza) == 3, str(senza))

        dopo = _get(porta, "/api/tasks?project=vista-figlio-uno&dopo=1")
        prova("?dopo=1 restituisce i task aperti oltre il primo (2 di 3)",
              len(dopo) == 2, str(dopo))
        prova("?dopo=1 non ripete il primo task dell'ordine",
              senza[0]["id"] not in {t["id"] for t in dopo}, str((senza, dopo)))
        prova("?dopo=1 rispetta lo stesso ordine di actions.tasks_list",
              [t["id"] for t in dopo] == [t["id"] for t in senza[1:]], str((senza, dopo)))
    finally:
        httpd.shutdown()


if __name__ == "__main__":
    import os
    import sys
    import tempfile
    from pathlib import Path

    RADICE = Path(__file__).resolve().parent.parent.parent
    sys.path.insert(0, str(RADICE))

    CASA = Path(tempfile.mkdtemp(prefix="plancia-prova-api-prossimi-"))
    os.environ["PLANCIA_HOME"] = str(CASA)

    from plancia import store
    _conn0 = store.connect()
    store.init_db(_conn0)
    store.migrate(_conn0)

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
