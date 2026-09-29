"""L'indice sui turni: cercare dentro quello che è stato detto, non solo il titolo.

Fino al 9 agosto 2026 `plancia_search` prometteva "tutto quello che Plancia sa" e
indicizzava, per ogni sessione, il **solo primo prompt**. Misurato: 0,80 MB su
979 MB di transcript, cioè lo 0,08%. Nessuna risposta di Claude, niente di quello
che veniva scoperto a metà lavoro, niente di quello che si vuole ritrovare sei
settimane dopo. Ed è per questo che in tutte le sessioni registrate quel tool è
stato chiamato cinque volte e non è mai diventato un'abitudine: non trovava.

Qui invece finisce la prosa vera di ogni turno, di Claude e sua. Il conto che
rende la cosa possibile: dentro quei 979 MB di JSONL il testo è l'1,7%, circa 17
MB, perché il resto sono metadati, allegati e risultati di tool. Un indice su
diciassette megabyte sta in tasca.

Ogni risultato torna con il percorso del file e il numero di riga, così la cosa
trovata si apre invece di essere riassunta.
"""

from __future__ import annotations

import json
import os
import sqlite3
from bisect import bisect_right
from pathlib import Path

from . import config, esclusi

# Prima si leggeva `Path.home() / ".claude" / "projects"` congelato una volta
# per tutte all'importazione del modulo: su una macchina con
# `CLAUDE_CONFIG_DIR` puntato altrove (o in una prova che sposta
# `config.CLAUDE_DIR` per isolarsi, come fa tools/prove/sessione.py)
# l'indicizzazione guardava sempre `~/.claude/projects` vero e non trovava
# niente (residuo dei tester dell'ondata 2, L1-INGEST-B, 16/09/2026). Niente
# costante di modulo: si legge `config.CLAUDE_DIR` a ogni chiamata, come fanno
# già `ingest.py` e `sessione.py` per lo stesso motivo.

SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS turni_fts USING fts5(
    testo,
    sessione UNINDEXED,
    ruolo UNINDEXED,
    ts UNINDEXED,
    progetto UNINDEXED,
    percorso UNINDEXED,
    riga UNINDEXED
);
CREATE TABLE IF NOT EXISTS turni_file (
    percorso TEXT PRIMARY KEY,
    mtime REAL NOT NULL,
    dimensione INTEGER NOT NULL,
    turni INTEGER NOT NULL DEFAULT 0
);
-- Da riga dell'indice a file: un intervallo di rowid per file (le righe di un
-- file si scrivono di seguito). Serve alla ricerca per sapere di chi e' una
-- riga senza leggere la riga: le colonne di `turni_fts` stanno nella tabella
-- del contenuto, e leggerle per ogni corrispondenza costa un accesso a disco
-- ciascuna (cinque secondi per "il" a cache fredda su 40 mila turni).
CREATE TABLE IF NOT EXISTS turni_mappa (
    rid_da INTEGER PRIMARY KEY,
    rid_a INTEGER NOT NULL,
    percorso TEXT NOT NULL,
    sessione TEXT NOT NULL,
    progetto TEXT NOT NULL
);
"""

#: Sotto questa soglia un turno è "ok", "fatto", "sì": rumore che gonfia l'indice
#: senza che nessuno lo cerchi mai.
MINIMO = 40


def prepara(conn) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def _testo(msg: dict) -> str:
    """La prosa di un messaggio, senza i blocchi che non sono prosa.

    I risultati dei tool restano fuori di proposito: sono il grosso dei byte e
    quasi mai la cosa che si ricorda. Chi cerca il contenuto di un file cerca il
    file, non la sessione in cui è stato letto.
    """
    contenuto = msg.get("content")
    if isinstance(contenuto, str):
        return contenuto
    if not isinstance(contenuto, list):
        return ""
    pezzi = [c.get("text") or "" for c in contenuto
             if isinstance(c, dict) and c.get("type") == "text"]
    return "\n".join(p for p in pezzi if p.strip())


def casa_codificata(casa) -> str:
    """La home scritta come la scrive Claude Code nei nomi cartella. E' la stessa
    codifica di `esclusi._codifica` (misurata sui nomi veri di
    `~/.claude/projects`): ogni carattere che non e' `[A-Za-z0-9]` diventa un
    trattino, uno per uno. Su macOS e Linux `/Users/x` da' `-Users-x`; su Windows
    `C:\\Users\\x` da' `C--Users-x` (i due punti e la barra sono due trattini)."""
    return esclusi._codifica(str(casa))


