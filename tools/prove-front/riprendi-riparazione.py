"""Prove del front per la RIPARAZIONE-SERVER della seconda passata di Plancia 2.0.

Il tester (Chrome headless, un archivio dimostrativo) aveva trovato nella
dashboard web:

- "In background" su una sessione APERTA mostrava «avviato in background ->
  undefined #undefined», chiudeva il cassetto e non copiava niente: il server
  risponde `lanciato: false` con il piano e il messaggio, e il front li
  ignorava;
- il piano ("riprende la sessione originale" / "parte una sessione NUOVA") non
  compariva mai prima del lancio, anche se l'endpoint lo dava gia';
- rifiniture: nella Ricerca la barra laterale evidenziava ancora «Oggi»; nel
  dettaglio di un post l'etichetta «fonte» era minuscola; su mobile il badge del
  conteggio copriva l'icona; nel grafo della memoria a 65 nodi i nomi dei vicini
  del nodo scelto si sovrapponevano.

Sono prove statiche sul sorgente (come le altre di questa cartella) piu' un
controllo eseguito con Node, quando c'e', del testo che `pianoTesto()` compone;
il comportamento nel browser, con lo schermo davanti, lo guarda chi ha fatto la
riparazione (istantanee in tools/scatti.sh e nel rapporto).
"""

import json
import re
import shutil
import subprocess


def _leggi(radice, nome):
    return (radice / "web" / nome).read_text(encoding="utf-8")


def _dizionario(sorgente, nome):
    marcatore = f"const {nome} = {{"
    if marcatore not in sorgente:
        return ""
    i = sorgente.index(marcatore)
    return sorgente[i:sorgente.index("\n};", i)]


def _funzione(sorgente, firma):
    """Il testo di una `function nome(...) { ... }` (graffe bilanciate), o ''."""
    if firma not in sorgente:
        return ""
    i = sorgente.index(firma)
    j = sorgente.index(") {", i) + 2      # la graffa del corpo, non quella di un parametro `= {}`
    livello = 0
    for k in range(j, len(sorgente)):
        if sorgente[k] == "{":
            livello += 1
        elif sorgente[k] == "}":
            livello -= 1
            if livello == 0:
                return sorgente[i:k + 1]
    return sorgente[i:]


def _linea(sorgente, marcatore):
    """L'intera dichiarazione `const X = ...;` che comincia con `marcatore`."""
    if marcatore not in sorgente:
        return ""
    i = sorgente.index(marcatore)
    livello = 0
    for k in range(i, len(sorgente)):
        c = sorgente[k]
        if c in "([{":
            livello += 1
        elif c in ")]}":
            livello -= 1
        elif c == ";" and livello <= 0:
            return sorgente[i:k + 1]
    return sorgente[i:]


PIANI = (("piano_riprendi", ("{sid}",)), ("piano_copia", ("{sid}",)),
         ("piano_nuova", ("{motivo}",)), ("piano_niente", ("{sid}",)),
         ("piano_niente_codex", ("{sid}", "{motivo}")), ("piano_da_zero", ()),
         ("copia_sessione", ()), ("continua_riprendi", ()), ("continua_copia", ()),
         ("continua_nuova", ()))

NOMI_NODE = (
    "pianoTesto(): sessione chiusa, in italiano, dice che riprende la sessione originale",
    "pianoTesto(): sessione persa, in italiano, dice NUOVA e il motivo",
    "pianoTesto(): sessione aperta, in inglese, dice che non la tocca e mette l'id corto",
    "pianoTesto(): il motivo con un carattere HTML viene scappato",
)


def _chiavi(blocco):
    return re.findall(r"['\"]([a-z_]+)['\"]\s*:\s*'((?:[^'\\]|\\.)*)'", blocco)


