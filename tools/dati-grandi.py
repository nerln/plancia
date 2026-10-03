#!/usr/bin/env python3
"""Ingrandisce l'archivio dimostrativo: migliaia di task e di sessioni, un centinaio di
progetti, qualche centinaio di schede di memoria con i loro legami. Serve a misurare
l'app Mac (mac/Prove/misura.sh) con una mole che le viste vere possono raggiungere.

    PLANCIA_HOME=<cartella di prova> python3 tools/demo-data.py
    PLANCIA_HOME=<cartella di prova> python3 tools/dati-grandi.py

Aggiunge a quello che demo-data.py ha scritto, non cancella niente. Tutto e' finto e
generato da un seme fisso: due esecuzioni danno lo stesso archivio. Come demo-data.py
si rifiuta di partire senza PLANCIA_HOME o con PLANCIA_HOME sull'archivio vero, e non
accetta opzioni.
"""

import os
import random
import sys
from datetime import datetime, timedelta, timezone

if __name__ == "__main__":
    _casa = os.environ.get("PLANCIA_HOME", "")
    _vera = os.path.realpath(os.path.expanduser("~/.plancia"))
    if (len(sys.argv) > 1 or not _casa
            or os.path.realpath(os.path.expanduser(_casa)) == _vera):
        sys.stderr.write(
            "uso: PLANCIA_HOME=<cartella di prova> python3 tools/dati-grandi.py\n"
            "Scrive nell'archivio in PLANCIA_HOME: senza PLANCIA_HOME, o con PLANCIA_HOME\n"
            "su ~/.plancia, non parte. Non accetta opzioni.\n")
        sys.exit(2)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from plancia import store  # noqa: E402

N_PROGETTI = 100
N_SESSIONI = 4000
N_TASK = 6000
N_SCHEDE = 260
N_POST = 120
N_EVENTI = 1500

random.seed(23)
ORA = datetime.now(timezone.utc)
PAROLE = ("indice", "cache", "sync", "layout", "parser", "export", "filtro", "coda", "tabella",
          "grafo", "voce", "ricerca", "archivio", "sessione", "lavagna", "memoria", "scheda",
          "modello", "server", "cliente", "test", "rilascio", "nota", "bozza", "vista")
VERBI = ("Sistemare", "Rifare", "Provare", "Scrivere", "Controllare", "Spostare", "Unire",
         "Togliere", "Capire", "Misurare", "Ripulire", "Documentare")
STATI = ("aperto", "aperto", "aperto", "in corso", "bloccato", "fatto", "fatto", "fatto",
         "fatto", "archiviato")
TIPI = ("user", "feedback", "project", "reference")


def quando(giorni_fa, ore=None):
    d = ORA - timedelta(days=giorni_fa, minutes=random.randint(0, 1400))
    if ore is not None:
        d = d.replace(hour=ore)
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")


def frase(n=4):
    return " ".join(random.choice(PAROLE) for _ in range(n))


