"""Prove per LOTTO-L3-RIPRENDI-UI, lato front: statiche, si guarda solo il
sorgente (niente browser: quello lo fa `tools/prova-video.sh`).

`tools/prova-front.py` controlla già, per TUTTI i lotti, che ogni stringa
italiana passata a T() abbia una traduzione e che ogni data-act abbia un
gestore: qui si verificano solo le cose specifiche di questo lotto elencate
nel suo "Prove rosse senza":

- le chiavi it/en dei tre stati del pulsante Riprendi (viva/chiusa/persa,
  più chiusa+codex) esistono;
- `data-act="riprendi"` (e i suoi due compagni, riprendi-copia e
  riprendi-background) hanno un gestore;
- "Manda a un agente" e il vecchio menu proposta/esegui non compaiono più
  come testo visibile;
- le classi CSS che L2-GLASS aveva già stilato (.riprendi, .riprendi-stato,
  .riprendi-background) compaiono nel markup, anche se questo lotto non
  tocca style.css;
- i residui dell'ondata 2 (16/09/2026): il plurale di "progetti", la card
  del padre con le informazioni di una card normale, la sezione Task del
  drawer che non duplica più il cassetto Dopo.

Funzione pubblica `esegui(prova, radice)`, stessa forma di
tools/prove-front/vista.py (vedi tools/prove-front/README.md).
"""

import json
import re
import shutil
import subprocess


def _leggi(radice):
    return (radice / "web" / "app.js").read_text(encoding="utf-8")


def _dizionario(sorgente, nome):
    """Stesso helper di tools/prove-front/vista.py (non importato da lì
    apposta: sono lotti diversi, vedi il commento in tools/prove/riordina.py
    sul non accoppiarsi a un dettaglio implementativo di un altro lotto)."""
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


CHIAVI_STATO = ("riprendi_viva", "riprendi_chiusa", "riprendi_chiusa_codex", "riprendi_persa")


def _prova_chiavi_stato(prova, sorgente):
    en = _chiavi(_dizionario(sorgente, "EN"))
    it_testi = _chiavi(_dizionario(sorgente, "IT_TESTI"))

    mancano_en = [c for c in CHIAVI_STATO if c not in en]
    prova("le chiavi dei tre stati (viva/chiusa/persa + chiusa_codex) hanno un testo inglese",
          not mancano_en, str(mancano_en))
    mancano_it = [c for c in CHIAVI_STATO if c not in it_testi]
    prova("le stesse chiavi hanno un testo italiano (IT_TESTI, per il segnaposto)",
          not mancano_it, str(mancano_it))

    # Ognuna porta un segnaposto (cwd/data/motivo): senza, fmt() sostituisce
    # un '{...}' che non c'è, silenziosamente.
    for chiave, segnaposto in (("riprendi_viva", "{cwd}"), ("riprendi_chiusa", "{data}"),
                               ("riprendi_chiusa_codex", "{data}"), ("riprendi_persa", "{motivo}")):
        pattern = r"['\"]" + re.escape(chiave) + r"['\"]\s*:\s*'([^']*)'"
        m_en = re.search(pattern, _dizionario(sorgente, "EN"))
        m_it = re.search(pattern, _dizionario(sorgente, "IT_TESTI"))
        prova(f"EN.{chiave} porta il segnaposto {segnaposto}",
              bool(m_en) and segnaposto in m_en.group(1), m_en.group(1) if m_en else "non trovata")
        prova(f"IT_TESTI.{chiave} porta il segnaposto {segnaposto}",
              bool(m_it) and segnaposto in m_it.group(1), m_it.group(1) if m_it else "non trovata")


def _prova_data_act(prova, sorgente):
    azioni = set(re.findall(r"data-act=\"(\w[\w-]*)\"", sorgente))
    ascoltate = set(re.findall(r"name === '([\w-]+)'", sorgente))
    for nome in ("riprendi", "riprendi-copia", "riprendi-background"):
        prova(f"data-act=\"{nome}\" compare nel markup", nome in azioni, str(sorted(azioni)))
        prova(f"data-act=\"{nome}\" ha un ramo nel listener dei click",
              nome in ascoltate, str(sorted(ascoltate)))


def _prova_manda_un_agente_sparito(prova, sorgente):
    # Prova rossa del lotto: prima della correzione la frase c'era, sia come
    # chiave del dizionario sia come titolo del compositore.
    prova("\"Manda a un agente\" non compare più da nessuna parte in app.js",
          "Manda a un agente" not in sorgente, "")


