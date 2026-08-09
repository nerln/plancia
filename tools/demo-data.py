#!/usr/bin/env python3
"""Crea un archivio Plancia finto, per gli screenshot e per provarlo a vuoto.

    PLANCIA_HOME=/tmp/plancia-demo python3 tools/demo-data.py
    PLANCIA_HOME=/tmp/plancia-demo ./bin/plancia serve --port 7799 --no-sync

I dati non hanno niente a che vedere con nessuno: servono solo a far vedere
com'è fatta l'interfaccia quando c'è dentro qualcosa.
"""

import os
import random
import shutil
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from plancia import store  # noqa: E402

random.seed(11)
ORA = datetime.now(timezone.utc)


def quando(giorni, ore=9):
    return (ORA - timedelta(days=giorni)).replace(hour=ore, minute=random.randint(0, 59),
                                                  second=0, microsecond=0
                                                  ).strftime("%Y-%m-%dT%H:%M:%SZ")


PROGETTI = [
    ("lumen", "Lumen", "progetto", 1, 1,
     "CLI that turns a folder of markdown into a searchable static site. Rust, no runtime deps."),
    ("apiary", "Apiary", "infra", 1, 1,
     "Self-hosted gateway in front of three model providers, with per-project budgets."),
    ("field-notes", "Field notes", "ricerca", 1, 0,
     "Reading notes and replications for the thesis chapter on retrieval failure modes."),
    ("harbour", "Harbour", "progetto", 2, 0,
     "Deploy tool for small teams: one config file, no YAML pyramid."),
    ("site", "Personal site", "progetto", 3, 0,
     "Static site and writing. Rebuilt in April, still missing the archive page."),
    ("inbox-zero", "Inbox triage", "infra", 3, 0,
     "Scripts that file mail into projects. Works, ugly, nobody else should see it."),
    ("atlas", "Atlas", "ricerca", 2, 0,
     "Comparing three embedding models on a corpus of support tickets."),
]

# (progetto, titolo, messaggi, tool, token, giorni fa, agente, scambi)
SESSIONI = [
    ("lumen", "Incremental build for the search index", 34, 210, 41000, 0),
    ("lumen", "Fix the anchor links in generated headings", 9, 44, 8200, 1),
    ("apiary", "Per-project budget ceilings and a hard stop", 51, 380, 96000, 0),
    ("apiary", "Rate limit backoff was retrying on 400s", 12, 61, 11500, 2),
    ("field-notes", "Replicate the retrieval ablation on the small set", 28, 190, 54000, 1),
    ("field-notes", "Write up why the second baseline collapsed", 17, 33, 30000, 3),
    ("harbour", "One config file, three environments", 22, 140, 26000, 2),
    ("harbour", "Rollback needs to be one command", 14, 96, 19000, 5),
    ("atlas", "Ticket corpus cleaning, drop the duplicates", 19, 155, 23000, 4),
    ("atlas", "Three models on the same 2000 tickets", 31, 240, 61000, 6),
    ("site", "Archive page that does not need a build step", 8, 40, 7400, 8),
    ("lumen", "Ship 0.4 and write the changelog", 26, 170, 38000, 7),
    ("apiary", "Move the budget store to SQLite", 20, 130, 27000, 9),
    ("field-notes", "Read the two papers from Tuesday and take notes", 11, 22, 14000, 11),
    ("harbour", "Health checks before the switch", 16, 105, 21000, 13),
    ("atlas", "First numbers, and they are not great", 24, 160, 35000, 15),
    ("lumen", "Search was quadratic on large folders", 29, 200, 44000, 18),
    ("apiary", "Streaming responses through the proxy", 35, 260, 58000, 21),
    ("inbox-zero", "Filing rules keep drifting, rewrite them", 13, 70, 15000, 24),
    ("site", "Move the writing over from the old repo", 10, 55, 9800, 27),
]

