"""Prove per LOTTO-L2-VISTA, lato front: statiche, si guarda solo il
sorgente (niente browser: quello lo fa tools/prova-video.sh, che apre
davvero la pagina e conta le righe di Prossimi, l'albero, il cassetto Dopo).
Qui si verifica solo quello che tools/prova-front.py non guarda già da solo:

- le chiavi T() nuove del lotto esistono in italiano (IT_TESTI o come frase
  italiana che è già, essa stessa, la chiave) e in inglese (EN);
- ogni data-act nuovo (prossimi-altri, albero-toggle, cassetto-dopo) ha un
  ramo `name === '...'` nel listener (tools/prova-front.py lo controlla già
  per TUTTI i data-act del file, ma un controllo mirato qui distingue subito
  "manca il gestore di un mio bottone" da "è un bottone di un altro lotto");
- "Task aperti" non è più il titolo del pannello di Oggi (prova rossa del
  lotto: prima della correzione lo è, con taskRows(d.task.slice(0,8)));
- le classi CSS concordate con L2-GLASS compaiono nel JS.

Funzione pubblica `esegui(prova, radice)`, stessa forma di
tools/prove-front/font.py (vedi tools/prove-front/README.md).
"""

import re


def _leggi(radice):
    return (radice / "web" / "app.js").read_text(encoding="utf-8")


def _dizionario(sorgente, nome):
    """Il corpo del dizionario `const NOME = { ... };`, così come
    tools/prova-front.py legge EN: da 'const NOME = {' al primo '\\n};'.

    '' (non un'eccezione) quando il blocco non c'è: senza, una singola
    chiamata che fallisce ferma con un ValueError l'intero modulo prima che
    una sola `prova()` sia stata registrata, e prova-front.py la conta come
    un solo fallimento col nome del file invece delle prove singole (una
    per una) che invocano questa funzione."""
    marcatore = f"const {nome} = {{"
    if marcatore not in sorgente:
        return ""
    inizio = sorgente.index(marcatore)
    fine = sorgente.index("\n};", inizio)
    return sorgente[inizio:fine]


def _chiavi(blocco):
    chiavi = set(re.findall(r"'((?:[^'\\]|\\.)*)'\s*:", blocco))
    chiavi |= set(re.findall(r'"((?:[^"\\]|\\.)*)"\s*:', blocco))
    return chiavi


CHIAVI_NUOVE = ("prossimi", "prossimi_altri", "prossimi_vuoto", "area_senza",
                "cartelle_viste", "tutti_i_task", "tutti_i_task_nota",
                "dopo", "dopo_conta")


def _prova_chiavi_t(prova, sorgente):
    en = _chiavi(_dizionario(sorgente, "EN"))
    it_testi = _chiavi(_dizionario(sorgente, "IT_TESTI"))

    mancano_it = [c for c in CHIAVI_NUOVE if c not in it_testi]
    prova("le chiavi nuove di Prossimi/albero/Dopo hanno un testo italiano (IT_TESTI)",
          not mancano_it, str(mancano_it))

    mancano_en = [c for c in CHIAVI_NUOVE if c not in en]
    prova("le stesse chiavi hanno un testo inglese (EN)",
          not mancano_en, str(mancano_en))

    # 'Lavagna' non è una chiave nuova (punto 5 del lotto: il nome della
    # chiave non cambia), ma il suo testo sì: deve valere qualcosa di
    # diverso da 'Lavagna'/'Board' in entrambe le lingue, altrimenti il
    # menu mostrerebbe ancora "Lavagna".
    prova("la chiave 'Lavagna' ha un nuovo testo italiano (IT_TESTI)",
          it_testi and "Lavagna" in it_testi, "")
    prova("la chiave 'Lavagna' non traduce più in inglese con 'Board'",
          "Board" not in _dizionario(sorgente, "EN"), "")

    # I due template con {n} portano davvero il segnaposto in entrambe le
    # lingue: senza, conN() sostituirebbe un '{n}' che non c'è, silenzioso.
    for chiave in ("prossimi_altri", "dopo_conta"):
        pattern = r"['\"]" + re.escape(chiave) + r"['\"]\s*:\s*'([^']*)'"
        m_it = re.search(pattern, _dizionario(sorgente, "IT_TESTI"))
        m_en = re.search(pattern, _dizionario(sorgente, "EN"))
        prova(f"IT_TESTI.{chiave} contiene il segnaposto {{n}}",
              bool(m_it) and "{n}" in m_it.group(1), m_it.group(1) if m_it else "non trovata")
        prova(f"EN.{chiave} contiene il segnaposto {{n}}",
              bool(m_en) and "{n}" in m_en.group(1), m_en.group(1) if m_en else "non trovata")


def _prova_data_act(prova, sorgente):
    azioni = set(re.findall(r"data-act=\"(\w[\w-]*)\"", sorgente))
    ascoltate = set(re.findall(r"name === '([\w-]+)'", sorgente))
    for nome in ("prossimi-altri", "albero-toggle", "cassetto-dopo"):
        prova(f"data-act=\"{nome}\" compare nel markup", nome in azioni, str(sorted(azioni)))
        prova(f"data-act=\"{nome}\" ha un ramo nel listener dei click",
              nome in ascoltate, str(sorted(ascoltate)))