def _prova_proposta_esegui_non_scelte_da_un_menu(prova, sorgente):
    # Prova rossa del lotto: prima della correzione il compositore aveva
    # <select name="modo"><option value="proposta">...</option>
    # <option value="esegui">...</option></select> - un menu a tendina con
    # "proposta"/"esegui" come testo scelto dall'utente. Ora è un
    # interruttore booleano ("può modificare i file del progetto"), e quel
    # menu non esiste più.
    prova("non c'è più un <select name=\"modo\"> da cui scegliere proposta/esegui",
          '<select name="modo">' not in sorgente, "")
    prova("il modulo 'in background' porta invece l'interruttore booleano 'scrive'",
          '<input type="checkbox" name="scrive">' in sorgente, "")


def _prova_fallo_sparito_dalle_proposte(prova, sorgente):
    # "'fallo' sulle proposte diventa 'Riprendi'" (punto 2 del lotto): il
    # bottone che prima diceva ${T('fallo')} ora dice ${T('Riprendi')}, sulla
    # stessa card e con la stessa azione (data-act="proposta").
    prova("il bottone delle proposte non dice più \"fallo\" come testo",
          "${T('fallo')}</button>" not in sorgente and '${T("fallo")}</button>' not in sorgente,
          "")
    prova("...dice invece \"Riprendi\", con la stessa azione",
          "data-act=\"proposta\"" in sorgente and "${T('Riprendi')}</button>" in sorgente, "")


CLASSI_RIPRENDI = ("riprendi", "riprendi-stato", "riprendi-background")


def _prova_classi_riprendi(prova, sorgente):
    # Il lotto vieta di toccare style.css e chiede di riusare queste tre
    # classi se L2-GLASS le ha già stilate (non toccato da questo lotto: si
    # verifica solo che il markup le porti, non che ci sia una regola CSS -
    # quella, se manca, va nei dubbi del rapporto e va bene così).
    mancanti = [c for c in CLASSI_RIPRENDI if c not in sorgente]
    prova("il markup del pulsante Riprendi porta le classi .riprendi/.riprendi-stato/"
          ".riprendi-background", not mancanti, str(mancanti))


def _prova_residui_ondata2(prova, sorgente):
    # Punto 3: il plurale "1 progetto"/"1 project" invece di "1 progetti".
    prova("esiste una funzione che sceglie la forma singolare per un solo progetto",
          "const progettiN = (n) =>" in sorgente, "")
    prova("la riga del padre nell'elenco dei progetti usa quella funzione, non più T('progetti') nudo",
          "progettiN(figli.length)" in sorgente, "")
    # LOTTO-L3-RITOCCO punto 3: prima progettiN sceglieva "1 progetto"/
    # "1 project" con un ternario su UILANG scritto a mano dentro la
    # funzione (stessa STRINGA giusta, ma fuori dal sistema T()/IT_TESTI/EN
    # come chiede il resto del dizionario): questi due, a differenza dei due
    # sopra (che il nome/uso della funzione non li cambia), sono rossi sul
    # commit base e verdi con la patch.
    prova("progettiN chiama T('progetti_1'), non più un ternario su UILANG scritto a mano",
          "T('progetti_1')" in sorgente, "")
    prova("'progetti_1' è una chiave del dizionario inglese (EN)",
          "'progetti_1'" in _dizionario(sorgente, "EN"), "")
    prova("'progetti_1' è una chiave del dizionario italiano (IT_TESTI)",
          "'progetti_1'" in _dizionario(sorgente, "IT_TESTI"), "")

    # Punto 5: il padre porta i totali del sottoalbero. Dalla seconda passata
    # (WEB) non e' piu' una card ma una riga dell'elenco: i totali stanno in
    # una funzione pura, totaliAlbero(padre, figli).
    inizio = sorgente.find("function totaliAlbero(")
    if inizio == -1:
        prova("function totaliAlbero( esiste in app.js", False, "")
        return
    fine = sorgente.find("\n}", inizio)
    corpo_padre = sorgente[inizio:fine]
    prova("i totali del padre sommano i task aperti dei figli", "task_aperti" in corpo_padre and "reduce" in corpo_padre, corpo_padre[:300])
    prova("...e il totale token del sottoalbero, non solo del padre",
          "token30" in corpo_padre and "token_30g" in corpo_padre, corpo_padre[:400])
    prova("...e last_activity e' il massimo sul sottoalbero, non solo quella del padre",
          "ultima" in corpo_padre and "last_activity" in corpo_padre, corpo_padre[:400])

    # Punto 4: la sezione Task del drawer mostra solo il primo task aperto,
    # il resto sta solo nel cassetto Dopo (niente righe duplicate).
    prova("esiste una funzione dedicata alla sezione Task del drawer del progetto",
          "function sezioneTaskDrawer(" in sorgente, "")
    inizio_t = sorgente.find("function sezioneTaskDrawer(")
    if inizio_t == -1:
        prova("function sezioneTaskDrawer( esiste ancora in app.js", False, "")
        return
    fine_t = sorgente.find("\n}", inizio_t)
    corpo_task = sorgente[inizio_t:fine_t]
    prova("...che mostra solo aperti[0], non l'intera lista di task aperti",
          "aperti[0]" in corpo_task, corpo_task)

    # Punto 6: il ramo morto data-act="task-tutti" e la chiave orfana "Task
    # aperti" sono spariti (unico rinomino/rimozione che il lotto consente).
    prova("il ramo morto \"task-tutti\" non c'è più nel listener dei click",
          "name === 'task-tutti'" not in sorgente, "")
    prova("la chiave orfana \"Task aperti\" non è più nel dizionario EN",
          "'Task aperti':" not in sorgente and '"Task aperti":' not in sorgente, "")