COMMIT = [
    ("lumen", "Build the index incrementally instead of from scratch", 0),
    ("lumen", "Stop generating duplicate heading anchors", 1),
    ("apiary", "Hard stop when a project passes its ceiling", 0),
    ("apiary", "Do not retry requests the server already refused", 2),
    ("harbour", "Roll back with one command", 5),
    ("harbour", "Read three environments from one file", 2),
    ("atlas", "Drop duplicate tickets before scoring", 4),
    ("atlas", "Score all three models on the same split", 6),
    ("lumen", "Release 0.4", 7),
    ("apiary", "Keep budgets in SQLite, not in memory", 9),
    ("lumen", "Search no longer walks the tree twice", 18),
    ("apiary", "Pass streamed responses straight through", 21),
    ("site", "Archive page, no build step", 8),
    ("harbour", "Wait for health checks before switching", 13),
]

TASK = [
    ("Write the migration note for Apiary 2.0", "apiary", 1, "aperto", None),
    ("Decide whether Lumen keeps the plugin API", "lumen", 1, "in corso", None),
    ("Rerun the ablation with the larger split", "field-notes", 2, "aperto", None),
    ("Harbour: rollback still leaves the old release dir", "harbour", 2, "bloccato", None),
    ("Archive page for the site", "site", 3, "aperto", None),
    ("Ship Lumen 0.4", "lumen", 1, "fatto", 7),
    ("Move budgets off the in-memory store", "apiary", 2, "fatto", 9),
]

POST = [
    ("Lumen 0.4 builds the search index incrementally. On a 4000 file folder that "
     "took the rebuild from 19 seconds to under one.", "pubblicato", "lumen", "commit 4f1a2c9"),
    ("Spent two hours on a bug where the proxy retried requests the server had "
     "already refused. The fix is one line. The lesson is not.", "approvato", "apiary",
     "commit 8c3e11d"),
    ("Three embedding models, the same 2000 support tickets. The cheapest one wins "
     "on this corpus and I did not expect that.", "bozza", "atlas", "session"),
    ("Harbour now rolls back with one command instead of four.", "idea", "harbour",
     "commit a91f004"),
]

# I turni finti, per la vista Cerca. Vengono scritti come veri transcript JSONL e
# indicizzati dal codice vero: uno screenshot della ricerca fatto su righe infilate
# a mano nell'indice mostrerebbe una cosa che il programma non sa fare.
# (sessione, ruolo, testo)
TURNI = [
    ("demo-000", "user",
     "The search index rebuilds the whole corpus on every save and it takes 19 "
     "seconds. Make it incremental, but do not break the case where a file is "
     "renamed rather than edited."),
    ("demo-000", "assistant",
     "Found it. The rebuild was keyed on the file path, so a rename looked like a "
     "new document and the old entry stayed behind as a ghost. Keying on the "
     "content hash instead makes renames free and drops the rebuild to 0.8 s."),
    ("demo-000", "assistant",
     "One thing worth knowing: the incremental path now trusts mtime, so a restore "
     "from backup that preserves timestamps will not be picked up. There is a "
     "--full flag for that, and it is in the readme."),
    ("demo-001", "user",
     "Two headings with the same text generate the same anchor, so the second link "
     "always jumps to the first one."),
    ("demo-001", "assistant",
     "Appending a counter is what most generators do, but it makes every link "
     "fragile: insert a heading above and all the numbers shift. I disambiguated "
     "with the parent heading instead, which is stable under insertion."),
    ("demo-002", "user",
     "Budgets have to be enforced at the gateway, not in each client. A client that "
     "forgets to check is not a client that gets to spend more."),
    ("demo-002", "assistant",
     "The ceiling is per project and per window, and the counter is written before "
     "the request goes out rather than after it comes back, so a crash mid-request "
     "cannot lose the spend. It costs one extra write per call."),
    ("demo-003", "assistant",
     "The retry loop was firing on 400s. A 400 means the server understood and "
     "refused, so retrying it is guaranteed to fail three more times and delay the "
     "error the caller needed to see two seconds ago. Retries now only cover 429 "
     "and 5xx."),
    ("demo-004", "user",
     "Rerun the ablation on the small split before we say anything about the "
     "second baseline collapsing."),
    ("demo-004", "assistant",
     "It reproduces. The second baseline loses 31 points on the small split and "
     "stays flat on the large one, which rules out the sampling explanation and "
     "points at the tokeniser. The full grid is in results/ablation-small.csv."),
    ("demo-006", "assistant",
     "One config file, three environments, and the difference between them is nine "
     "lines. The previous setup had the same nine lines spread over three files of "
     "two hundred, which is why nobody could tell what staging actually did."),
    ("demo-007", "user",
     "Rollback is four commands and I always get the order wrong under pressure. "
     "It has to be one."),
    ("demo-008", "assistant",
     "The ticket corpus had 2,000 documents and 214 of them were duplicates, mostly "
     "autoresponders. Dropping them moved every model's score, so the earlier "
     "comparison was measuring the duplicate rate as much as the embeddings."),
]