#: La home scritta come la scrive Claude Code nei nomi cartella.
CASA = casa_codificata(Path.home())


def _etichetta(nome: str) -> str:
    """Da nome cartella di Claude Code a etichetta corta.

    Le cartelle sono il percorso vero con gli slash sostituiti da trattini, e i
    trattini nei nomi veri non si distinguono da quelli aggiunti: la decodifica
    esatta non esiste. L'etichetta serve a dire dove si stava lavorando e a
    reggere un filtro, quindi si punta al leggibile.
    """
    resto = nome[len(CASA):] if nome.startswith(CASA) else nome
    resto = resto.strip("-")
    if resto.startswith("dev-"):
        # I worktree di Claude finiscono in `--claude-worktrees-<nome>`: sono lo
        # stesso progetto e vanno sotto la stessa etichetta.
        return resto[4:].split("--claude-worktrees", 1)[0].strip("-") or "dev"
    # Prima del Drive: le scratchpad stanno sotto /private/tmp ma si portano
    # dentro il percorso del Drive, e senza questo controllo finivano etichettate
    # come lavoro vero con dentro un uuid.
    if resto.startswith(("private-tmp", "private-var")):
        return "tmp"
    if "Il-mio-Drive" in resto:
        coda = resto.split("Il-mio-Drive", 1)[1].strip("-")
        return f"Drive/{coda.replace('-', ' ')}" if coda else "Drive"
    return resto.replace("-", " ") or "casa"


def _progetto(percorso: Path, radice: Path) -> str:
    """Il progetto di un transcript, risalendo dai sottoagenti.

    I transcript dei sottoagenti stanno in `<progetto>/subagents/workflows/<id>/`,
    quindi la cartella che li contiene è l'id del workflow e non dice niente.
    Quella buona è la prima sotto la radice.
    """
    try:
        parti = percorso.relative_to(radice).parts
    except ValueError:
        return _etichetta(percorso.parent.name)
    return _etichetta(parti[0]) if len(parti) > 1 else "casa"


def _leggi(percorso: Path, radice: Path):
    """I turni di un file, con il numero di riga a cui stanno."""
    sessione = percorso.stem
    with percorso.open(encoding="utf-8", errors="replace") as fh:
        for n, riga in enumerate(fh, 1):
            try:
                d = json.loads(riga)
            except Exception:
                continue
            msg = d.get("message")
            if not isinstance(msg, dict) or msg.get("role") not in ("assistant", "user"):
                continue
            testo = _testo(msg).strip()
            if len(testo) < MINIMO:
                continue
            yield {
                "testo": testo,
                "sessione": sessione,
                "ruolo": msg["role"],
                "ts": d.get("timestamp") or "",
                "progetto": _progetto(percorso, radice),
                "percorso": str(percorso),
                "riga": n,
            }