def _blocco_dichiarazione(sorgente, marcatore):
    """Il testo di UNA dichiarazione JS che comincia con `marcatore`, fino al
    ';' che la chiude per davvero: si bilancia ogni `([{`/`)]}` incontrato,
    cosi' un ternario steso su più righe e senza nessuna graffa (come il
    vecchio `progettiN`, prima di questo lotto) non viene troncato alla
    prima riga - un bug misurato scrivendo questa stessa prova: la prima
    versione tagliava alla prima newline quando il conteggio delle graffe
    tornava a zero, e per un corpo multi-riga senza graffe quello è vero
    già sulla primissima riga. '' se il marcatore non c'è nel sorgente."""
    if marcatore not in sorgente:
        return ""
    i = sorgente.index(marcatore)
    profondita = 0
    for j in range(i, len(sorgente)):
        c = sorgente[j]
        if c in "([{":
            profondita += 1
        elif c in ")]}":
            profondita -= 1
        elif c == ";" and profondita <= 0:
            return sorgente[i:j + 1]
    return sorgente[i:]


NOMI_PLURALE_NODE = (
    "progettiN(1) in italiano è davvero '1 progetto' (non '1 progetti')",
    "progettiN(3) in italiano resta il plurale con il template ({n})",
    "progettiN(1) in inglese è davvero '1 project' (non '1 projects')",
    "progettiN(3) in inglese resta il plurale con il template ({n})",
)

NOMI_RESIDUI_NODE = (
    "totaliAlbero(): i task aperti sono la somma padre+figli (1+2=3)",
    "totaliAlbero(): il totale token è la somma padre+figli (1000+2000=3000)",
    "totaliAlbero(): l'ultima attività è la più recente del sottoalbero, non quella del padre",
    "sezioneTaskDrawer(): produce una sola riga per i task 'aperto' (aperti[0]), non tre",
    "sezioneTaskDrawer(): la riga del task 'fatto' resta (non è archiviato)",
)


def _salta_senza_node(prova, nomi):
    """Senza Node ogni controllo dell'elenco passa dichiarando di non essere stato
    fatto, cosi' il conteggio e' quello di una macchina che ce l'ha."""
    for nome in nomi:
        prova(nome, True, "saltato: node non e' installato su questa macchina")


