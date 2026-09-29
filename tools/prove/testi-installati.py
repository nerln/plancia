"""Prove sui testi che Plancia scrive sulla macchina di chi la installa e che un
agente legge: le skill installate (italiano e inglese), le descrizioni e le
istruzioni del server MCP, i prompt degli agenti vocali, il briefing e l'avviso
che l'hook infila in ogni sessione.

Plancia la installano persone diverse dall'autore, quindi un testo di questo
tipo parla dell'utente come "l'utente" (in inglese "the user", "they",
"their"), mai come di una persona precisa. Qui si controlla che non ci sia:

- il nome dell'autore. Non e' scritto in questo file: si legge da
  `pyproject.toml`, dove sta gia' come autore del pacchetto, e si cerca (nome
  di battesimo e cognome, anche dentro un'altra parola, per prendere pure un
  percorso come `/Users/<nome>/`) in ogni testo raccolto qui sotto e in ogni
  stringa dei programmi installati (`plancia/*.py`, `bin/*`);
- un pronome maschile riferito all'utente: `he`, `him`, `his`, `himself` come
  parole intere in inglese; `lui`, `suo`, `sua`, `suoi`, `sue` e i clitici
  (`digli`, `dagli` come "da' a lui", `glielo`, `gliela`, `chiedergli`...) in
  italiano.

I testi si raccolgono importando i moduli (le costanti delle skill, gli schemi
dei tool, la risposta a `initialize`, il briefing di un archivio in memoria) e,
per l'hook `bin/plancia-hook` che e' uno script senza estensione, leggendone le
stringhe dal sorgente con `ast`: cosi' i commenti e i docstring, dove l'autore
racconta la storia di una decisione, non contano. Non contano nemmeno i testi
che l'utente non riceve mai.

Limite dichiarato: le regole dell'italiano riconoscono una lista di forme, non
la grammatica. `gli` da solo e' anche l'articolo ("gli obiettivi") e non si puo'
vietare; `dagli` e' anche "da + gli" ("dagli appunti"): si vieta solo davanti a
un articolo o a `da`. Una frase nuova con un pronome che la lista non conosce
passa: chi scrive un testo per un agente lo rilegge comunque.
"""

import ast
import re
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent.parent

# Inglese: parole intere, senza distinguere le maiuscole.
EN = re.compile(r"\b(?:he|him|his|himself)\b", re.I)

# Italiano. Le forme con `gli` attaccato a un verbo sono una lista, non un
# suffisso qualunque: `figli`, `fogli`, `sbagli` non c'entrano.
IT = re.compile(
    r"\b(?:lui|suo|sua|suoi|sue)\b"
    r"|\b\w*(?:glielo|gliela|gliele|gliene)\b"
    r"|\b(?:digli|dirgli|dargli|chiedigli|chiedergli|mostragli|mostrargli|"
    r"spiegagli|spiegargli|ricordagli|ricordargli|consegnagli|consegnargli|"
    r"riferiscigli|riferirgli)\b"
    r"|\bdagli\s+(?:da|un|una|uno|il|lo|la|l'|i|le)\b",
    re.I)


def _nomi_autore():
    """Nome di battesimo e cognome dell'autore, letti da pyproject.toml."""
    testo = (RADICE / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'authors\s*=\s*\[\s*\{\s*name\s*=\s*"([^"]+)"', testo)
    if not m:
        return []
    return [p for p in m.group(1).split() if len(p) >= 4]


def _trovati(testo, nomi):
    """Le parole di `testo` che non devono esserci, con un pezzo di contesto."""
    fuori = []
    for regola in (EN, IT):
        for m in regola.finditer(testo):
            fuori.append(testo[max(0, m.start() - 25):m.end() + 15].replace("\n", " "))
    minuscolo = testo.lower()
    for nome in nomi:
        if nome.lower() in minuscolo:
            fuori.append("<il nome dell'autore>")
    return fuori


def _stringhe(oggetto):
    """Tutte le stringhe dentro un dict/lista/stringa (gli schemi dei tool)."""
    if isinstance(oggetto, str):
        yield oggetto
    elif isinstance(oggetto, dict):
        for v in oggetto.values():
            yield from _stringhe(v)
    elif isinstance(oggetto, (list, tuple)):
        for v in oggetto:
            yield from _stringhe(v)


