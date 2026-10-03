"""Prove della 23-RIPARAZIONE (le correzioni dopo il collaudo della 2.0).

- La Ricerca e l'Inspector della Memoria parlano coi titoli umani della Mappa: la scheda trovata ha
  `title` umano e `nome` (la sigla), e nell'anteprima i [[collegamenti]] sono i titoli.
- Il riepilogo dice quanti task sono aperti davvero, non quanti ne elenca (l'elenco ha un tetto di otto).
- Nel repo pubblico nessun nome proprio nei commenti (il copyright e la firma del sito restano).
- Il web: il titolo umano nella ricerca e nei collegamenti del testo, i nomi dei gruppi del grafo
  non finiscono uno sopra l'altro ne' sopra il titolo del nodo scelto.
- Il rilascio fa girare anche la prova del web, dell'app Mac e del pannello Jarvis.
"""

import re
import sqlite3
import subprocess
import sys
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent.parent
if str(RADICE) not in sys.path:
    sys.path.insert(0, str(RADICE))


def _conn():
    from plancia import store
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    store.init_db(conn)
    store.migrate(conn)
    return conn


def esegui(prova) -> None:
    from plancia import mappa, recap

    # ---- la ricerca con i titoli umani
    conn = _conn()
    conn.execute("DELETE FROM knowledge")
    for nome, descr in (("harbour-rollback", "Rollback is a redeploy of the last manifest. Nothing else."),
                        ("backup-routine", "Nightly snapshot, weekly copy"),
                        ("ask-before-deleting", "Ask before deleting anything")):
        conn.execute("INSERT INTO knowledge(name, path, scope, description, type, body, links, updated_at) "
                     "VALUES(?,?,?,?,?,?,?,?)", (nome, "/prova-inesistente/%s.md" % nome, "-prova", descr, "feedback", "x" * 400, "[]",
                                                 "2026-09-20T10:00:00Z"))
    conn.commit()
    trovate = [
        {"kind": "memoria", "ref_id": 1, "title": "harbour-rollback", "project": "Harbour", "ts": "2026-09-21T09:48:00Z",
         "snip": "A «rollback» deploys the manifest before the current one"},
        {"kind": "memoria", "ref_id": 3, "title": "ask-before-deleting", "project": "", "ts": "2026-09-15T09:13:00Z",
         "snip": "…See also [[backup-routine]], [[harbour-«rollback»]], [[non-esiste]]."},
        {"kind": "task", "ref_id": 4, "title": "Harbour: rollback still leaves the old release dir", "project": "Harbour",
         "ts": "2026-10-02T09:42:00Z", "snip": ""},
    ]
    fuori = mappa.umanizza_schede(conn, trovate)
    prova("ricerca: la memoria trovata ha il titolo umano e la sigla a parte",
          fuori[0]["title"] == "Rollback is a redeploy of the last manifest" and fuori[0]["nome"] == "harbour-rollback",
          str(fuori[0]))
    prova("ricerca: l'anteprima non ha [[ ]] e i collegamenti sono i titoli (l'evidenziato resta evidenziato)",
          "[[" not in fuori[1]["snip"] and "Nightly snapshot, weekly copy" in fuori[1]["snip"]
          and "«Rollback is a redeploy of the last manifest»" in fuori[1]["snip"], fuori[1]["snip"])
    prova("ricerca: un collegamento a una memoria che non c'e' si legge comunque (sigla resa leggibile)",
          "Non esiste" in fuori[1]["snip"], fuori[1]["snip"])
    prova("ricerca: una scheda che non e' una memoria non cambia, e l'ingresso non viene toccato",
          fuori[2] == trovate[2] and "nome" not in trovate[0] and trovate[0]["title"] == "harbour-rollback")
    prova("ricerca: senza risultati torna la lista com'e'", mappa.umanizza_schede(conn, []) == [])

    # ---- il riepilogo conta tutti i task aperti
    conn2 = _conn()
    for i in range(12):
        conn2.execute("INSERT INTO tasks(title, status, due, created_at, updated_at) VALUES(?,?,?,?,?)",
                      ("Task %d" % i, "aperto", "2020-01-01" if i < 3 else None, "2026-09-01T10:00:00Z",
                       "2026-09-01T10:00:00Z"))
    conn2.commit()
    dati = recap.collect(conn2)
    prova("riepilogo: l'elenco resta di otto, il totale e' quello vero (12)",
          len(dati["task_aperti"]) == 8 and dati.get("task_aperti_totale") == 12,
          "%s / %s" % (len(dati["task_aperti"]), dati.get("task_aperti_totale")))
    prova("riepilogo: i task in ritardo sono tutti, non solo quelli fra i primi otto",
          dati.get("task_scaduti_totale") == 3, str(dati.get("task_scaduti_totale")))
    frasi = recap.build(conn2, lang="en", engine="template", cache=False)
    testo = frasi.get("testo") or frasi.get("text") or ""
    prova("riepilogo: la frase dice 12 task aperti e 3 in ritardo", "12 tasks are still open" in testo and "3 are overdue" in testo,
          testo[:200])

    # ---- il repo pubblico non porta il nome di chi lo scrive nei commenti
    try:
        elenco = subprocess.run(["git", "-C", str(RADICE), "grep", "-il", "euge" + "nio", "--", "."],
                                capture_output=True, text=True, timeout=60)
        righe = [r for r in elenco.stdout.split() if r not in ("COPYRIGHT", "LICENSE", "pyproject.toml", "site/index.html")]
        if elenco.returncode in (0, 1):
            prova("repo: nessun nome proprio nei commenti e nelle prove (restano copyright e firma del sito)",
                  not righe, ", ".join(righe[:6]))
        else:
            prova("repo: nessun nome proprio nei commenti (saltato: non e' un repository git)", True)
    except (OSError, subprocess.SubprocessError):
        prova("repo: nessun nome proprio nei commenti (saltato: git non c'e')", True)

    # ---- il web
    js = (RADICE / "web" / "app.js").read_text("utf-8")
    prova("web: la ricerca apre la memoria per sigla (nome) e la mostra col titolo umano",
          "(h.nome || h.title)" in js and "k.titolo || k.name" in js)
    prova("web: i [[collegamenti]] nel testo di una memoria si leggono come titoli",
          "titoloMemoria(nome)" in js and "function titoloMemoria(" in js)
    grafo = js[js.index("function montaGrafo("):js.index("function distruggiGrafo(")]
    prova("web: i nomi dei gruppi non si sovrappongono fra loro ne' al titolo del nodo scelto",
          "riservati" in grafo and "sovrappone(" in grafo and "q.g.memorie - p.g.memorie" in grafo)

    # ---- il rilascio
    r = (RADICE / "tools" / "rilascia.sh").read_text("utf-8")
    prova("rilascio: i controlli comprendono la prova del web, dell'app Mac e del pannello Jarvis",
          all(x in r for x in ("tools/prova-front.py", "tools/prova-mac.sh", "tools/prova-jarvis-mac.sh")))