def indicizza(conn, completo: bool = False, radice: Path | None = None, escl: dict | None = None) -> dict:
    """Aggiorna l'indice. Incrementale: un file già visto e non cambiato si salta.

    Torna il conto di cosa è successo, perché un indicizzatore che dice solo
    "fatto" non permette di accorgersi che ha saltato tutto.
    """
    prepara(conn)
    radice = radice or (config.CLAUDE_DIR / "projects")
    escl = escl if escl is not None else esclusi.carica()
    if completo:
        conn.execute("DELETE FROM turni_fts")
        conn.execute("DELETE FROM turni_file")
        conn.execute("DELETE FROM turni_mappa")

    visti = {r[0]: (r[1], r[2]) for r in
             conn.execute("SELECT percorso, mtime, dimensione FROM turni_file")}

    esito = {"file_nuovi": 0, "file_aggiornati": 0, "file_saltati": 0, "turni": 0}
    for percorso in sorted(radice.rglob("*.jsonl")):
        # Cartella o sessione privata: fuori dall'indice a testo pieno prima
        # ancora di guardare mtime/dimensione. `radice` è la stessa che
        # `_componenti_progetti` userà per il confronto: nelle prove che la
        # spostano è quella, non la costante di modulo, a dover corrispondere.
        if esclusi.trascrizione_esclusa(percorso, escl, radice=radice):
            continue
        chiave = str(percorso)
        try:
            st = percorso.stat()
        except OSError:
            continue
        prima = visti.get(chiave)
        if prima and abs(prima[0] - st.st_mtime) < 1 and prima[1] == st.st_size:
            esito["file_saltati"] += 1
            continue

        if prima:
            conn.execute("DELETE FROM turni_fts WHERE percorso = ?", (chiave,))
            conn.execute("DELETE FROM turni_mappa WHERE percorso = ?", (chiave,))
            esito["file_aggiornati"] += 1
        else:
            esito["file_nuovi"] += 1

        righe = list(_leggi(percorso, radice))
        if righe:
            ultimo = _ultimo_id(conn)
            conn.executemany(
                "INSERT INTO turni_fts(testo, sessione, ruolo, ts, progetto, percorso, riga) "
                "VALUES(:testo, :sessione, :ruolo, :ts, :progetto, :percorso, :riga)", righe)
            nuovo = _ultimo_id(conn)
            # le righe di un file si scrivono di seguito: se cosi' non e' stato,
            # l'intervallo non si registra e la mappa risulta incompleta (sotto)
            if nuovo - ultimo == len(righe):
                conn.execute(
                    "INSERT OR REPLACE INTO turni_mappa(rid_da, rid_a, percorso, sessione, progetto) "
                    "VALUES(?,?,?,?,?)",
                    (ultimo + 1, nuovo, chiave, righe[0]["sessione"], righe[0]["progetto"]))
        conn.execute(
            "INSERT INTO turni_file(percorso, mtime, dimensione, turni) VALUES(?,?,?,?) "
            "ON CONFLICT(percorso) DO UPDATE SET mtime=excluded.mtime, "
            "dimensione=excluded.dimensione, turni=excluded.turni",
            (chiave, st.st_mtime, st.st_size, len(righe)))
        esito["turni"] += len(righe)

    # La mappa dei rowid e' un indice dell'indice: se non copre tutte le righe
    # (primo giro dopo l'aggiornamento, righe cancellate dalla purga dei percorsi
    # esclusi, righe scritte da fuori) si rifa' da capo, una volta.
    if mappa(conn) is None:
        ricostruisci_mappa(conn)
    conn.commit()
    return esito


#: Il progetto vero, quando Plancia lo conosce. La cartella da cui parte una
#: sessione dice poco: il 94% dei turni sta sotto una sola cartella, il Drive,
#: perché è da lì che si lavora. Ma l'ingest ha già legato ogni sessione al suo
#: progetto, quindi il nome buono si prende con una giuntura e la cartella resta
#: come ripiego per le sessioni che l'ingest non ha ancora visto.
#:
#: `main.` davanti alle tabelle: con i compartimenti la connessione ha delle
#: viste temporanee con lo stesso nome, e una giuntura sulle viste (che filtrano
#: con `IN (SELECT ...)`) faceva ripetere quel controllo per ogni riga trovata:
#: quattro secondi per la parola "il".
GIUNTURA = ("LEFT JOIN main.sessions ON sessions.session_id = turni_fts.sessione "
            "LEFT JOIN main.projects ON projects.id = sessions.project_id")