def esegui(prova, radice) -> None:
    js = _leggi(radice, "app.js")
    css = _leggi(radice, "style.css")
    en = dict(_chiavi(_dizionario(js, "EN")))
    it = dict(_chiavi(_dizionario(js, "IT_TESTI")))

    # --- i testi del piano -------------------------------------------------
    for chiave, segnaposti in PIANI:
        prova(f"il testo «{chiave}» c'e' in inglese e in italiano",
              chiave in en and chiave in it, f"en={chiave in en} it={chiave in it}")
        prova(f"...e porta i segnaposto {segnaposti or 'nessuno'} in tutte e due le lingue",
              all(p in en.get(chiave, "") and p in it.get(chiave, "") for p in segnaposti),
              f"{en.get(chiave)!r} / {it.get(chiave)!r}")

    # --- il cassetto mostra il piano PRIMA di lanciare ---------------------
    prova("pianoTesto() e mostraPiano() esistono",
          bool(_funzione(js, "function pianoTesto(")) and bool(_funzione(js, "function mostraPiano(")), "")
    apri = _funzione(js, "async function apriRiprendi(")
    prova("il cassetto di un task chiede il piano e lo mostra (mostraPiano(r.piano))",
          "mostraPiano(r.piano)" in apri and "/api/riprendi/' + dati.task" in apri, apri[-500:])
    prova("...anche per una riga della lavagna con la sua sessione (anteprima su /api/cantiere)",
          "anteprima: true" in apri and "dati.sessione" in apri, apri[-800:])
    prova("...e c'e' una casella per lavorare su una COPIA, nascosta finche' la sessione non e' aperta",
          'name="copia"' in apri and 'id="riprendi-copia" hidden' in apri
          and "piano.stato !== 'viva'" in _funzione(js, "function mostraPiano("), "")
    prova("la casella 'copia' ricalcola il piano (change -> anteprima con copia)",
          "input[name=copia]" in js and "copia: box.checked" in js, "")

    # --- il click su In background con la sessione aperta ------------------
    i = js.index("name === 'riprendi-background'")
    corpo = js[i:js.index("name === 'lancio'", i)]
    prova("In background: se il server risponde lanciato:false il cassetto NON si chiude e si mostra il piano",
          "r.lanciato === false" in corpo and "mostraPiano(r.piano, r.messaggio)" in corpo
          and corpo.index("r.lanciato === false") < corpo.index("$('#drawer').hidden = true"),
          corpo[:1200])
    prova("...il messaggio da incollare si copia negli appunti (con un ripiego se negati)",
          "navigator.clipboard.writeText(r.messaggio)" in corpo and "catch (e)" in corpo, "")
    prova("...il toast di avvio non legge r.agente/r.run prima di aver controllato (niente 'undefined #undefined')",
          corpo.index("r.lanciato === false") < corpo.index("r.agente} #${r.run}"), "")
    prova("...e dice DOVE e' ripartito il lavoro (originale, copia o nuova)",
          "T('continua_' + (r.continua || 'nuova'))" in corpo, "")
    prova("...la richiesta porta 'copia' sia per un task sia per la lavagna",
          corpo.count("copia") >= 4 and "scrive, copia" in corpo, "")

    # --- il motivo nuovo si traduce ----------------------------------------
    for motivo in ("la cartella della sessione non c'è più", "della sessione non si sa la cartella",
                   "il rollout è stato toccato da un lancio di Plancia appena finito"):
        prova(f"il motivo «{motivo}» ha la traduzione inglese (Tmot)",
              f'"{motivo}"' in js, "")

    # --- le rifiniture ------------------------------------------------------
    ric = _funzione(js, "function disegnaRisultati(")
    prova("Ricerca: nessuna voce della barra laterale resta evidenziata",
          "classList.remove('on')" in ric and ".rail nav a" in ric, ric[:400])
    dettaglio = js[js.index("DETTAGLI.social = async"):js.index("/* ------------------------------------------------------------------ memoria */")]
    prova("dettaglio di un post: l'etichetta e' «Fonte», maiuscola come le altre",
          "T('Fonte')" in dettaglio and "T('fonte')" not in dettaglio, "")
    prova("grafo della memoria: solo il nodo scelto o sotto il puntatore si scrive anche se si sovrappone",
          "const forte = prio >= 900;" in js and "if (!forte && presi.some(" in js, "")
    prova("...e il riquadro di una scritta e' piu' largo e alto (i nomi non si toccano)",
          "measureText(nome).width + 14" in js and "y - 14" in js and "y + 6" in js, "")
    mobile = css[css.index("@media (max-width: 860px)"):css.index("@media (max-width: 500px)")]
    prova("mobile: il conteggio e' un distintivo sull'angolo dell'icona, non sopra il suo centro",
          "left: calc(50% + 5px)" in mobile and ".rail nav a em" in mobile, "")

    # --- il testo che pianoTesto() compone, eseguito per davvero -------------
    node = shutil.which("node")
    if not node:
        for nome in NOMI_NODE:
            prova(nome, True, "saltato: node non e' installato su questa macchina")
        return
    pezzi = [_dizionario(js, "EN") + "\n};", _dizionario(js, "IT_TESTI") + "\n};",
             _linea(js, "const esc = "), _linea(js, "const T = (s) =>"),
             _linea(js, "const fmt = "),
             _linea(js, "const MOTIVI_PREFISSI = "), _funzione(js, "function Tmot("),
             _funzione(js, "function pianoTesto(")]
    if not all(pezzi):
        prova("estratti da app.js i pezzi per eseguire pianoTesto()", False,
              str([i for i, p in enumerate(pezzi) if not p]))
        return
    script = "let UILANG = 'it';\n" + "\n".join(pezzi) + """
const chiusa = { modo: 'riprendi', stato: 'chiusa', motivo: 'x', agent: 'claude', origine: 'abcd1234-ffff' };
const persa = { modo: 'nuova', stato: 'persa', motivo: 'sessione scaduta', agent: 'claude', origine: 'abcd1234-ffff' };
const aperta = { modo: 'niente', stato: 'viva', motivo: 'aperta in /x', agent: 'claude', origine: 'abcd1234-ffff' };
const strano = { modo: 'nuova', stato: 'persa', motivo: 'cartella <b>&', agent: 'claude', origine: 'abcd1234-ffff' };
const fuori = {};
fuori.chiusa_it = pianoTesto(chiusa);
fuori.persa_it = pianoTesto(persa);
UILANG = 'en';
fuori.aperta_en = pianoTesto(aperta);
fuori.strano_en = pianoTesto(strano);
console.log(JSON.stringify(fuori));
"""
    try:
        r = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=15)
        fuori = json.loads(r.stdout.strip().splitlines()[-1]) if r.returncode == 0 else None
        errore = r.stderr[-500:]
    except Exception as exc:  # noqa: BLE001 - un NO pulito
        fuori, errore = None, repr(exc)
    if fuori is None:
        for nome in NOMI_NODE:
            prova(nome, False, f"node: {errore}")
        return
    prova(NOMI_NODE[0], "Riprende la sessione originale (abcd1234)" in fuori["chiusa_it"]
          and "non in una sessione nuova" in fuori["chiusa_it"], fuori["chiusa_it"])
    prova(NOMI_NODE[1], "NUOVA" in fuori["persa_it"] and "sessione scaduta" in fuori["persa_it"],
          fuori["persa_it"])
    prova(NOMI_NODE[2], "abcd1234" in fuori["aperta_en"] and "will not touch" in fuori["aperta_en"],
          fuori["aperta_en"])
    prova(NOMI_NODE[3], "<b>" not in fuori["strano_en"] and "&lt;b&gt;" in fuori["strano_en"],
          fuori["strano_en"])