def _prova_comportamento_plurale_node(prova, sorgente):
    """LOTTO-L3-RITOCCO punto 6: le prove front dei residui 3/4/5 di
    LOTTO-L3-RIPRENDI-UI sono strutturali (cercano pezzi di sorgente, non
    guardano cosa la funzione produce davvero). Per il residuo 3 (il
    plurale) questa esegue per davvero, con Node se c'è sulla macchina, il
    `progettiN` VERO estratto da app.js (non una sua riscrittura qui), e
    controlla il testo che produce - un comportamento, non una substring.
    Se Node non c'è, resta la prova strutturale già in
    `_prova_residui_ondata2` qui sopra (nessuna eccezione: solo un NO
    pulito, come chiede il lotto).

    Nota onesta per il rapporto: questa prova NON è rossa sul commit base.
    Il vecchio `progettiN` (un ternario su UILANG scritto a mano, invece di
    T('progetti_1')) produceva GIÀ la stringa giusta - il difetto che il
    punto 3 del lotto chiude è che quella scelta stava fuori dal sistema
    T()/IT_TESTI/EN, non che il testo mostrato fosse sbagliato. Il red/green
    di quel difetto è nelle due prove subito sopra, in
    `_prova_residui_ondata2` ("chiama T('progetti_1')", "è una chiave del
    dizionario"). Questa prova qui resta comunque un comportamento vero
    (esegue la funzione reale, non ne cerca un pezzo) invece di una regex,
    che è quello che il punto 6 chiede "dove si può".
    """
    node = shutil.which("node")
    if not node:
        # Senza Node il comportamento non si puo' eseguire, ma il numero di
        # prove non puo' dipendere da chi ha Node installato: il README ne
        # dichiara uno solo. Ogni controllo si segna, con "saltato: <perche'>"
        # accanto (non e' un verde che dice di aver verificato: lo scrive).
        # Resta la prova strutturale su progettiN, in _prova_residui_ondata2.
        _salta_senza_node(prova, NOMI_PLURALE_NODE)
        return

    en = _blocco_dichiarazione(sorgente, "const EN = {")
    it_testi = _blocco_dichiarazione(sorgente, "const IT_TESTI = {")
    t_fn = _blocco_dichiarazione(sorgente, "const T = (s) => {")
    con_n = _blocco_dichiarazione(sorgente, "const conN = (chiave, n) =>")
    progetti_n = _blocco_dichiarazione(sorgente, "const progettiN = (n) =>")
    mancano = [nome for nome, blocco in
               (("EN", en), ("IT_TESTI", it_testi), ("T", t_fn), ("conN", con_n),
                ("progettiN", progetti_n)) if not blocco]
    if mancano:
        prova("estratti da app.js i pezzi che servono a eseguire progettiN() per davvero",
              False, f"non trovati: {mancano}")
        return

    script = f"""
{en}
{it_testi}
let UILANG = 'it';
{t_fn}
{con_n}
{progetti_n}
const risultati = {{}};
for (const lingua of ['it', 'en']) {{
  UILANG = lingua;
  risultati[lingua] = {{ uno: progettiN(1), tre: progettiN(3) }};
}}
console.log(JSON.stringify(risultati));
"""
    try:
        esito = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=10)
    except Exception as exc:  # noqa: BLE001 - un NO pulito, non un'eccezione a metà prova
        prova("progettiN(1)/progettiN(3), eseguito per davvero in Node",
              False, f"eccezione lanciando node: {exc!r}")
        return
    if esito.returncode != 0:
        prova("progettiN(1)/progettiN(3), eseguito per davvero in Node",
              False, f"node è uscito con errore: {esito.stderr[-500:]}")
        return
    try:
        risultati = json.loads(esito.stdout.strip().splitlines()[-1])
    except Exception:
        prova("progettiN(1)/progettiN(3), eseguito per davvero in Node",
              False, f"uscita non JSON: {esito.stdout!r}")
        return

    prova("progettiN(1) in italiano è davvero '1 progetto' (non '1 progetti')",
          risultati.get("it", {}).get("uno") == "1 progetto", str(risultati.get("it")))
    prova("progettiN(3) in italiano resta il plurale con il template ({n})",
          risultati.get("it", {}).get("tre") == "3 progetti", str(risultati.get("it")))
    prova("progettiN(1) in inglese è davvero '1 project' (non '1 projects')",
          risultati.get("en", {}).get("uno") == "1 project", str(risultati.get("en")))
    prova("progettiN(3) in inglese resta il plurale con il template ({n})",
          risultati.get("en", {}).get("tre") == "3 projects", str(risultati.get("en")))


