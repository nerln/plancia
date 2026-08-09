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

RADICE = Path.home() / ".claude" / "projects"

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


def _progetto(percorso: Path) -> str:
    """Il nome cartella che Claude Code usa per il progetto, reso leggibile."""
    nome = percorso.parent.name
    return nome.replace("-Users-eugenionerelli-", "").replace("-", "/").strip("/")


def _leggi(percorso: Path):
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
                "progetto": _progetto(percorso),
                "percorso": str(percorso),
                "riga": n,
            }


def indicizza(conn, completo: bool = False, radice: Path | None = None) -> dict:
    """Aggiorna l'indice. Incrementale: un file già visto e non cambiato si salta.

    Torna il conto di cosa è successo, perché un indicizzatore che dice solo
    "fatto" non permette di accorgersi che ha saltato tutto.
    """
    prepara(conn)
    radice = radice or RADICE
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

        righe = list(_leggi(percorso))
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
    sql = ("SELECT sessione, ruolo, ts, progetto, percorso, riga, "
           "snippet(turni_fts, 0, '«', '»', '…', 24) AS frammento "
           "FROM turni_fts WHERE turni_fts MATCH ?")
    args = [domanda]
    if progetto:
        sql += " AND progetto LIKE ?"
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


def stato(conn) -> dict:
    prepara(conn)
    n = conn.execute("SELECT COUNT(*) FROM turni_fts").fetchone()[0]
    f = conn.execute("SELECT COUNT(*) FROM turni_file").fetchone()[0]
    peso = conn.execute("SELECT COALESCE(SUM(LENGTH(testo)),0) FROM turni_fts").fetchone()[0]
    return {"turni": n, "file": f, "testo_mb": round(peso / 1e6, 2)}