def _stringhe_del_sorgente(percorso):
    """Le stringhe di uno script Python, senza i docstring (i commenti non
    entrano in un albero `ast`)."""
    albero = ast.parse(Path(percorso).read_text(encoding="utf-8"))
    docstring = set()
    for nodo in ast.walk(albero):
        if isinstance(nodo, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            corpo = nodo.body
            if (corpo and isinstance(corpo[0], ast.Expr)
                    and isinstance(corpo[0].value, ast.Constant)
                    and isinstance(corpo[0].value.value, str)):
                docstring.add(id(corpo[0].value))
    return [n.value for n in ast.walk(albero)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
            and id(n) not in docstring]


def _istruzioni_del_server(mcp):
    """Il campo `instructions` della risposta a `initialize`."""
    raccolte = []
    vecchia = mcp.respond
    mcp.respond = lambda rid, result=None, error=None: raccolte.append(result)
    try:
        mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    finally:
        mcp.respond = vecchia
    return (raccolte[0] or {}).get("instructions", "") if raccolte else ""


def _briefing():
    import sqlite3
    from plancia import briefing, store
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    store.init_db(conn)
    try:
        return briefing.build(conn) + "\n" + briefing.build(conn, esteso=False)
    finally:
        conn.close()


def _testi():
    from plancia import agente, jarvis, mcp, recap, setup_claude

    testi = {}
    for lingua in ("it", "en"):
        testi[f"skill plancia ({lingua})"] = setup_claude.skill_text(lingua)
        testi[f"skill riepilogo ({lingua})"] = setup_claude.riepilogo_skill_text(lingua)
    for tool in mcp._TUTTI + mcp.TOOLS:
        testi[f"tool MCP {tool['name']}"] = "\n".join(_stringhe(tool))
    testi["indizi del dispatcher MCP"] = "\n".join(_stringhe(mcp.INDIZI))
    testi["istruzioni del server MCP"] = _istruzioni_del_server(mcp)
    testi["prompt dell'assistente vocale (agente)"] = agente.ISTRUZIONI
    testi["prompt di Jarvis"] = jarvis.PROMPT
    testi["prompt del riepilogo"] = recap.PROMPT
    testi["prompt della domanda a voce"] = recap.DOMANDA
    testi["briefing"] = _briefing()
    testi["avvisi dell'hook di sessione"] = "\n".join(
        _stringhe_del_sorgente(RADICE / "bin" / "plancia-hook"))
    return testi


def esegui(prova):
    nomi = _nomi_autore()
    prova("il nome dell'autore si legge da pyproject.toml", len(nomi) >= 2, str(nomi))

    # I due riconoscitori vedono davvero quello che devono vedere, e lasciano
    # stare quello che non c'entra: senza, una prova qui sotto potrebbe passare
    # perche' la regola non riconosce niente.
    prova("il riconoscitore inglese vede he, him, his",
          all(EN.search(f) for f in ("tell him", "if he asks", "on his Mac", "He said")))
    prova("e lascia stare the user, they, their, the, she",
          not any(EN.search(f) for f in
                  ("the user's Mac", "if they ask", "their projects", "then the end", "she")))
    prova("il riconoscitore italiano vede lui, suo, sua e i clitici",
          all(IT.search(f) for f in
              ("se te lo chiede lui", "il suo Mac", "la sua sessione", "digli la cartella",
               "dagli da incollare", "diglielo a voce", "chiediglielo", "evita di chiedergli")))
    prova("e lascia stare l'utente, gli articoli, dagli appunti e i figli",
          not any(IT.search(f) for f in
                  ("il Mac dell'utente", "gli obiettivi di Codex", "dagli appunti di sistema",
                   "i figli e i fogli", "sbagli spesso", "chiede l'utente")))
    prova("il nome dell'autore si trova anche dentro un percorso",
          bool(nomi) and bool(_trovati("/Users/" + nomi[0].lower() + "/x", nomi)))

    testi = _testi()
    prova("i testi installati sono stati raccolti tutti",
          len(testi) >= 30 and all(t.strip() for t in testi.values()),
          f"{len(testi)} testi, vuoti: {[n for n, t in testi.items() if not t.strip()]}")

    # Una prova positiva accanto a quelle "assenti": i testi parlano davvero
    # dell'utente, non e' sparito il soggetto.
    prova("la skill italiana parla dell'utente", "l'utente" in testi["skill plancia (it)"])
    prova("la skill inglese parla di the user",
          "the user" in testi["skill plancia (en)"])
    prova("la skill del riepilogo, nelle due lingue, parla dell'utente",
          "l'utente" in testi["skill riepilogo (it)"]
          and "the user" in testi["skill riepilogo (en)"])
    prova("le istruzioni del server MCP parlano di the user",
          "the user" in testi["istruzioni del server MCP"],
          testi["istruzioni del server MCP"][:120])

    for nome, testo in testi.items():
        fuori = _trovati(testo, nomi)
        prova(f"{nome}: niente nome dell'autore ne' pronomi maschili dell'utente",
              not fuori, str(fuori[:3]))

    # Ogni stringa dei programmi installati: niente nome dell'autore, mai (un
    # commento che racconta una decisione sta nel codice, non in una stringa).
    con_nome = []
    programmi = sorted((RADICE / "plancia").glob("*.py")) + sorted(
        p for p in (RADICE / "bin").iterdir() if p.is_file() and p.name != "plancia.cmd")
    for percorso in programmi:
        try:
            letterali = _stringhe_del_sorgente(percorso)
        except SyntaxError:
            continue  # non e' uno script Python
        for s in letterali:
            if any(n.lower() in s.lower() for n in nomi):
                con_nome.append(f"{percorso.name}: {s[:60]!r}")
    prova("nessuna stringa dei programmi installati porta il nome dell'autore",
          len(programmi) >= 20 and not con_nome,
          f"{len(programmi)} file; {con_nome[:3]}")