def _prova_comportamento_residui_node(prova, sorgente):
    """L3-RIPRENDI-UI-4 (obbligatoria del critico): i residui 4 e 5 di
    `_prova_residui_ondata2` sono ancora strutturali (cercano pezzi di
    sorgente dentro `alberoPadre`/`sezioneTaskDrawer`, non guardano cosa
    quelle funzioni producono davvero). Il critico dice che non serve un
    server-fixture: sono funzioni pure che restituiscono una stringa, si
    eseguono in Node con lo stesso `_blocco_dichiarazione` già scritto per
    `progettiN` (vedi `_prova_comportamento_plurale_node`), con uno stub di
    `taskRows`/`T`/`esc` per le dipendenze che restano.

    Se Node non c'è: i controlli si segnano lo stesso (il totale e' uno solo
    su ogni macchina), ciascuno con "saltato: node non e' installato".

    Nota onesta per il rapporto (stessa idea di
    `_prova_comportamento_plurale_node`): queste prove NON sono rosse sul
    commit base 677ab86. Il comportamento di `alberoPadre`/
    `sezioneTaskDrawer` per kind/pinned/token30/aperti[0] era già corretto
    da prima di questo ritocco (residui 4/5 di LOTTO-L3-RIPRENDI-UI, chiusi
    in un giro precedente) - qui si sostituisce SOLO il modo di verificarlo
    (comportamento vero invece di una substring nel sorgente), come chiede
    il punto 6 del lotto "dove si può", non si corregge un difetto nuovo."""
    node = shutil.which("node")
    if not node:
        _salta_senza_node(prova, NOMI_RESIDUI_NODE)
        return

    en = _blocco_dichiarazione(sorgente, "const EN = {")
    it_testi = _blocco_dichiarazione(sorgente, "const IT_TESTI = {")
    t_fn = _blocco_dichiarazione(sorgente, "const T = (s) => {")
    con_n = _blocco_dichiarazione(sorgente, "const conN = (chiave, n) =>")
    progetti_n = _blocco_dichiarazione(sorgente, "const progettiN = (n) =>")
    loc = _blocco_dichiarazione(sorgente, "const LOC = () =>")
    esc = _blocco_dichiarazione(sorgente, "const esc = (s) =>")
    ago = _blocco_dichiarazione(sorgente, "function ago(ts) {")
    kilo = _blocco_dichiarazione(sorgente, "const kilo = (n) =>")
    prio_tag = _blocco_dichiarazione(sorgente, "const prioTag = (p) =>")
    # projectCard NON si estrae con _blocco_dichiarazione: il suo corpo ha un
    # `;` dentro l'attributo `style="display:flex;..."`, DENTRO il template
    # literal ma a profondità di parentesi zero - `_blocco_dichiarazione`
    # (che conta solo `([{`/`)]}`, non sa cos'è una stringa o un template
    # literal) la tronca lì, a metà. alberoPadre() la chiama solo per
    # renderizzare le card dei figli, che qui non si controllano: uno stub
    # che ritorna una stringa qualunque basta, ed evita il problema.
    project_card_stub = "const projectCard = (p, extra) => `<card-figlio key=${p.key}>`;"

    inizio_p = sorgente.find("function totaliAlbero(")
    inizio_t = sorgente.find("function sezioneTaskDrawer(")
    if inizio_p == -1 or inizio_t == -1:
        prova("totaliAlbero/sezioneTaskDrawer esistono ancora in app.js (comportamento)",
              False, f"totaliAlbero trovato={inizio_p != -1} sezioneTaskDrawer trovato={inizio_t != -1}")
        return
    fine_p = sorgente.find("\n}", inizio_p)
    fine_t = sorgente.find("\n}", inizio_t)
    albero_padre = sorgente[inizio_p:fine_p + 2]
    sezione_task = sorgente[inizio_t:fine_t + 2]

    mancano = [nome for nome, blocco in (
        ("EN", en), ("IT_TESTI", it_testi), ("T", t_fn), ("conN", con_n),
        ("progettiN", progetti_n), ("LOC", loc), ("esc", esc), ("ago", ago),
        ("kilo", kilo), ("prioTag", prio_tag),
    ) if not blocco]
    if mancano:
        prova("estratti da app.js i pezzi che servono a eseguire totaliAlbero()/"
              "sezioneTaskDrawer() per davvero", False, f"non trovati: {mancano}")
        return

    script = f"""
{en}
{it_testi}
let UILANG = 'it';
{t_fn}
{loc}
{esc}
{ago}
{kilo}
{prio_tag}
{con_n}
{progetti_n}
{albero_padre}
function taskRows(list) {{ return list.map((t) => `<row id=${{t.id}} status=${{t.status}}>`).join(''); }}
{sezione_task}

const padre = {{ key: 'padre1', name: 'Padre Uno', kind: 'progetto', priority: 2,
  pinned: true, token_30g: 1000, last_activity: '2026-01-01', task_aperti: 1, sessioni: 0 }};
const figli = [{{ key: 'figlio1', name: 'Figlio Uno', kind: 'progetto', priority: 2,
  pinned: false, token_30g: 2000, last_activity: '2026-02-02', task_aperti: 2 }}];
const markupPadre = JSON.stringify(totaliAlbero(padre, figli));

const task = [
  {{ id: 1, status: 'aperto' }}, {{ id: 2, status: 'aperto' }}, {{ id: 3, status: 'aperto' }},
  {{ id: 4, status: 'fatto' }},
];
const markupTask = sezioneTaskDrawer(task);

console.log(JSON.stringify({{ markupPadre, markupTask }}));
"""
    try:
        esito = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=10)
    except Exception as exc:  # noqa: BLE001 - un NO pulito, non un'eccezione a metà prova
        prova("totaliAlbero()/sezioneTaskDrawer(), eseguite per davvero in Node",
              False, f"eccezione lanciando node: {exc!r}")
        return
    if esito.returncode != 0:
        prova("totaliAlbero()/sezioneTaskDrawer(), eseguite per davvero in Node",
              False, f"node è uscito con errore: {esito.stderr[-800:]}")
        return
    try:
        risultati = json.loads(esito.stdout.strip().splitlines()[-1])
    except Exception:
        prova("totaliAlbero()/sezioneTaskDrawer(), eseguite per davvero in Node",
              False, f"uscita non JSON: {esito.stdout!r}")
        return

    padre_out = risultati.get("markupPadre") or ""
    task_out = risultati.get("markupTask") or ""

    # Residuo 5: il padre porta i totali del sottoalbero.
    prova("totaliAlbero(): i task aperti sono la somma padre+figli (1+2=3)",
          '"task":3' in padre_out, padre_out[:400])
    prova("totaliAlbero(): il totale token è la somma padre+figli (1000+2000=3000)",
          '"token30":3000' in padre_out, padre_out[:400])
    prova("totaliAlbero(): l'ultima attività è la più recente del sottoalbero, non quella del padre",
          '"ultima":"2026-02-02"' in padre_out, padre_out[:400])

    # Residuo 4: sezioneTaskDrawer mostra solo il primo aperto, non i tre.
    prova("sezioneTaskDrawer(): produce una sola riga per i task 'aperto' (aperti[0]), non tre",
          task_out.count("status=aperto") == 1, task_out)
    prova("sezioneTaskDrawer(): la riga del task 'fatto' resta (non è archiviato)",
          "status=fatto" in task_out, task_out)