def _prova_task_aperti_non_piu_titolo(prova, sorgente):
    # La prova rossa del lotto: prima della correzione, il pannello di Oggi
    # ha <h3>${T('Task aperti')}</h3> come titolo (il resto del file può
    # ancora citare "Task aperti" come chiave di traduzione per altri usi,
    # es. il tag sulla card di un progetto: quello non è la vista Oggi).
    prova("il pannello di Oggi non ha più \"Task aperti\" come titolo",
          "T('Task aperti')" not in sorgente and 'T("Task aperti")' not in sorgente,
          "")
    prova("il pannello di Oggi ha invece 'prossimi' come titolo",
          "T('prossimi')" in sorgente, "")


def _prova_albero_chiuso_solo_cartelle_viste(prova, sorgente):
    # Prova rossa della correzione [L2-VISTA-2]: prima, ogni padre nasceva
    # chiuso incondizionatamente ('albero-padre card chiusa' e
    # 'albero-figli" hidden' fissi nel template, mai dietro una condizione),
    # quindi anche un padre qualunque (Lumen, Apiary, non solo
    # 'cartelle-viste') nasceva con i figli nascosti dietro un pulsante
    # etichettato con la chiave T('cartelle_viste'), pensata per il nome di
    # quell'area sola. Qui si cerca il confronto esplicito su padre.key
    # vicino alla variabile 'chiusa', e si esclude che le vecchie stringhe
    # fisse siano ancora nel markup del padre.
    inizio = sorgente.index("function alberoPadre(")
    fine = sorgente.index("\n}", inizio)
    corpo = sorgente[inizio:fine]
    prova("alberoPadre confronta la chiave del padre con 'cartelle-viste' "
          "per decidere se nasce chiuso (non tutti i padri)",
          bool(re.search(r"chiusa\s*=\s*padre\.key\s*===\s*['\"]cartelle-viste['\"]", corpo)),
          corpo[:400])
    prova("il markup del padre non forza più 'card chiusa' per tutti",
          not re.search(r"""albero-padre card chiusa["'`]""", corpo), corpo[:400])
    prova("il markup dei figli non forza più 'hidden' per tutti",
          'class="albero-figli" hidden>' not in corpo, corpo[:400])


CLASSI_CONCORDATE = (
    "prossimi", "prossimi-area", "prossimi-area-nome", "prossimi-area-conta",
    "prossimi-riga", "prossimi-progetto", "prossimi-cosa", "prossimi-fonte",
    "fonte-task", "fonte-next", "fonte-vuoto", "prossimi-scadenza",
    "prossimi-quando", "prossimi-altri", "prossimi-vuoto",
    "albero", "albero-padre", "albero-toggle", "albero-figli", "albero-figlio",
    "albero-totali", "chiusa",
    "cassetto-dopo", "cassetto-dopo-lista",
)


def _prova_classi(prova, sorgente):
    mancanti = [c for c in CLASSI_CONCORDATE if c not in sorgente]
    prova("tutte le classi concordate con L2-GLASS compaiono nel JS",
          not mancanti, str(mancanti))


def _prova_oggi_aspetta_prossimi_prima_di_tornare(prova, sorgente):
    # Punto 7 del lotto: mai un segnaposto "carico..." per il solo pannello.
    # Statico: si controlla che dentro views.oggi ci sia un await di
    # /api/prossimi (qualunque esito, try/catch) PRIMA del `return` che
    # produce l'HTML della vista, non che il pannello aspetti da solo dopo
    # essere già a video.
    inizio = sorgente.index("views.oggi = async () => {")
    fine = sorgente.index("\n};", inizio)
    corpo = sorgente[inizio:fine]
    pos_fetch = corpo.find("/api/prossimi")
    pos_return = corpo.find("\n  return `")
    prova("views.oggi chiama /api/prossimi prima del return (niente 'carico...' di pannello)",
          pos_fetch != -1 and pos_return != -1 and pos_fetch < pos_return,
          f"fetch={pos_fetch} return={pos_return}")


def esegui(prova, radice) -> None:
    sorgente = _leggi(radice)
    _prova_chiavi_t(prova, sorgente)
    _prova_data_act(prova, sorgente)
    _prova_task_aperti_non_piu_titolo(prova, sorgente)
    _prova_classi(prova, sorgente)
    _prova_oggi_aspetta_prossimi_prima_di_tornare(prova, sorgente)
    _prova_albero_chiuso_solo_cartelle_viste(prova, sorgente)


if __name__ == "__main__":
    import sys
    from pathlib import Path

    RADICE = Path(__file__).resolve().parent.parent.parent
    sys.path.insert(0, str(RADICE))

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

    esegui(prova, RADICE)
    print(f"\n{passati} passate, {len(falliti)} fallite")
    if falliti:
        for f in falliti:
            print(f"  - {f}")
        sys.exit(1)
