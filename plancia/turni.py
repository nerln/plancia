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
from pathlib import Path

from . import config

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


#: La home scritta come la scrive Claude Code nei nomi cartella: gli slash
#: diventano trattini.
CASA = str(Path.home()).replace("/", "-")


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


def indicizza(conn, completo: bool = False, radice: Path | None = None) -> dict:
    """Aggiorna l'indice. Incrementale: un file già visto e non cambiato si salta.

    Torna il conto di cosa è successo, perché un indicizzatore che dice solo
    "fatto" non permette di accorgersi che ha saltato tutto.
    """
    prepara(conn)
    radice = radice or (config.CLAUDE_DIR / "projects")
    if completo:
        conn.execute("DELETE FROM turni_fts")
        conn.execute("DELETE FROM turni_file")

    visti = {r[0]: (r[1], r[2]) for r in
             conn.execute("SELECT percorso, mtime, dimensione FROM turni_file")}

    esito = {"file_nuovi": 0, "file_aggiornati": 0, "file_saltati": 0, "turni": 0}
    for percorso in sorted(radice.rglob("*.jsonl")):
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
            esito["file_aggiornati"] += 1
        else:
            esito["file_nuovi"] += 1

        righe = list(_leggi(percorso, radice))
        if righe:
            conn.executemany(
                "INSERT INTO turni_fts(testo, sessione, ruolo, ts, progetto, percorso, riga) "
                "VALUES(:testo, :sessione, :ruolo, :ts, :progetto, :percorso, :riga)", righe)
        conn.execute(
            "INSERT INTO turni_file(percorso, mtime, dimensione, turni) VALUES(?,?,?,?) "
            "ON CONFLICT(percorso) DO UPDATE SET mtime=excluded.mtime, "
            "dimensione=excluded.dimensione, turni=excluded.turni",
            (chiave, st.st_mtime, st.st_size, len(righe)))
        esito["turni"] += len(righe)

    conn.commit()
    return esito


#: Il progetto vero, quando Plancia lo conosce. La cartella da cui parte una
#: sessione dice poco: il 94% dei turni sta sotto una sola cartella, il Drive,
#: perché è da lì che si lavora. Ma l'ingest ha già legato ogni sessione al suo
#: progetto, quindi il nome buono si prende con una giuntura e la cartella resta
#: come ripiego per le sessioni che l'ingest non ha ancora visto.
GIUNTURA = ("LEFT JOIN sessions ON sessions.session_id = turni_fts.sessione "
            "LEFT JOIN projects ON projects.id = sessions.project_id")
ETICHETTA = "COALESCE(NULLIF(projects.name, ''), turni_fts.progetto)"

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


def cerca(conn, q: str, limit: int = 12, progetto: str | None = None) -> list:
    """Cerca nei turni. Torna il testo com'era, non un riassunto.

    Il frammento è verbatim con i termini marcati, e accanto c'è dove riaprirlo:
    percorso e riga. Un risultato che non si può aprire vale la metà.
    """
    prepara(conn)
    domanda = _domanda(q)
    if not domanda:
        return []
    sql = (f"SELECT turni_fts.sessione, turni_fts.ruolo, turni_fts.ts, {ETICHETTA} AS progetto, "
           "turni_fts.percorso, turni_fts.riga, "
           "snippet(turni_fts, 0, '«', '»', '…', 24) AS frammento "
           f"FROM turni_fts {GIUNTURA} WHERE turni_fts MATCH ?")
    args = [domanda]
    if progetto:
        # L'espressione va ripetuta: SQLite non lascia usare l'alias del SELECT
        # dentro il WHERE.
        sql += f" AND {ETICHETTA} LIKE ?"
        args.append(f"%{progetto}%")
    # Si pesca largo e si stringe dopo: lo stesso testo compare in piu' file
    # perche' ogni sottoagente si porta dietro la sua copia del prompt, e senza
    # questo la prima pagina di risultati e' fatta di doppioni.
    sql += " ORDER BY rank, ts DESC LIMIT ?"
    args.append(limit * 4)
    try:
        righe = conn.execute(sql, args).fetchall()
    except Exception:
        # FTS5 rifiuta certe query scritte a mano: meglio nessun risultato che
        # un'eccezione in faccia a chi stava solo cercando una parola.
        return []

    visti, esito = set(), []
    for r in righe:
        d = dict(r)
        impronta = " ".join((d.get("frammento") or "").split())[:140]
        if impronta in visti:
            continue
        visti.add(impronta)
        esito.append(d)
        if len(esito) >= limit:
            break
    return esito


def raggruppa(conn, q: str, tetto: int = 8) -> list:
    """Da quali progetti vengono i risultati di una domanda, e quanti per uno.

    Una pagina di risultati ne mostra dodici e non dice niente sugli altri
    trecento. Questo conta su tutto l'indice, quindi si vede subito se la cosa
    cercata sta in un progetto solo o è sparsa, e si può stringere.
    """
    prepara(conn)
    domanda = _domanda(q)
    if not domanda:
        return []
    try:
        righe = conn.execute(
            f"SELECT {ETICHETTA} e, COUNT(*) n FROM turni_fts {GIUNTURA} "
            "WHERE turni_fts MATCH ? GROUP BY e ORDER BY n DESC LIMIT ?",
            (domanda, tetto)).fetchall()
    except Exception:
        return []
    return [{"progetto": r[0] or "?", "turni": r[1]} for r in righe]


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