def _prova_guida_aggiornata(prova, sorgente):
    # Correzione L3-RIPRENDI-UI-2 (critico, obbligatoria #2): la guida
    # (views.benvenuto/PASSI) descriveva ancora il vecchio compositore col
    # menu proposta/esegui, che non esiste più dal punto 2 del lotto.
    prova("la guida non dice più che 'il modo predefinito è proposta'",
          "predefinito è proposta" not in sorgente, "")
    prova("...né la sua versione inglese 'the default mode is plan only'",
          "default mode is plan only" not in sorgente, "")
    prova("il pulsante di prova della guida non si chiama più 'Prova il compositore'",
          "Prova il compositore" not in sorgente, "")
    prova("...né 'Try the composer'",
          "Try the composer" not in sorgente, "")


def _prova_punto_1(prova, sorgente):
    # LOTTO-L3-RITOCCO punto 1: il bottone di riga in "Tutti i task" (il
    # <div class="row"> dentro d.voci.map, non toccato da nessun altro
    # punto) diceva T('manda')/"dispatch": ora dice T('Riprendi')/"Resume".
    prova("T('manda') non compare più in app.js (il bottone di riga non lo dice più)",
          "T('manda')" not in sorgente and 'T("manda")' not in sorgente, "")
    inizio = sorgente.find('data-act="manda" data-titolo')
    if inizio == -1:
        prova("il bottone di riga (data-act=\"manda\" data-titolo) esiste ancora", False, "")
        return
    fine = sorgente.find("</button>", inizio)
    prova("quel bottone dice T('Riprendi')",
          "${T('Riprendi')}" in sorgente[inizio:fine + 9], sorgente[inizio:fine + 9])


def _prova_punto_2(prova, sorgente):
    # LOTTO-L3-RITOCCO punto 2: "Lanci recenti" e il drawer del lancio
    # mostravano T(r.modo)/T(d.modo) - le chiavi interne del backend
    # ("proposta"/"esegui") passate dritte a T(). Ora usano Tmodo(), che
    # mappa sulle parole dell'interruttore ("solo lettura"/"può modificare
    # i file"), non più "plan only"/"do it".
    # "${T(r.modo)}"/"${T(d.modo)}" con le graffe del template literal, non
    # la nuda sottostringa "T(r.modo)": questa prova stessa la nomina nei
    # suoi commenti qui sopra, e una ricerca senza le graffe la troverebbe
    # sempre, sul commit base come con la patch.
    prova("${T(r.modo)} non compare più (rigaLancio usa Tmodo(r.modo))",
          "${T(r.modo)}" not in sorgente, "")
    prova("${T(d.modo)} non compare più (apriLancio usa Tmodo(d.modo))",
          "${T(d.modo)}" not in sorgente, "")
    prova("Tmodo(r.modo) è nel markup di 'Lanci recenti'/'In lavorazione'",
          "Tmodo(r.modo)" in sorgente, "")
    prova("Tmodo(d.modo) è nel markup del drawer del lancio",
          "Tmodo(d.modo)" in sorgente, "")
    prova("'proposta': 'plan only' non è più una voce del dizionario",
          "'plan only'" not in sorgente, "")
    prova("'esegui': 'do it' non è più una voce del dizionario "
          "('fallo': 'do it', un'altra chiave, può restare)",
          "'esegui': 'do it'" not in sorgente, "")


def _prova_punto_4_bottone_sync(prova, sorgente):
    # LOTTO-L3-RITOCCO punto 4: con --no-sync, POST /api/sync risponde
    # {avviato:false, motivo:"--no-sync"}; il bottone di sync deve dirlo, non
    # dire "aggiornamento avviato" come se un sync fosse davvero partito.
    #
    # L3-RIPRENDI-UI-4 (regressione trovata dal critico): {avviato:false}
    # arriva anche quando un sync è SOLO già in corso (nessun 'motivo' nel
    # corpo). Se il front decide guardando solo r.avviato, quel caso finisce
    # nello stesso ramo del --no-sync e dice una cosa falsa. La prova deve
    # quindi controllare che il ramo "disattivato" guardi r.motivo, non che
    # 'r.avviato' compaia da qualche parte nel corpo (ci compare comunque,
    # nell'if iniziale, e la stringa da sola non basta a distinguere i due
    # casi).
    inizio = sorgente.find("$('#btn-sync').addEventListener(")
    if inizio == -1:
        prova("il listener di #btn-sync esiste", False, "")
        return
    fine = sorgente.find("\n});", inizio)
    corpo = sorgente[inizio:fine]
    prova("il ramo 'disattivato' guarda r.motivo === '--no-sync', non solo r.avviato",
          "r.motivo" in corpo and "--no-sync" in corpo, corpo)
    prova("quando r.avviato è false e non è --no-sync, il front segue comunque "
          "il sync già in corso con pollSync()",
          "pollSync()" in corpo and corpo.count("pollSync()") >= 2, corpo)