ETICHETTA = "COALESCE(NULLIF(projects.name, ''), turni_fts.progetto)"
#: La stessa etichetta per chi guarda dentro un compartimento: il progetto conta
#: solo se sessione e progetto sono visibili a chi guarda (`_tp_sp`).
ETICHETTA_FILTRATA = ("CASE WHEN _tp_sp(sessions.id, projects.id) THEN "
                      "COALESCE(NULLIF(projects.name, ''), turni_fts.progetto) "
                      "ELSE turni_fts.progetto END")

#: Gli operatori che FTS5 riconosce. Se ce n'è uno, la domanda è scritta apposta
#: e va lasciata stare.
OPERATORI = ("\"", "*", " OR ", " AND ", " NOT ", "NEAR(", ":")


def _domanda(q: str) -> str:
    """Da parole a query FTS5, con l'OR al posto dell'AND.

    FTS5 mette AND fra le parole, quindi chi scrive tre parole trova solo i turni
    che le contengono tutte e tre. Provato il 9 agosto 2026: `node_modules editor
    nozze` dava zero risultati mentre ognuna delle tre, da sola, ne dava. Con OR
    il punteggio fa il suo lavoro e mette davanti chi ne contiene di più, che è
    quello che uno si aspetta scrivendo tre parole.
    """
    q = (q or "").strip()
    if not q or any(o in q for o in OPERATORI):
        return q
    parole = [p for p in q.split() if p]
    return " OR ".join(parole) if len(parole) > 1 else q


# --------------------------------------------------------------------------
# la mappa da riga a file
# --------------------------------------------------------------------------

def _ultimo_id(conn) -> int:
    """L'ultimo rowid dell'indice. Si legge da `turni_fts_docsize` (una riga per
    turno, minuscola) e non da `turni_fts`, che per un massimo leggerebbe tutto."""
    return conn.execute("SELECT COALESCE(MAX(id), 0) FROM turni_fts_docsize").fetchone()[0]


def mappa(conn):
    """La mappa da rowid a file, o None se non copre tutto l'indice.

    Torna `(inizi, blocchi)`: `inizi` e' la lista ordinata dei primi rowid,
    `blocchi[i]` e' `(ultimo rowid, percorso, sessione, progetto)`. Copre tutto se
    la somma degli intervalli e' il numero dei turni e l'ultimo intervallo arriva
    all'ultimo turno: se qualcuno ha scritto o cancellato righe senza passare da
    `indicizza`, i conti non tornano e chi cerca ripiega sulla strada lenta."""
    try:
        n, ultimo = conn.execute(
            "SELECT COUNT(*), COALESCE(MAX(id), 0) FROM turni_fts_docsize").fetchone()
        righe = conn.execute(
            "SELECT rid_da, rid_a, percorso, sessione, progetto FROM turni_mappa "
            "ORDER BY rid_da").fetchall()
    except sqlite3.Error:
        return None
    coperti = sum(r[1] - r[0] + 1 for r in righe)
    if coperti != n or (righe and max(r[1] for r in righe) != ultimo):
        return None
    for prec, r in zip(righe, righe[1:]):
        if r[0] <= prec[1]:  # intervalli sovrapposti: qualcosa non torna
            return None
    return [r[0] for r in righe], [(r[1], r[2], r[3], r[4]) for r in righe]


def ricostruisci_mappa(conn) -> int:
    """Rifa la mappa leggendo tutto l'indice una volta. Torna il numero di
    intervalli. Un intervallo e' una serie di rowid di seguito dello stesso file:
    un buco (righe cancellate) ne apre un altro, cosi' la mappa non dice mai che
    esiste una riga che non c'e'."""
    prepara(conn)
    conn.execute("DELETE FROM turni_mappa")
    blocchi, corrente = [], None
    for rid, percorso, sessione, progetto in conn.execute(
            "SELECT rowid, percorso, sessione, progetto FROM turni_fts ORDER BY rowid"):
        if corrente and corrente[2] == percorso and corrente[1] + 1 == rid:
            corrente[1] = rid
            continue
        corrente = [rid, rid, percorso, sessione or "", progetto or ""]
        blocchi.append(corrente)
    conn.executemany(
        "INSERT INTO turni_mappa(rid_da, rid_a, percorso, sessione, progetto) "
        "VALUES(?,?,?,?,?)", blocchi)
    conn.commit()
    return len(blocchi)