MEMORIA = [
    ("lumen-architecture", "How Lumen is put together and why the index is a single file",
     "project", "lumen"),
    ("apiary-budgets", "Budget ceilings are per project, enforced at the proxy, not the client",
     "project", "apiary"),
    ("writing-style", "Short sentences. Concrete nouns. No em dash.", "feedback", None),
    ("thesis-scope", "Chapter three covers retrieval failure, not generation",
     "project", "field-notes"),
    ("machine-setup", "Where the models live and why the cache is on the external drive",
     "reference", None),
]


# La lavagna: quello che i tre agenti hanno aperto in questo momento.
# (fonte, chiave, titolo, stato, stato d'origine, progetto, giorni fa)
AGENDA = [
    ("claude", "s-a1/0", "Make the index build incrementally", "in corso", "in_progress",
     "lumen", 0),
    ("claude", "s-a1/1", "Anchor links collide on repeated headings", "aperto", "pending",
     "lumen", 0),
    ("claude", "s-b2/0", "Hard stop when a project passes its ceiling", "aperto", "pending",
     "apiary", 1),
    ("claude", "s-c3/0", "Write up why the second baseline collapsed", "aperto", "pending",
     "field-notes", 1),
    ("codex", "g-71", "Port the rollback path to the new release layout", "in corso", "active",
     "harbour", 2),
    ("codex", "g-72", "Score the third model on the cleaned split", "bloccato", "usage_limited",
     "atlas", 2),
    ("codex", "g-70", "Streaming responses through the proxy", "fatto", "complete", "apiary", 4),
]

# I lanci: due andati bene, uno male. Quello fallito diventa una proposta.
# (agente, modo, prompt, progetto, stato, esito, token, costo, ore fa)
LANCI = [
    ("claude", "proposta", "Harbour: rollback still leaves the old release dir", "harbour",
     "riuscito", "The old dir is left because the switch happens before the cleanup step. "
     "I would move the unlink after the health check passes, and add a test that asserts "
     "the release dir count stays at two.", 14200, 0.21, 3),
    ("codex", "esegui", "Drop duplicate tickets before scoring", "atlas", "riuscito",
     "Deduplicated on (subject, first 200 chars of body). 2143 tickets became 1987. "
     "Scores moved by less than a point, so the duplicates were not the problem.",
     22800, 0.34, 20),
    ("claude", "proposta", "Rerun the ablation with the larger split", "field-notes", "fallito",
     "the model process exited before returning a result", 800, 0.02, 6),
]


def scrivi_turni(conn):
    """Transcript finti su disco, poi indicizzati dal codice vero.

    Passare dal file invece che infilare righe nell'indice a mano serve a una
    cosa sola: quello che si vede nella vista Cerca deve essere quello che il
    programma sa fare, compreso il percorso e la riga sotto ogni risultato.
    """
    import json
    from pathlib import Path

    from plancia import turni

    radice = Path(store.config.DB_PATH).parent / "demo-transcripts"
    if radice.exists():
        shutil.rmtree(radice)
    cartella = radice / "esempio"
    cartella.mkdir(parents=True)

    per_sessione = {}
    for sessione, ruolo, testo in TURNI:
        per_sessione.setdefault(sessione, []).append((ruolo, testo))
    for sessione, righe in per_sessione.items():
        with (cartella / f"{sessione}.jsonl").open("w", encoding="utf-8") as fh:
            for i, (ruolo, testo) in enumerate(righe):
                fh.write(json.dumps({
                    "type": ruolo,
                    "timestamp": quando(i % 4, 10 + i),
                    "message": {"role": ruolo,
                                "content": [{"type": "text", "text": testo}]},
                }) + "\n")
    esito = turni.indicizza(conn, completo=True, radice=radice)
    print(f"turni indicizzati: {esito['turni']}")