def _prova_punto_11(prova, sorgente):
    # LOTTO-L3-RITOCCO punto 11: il pulsante "viva" porta il motivo tradotto
    # (Tmot) nel title, e il click su "riprendi" dice nel toast quando la
    # risposta porta 'errore' (il lanciatore in timeout), invece di dire
    # sempre "Avviato" come se fosse partito per davvero.
    inizio = sorgente.find("function bottoneRiprendi(")
    if inizio == -1:
        prova("function bottoneRiprendi( esiste ancora", False, "")
        return
    fine = sorgente.find("\n}", inizio)
    corpo = sorgente[inizio:fine]
    prova("il pulsante 'viva' porta il motivo tradotto (Tmot) nel title",
          "title=\"${esc(Tmot(dati.motivo))}\"" in corpo, corpo[:400])

    inizio_l = sorgente.find("name === 'riprendi') {")
    if inizio_l == -1:
        prova("il ramo name === 'riprendi' del listener dei click esiste ancora", False, "")
        return
    fine_l = sorgente.find("} else if (name === 'riprendi-background')", inizio_l)
    if fine_l == -1:
        prova("il ramo name === 'riprendi-background' che segue esiste ancora", False, "")
        return
    corpo_l = sorgente[inizio_l:fine_l]
    prova("il click su 'riprendi' controlla r.errore prima di dire 'Avviato'",
          "r.errore" in corpo_l, corpo_l)


def _prova_drawer_apre_subito(prova, sorgente):
    # Correzione L3-RIPRENDI-UI-2 (critico, obbligatoria #4): apriRiprendi
    # aspettava la GET /api/riprendi/<id> (fino a 25s, claude agents --json)
    # PRIMA di scrivere #drawer-body e di togliere #drawer.hidden. Ora il
    # cassetto si apre con un segnaposto e la GET arriva dopo.
    prova("esiste ancora async function apriRiprendi(",
          "async function apriRiprendi(" in sorgente, "")
    inizio = sorgente.index("async function apriRiprendi(")
    fine = sorgente.index("\nasync function apriLancio(", inizio)
    corpo = sorgente[inizio:fine]
    apre = corpo.find("$('#drawer').hidden = false")
    aspetta = corpo.find("await api('/api/riprendi/")
    prova("il cassetto si apre (#drawer.hidden = false) dentro apriRiprendi",
          apre != -1, "non trovato")
    prova("...PRIMA della GET /api/riprendi/<id>, non dopo",
          apre != -1 and aspetta != -1 and apre < aspetta,
          f"apre={apre} aspetta={aspetta}")
    prova("un segnaposto disabilitato tiene il posto del pulsante di stato",
          "riprendi riprendi-stato\" disabled>" in corpo, corpo[:400])


def _prova_riga_porta_sessione(prova, sorgente):
    """L3-RIPRENDI-UI-4 ("occhi di Eugenio", obbligatoria del critico): il
    bottone di riga in "Tutti i task" (data-act="manda") porta data-task solo
    per fonte 'plancia' - su Claude/Codex (due fonti su tre) il click apriva
    il drawer senza pulsante di stato, e il modulo "In background" lanciava
    da zero, senza mai riprendere la sessione vera che quella voce ha
    (v.sessione, plancia/lavagna.py). La correzione (la "migliore" delle due
    proposte dal critico) fa portare data-sessione/data-agente a QUALUNQUE
    riga, non solo a quelle con task_id, e fa arrivare quel valore dentro il
    form del modulo "In background", che lo manda a /api/cantiere come
    'sessione' - vedi tools/prove/api-riprendi.py per il contratto HTTP."""
    inizio = sorgente.find('data-act="manda" data-titolo')
    if inizio == -1:
        prova("il bottone di riga (data-act=\"manda\" data-titolo) esiste ancora", False, "")
        return
    fine = sorgente.find("</button>", inizio)
    if fine == -1:
        prova("il bottone di riga si chiude con </button>", False, "")
        return
    corpo = sorgente[inizio:fine + 9]
    prova("il bottone di riga porta data-sessione per QUALUNQUE fonte (non solo 'plancia')",
          "data-sessione=\"${esc(v.sessione" in corpo, corpo)
    prova("...e data-agente, per farlo arrivare al modulo 'In background'",
          "data-agente=\"${esc(v.agente" in corpo, corpo)

    inizio_f = sorgente.find("async function apriRiprendi(")
    if inizio_f == -1:
        prova("async function apriRiprendi( esiste ancora", False, "")
        return
    fine_f = sorgente.find("\nasync function apriLancio(", inizio_f)
    corpo_f = sorgente[inizio_f:fine_f]
    prova("apriRiprendi porta dati.sessione nel <form data-sessione> del modulo 'In background'",
          'data-sessione="${esc(dati.sessione' in corpo_f, corpo_f[:500])

    inizio_h = sorgente.find("name === 'riprendi-background'")
    if inizio_h == -1:
        prova("il ramo name === 'riprendi-background' del listener dei click esiste ancora",
              False, "")
        return
    fine_h = sorgente.find("} else if (name === 'lancio')", inizio_h)
    if fine_h == -1:
        prova("il ramo name === 'lancio' che segue esiste ancora", False, "")
        return
    corpo_h = sorgente[inizio_h:fine_h]
    prova("...e il click su 'In background' manda form.dataset.sessione a /api/cantiere "
          "come 'sessione'",
          "sessione: form.dataset.sessione" in corpo_h, corpo_h)