def main():
    conn = store.connect()
    store.init_db(conn)
    store.migrate(conn)

    ids = [r["id"] for r in conn.execute("SELECT id FROM projects")]
    for i in range(N_PROGETTI):
        pid = store.upsert_project(
            conn, f"prova-{i:03d}", f"Progetto di prova {i:03d}", kind="progetto",
            priority=random.randint(1, 3), pinned=0, summary=frase(9), auto=0, _force=True)
        ids.append(pid)
        conn.execute("UPDATE projects SET last_activity=? WHERE id=?", (quando(random.randint(0, 200)), pid))

    for i in range(N_SESSIONI):
        pid = random.choice(ids)
        inizio = quando(random.randint(0, 400), random.randint(7, 22))
        n_user = random.randint(2, 60)
        agente = "codex" if i % 3 == 1 else "claude"
        fine = (datetime.strptime(inizio, "%Y-%m-%dT%H:%M:%SZ")
                + timedelta(seconds=90 * n_user)).strftime("%Y-%m-%dT%H:%M:%SZ")
        titolo = f"{random.choice(VERBI)} {frase(3)}"
        conn.execute(
            "INSERT INTO sessions(session_id, project_id, file, cwd, title, first_prompt, "
            "started_at, ended_at, n_user, n_assistant, n_tools, models, tools, "
            "in_tokens, out_tokens, agent, scambi, updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (f"grande-{i:05d}", pid, "", "~/dev/prova", titolo, titolo + ". " + frase(12),
             inizio, fine, n_user, n_user * 6, random.randint(0, 200),
             '["claude-opus-5"]' if agente == "claude" else '["gpt-5.4"]',
             '{"Read": 40, "Edit": 12}', random.randint(1000, 90000), random.randint(500, 40000),
             agente, 0, store.now()))

    for i in range(N_TASK):
        pid = random.choice(ids)
        stato = random.choice(STATI)
        ts = quando(random.randint(0, 300))
        due = (ORA + timedelta(days=random.randint(-20, 40))).strftime("%Y-%m-%d") if i % 4 == 0 else None
        cur = conn.execute(
            "INSERT INTO tasks(title, body, status, priority, project_id, source, due, "
            "created_at, updated_at, done_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (f"{random.choice(VERBI)} {frase(4)}", frase(20), stato, random.randint(1, 3), pid,
             random.choice(("claude", "codex", "plancia")), due, ts, ts,
             ts if stato in ("fatto", "archiviato") else None))
        if stato not in ("fatto", "archiviato"):
            conn.execute(
                "INSERT INTO agenda(fonte, chiave, titolo, dettaglio, stato, stato_origine, "
                "agente, sessione, project_id, task_id, creato_at, aggiornato_at, visto_at) "
                "VALUES('plancia',?,?,'',?,?,'plancia','',?,?,?,?,?)",
                (f"t{cur.lastrowid}", f"{random.choice(VERBI)} {frase(4)}", stato, stato, pid,
                 cur.lastrowid, ts, ts, store.now()))
    for i in range(N_TASK // 3):
        fonte = "claude" if i % 2 else "codex"
        ts = quando(random.randint(0, 300))
        conn.execute(
            "INSERT INTO agenda(fonte, chiave, titolo, dettaglio, stato, stato_origine, "
            "agente, sessione, project_id, creato_at, aggiornato_at, visto_at) "
            "VALUES(?,?,?,'',?,?,?,'',?,?,?,?)",
            (fonte, f"g{i}", f"{random.choice(VERBI)} {frase(4)}",
             random.choice(("aperto", "in corso")), "pending", fonte, random.choice(ids),
             ts, ts, store.now()))

    nomi = [f"scheda-{i:03d}" for i in range(N_SCHEDE)]
    for i, nome in enumerate(nomi):
        vicini = random.sample(nomi, random.randint(1, 4))
        legami = "[" + ", ".join('"%s"' % v for v in vicini if v != nome) + "]"
        conn.execute(
            "INSERT INTO knowledge(name, path, scope, description, type, body, links, "
            "project_id, updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (nome, f"/prova/{nome}.md", "prova", frase(10), random.choice(TIPI),
             f"# {nome}\n\n{frase(60)}\n", legami, random.choice(ids), quando(random.randint(0, 200))))

    for i in range(N_POST):
        ts = quando(random.randint(0, 90))
        stato = random.choice(("bozza", "pronto", "pubblicato"))
        conn.execute(
            "INSERT INTO posts(platform, status, text, url, project_id, source_ref, "
            "published_at, created_at, updated_at) VALUES('x',?,?,?,?,?,?,?,?)",
            (stato, frase(25), None, random.choice(ids), "prova",
             ts if stato == "pubblicato" else None, ts, ts))

    for i in range(N_EVENTI):
        store.add_event(conn, quando(random.randint(0, 200)), "sessione", frase(5), frase(4),
                        random.choice(ids), f"g{i}", "claude", dedup=f"grande-ev-{i}")

    store.rebuild_search(conn)
    conn.commit()

    # il registro eventi (eventi.jsonl) che l'app legge con /api/eventi
    from plancia import eventi
    for i in range(400):
        eventi.scrivi(random.choice(eventi.TIPI), frase(5), progetto=f"prova-{random.randint(0, N_PROGETTI - 1):03d}",
                      origine="prova")
    conn.close()
    print(f"archivio grande pronto in {store.config.DB_PATH}: {N_TASK} task, {N_SESSIONI} sessioni, "
          f"{N_SCHEDE} schede, {N_PROGETTI} progetti in piu'")


if __name__ == "__main__":
    main()
