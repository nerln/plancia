#!/usr/bin/env python3
"""Crea un archivio Plancia finto, per gli screenshot e per provarlo a vuoto.

    PLANCIA_HOME=/tmp/plancia-demo python3 tools/demo-data.py
    PLANCIA_HOME=/tmp/plancia-demo ./bin/plancia serve --port 7844 --no-sync

La porta è indifferente (qui usiamo la stessa di tools/scatti.sh solo per
coerenza con l'esempio); quello che conta è isolare PLANCIA_HOME.

I dati non hanno niente a che vedere con nessuno: servono solo a far vedere
com'è fatta l'interfaccia quando c'è dentro qualcosa.
"""

import json
import os
import random
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Sicura (29/09/2026): questo script CANCELLA le tabelle dell'archivio che trova e
# riscrive config.json. Senza PLANCIA_HOME, o con PLANCIA_HOME sulla cartella dati
# vera, lavorerebbe sull'archivio di chi lo lancia: e' successo una volta con un
# `--help`. Si ferma prima di importare Plancia.
if __name__ == "__main__":
    _casa = os.environ.get("PLANCIA_HOME", "")
    _vera = os.path.realpath(os.path.expanduser("~/.plancia"))
    if (len(sys.argv) > 1 or not _casa
            or os.path.realpath(os.path.expanduser(_casa)) == _vera):
        sys.stderr.write(
            "uso: PLANCIA_HOME=<cartella di prova> python3 tools/demo-data.py\n"
            "Cancella e riscrive l'archivio in PLANCIA_HOME: senza PLANCIA_HOME, o con\n"
            "PLANCIA_HOME su ~/.plancia, non parte. Non accetta opzioni.\n")
        sys.exit(2)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from plancia import richiamo, slot, store  # noqa: E402

random.seed(11)
ORA = datetime.now(timezone.utc)


def quando(giorni, ore=9):
    return (ORA - timedelta(days=giorni)).replace(hour=ore, minute=random.randint(0, 59),
                                                  second=0, microsecond=0
                                                  ).strftime("%Y-%m-%dT%H:%M:%SZ")


def scadenza(giorni):
    """Una data (YYYY-MM-DD) a `giorni` da oggi: negativo per una scadenza già
    passata. Serve solo a scaglionare le scadenze dei task finti (LOTTO-L2-DEMO
    punto 1), non ha nulla a che fare con `quando()`, che scrive timestamp
    passati per attività già avvenuta."""
    return (ORA + timedelta(days=giorni)).strftime("%Y-%m-%d")


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

# Le tre aree (LOTTO-L2-DEMO punto 1): padri manuali con tre figli l'uno,
# collegati sotto con slot.set_parent invece che con un parent_id scritto a
# mano, per passare dalla stessa strada di un uso vero. I figli sono progetti
# già in PROGETTI sopra: nessuna area nasce senza almeno tre, come chiede il
# lotto. `postcard` e `kiln` esistono solo per completare i tre figli di
# `backlot` (gli altri due li aveva già l'elenco di sopra).
AREE = [
    ("signalworks", "Signalworks", "infra", 1, 0,
     "The handful of tools that turn raw sensor logs into an alert someone can act on."),
    ("fieldcraft", "Fieldcraft", "progetto", 1, 0,
     "Setting up and tearing down instruments in the field, so a trip needs one packing list."),
    ("backlot", "Backlot", "progetto", 2, 0,
     "The small stuff that keeps the other two areas running: hosting, exports, the odd rewrite."),
]

PROGETTI_AREA = [
    ("postcard", "Postcard", "progetto", 2, 0,
     "One-page status pages generated from a template, for clients who just want a link."),
    ("kiln", "Kiln", "infra", 3, 0,
     "Build cache for the site generators upstream, so a full rebuild is the exception."),
]

# Progetti senza area (punto 1: "qualche progetto senza area"): restano radici
# senza figli e senza padre, per la riga "senza_area" del pannello Prossimi.
SENZA_AREA = [
    ("gutter", "Gutter", "progetto", 2, 0,
     "Log rotation and cleanup for machines nobody watches until they fill up."),
    ("almanac", "Almanac", "ricerca", 3, 0,
     "A running log of which release broke which downstream project."),
    ("spindle", "Spindle", "progetto", 2, 0,
     "Turns a folder of audio recordings into timestamped transcripts overnight."),
]