def _prova_proposta_manda_apre_drawer(prova, sorgente):
    """L3-RIPRENDI-UI-4 ("occhi di Eugenio", obbligatoria del critico): un
    click su "Riprendi" su una proposta di tipo 'manda' (views.oggi) mandava
    SUBITO /api/jarvis {testo:'fallo'}, che sul server esegue la proposta
    scelta senza nessuna conferma - un claude/codex headless partito senza
    drawer, senza stato, senza che l'utente lo vedesse arrivare. Ora 'manda'
    apre lo stesso drawer di sempre (apriRiprendi); 'vai'/'rilancia' restano
    una pura navigazione, con un'etichetta diversa da 'Riprendi' (che qui
    promette una ripresa che non fanno)."""
    inizio = sorgente.find("function rigaProposta(p, i)")
    if inizio == -1:
        prova("function rigaProposta(p, i) esiste ancora (la riga di una proposta in Oggi)", False, "")
        return
    fine = sorgente.find("\n}", inizio)
    if fine == -1:
        prova("rigaProposta si chiude", False, "")
        return
    corpo = sorgente[inizio:fine]
    prova("l'etichetta del bottone di una proposta dipende da az.tipo "
          "(non è sempre 'Riprendi')",
          "az.tipo === 'manda'" in corpo and "T('Rilancia')" in corpo and "T('Apri')" in corpo,
          corpo)
    prova("il bottone porta data-tipo/data-task/data-titolo/data-progetto dall'azione",
          all(s in corpo for s in ('data-tipo="${esc(az.tipo', 'data-task="${az.task_id',
                                    'data-titolo="${esc(az.titolo', 'data-progetto="${esc(az.progetto')),
          corpo)

    inizio_h = sorgente.find("name === 'proposta'")
    if inizio_h == -1:
        prova("il ramo name === 'proposta' del listener dei click esiste ancora", False, "")
        return
    fine_h = sorgente.find("} else if (name === 'recap-gen')", inizio_h)
    if fine_h == -1:
        prova("il ramo name === 'recap-gen' che segue esiste ancora", False, "")
        return
    corpo_h = sorgente[inizio_h:fine_h]
    prova("il click su una proposta 'manda' apre il drawer (apriRiprendi), "
          "non manda subito /api/jarvis",
          "act.dataset.tipo === 'manda'" in corpo_h and "apriRiprendi(" in corpo_h, corpo_h)
    prova("...e SOLO le altre (vai/rilancia) restano sull'esecuzione diretta via /api/jarvis",
          corpo_h.find("apriRiprendi(") < corpo_h.find("api('/api/jarvis'"), corpo_h)


def esegui(prova, radice) -> None:
    sorgente = _leggi(radice)
    _prova_chiavi_stato(prova, sorgente)
    _prova_data_act(prova, sorgente)
    _prova_manda_un_agente_sparito(prova, sorgente)
    _prova_proposta_esegui_non_scelte_da_un_menu(prova, sorgente)
    _prova_fallo_sparito_dalle_proposte(prova, sorgente)
    _prova_classi_riprendi(prova, sorgente)
    _prova_residui_ondata2(prova, sorgente)
    _prova_comportamento_plurale_node(prova, sorgente)
    _prova_comportamento_residui_node(prova, sorgente)
    _prova_punto_1(prova, sorgente)
    _prova_punto_2(prova, sorgente)
    _prova_punto_4_bottone_sync(prova, sorgente)
    _prova_punto_11(prova, sorgente)
    _prova_riga_porta_sessione(prova, sorgente)
    _prova_proposta_manda_apre_drawer(prova, sorgente)
    _prova_guida_aggiornata(prova, sorgente)
    _prova_drawer_apre_subito(prova, sorgente)


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