# --------------------------------------------------------------------------
# la ricerca
# --------------------------------------------------------------------------

class Filtro:
    """Chi guarda dentro un compartimento: `vede(sessione, percorso)` dice se un
    turno e' suo, `sessioni` e `progetti` sono gli id (righe di `sessions` e
    `projects`) che gli sono visibili. Un progetto che non vede non ne dà il nome
    all'etichetta: resta la cartella."""

    def __init__(self, vede, sessioni, progetti):
        self.vede, self.sessioni, self.progetti = vede, sessioni, progetti


def _etichette(conn):
    """`session_id -> (id sessione, id progetto, nome progetto)`."""
    return {r[0]: (r[1], r[2], r[3]) for r in conn.execute(
        "SELECT s.session_id, s.id, p.id, p.name FROM main.sessions s "
        "LEFT JOIN main.projects p ON p.id = s.project_id")}


def _veloce(conn, domanda, limit, filtro, tetto, vuoi_turni, vuoi_gruppi):
    """La ricerca che non legge le righe trovate una per una.

    Il rango si prende dall'indice (`rowid, rank`, senza le colonne), il file di
    ogni riga dalla mappa, la visibilita' e l'etichetta una volta per file. Le
    righe vere si leggono solo per i pochi candidati: il resto costa l'indice e
    un po' di aritmetica. Torna `(turni, gruppi)`, o None se la mappa non copre
    l'indice (chi chiama ripiega sulla strada lenta)."""
    m = mappa(conn)
    if m is None:
        return None
    inizi, blocchi = m
    noti = _etichette(conn)
    per_blocco = {}

    def vedi(i):
        """Per un blocco: `(visibile, etichetta)`."""
        v = per_blocco.get(i)
        if v is None:
            _, percorso, sessione, cartella = blocchi[i]
            s = noti.get(sessione)
            ok, nome = True, cartella
            if filtro is not None:
                try:
                    ok = bool(filtro.vede(sessione, percorso))
                except Exception:  # noqa: BLE001 - nel dubbio, invisibile
                    ok = False
                if not (s and s[0] in filtro.sessioni and s[1] in filtro.progetti):
                    s = None
            if s and s[2]:
                nome = s[2]
            v = per_blocco[i] = (ok, nome)
        return v

    try:
        trovate = conn.execute(
            "SELECT rowid, rank FROM turni_fts WHERE turni_fts MATCH ? ORDER BY rank",
            (domanda,)).fetchall()
    except Exception:  # noqa: BLE001 - FTS5 rifiuta certe query scritte a mano
        return [], []
    conta, candidati, soglia = {}, [], None
    largo = limit * 4
    for rid, rank in trovate:
        i = bisect_right(inizi, rid) - 1
        if i < 0 or rid > blocchi[i][0]:
            return None
        ok, nome = vedi(i)
        if not ok:
            continue
        if vuoi_gruppi:
            conta[nome] = conta.get(nome, 0) + 1
        if not vuoi_turni or largo <= 0:
            continue
        if soglia is not None and rank > soglia:
            if not vuoi_gruppi:
                break
            continue
        candidati.append((rank, rid, i))
        if soglia is None and len(candidati) >= largo:
            soglia = rank  # i pari merito si tengono tutti: decide `ts`
    gruppi = []
    if vuoi_gruppi:
        # a pari conteggio l'ordine e' quello di sempre (nome alla rovescia): un
        # pari merito non deve cambiare il gruppo che compare per ultimo
        primi = sorted(sorted(conta.items(), key=lambda kv: kv[0], reverse=True),
                       key=lambda kv: -kv[1])[:tetto]
        gruppi = [{"progetto": nome or "?", "turni": n} for nome, n in primi]
    if not vuoi_turni or not candidati:
        return [], gruppi

    # `ORDER BY rank, ts DESC`: il tempo serve solo a sciogliere i pari merito
    ts = {}
    rids = [c[1] for c in candidati]
    for k in range(0, len(rids), 400):
        pezzo = rids[k:k + 400]
        for rid, t in conn.execute(
                "SELECT rowid, ts FROM turni_fts WHERE rowid IN (%s)" % ",".join("?" * len(pezzo)),
                pezzo):
            ts[rid] = t or ""
    candidati.sort(key=lambda c: c[1])
    candidati.sort(key=lambda c: ts.get(c[1], ""), reverse=True)
    candidati.sort(key=lambda c: c[0])
    scelti = candidati[:largo]
    dove = {c[1]: c[2] for c in scelti}
    dettagli = {}
    ordine = [c[1] for c in scelti]
    for k in range(0, len(ordine), 400):
        pezzo = ordine[k:k + 400]
        for r in conn.execute(
                "SELECT rowid, sessione, ruolo, ts, percorso, riga, "
                "snippet(turni_fts, 0, '«', '»', '…', 24) AS frammento "
                "FROM turni_fts WHERE turni_fts MATCH ? AND rowid IN (%s)" % ",".join("?" * len(pezzo)),
                [domanda] + pezzo):
            dettagli[r[0]] = r
    esito, visti = [], set()
    for rid in ordine:
        r = dettagli.get(rid)
        if r is None or r[4] != blocchi[dove[rid]][1]:
            return None  # la mappa non dice il vero: strada lenta
        d = {"sessione": r[1], "ruolo": r[2], "ts": r[3],
             "progetto": vedi(dove[rid])[1], "percorso": r[4], "riga": r[5],
             "frammento": r[6]}
        impronta = " ".join((d.get("frammento") or "").split())[:140]
        if impronta in visti:
            continue
        visti.add(impronta)
        esito.append(d)
        if len(esito) >= limit:
            break
    return esito, gruppi