def main():
    conn = store.connect()
    store.init_db(conn)
    store.migrate(conn)
    for tabella in ("events", "sessions", "commits", "tasks", "posts", "knowledge",
                    "repos", "project_links", "projects", "capabilities", "agenda", "runs"):
        conn.execute(f"DELETE FROM {tabella}")

    ids = {}
    for key, nome, kind, prio, pin, riassunto in PROGETTI:
        pid = store.upsert_project(conn, key, nome, kind=kind, priority=prio, pinned=pin,
                                   summary=riassunto, auto=0, _force=True)
        ids[key] = pid
        store.link_project(conn, pid, "repo", key)
        conn.execute("INSERT INTO repos(name, description, visibility, url, pushed_at, "
                     "project_id, updated_at) VALUES(?,?,?,?,?,?,?)",
                     (key, riassunto[:70], "public", f"https://github.com/example/{key}",
                      quando(1), pid, store.now()))

    conn.execute("UPDATE projects SET next_action=? WHERE key='apiary'",
                 ("write the 2.0 migration note before anyone upgrades",))
    conn.execute("UPDATE projects SET next_action=? WHERE key='field-notes'",
                 ("rerun the ablation with the larger split",))
    conn.execute("UPDATE projects SET status='in pausa' WHERE key='inbox-zero'")
    conn.execute("UPDATE projects SET status='concluso' WHERE key='site'")

    for i, (key, titolo, n_user, n_tools, out, giorni) in enumerate(SESSIONI):
        inizio = quando(giorni, 9 + (i % 8))
        # due agenti sullo stesso archivio: uno ogni tre è Codex
        agente = "codex" if i % 3 == 1 else "claude"
        scambi = 4 if (agente == "codex" and i % 6 == 1) else 0
        conn.execute(
            "INSERT INTO sessions(session_id, project_id, file, cwd, title, first_prompt, "
            "started_at, ended_at, n_user, n_assistant, n_tools, models, tools, "
            "in_tokens, out_tokens, agent, scambi, updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (f"demo-{i:03d}", ids[key], "", f"~/dev/{key}", titolo,
             titolo + ". Start from what is already there and do not rewrite the module.",
             inizio, inizio, n_user, n_user * 6, n_tools,
             '["claude-opus-5"]' if agente == "claude" else '["gpt-5.4"]',
             '{"Read": 40, "Edit": 12, "Bash": 9}',
             out * 12, out, agente, scambi, store.now()))
        if scambi:
            store.add_event(conn, inizio, "scambio",
                            f"Codex and Claude talked in {titolo}",
                            f"{scambi} messages between agents", ids[key], f"demo-{i:03d}",
                            "codex", dedup=f"x{i}")
        store.add_event(conn, inizio, "sessione", titolo, f"{n_user} messaggi · {n_tools} tool",
                        ids[key], f"demo-{i:03d}", "claude", dedup=f"s{i}")
        store.touch_project(conn, ids[key], inizio)

    for i, (repo, messaggio, giorni) in enumerate(COMMIT):
        data = quando(giorni, 11)
        conn.execute("INSERT INTO commits(repo, sha, message, date, url) VALUES(?,?,?,?,?)",
                     (repo, f"{i:040x}", messaggio, data, ""))
        store.add_event(conn, data, "commit", messaggio, repo, ids[repo], f"c{i}", "github",
                        dedup=f"c{i}")

    for titolo, key, prio, stato, chiuso in TASK:
        ts = quando(random.randint(1, 6))
        conn.execute(
            "INSERT INTO tasks(title, body, status, priority, project_id, source, "
            "created_at, updated_at, done_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (titolo, "", stato, prio, ids[key], "claude", ts, ts,
             quando(chiuso) if chiuso is not None else None))

    for testo, stato, key, fonte in POST:
        ts = quando(random.randint(0, 8))
        conn.execute(
            "INSERT INTO posts(platform, status, text, url, project_id, source_ref, "
            "published_at, created_at, updated_at) VALUES('x',?,?,?,?,?,?,?,?)",
            (stato, testo, "https://x.com/example/status/1" if stato == "pubblicato" else None,
             ids[key], fonte, ts if stato == "pubblicato" else None, ts, ts))

    for nome, descrizione, tipo, key in MEMORIA:
        conn.execute(
            "INSERT INTO knowledge(name, path, scope, description, type, body, links, "
            "project_id, updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (nome, f"/demo/{nome}.md", "demo", descrizione, tipo,
             f"# {nome}\n\n{descrizione}\n", "[]",
             ids.get(key), quando(random.randint(1, 20))))

    for nome, kind, descrizione in [
            ("plancia", "skill", "Read and update Plancia from any session"),
            ("riepilogo", "skill", "The spoken daily recap"),
            ("release", "skill", "Cut a release: changelog, tag, notes"),
            ("morning", "routine", "Daily briefing at 08:45")]:
        conn.execute("INSERT INTO capabilities(name, kind, description, path, meta, updated_at) "
                     "VALUES(?,?,?,?,'{}',?)",
                     (nome, kind, descrizione, f"/demo/{nome}", quando(3)))

    for fonte, chiave, titolo, stato, origine, key, giorni in AGENDA:
        ts = quando(giorni, 10)
        conn.execute(
            "INSERT INTO agenda(fonte, chiave, titolo, dettaglio, stato, stato_origine, "
            "agente, sessione, project_id, creato_at, aggiornato_at, visto_at) "
            "VALUES(?,?,?,'',?,?,?,'',?,?,?,?)",
            (fonte, chiave, titolo, stato, origine, fonte, ids[key], ts, ts, store.now()))

    # i task di Plancia stanno sulla lavagna come gli altri: la lavagna esiste
    # proprio per non dover guardare in tre posti diversi
    for r in conn.execute("SELECT id, title, status, project_id, updated_at FROM tasks"):
        if r["status"] == "fatto":
            continue
        conn.execute(
            "INSERT INTO agenda(fonte, chiave, titolo, dettaglio, stato, stato_origine, "
            "agente, sessione, project_id, task_id, creato_at, aggiornato_at, visto_at) "
            "VALUES('plancia',?,?,'',?,?,'plancia','',?,?,?,?,?)",
            (f"t{r['id']}", r["title"], r["status"], r["status"], r["project_id"], r["id"],
             r["updated_at"], r["updated_at"], store.now()))

    for i, (agente, modo, prompt, key, stato, esito, token, costo, ore) in enumerate(LANCI):
        inizio = (ORA - timedelta(hours=ore)).strftime("%Y-%m-%dT%H:%M:%SZ")
        fine = (ORA - timedelta(hours=ore, minutes=-4)).strftime("%Y-%m-%dT%H:%M:%SZ")
        conn.execute(
            "INSERT INTO runs(agente, modo, prompt, cwd, stato, inizio, fine, sessione, "
            "esito, log, token, costo) VALUES(?,?,?,?,?,?,?,'',?,'',?,?)",
            (agente, modo, prompt, f"~/dev/{key}", stato, inizio, fine, esito, token, costo))
        store.add_event(conn, fine, "lancio", prompt,
                        f"{agente} · {stato}", ids[key], f"r{i}", agente, dedup=f"r{i}")

    # un repo con roba non committata: e' il segnale che fa nascere una proposta
    conn.execute("UPDATE repos SET dirty=7, branch='main', local_path='~/dev/lumen' "
                 "WHERE name='lumen'")

    store.set_meta(conn, "demo", "1")
    store.set_meta(conn, "onboarding_fatto", "1")
    store.set_meta(conn, "last_sync_end", store.now())
    store.rebuild_search(conn)
    conn.commit()
    scrivi_turni(conn)

    # Il riepilogo lo scrive il motore a modello sui dati finti, così quello che
    # si vede negli screenshot è davvero quello che l'app produce.
    from plancia import recap  # noqa: E402
    recap.build(conn, lang="en", engine="template", cache=True)
    conn.close()
    print(f"archivio dimostrativo pronto in {store.config.DB_PATH}")


if __name__ == "__main__":
    main()