# Il legame figlio -> area, usato subito dopo la creazione dei progetti.
FIGLI_AREA = {
    "signalworks": ["lumen", "apiary", "atlas"],
    "fieldcraft": ["field-notes", "harbour", "inbox-zero"],
    "backlot": ["site", "postcard", "kiln"],
}

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

# (titolo, progetto, priorità, stato, giorni fa se chiuso, scadenza)
# La scadenza è un'offerta di giorni da oggi (scadenza(), negativo = già
# passata): scaglionata apposta (LOTTO-L2-DEMO punto 1) così il pannello
# Prossimi mostra un ordine visibile invece di righe tutte uguali.
TASK = [
    ("Write the migration note for Apiary 2.0", "apiary", 1, "aperto", None, scadenza(2)),
    ("Decide whether Lumen keeps the plugin API", "lumen", 1, "in corso", None, scadenza(1)),
    ("Rerun the ablation with the larger split", "field-notes", 2, "aperto", None, scadenza(5)),
    ("Harbour: rollback still leaves the old release dir", "harbour", 2, "bloccato", None,
     scadenza(-1)),
    ("Archive page for the site", "site", 3, "aperto", None, None),
    ("Ship Lumen 0.4", "lumen", 1, "fatto", 7, None),
    ("Move budgets off the in-memory store", "apiary", 2, "fatto", 9, None),
    ("Cut the first Kiln cache eviction policy", "kiln", 1, "aperto", None, scadenza(3)),
    ("Swap Postcard's template loader for something that caches", "postcard", 2, "in corso",
     None, scadenza(-2)),
]