def _lento(conn, domanda, limit, progetto, filtro, tetto, vuoi_turni, vuoi_gruppi):
    """La stessa ricerca in SQL, quando la mappa non c'e' o si cerca per progetto.
    Legge ogni riga trovata, quindi a cache fredda costa: per questo la mappa."""
    if filtro is None:
        etichetta, guardia = ETICHETTA, ""
    else:
        memo = {}

        def visibile_sql(sessione, percorso):
            k = (sessione, percorso)
            if k not in memo:
                try:
                    memo[k] = 1 if filtro.vede(sessione, percorso or "") else 0
                except Exception:  # noqa: BLE001 - nel dubbio, invisibile
                    memo[k] = 0
            return memo[k]
        conn.create_function("_tp_ok", 2, visibile_sql)
        conn.create_function("_tp_sp", 2, lambda s, p: 1 if (
            s in filtro.sessioni and p in filtro.progetti) else 0)
        etichetta = ETICHETTA_FILTRATA
        guardia = " AND _tp_ok(turni_fts.sessione, turni_fts.percorso)"
    esito, gruppi = [], []
    try:
        if vuoi_turni:
            sql = ("SELECT turni_fts.sessione, turni_fts.ruolo, turni_fts.ts, %s AS progetto, "
                   "turni_fts.percorso, turni_fts.riga, "
                   "snippet(turni_fts, 0, '«', '»', '…', 24) AS frammento "
                   "FROM turni_fts %s WHERE turni_fts MATCH ?%s" % (etichetta, GIUNTURA, guardia))
            args = [domanda]
            if progetto:
                # L'espressione va ripetuta: SQLite non lascia usare l'alias del
                # SELECT dentro il WHERE.
                sql += " AND %s LIKE ?" % etichetta
                args.append("%%%s%%" % progetto)
            # Si pesca largo e si stringe dopo: lo stesso testo compare in piu' file
            # perche' ogni sottoagente si porta dietro la sua copia del prompt, e senza
            # questo la prima pagina di risultati e' fatta di doppioni.
            sql += " ORDER BY rank, ts DESC LIMIT ?"
            args.append(limit * 4)
            visti = set()
            for r in conn.execute(sql, args).fetchall():
                d = dict(zip(("sessione", "ruolo", "ts", "progetto", "percorso", "riga",
                              "frammento"), tuple(r)))
                impronta = " ".join((d.get("frammento") or "").split())[:140]
                if impronta in visti:
                    continue
                visti.add(impronta)
                esito.append(d)
                if len(esito) >= limit:
                    break
        if vuoi_gruppi:
            gr = conn.execute(
                "SELECT %s e, COUNT(*) n FROM turni_fts %s WHERE turni_fts MATCH ?%s "
                "GROUP BY e ORDER BY n DESC, e DESC LIMIT ?" % (etichetta, GIUNTURA, guardia),
                (domanda, tetto)).fetchall()
            gruppi = [{"progetto": r[0] or "?", "turni": r[1]} for r in gr]
    except Exception:  # noqa: BLE001
        # FTS5 rifiuta certe query scritte a mano: meglio nessun risultato che
        # un'eccezione in faccia a chi stava solo cercando una parola.
        return [], []
    return esito, gruppi