# Le tre carte di stato di "Riprendi" (LOTTO-L2-DEMO punto 1, verdetto
# 16/09/2026 §B): un task per "chiusa" e uno per "persa" (host diverso).
# "persa" (mai registrata) non serve una riga a parte: ogni task di TASK qui
# sopra nasce già senza session_id, quindi è già quello stato di default.
# "viva" non si simula: non c'è modo scriptabile di dire "questa sessione è
# davvero aperta adesso" senza un processo vero dietro (lo dice anche
# riprendi._claude_vivo quando non riesce a interrogare nient'altro).
#
# (titolo, progetto, session_id, agent, cwd, host)
# host vuoto = "questa macchina", per riprendi.stato (`if host_task and
# host_task != host_ora`, falso su stringa vuota): non c'è bisogno del vero
# hostname per dire "stessa macchina", e scriverlo nel db dimostrativo
# esporrebbe un nome vero (punto 2 del lotto) per niente.
TASK_RIPRESA = [
    ("Wire the retry budget into the nightly job", "apiary", "demo-closed-01",
     "claude", "~/dev/apiary", ""),
    ("Rotate the backup keys before they expire", "harbour", "demo-otherhost-01",
     "claude", "~/dev/harbour", "altra-scrivania"),
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

# La memoria dimostrativa: una cinquantina di schede in inglese, dei quattro tipi
# di sempre, con legami veri fra loro (i `[[nome]]` che una scheda scrive) e
# qualche scheda senza legami. Tutto inventato: e' quello che la Mappa e il grafo
# mostrano negli screenshot, e cinque pallini scollegati non mostrano niente.
# (nome, tipo, progetto, descrizione, dettaglio): senza dettaglio la scheda resta
# corta, e il richiamo la scarta (pallino vuoto nel grafo).
MEMORIA = [
    ("user-role", "user", None,
     "Solo maintainer of a handful of small tools; writes Rust and Python daily",
     "Works alone most of the time and reviews their own diffs before merging. Prefers an "
     "explanation that starts from the code that exists over one that starts from theory."),
    ("user-schedule", "user", None,
     "Deep work in the morning, meetings and mail after two",
     "Anything that needs a decision is queued for the morning summary instead of "
     "interrupting the afternoon. Weekends are for the thesis, not for the tools."),
    ("user-thesis-status", "user", "field-notes",
     "Third year of a part-time PhD on retrieval failure modes",
     "Chapter three is the current focus. Chapters one and two are with the supervisor, "
     "and the next committee meeting is the first week of December."),
    ("user-hardware", "user", None,
     "Laptop for daily work, a small always-on box for builds and the gateway",
     "The box has no display and is reached over ssh. Anything that needs a GPU runs on "
     "the laptop, and long jobs are started with a log file and a name."),
    ("user-languages", "user", None,
     "Fluent in English and Italian; writes docs in English", ""),
    ("writing-style", "feedback", None,
     "Short sentences. Concrete nouns. No em dash.",
     "Applies to docs, commit messages and replies alike. If a sentence needs a semicolon "
     "it is probably two sentences. Numbers go in as digits, with the unit."),
    ("commit-messages", "feedback", None,
     "Imperative mood, subject under 60 characters, body only when the why is not obvious",
     "The subject says what the change does, the body says why it was needed. No ticket "
     "numbers in the subject, no trailing period, no prefix in square brackets."),
    ("no-surprise-refactors", "feedback", None,
     "Do not reformat or rename files the task did not ask about",
     "A diff should contain the change that was requested and nothing else. If a nearby "
     "cleanup looks worth doing, mention it at the end instead of doing it."),
    ("test-first-on-bugs", "feedback", None,
     "For a bug, write the failing test first and show it failing",
     "Then fix it, then show the same test passing. A bug fix without a test that failed "
     "before the change is treated as a guess."),
    ("ask-before-deleting", "feedback", None,
     "Never delete data or branches without asking, even in scratch folders",
     "Moving to a trash folder is fine. Force pushes, dropped tables and removed "
     "directories always need a yes first, in the same conversation."),
    ("small-prs", "feedback", "lumen",
     "Keep pull requests under 300 changed lines; split otherwise",
     "A large change goes in as a series where each step builds and passes on its own. "
     "The first step is usually the refactor that makes the real change small."),
    ("plain-status-updates", "feedback", None,
     "Status updates say what changed and what is next, in two sentences",
     "No adjectives about how it went, no apologies for how long it took. If something is "
     "blocked, the blocker goes first."),
    ("dependency-policy", "feedback", "lumen",
     "Prefer the standard library; a new dependency needs a sentence of justification",
     "The sentence names what the dependency does that is not worth writing, who "
     "maintains it, and how many transitive packages it pulls in."),
    ("explain-tradeoffs", "feedback", None,
     "When two options are reasonable, name both and the cost of each, then pick one",
     "The pick comes with the condition under which the other option would win, so the "
     "decision can be revisited without redoing the analysis."),
    ("dates-absolute", "feedback", None,
     "Write absolute dates in notes and tasks, never 'next Friday'", ""),
    ("no-emoji", "feedback", None,
     "No emoji in code, commit messages or docs", ""),
    ("lumen-architecture", "project", "lumen",
     "How Lumen is put together and why the index is a single file",
     "Pages are parsed in parallel, rendered from one template, and the search index is "
     "written last. Nothing outside the output folder is ever touched."),
    ("lumen-index-format", "project", "lumen",
     "The search index is one file, written atomically, rebuilt only for changed pages",
     "Terms are sorted and prefix-compressed, postings are delta-encoded. The file is "
     "written next to the final path and renamed, so a reader never sees half an index."),
    ("lumen-release-checklist", "project", "lumen",
     "Tag, build the three targets, checksum, then the changelog, in that order",
     "The changelog is written last because it quotes the checksums. The tag is created "
     "from the commit that CI built, never from the working tree."),
    ("lumen-markdown-quirks", "project", "lumen",
     "Front matter is optional; tables need a header row or they render as text",
     "Nested lists use four spaces. A fenced block inside a list item must be indented to "
     "the item's text, otherwise the renderer closes the list."),
    ("apiary-budgets", "project", "apiary",
     "Budget ceilings are per project, enforced at the proxy, not the client",
     "A request over budget gets a 429 with the remaining amount in a header. Budgets "
     "reset at midnight UTC and the counters live in memory, backed up every minute."),
    ("apiary-providers", "project", "apiary",
     "Three upstream providers behind one route table; failover is by error class",
     "Timeouts and 5xx move to the next provider, 4xx never do. Latency is recorded but "
     "not used for routing, because it made the choice flap."),
    ("apiary-key-rotation", "project", "apiary",
     "Provider keys rotate on the first of the month; the proxy reads them at start",
     "A rotation needs a restart, which takes two seconds. The old key stays valid for a "
     "day so in-flight requests finish."),
    ("apiary-logging", "project", "apiary",
     "Request logs keep the route and token counts, never the prompt body",
     "Logs are rotated daily and kept for two weeks. Anything that would identify a "
     "person is dropped before the line is written."),
    ("thesis-scope", "project", "field-notes",
     "Chapter three covers retrieval failure, not generation",
     "The claim is that most failures are decided before the model sees a token: the "
     "query, the chunking and the index. Generation quality is a separate chapter."),
    ("thesis-replication-plan", "project", "field-notes",
     "Replicate two prior results before proposing anything new",
     "The first replication is done and matches within noise. The second needs a dataset "
     "that has to be requested, and the request goes out this week."),
    ("thesis-reading-list", "project", "field-notes",
     "Forty papers on the list; twelve read in full, the rest skimmed for the method",
     "Each paper gets a note with the setup, the metric and one sentence on what would "
     "make the result not hold. Notes live next to the PDF."),
    ("harbour-config-format", "project", "harbour",
     "One TOML file per environment; secrets are references, never values",
     "A reference looks like vault:project/name and is resolved at deploy time. A config "
     "that contains a literal secret fails validation."),
    ("harbour-rollback", "project", "harbour",
     "Rollback means redeploying the previous manifest, not reverting the git history",
     "Every deploy stores its manifest. A rollback is a deploy of the one before, so the "
     "history stays honest and the log shows both events."),
    ("atlas-corpus", "project", "atlas",
     "Support tickets from 2023 to 2025, anonymised, about 40 thousand rows",
     "Names, addresses and order numbers are replaced by placeholders before anything is "
     "embedded. The raw export is deleted after the anonymised copy is verified."),
    ("atlas-embedding-models", "project", "atlas",
     "Three models compared at the same dimension; the smallest is within two points",
     "Recall at 10 is within two points across the three, and the smallest is four times "
     "faster. The decision waits for the evaluation on the long tickets."),
    ("atlas-eval-protocol", "project", "atlas",
     "Fixed query set of 300, judged in two passes, disagreements go to a third",
     "The query set never changes between runs, so numbers stay comparable. Judgements "
     "are stored with the model name and the date."),
    ("site-archive-page", "project", "site",
     "The archive page is the only missing piece; it needs tags first", ""),
    ("inbox-rules", "project", "inbox-zero",
     "Mail is filed by sender domain first, then by keyword, never by content",
     "Filing by content was tried and dropped: it was slow and it was wrong in ways that "
     "were hard to notice. A message that matches nothing stays in the inbox."),
    ("signalworks-alert-rules", "project", "signalworks",
     "An alert needs two consecutive out-of-range readings before it pages anyone",
     "One reading is noise, two in a row is a trend. The threshold and the window are per "
     "sensor type, and the defaults are conservative."),
    ("signalworks-log-format", "project", "signalworks",
     "Sensor logs are CSV with a UTC timestamp, one file per device per day",
     "The header row is mandatory. A file is closed at midnight UTC and never edited "
     "afterwards; corrections go in a sidecar file."),
    ("fieldcraft-packing-list", "project", "fieldcraft",
     "One packing list per trip type; the spare batteries line has been missed twice",
     "The list is checked off at the door, not in the van. After a trip the list is "
     "updated the same day, while the misses are still fresh."),
    ("kiln-cache-keys", "project", "kiln",
     "Cache keys hash inputs and the tool version; a version bump invalidates everything",
     "Keys never include timestamps or absolute paths. A cold cache is expected after a "
     "tool upgrade and is not treated as a bug."),
    ("postcard-template", "project", "postcard",
     "One template, one data file; clients never edit the HTML", ""),
    ("gutter-rotation", "project", "gutter",
     "Rotate at 100 MB or weekly, keep four archives",
     "Archives are compressed and named with the date. The job logs what it removed, so a "
     "missing file can be explained after the fact."),
    ("spindle-models", "project", "spindle",
     "The speech model runs offline; a night of audio takes about two hours",
     "Long recordings are cut at silences of two seconds or more. Timestamps refer to the "
     "original file, not the cut pieces."),
    ("almanac-format", "project", "almanac",
     "One line per release: date, project, what broke, which commit fixed it",
     "The log is append-only and plain text, so it can be searched with grep. A release "
     "that broke nothing gets no line."),
    ("machine-setup", "reference", None,
     "Where the models live and why the cache is on the external drive",
     "Models are large and rarely change, so they sit on the external drive with a cache "
     "of the two in use on the internal one. The paths are set in one shell file."),
    ("backup-routine", "reference", None,
     "Nightly snapshot of the projects folder, weekly copy to the external drive",
     "Snapshots are kept for 30 days. A restore is tested on the first of the month, on "
     "a scratch folder, and the result is written in the log."),
    ("ci-runners", "reference", "harbour",
     "Two self-hosted runners; the second one is only for releases",
     "The release runner has the signing key and no network access except the artifact "
     "store. The other one runs everything else and can be wiped freely."),
    ("glossary-retrieval", "reference", "field-notes",
     "Recall at k, MRR and nDCG as used in chapter three, with the exact formulas",
     "Each metric is defined once, with the cutoff written out, so a number quoted in the "
     "text can be recomputed from the tables."),
    ("style-guide-docs", "reference", "lumen",
     "Docs headings are sentence case; code samples are runnable",
     "A sample that cannot be pasted and run is marked as a sketch. Commands are shown "
     "without a prompt character so they copy cleanly."),
    ("release-calendar", "reference", None,
     "Lumen ships on the first Tuesday of the month, Apiary whenever a provider changes",
     "Other projects ship when they are ready. A release never goes out on a Friday or "
     "the day before a trip."),
    ("vault-layout", "reference", "apiary",
     "Secrets live under one prefix per project; read access is per project",
     "The gateway can read its own prefix and nothing else. Adding a project means "
     "adding a prefix and a policy, in that order."),
    ("hosting-notes", "reference", "backlot",
     "Static sites on one small host behind a CDN; exports go to object storage",
     "The host serves nothing dynamic. DNS changes are made by hand and written in the "
     "log, with the old value, before they are made."),
    ("editor-setup", "reference", None,
     "Editor settings live in the dotfiles repo; formatters run on save", ""),
]

# Chi rimanda a chi: i `[[nome]]` che una scheda scrive. Ogni legame e' scritto una
# volta sola (dal lato piu' vecchio): il grafo li tratta come archi non orientati.
# Le schede che qui non compaiono in nessuna lista sono gli orfani della demo.
LEGAMI_MEMORIA = {
    "user-role": ["writing-style", "explain-tradeoffs", "plain-status-updates"],
    "user-schedule": ["plain-status-updates", "release-calendar", "inbox-rules"],
    "user-thesis-status": ["thesis-scope", "thesis-reading-list"],
    "user-hardware": ["machine-setup", "ci-runners", "spindle-models", "fieldcraft-packing-list"],
    "writing-style": ["style-guide-docs", "commit-messages"],
    "commit-messages": ["small-prs", "test-first-on-bugs"],
    "no-surprise-refactors": ["small-prs", "lumen-architecture"],
    "test-first-on-bugs": ["lumen-markdown-quirks", "apiary-providers"],
    "ask-before-deleting": ["backup-routine", "gutter-rotation"],
    "small-prs": ["lumen-release-checklist"],
    "dependency-policy": ["lumen-architecture", "harbour-config-format"],
    "explain-tradeoffs": ["atlas-embedding-models", "apiary-providers"],
    "lumen-architecture": ["lumen-index-format", "lumen-markdown-quirks",
                           "lumen-release-checklist", "style-guide-docs"],
    "lumen-release-checklist": ["release-calendar", "ci-runners"],
    "apiary-budgets": ["apiary-providers", "apiary-logging", "apiary-key-rotation"],
    "apiary-key-rotation": ["vault-layout"],
    "apiary-providers": ["apiary-logging"],
    "thesis-scope": ["thesis-replication-plan", "glossary-retrieval", "atlas-eval-protocol"],
    "thesis-reading-list": ["thesis-replication-plan"],
    "atlas-corpus": ["atlas-embedding-models", "atlas-eval-protocol"],
    "atlas-eval-protocol": ["glossary-retrieval"],
    "harbour-config-format": ["harbour-rollback", "vault-layout", "ci-runners"],
    "signalworks-alert-rules": ["signalworks-log-format", "fieldcraft-packing-list",
                                "gutter-rotation"],
    "signalworks-log-format": ["gutter-rotation"],
    "kiln-cache-keys": ["lumen-index-format", "hosting-notes"],
    "hosting-notes": ["backup-routine"],
    "almanac-format": ["lumen-release-checklist", "kiln-cache-keys"],
    "machine-setup": ["backup-routine"],
}


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


def cartella_demo(cwd):
    """Una cartella VERA, sotto `PLANCIA_HOME/lavoro`, al posto di `~/dev/<nome>`:
    una sessione chiusa la cui cartella non esiste piu' e' "persa" (la
    trascrizione si cerca per cartella), e lo stato "chiusa" del task Riprendi
    va mostrato con una che c'e'. Nessun percorso della macchina di chi la crea
    finisce nel repo: sta nell'archivio dimostrativo, che si butta."""
    cartella = store.config.DATA_DIR / "lavoro" / Path(cwd).name
    cartella.mkdir(parents=True, exist_ok=True)
    return str(cartella)


def cartella_claude_config():
    """`PLANCIA_HOME/claude-config`: il CLAUDE_CONFIG_DIR finto sotto cui
    scrivere la trascrizione di `scrivi_trascrizione_chiusa`, mai il vero
    `~/.claude` dell'utente (regola della sessione)."""
    return store.config.DATA_DIR / "claude-config"


def scrivi_trascrizione_chiusa(cwd, session_id):
    """La trascrizione finta per lo stato "chiusa" di riprendi.stato
    (LOTTO-L2-DEMO punto 1): il codice vero la cerca in
    `CLAUDE_CONFIG_DIR/projects/<cartella>/<session_id>.jsonl`, dove
    `<cartella>` è `richiamo.cartella_sessione(cwd)` (lo stesso calcolo che fa
    `riprendi._trascrizione_claude`). Si scrive sotto `PLANCIA_HOME/claude-config`
    invece che nel `~/.claude` vero: per vederla nel server bisogna esportare
    CLAUDE_CONFIG_DIR su questa cartella (il valore lo stampa `main()`), non
    toccare l'archivio vero dell'utente.
    """
    cartella = cartella_claude_config() / "projects" / richiamo.cartella_sessione(cwd)
    cartella.mkdir(parents=True, exist_ok=True)
    riga = {
        "type": "assistant",
        "timestamp": quando(1),
        "message": {"role": "assistant", "content": [
            {"type": "text",
             "text": "The retry budget is wired into the nightly job now: it stops "
                     "after three attempts instead of hammering the queue until morning."}]},
    }
    (cartella / f"{session_id}.jsonl").write_text(json.dumps(riga) + "\n", encoding="utf-8")


def scrivi_config_server():
    """`config.json` nella PLANCIA_HOME finta (correzione del critico 18/09,
    LOTTO-L2-DEMO): il ticker di `plancia.api.serve` gira comunque anche con
    `--no-sync` (quel flag salta solo il sync d'avvio, non il thread che
    rilancia `start_sync` ogni `sync_caldo_minuti`), e un giro caldo durante
    gli scatti rilegge Codex/Claude veri della macchina e ingerisce nomi reali
    nel db dimostrativo. Un `sync_caldo_minuti` alto tiene il ticker fermo
    per ore, quindi non conta più quanto lo script che fa gli scatti resta
    acceso. `motore_riepilogo: template` evita che il primo caricamento di
    Oggi, se la cache del riepilogo per qualche motivo non fa match, lanci un
    `claude -p` vero (plancia/recap.py, default 'claude') dentro l'ambiente
    finto."""
    store.config.save_config({
        "sync_caldo_minuti": 1440,
        "sync_freddo_minuti": 1440,
        "motore_riepilogo": "template",
    })


def main():
    scrivi_config_server()
    conn = store.connect()
    store.init_db(conn)
    store.migrate(conn)
    for tabella in ("events", "sessions", "commits", "tasks", "posts", "knowledge",
                    "repos", "project_links", "projects", "capabilities", "agenda", "runs"):
        conn.execute(f"DELETE FROM {tabella}")

    ids = {}
    for key, nome, kind, prio, pin, riassunto in PROGETTI + AREE + PROGETTI_AREA + SENZA_AREA:
        pid = store.upsert_project(conn, key, nome, kind=kind, priority=prio, pinned=pin,
                                   summary=riassunto, auto=0, _force=True)
        ids[key] = pid
        store.link_project(conn, pid, "repo", key)
        conn.execute("INSERT INTO repos(name, description, visibility, url, pushed_at, "
                     "project_id, updated_at) VALUES(?,?,?,?,?,?,?)",
                     (key, riassunto[:70], "public", f"https://github.com/example/{key}",
                      quando(1), pid, store.now()))

    # Le tre aree (LOTTO-L2-DEMO punto 1): stesso set_parent che usa un uso
    # vero, non un parent_id scritto a mano, così un errore lì lo si vede qui.
    for padre, figli in FIGLI_AREA.items():
        for figlio in figli:
            esito = slot.set_parent(conn, figlio, padre, "l2-demo-aree")
            if not esito["ok"]:
                raise RuntimeError(f"set_parent({figlio}, {padre}): {esito['motivo']}")

    conn.execute("UPDATE projects SET next_action=? WHERE key='atlas'",
                 ("score the fourth model before writing anything up",))
    conn.execute("UPDATE projects SET next_action=? WHERE key='signalworks'",
                 ("decide which two tools get the shared config format",))
    conn.execute("UPDATE projects SET next_action=? WHERE key='fieldcraft'",
                 ("write the packing list once, stop rebuilding it per trip",))
    conn.execute("UPDATE projects SET next_action=? WHERE key='backlot'",
                 ("move the last export script off the machine under the desk",))
    conn.execute("UPDATE projects SET next_action=? WHERE key='gutter'",
                 ("add the disk-full alert before it happens again",))
    conn.execute("UPDATE projects SET next_action=? WHERE key='almanac'",
                 ("log last week's breakage before it is forgotten",))
    conn.execute("UPDATE projects SET next_action=? WHERE key='spindle'",
                 ("fix the timestamp drift on recordings over an hour",))
    conn.execute("UPDATE projects SET status='in pausa' WHERE key='inbox-zero'")
    conn.execute("UPDATE projects SET status='concluso' WHERE key='site'")

    # Ultime attività scaglionate per gli 8 progetti nuovi (LOTTO-L2-DEMO
    # punto 1, correzione del critico 18/09): senza questo, postcard e kiln
    # non hanno nessuna riga in SESSIONI e restano "never" nel pannello
    # Prossimi e nelle card di Progetti. Le tre aree sono padri senza sessioni
    # proprie: si toccano con la data del figlio più recente (min(giorni fa)
    # in SESSIONI), così l'area non sembra più vecchia del lavoro che contiene.
    # I tre progetti senza area (gutter, almanac, spindle) e i due figli nuovi
    # di backlot (postcard, kiln) prendono una data scaglionata a mano, diversa
    # l'una dall'altra: il numero non deve avere senso, deve solo essere distinto.
    store.touch_project(conn, ids["postcard"], quando(3))
    store.touch_project(conn, ids["kiln"], quando(6))
    store.touch_project(conn, ids["gutter"], quando(2))
    store.touch_project(conn, ids["almanac"], quando(10))
    store.touch_project(conn, ids["spindle"], quando(5))
    # signalworks: min(lumen 0, apiary 0, atlas 4) = 0
    store.touch_project(conn, ids["signalworks"], quando(0))
    # fieldcraft: min(field-notes 1, harbour 2, inbox-zero 24) = 1
    store.touch_project(conn, ids["fieldcraft"], quando(1))
    # backlot: min(site 8, postcard 3, kiln 6) = 3
    store.touch_project(conn, ids["backlot"], quando(3))

    for i, (key, titolo, n_user, n_tools, out, giorni) in enumerate(SESSIONI):
        inizio = quando(giorni, 9 + (i % 8))
        # due agenti sullo stesso archivio: uno ogni tre è Codex
        agente = "codex" if i % 3 == 1 else "claude"
        scambi = 4 if (agente == "codex" and i % 6 == 1) else 0
        # una sessione dura: con inizio e fine uguali la colonna Durata dell'app resta vuota
        fine = (datetime.strptime(inizio, "%Y-%m-%dT%H:%M:%SZ")
                + timedelta(seconds=90 * n_user)).strftime("%Y-%m-%dT%H:%M:%SZ")
        conn.execute(
            "INSERT INTO sessions(session_id, project_id, file, cwd, title, first_prompt, "
            "started_at, ended_at, n_user, n_assistant, n_tools, models, tools, "
            "in_tokens, out_tokens, agent, scambi, updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (f"demo-{i:03d}", ids[key], "", f"~/dev/{key}", titolo,
             titolo + ". Start from what is already there and do not rewrite the module.",
             inizio, fine, n_user, n_user * 6, n_tools,
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

    for titolo, key, prio, stato, chiuso, due in TASK:
        ts = quando(random.randint(1, 6))
        conn.execute(
            "INSERT INTO tasks(title, body, status, priority, project_id, source, due, "
            "created_at, updated_at, done_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (titolo, "", stato, prio, ids[key], "claude", due, ts, ts,
             quando(chiuso) if chiuso is not None else None))

    # Le tre carte di stato di "Riprendi" (vedi il commento su TASK_RIPRESA):
    # session_id/agent/cwd/host, le colonne che riprendi.stato legge per
    # decidere. Nessun `due`: qui il punto è lo stato di ripresa, non le
    # scadenze scaglionate (quelle sono in TASK, sopra).
    for titolo, key, sid, agent, cwd, host in TASK_RIPRESA:
        ts = quando(1)
        if not host:
            # una sessione "chiusa" si riprende solo se la sua cartella c'e' ancora
            # (riprendi._stato_da): ne serve una vera, dentro l'archivio dimostrativo
            cwd = cartella_demo(cwd)
        conn.execute(
            "INSERT INTO tasks(title, body, status, priority, project_id, source, "
            "session_id, agent, cwd, host, created_at, updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (titolo, "", "aperto", 1, ids[key], "claude", sid, agent, cwd,
             host, ts, ts))

    # La trascrizione finta per lo stato "chiusa": vedi scrivi_trascrizione_chiusa.
    chiusa = next(t for t in TASK_RIPRESA if t[2] == "demo-closed-01")
    scrivi_trascrizione_chiusa(cartella_demo(chiusa[4]), chiusa[2])

    for testo, stato, key, fonte in POST:
        ts = quando(random.randint(0, 8))
        conn.execute(
            "INSERT INTO posts(platform, status, text, url, project_id, source_ref, "
            "published_at, created_at, updated_at) VALUES('x',?,?,?,?,?,?,?,?)",
            (stato, testo, "https://x.com/example/status/1" if stato == "pubblicato" else None,
             ids[key], fonte, ts if stato == "pubblicato" else None, ts, ts))

    # Un generatore a parte: aggiungere o togliere schede non deve spostare i numeri
    # casuali di tutto quello che viene dopo nell'archivio.
    caso_memoria = random.Random(41)
    nomi_memoria = {m[0] for m in MEMORIA}
    for nome, tipo, key, descrizione, dettaglio in MEMORIA:
        vicini = [v for v in LEGAMI_MEMORIA.get(nome, []) if v in nomi_memoria and v != nome]
        corpo = f"# {nome}\n\n{descrizione}\n"
        if dettaglio:
            corpo += f"\n{dettaglio}\n"
        if vicini:
            corpo += "\nSee also " + ", ".join(f"[[{v}]]" for v in vicini) + ".\n"
        conn.execute(
            "INSERT INTO knowledge(name, path, scope, description, type, body, links, "
            "project_id, updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (nome, f"/demo/{nome}.md", "demo", descrizione, tipo, corpo,
             json.dumps(vicini), ids.get(key), quando(caso_memoria.randint(1, 20))))

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
    print(f"per vedere lo stato \"chiusa\" (task Riprendi): "
          f"export CLAUDE_CONFIG_DIR={cartella_claude_config()}")


if __name__ == "__main__":
    main()