def ricerca(conn, q: str, limit: int = 12, progetto: str | None = None,
            filtro: Filtro | None = None, tetto: int = 8,
            turni: bool = True, gruppi: bool = True):
    """`(turni, gruppi)` di una domanda: i turni trovati (il testo com'era, con
    dove riaprirlo) e da quali progetti vengono, contati su tutto l'indice.

    Con `filtro` (i compartimenti) il filtro sta DENTRO la ricerca, prima del
    taglio per rango: chi ha poche cose in un archivio grande le trova. Senza
    `progetto` e con la mappa in ordine si usa la strada veloce."""
    prepara(conn)
    domanda = _domanda(q)
    if not domanda:
        return [], []
    if not progetto:
        fatto = _veloce(conn, domanda, limit, filtro, tetto, turni, gruppi)
        if fatto is not None:
            return fatto
    return _lento(conn, domanda, limit, progetto, filtro, tetto, turni, gruppi)


def cerca(conn, q: str, limit: int = 12, progetto: str | None = None) -> list:
    """Cerca nei turni. Torna il testo com'era, non un riassunto.

    Il frammento è verbatim con i termini marcati, e accanto c'è dove riaprirlo:
    percorso e riga. Un risultato che non si può aprire vale la metà.
    """
    return ricerca(conn, q, limit, progetto, gruppi=False)[0]


def raggruppa(conn, q: str, tetto: int = 8) -> list:
    """Da quali progetti vengono i risultati di una domanda, e quanti per uno.

    Una pagina di risultati ne mostra dodici e non dice niente sugli altri
    trecento. Questo conta su tutto l'indice, quindi si vede subito se la cosa
    cercata sta in un progetto solo o è sparsa, e si può stringere.
    """
    return ricerca(conn, q, tetto=tetto, turni=False)[1]


def progetti(conn) -> list:
    """Le etichette presenti nell'indice, dalla più battuta alla meno.

    Serve a rendere il filtro usabile: senza questo elenco `--project` è un
    campo in cui indovinare, e un filtro che non matcha torna vuoto senza dire
    perché.
    """
    prepara(conn)
    righe = conn.execute(
        f"SELECT {ETICHETTA} e, COUNT(*) n FROM turni_fts {GIUNTURA} "
        "WHERE e <> '' GROUP BY e ORDER BY n DESC").fetchall()
    return [{"progetto": r[0], "turni": r[1]} for r in righe]


def stato(conn) -> dict:
    prepara(conn)
    n = conn.execute("SELECT COUNT(*) FROM turni_fts").fetchone()[0]
    f = conn.execute("SELECT COUNT(*) FROM turni_file").fetchone()[0]
    peso = conn.execute("SELECT COALESCE(SUM(LENGTH(testo)),0) FROM turni_fts").fetchone()[0]
    return {"turni": n, "file": f, "testo_mb": round(peso / 1e6, 2)}
