"""Prove per L4-VETRO: il vetro esteso a ogni superficie, in web/style.css;
il materiale nativo dietro tutta la finestra, in mac/Sources/main.swift.

Statiche, si guarda solo il sorgente (niente browser, niente server): sono
le condizioni scritte in docs/lotti/LOTTO-L4-VETRO.md, sotto "Prove rosse
senza". La funzione pubblica è `esegui(prova, radice)`, la stessa forma
usata da tools/prova-front.py (vedi tools/prove-front/README.md).

Decisione di Eugenio del 18/09/2026 ("voglio un più ampio uso di liquid
glass ... deve sembrare tutto vetro"): SOSTITUISCE l'elenco chiuso di
L2-GLASS (rail/topbar/drawer/palette semitrasparenti, card/klane/panel
opachi VIETATI dal vetro). Le prove di L2-GLASS che imponevano quell'elenco
chiuso sono state tolte da questo file, non solo riscritte, perché
contraddicono la regola nuova (aperta: ogni superficie con uno sfondo è
vetro) - una prova verde su "VIETATO backdrop-filter su .card/.klane" non
può stare nello stesso file di una prova verde su ".card/.klane usano
--surface-1/2" quando .card e .klane hanno DAVVERO backdrop-filter oggi:
sarebbero in contraddizione fra loro, non solo con il codice. Tolta anche
la prova che sincronizzava --rail-w (CSS) con un `railW` in main.swift: il
materiale nativo non è più largo quanto il rail, ma quanto tutta la
finestra, quindi quel numero in Swift non esiste più e la prova non
proverebbe più niente.
"""

import re

FOGLIO = "web/style.css"
FOGLIO_SWIFT = "mac/Sources/main.swift"

# LOTTO-L5-RIFINITURA punto 3: il margine minimo di luminanza relativa (WCAG)
# che --text-2 deve tenere sotto --text-3 nel tema chiaro perché la
# gerarchia fra testo secondario e terziario si veda. Scelto sotto il
# margine vero fra #444d5c e #5d6774 (~0,06, vedi il commento su --text-2 in
# html[data-resolved="light"]) cosi' da avere un margine di sicurezza, ma
# ben sopra lo ~0,007 che c'era prima della correzione (--text-2 e --text-3
# quasi identiche).
MARGINE_LUMINANZA_MIN = 0.03


def _rimuovi_commenti(testo):
    return re.sub(r"/\*.*?\*/", "", testo, flags=re.S)


def _luminanza_relativa(hex_colore):
    """Luminanza relativa WCAG (0..1) di un colore #rrggbb."""
    hex_colore = hex_colore.lstrip("#")
    componenti = (int(hex_colore[i:i + 2], 16) / 255.0 for i in (0, 2, 4))

    def linearizza(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (linearizza(c) for c in componenti)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _prova_gerarchia_testo_chiaro(prova, testo):
    # --text-2 e --text-3 quasi uguali dopo la correzione di contrasto di
    # L4-VETRO-2 (vedi il commento sopra --text-2 in html[data-resolved=
    # "light"]): qui si controlla che --text-2 sia rimasta davvero più
    # scura di --text-3 di un margine che si vede, non solo un'unità di
    # meno sull'ultima cifra esadecimale. --text-3 non si tocca (il suo
    # numero è quello misurato su pixel veri da L4-VETRO-2): questa prova
    # guarda solo la distanza fra le due, non ridimostra il 4,5:1 di --text-3.
    m = re.search(r'html\[data-resolved="light"\]\s*\{([^}]*)\}', testo, re.S)
    prova(f'{FOGLIO}: html[data-resolved="light"] si trova', m is not None)
    if not m:
        return
    corpo = m.group(1)
    m2 = re.search(r"--text-2:\s*(#[0-9a-fA-F]{6})", corpo)
    m3 = re.search(r"--text-3:\s*(#[0-9a-fA-F]{6})", corpo)
    prova(f"{FOGLIO}: --text-2 e --text-3 sono dichiarate nel tema chiaro come colori esadecimali",
          bool(m2 and m3), corpo.strip()[:200])
    if not (m2 and m3):
        return
    testo2, testo3 = m2.group(1), m3.group(1)
    luminanza2 = _luminanza_relativa(testo2)
    luminanza3 = _luminanza_relativa(testo3)
    prova(f"{FOGLIO}: nel tema chiaro --text-2 ({testo2}) è più scura di --text-3 ({testo3}) "
          f"di almeno {MARGINE_LUMINANZA_MIN} di luminanza relativa (gerarchia visibile)",
          luminanza3 - luminanza2 >= MARGINE_LUMINANZA_MIN,
          f"luminanza --text-2={luminanza2:.4f}, --text-3={luminanza3:.4f}, "
          f"differenza={luminanza3 - luminanza2:.4f}")


def _prova_surface_glass(prova, testo):
    # --surface-0 resta piena (è il fondo della pagina, dietro tutto); -1 e
    # -2 sono entrambe semitrasparenti (contengono "transparent"): è la
    # regola nuova che sostituisce l'elenco chiuso di L2-GLASS.
    for nome in ("--surface-0", "--surface-1", "--surface-2"):
        m = re.search(re.escape(nome) + r":\s*([^;]+);", testo)
        prova(f"{FOGLIO}: {nome} è dichiarata", bool(m), "variabile non trovata")
        if not m:
            continue
        valore = m.group(1).strip()
        if nome == "--surface-0":
            prova(f"{FOGLIO}: {nome} resta opaca (niente transparent, è il fondo dietro tutto)",
                  "transparent" not in valore, valore)
        else:
            prova(f"{FOGLIO}: {nome} è semitrasparente (contiene transparent)",
                  "transparent" in valore, valore)
    m = re.search(r"--glass-line:\s*([^;]+);", testo)
    prova(f"{FOGLIO}: --glass-line è dichiarata", bool(m), "")


def _prova_pannelli_vetro(prova, testo_senza_commenti):
    # I pannelli che il verdetto di L2-GLASS teneva opachi per decreto
    # ("mai vetro", elenco VIETATI) oggi usano --surface-1/2, non più
    # --elev/--panel come sfondo pieno. .albero-figlio e .trovato (aggiunti
    # in L4-VETRO-2, correzione del critico) erano rimasti opachi nella
    # prima versione del lotto nonostante il punto 1 chiedesse vetro su
    # "ogni superficie che oggi usa --elev/--panel/--panel-2 come sfondo
    # opaco": senza questa riga la prova non se ne sarebbe accorta.
    for selettore in (".card", ".panel", ".klane", ".prossimi-riga", ".palette-box",
                      ".albero-figlio", ".trovato"):
        m = re.search(re.escape(selettore) + r"\s*\{([^}]*)\}", testo_senza_commenti)
        prova(f"{FOGLIO}: {selettore} è dichiarato", bool(m), "selettore non trovato")
        if not m:
            continue
        corpo = m.group(1)
        # --surface-inset (L4-VETRO-2, correzione del critico: la tinta
        # propria degli innestati, .albero-figlio e .prossimi-riga qui
        # dentro, vedi il commento su --surface-inset in :root) è
        # translucida come --surface-1/-2, solo pensata per comporsi sopra
        # un genitore già di vetro senza superare la fascia - conta come
        # "vetro", non come l'opaco --elev/--panel che questa prova vieta.
        usa_surface = bool(re.search(r"background:\s*var\(--surface-(?:1|2|inset)\)", corpo))
        usa_opaco = bool(re.search(r"background:\s*var\(--(elev|panel)\)\s*;", corpo))
        prova(f"{FOGLIO}: {selettore} usa var(--surface-1)/var(--surface-2)/var(--surface-inset) "
              "come background, non var(--elev)/var(--panel) opachi",
              usa_surface and not usa_opaco, corpo.strip())


def _prova_livelli_vetro(prova, testo_senza_commenti):
    # L4-VETRO-2: il critico ha trovato che il blur era stato tolto (o
    # ridotto a 12px) dalle superfici di primo livello senza una misura
    # vera a sostegno - corretto rimettendo saturate(1.4) blur(18px)
    # ovunque il punto 1 del lotto lo chiede. Senza questa prova, un futuro
    # taglio del blur per "prestazioni" tornerebbe a passare inosservato
    # (vedi le "consigliate" del rapporto del critico).
    NON_INNESTATE = (".panel", ".card", ".klane", ".cell", ".albero-padre",
                      ".agent-card", ".palette-box", ".drawer-panel", ".toast")
    for selettore in NON_INNESTATE:
        # Ancorato a inizio riga: senza, ".drawer-panel" combacerebbe anche
        # con la coda del selettore composto usato dalla regola sul tema
        # chiaro (html[data-resolved="light"] .palette-box, html[...]
        # .drawer-panel { ... }, qui sopra in _prova_overlay_chiaro), che
        # non ha il blur - una prova sul selettore sbagliato.
        m = re.search(r"(?m)^" + re.escape(selettore) + r"\s*\{([^}]*)\}", testo_senza_commenti)
        prova(f"{FOGLIO}: {selettore} è dichiarato", bool(m), "selettore non trovato")
        if not m:
            continue
        corpo = m.group(1)
        prova(f"{FOGLIO}: {selettore} ha un backdrop-filter proprio con blur(18px)",
              bool(re.search(r"backdrop-filter:\s*saturate\([\d.]+\)\s*blur\(18px\)", corpo)),
              corpo.strip())

    # .albero-figlio condivide la classe .card (che ha il backdrop-filter
    # qui sopra) ma è innestata dentro .albero-padre, già vetro: deve
    # cancellare il blur ricevuto da .card, non solo non ridichiararlo -
    # altrimenti il blur di .card resterebbe applicato comunque (stessa
    # specificità, ma .card non viene mai sovrascritta su questa proprietà).
    m_figlio = re.search(r"\.albero-figlio\s*\{([^}]*)\}", testo_senza_commenti)
    prova(f"{FOGLIO}: .albero-figlio è dichiarato", bool(m_figlio), "selettore non trovato")
    if m_figlio:
        corpo = m_figlio.group(1)
        prova(f"{FOGLIO}: .albero-figlio annulla il backdrop-filter di .card "
              "(backdrop-filter: none, un livello di vetro per punto dello schermo)",
              bool(re.search(r"backdrop-filter:\s*none\s*;", corpo)) and "blur(" not in corpo,
              corpo.strip())


def _prova_inversa_livelli(prova, testo_senza_commenti):
    # L4-VETRO-2, punto 11 del lotto (consigliata del critico del primo
    # giro): la prova diretta (_prova_livelli_vetro qui sopra) controlla che
    # le superfici di primo livello ABBIANO il blur; questa controlla il
    # contrario - che gli elementi innestati NON ce l'abbiano (un secondo
    # backdrop-filter sopra un pannello già di vetro non aggiunge niente a
    # occhio e costa in prestazioni, vedi il commento sopra .rail). Copre
    # anche la richiesta esplicita del lotto che .rail e .topbar abbiano
    # LO STESSO valore di blur dei pannelli (prima erano saturate(1.6)
    # blur(14px), un vetro "diverso" solo perché erano bordi della UI).
    INNESTATI = (".kcard", ".prossimi-riga", ".row", ".pres", ".albero-figlio")
    for selettore in INNESTATI:
        m = re.search(r"(?m)^" + re.escape(selettore) + r"\s*\{([^}]*)\}", testo_senza_commenti)
        prova(f"{FOGLIO}: {selettore} è dichiarato", bool(m), "selettore non trovato")
        if not m:
            continue
        corpo = m.group(1)
        prova(f"{FOGLIO}: {selettore} non ha un backdrop-filter con blur (elemento innestato, "
              "un livello di vetro per punto dello schermo)",
              "blur(" not in corpo, corpo.strip())

    m_panel = re.search(r"(?m)^\.panel\s*\{([^}]*)\}", testo_senza_commenti)
    prova(f"{FOGLIO}: .panel è dichiarato", bool(m_panel), "selettore non trovato")
    valore_panel = None
    if m_panel:
        mm = re.search(r"backdrop-filter:\s*(saturate\([\d.]+\)\s*blur\(18px\))", m_panel.group(1))
        valore_panel = mm.group(1) if mm else None
        prova(f"{FOGLIO}: .panel ha un backdrop-filter riconoscibile (saturate(...) blur(18px))",
              bool(valore_panel), m_panel.group(1).strip())

    CON_BLUR = (".drawer-panel", ".palette-box", ".toast", ".rail", ".topbar")
    for selettore in CON_BLUR:
        m = re.search(r"(?m)^" + re.escape(selettore) + r"\s*\{([^}]*)\}", testo_senza_commenti)
        prova(f"{FOGLIO}: {selettore} è dichiarato", bool(m), "selettore non trovato")
        if not m:
            continue
        corpo = m.group(1)
        mm = re.search(r"backdrop-filter:\s*(saturate\([\d.]+\)\s*blur\(18px\))", corpo)
        prova(f"{FOGLIO}: {selettore} ha un backdrop-filter con blur(18px)",
              bool(mm), corpo.strip())
        if mm and valore_panel and selettore in (".rail", ".topbar"):
            prova(f"{FOGLIO}: {selettore} ha lo stesso valore di backdrop-filter di .panel "
                  "(rail e topbar allineati ai pannelli, non più ai valori propri di L2-GLASS)",
                  mm.group(1) == valore_panel, f"{selettore}={mm.group(1)!r} .panel={valore_panel!r}")


def _prova_html_app_mac(prova, testo):
    # Decisione 18/09: il fondo dentro l'app è trasparente su TUTTA la
    # finestra (prima solo la colonna --rail-w, con un linear-gradient).
    m_body = re.search(r'html\[data-app="mac"\]\s+body\s*\{([^}]*)\}', testo)
    prova('web/style.css: html[data-app="mac"] body è dichiarato', bool(m_body), "")
    if m_body:
        corpo = m_body.group(1)
        ha_transparent = bool(re.search(r"background:\s*(transparent|none)\s*;", corpo))
        ha_railw = "--rail-w" in corpo
        prova('web/style.css: html[data-app="mac"] body ha background: transparent (o none) '
              "e nessun gradiente con --rail-w",
              ha_transparent and not ha_railw, corpo.strip())


def _prova_body_aloni(prova, testo_senza_commenti):
    # Fuori dall'app il vetro ha aloni morbidi da sfocare, fissi dietro
    # tutto; dentro l'app il materiale nativo fa già da sfondo (vedi
    # "dentro l'app" in fondo al foglio) e gli aloni si spengono.
    # L4-VETRO-2: il coordinatore ha misurato che due gradient a bassa
    # opacità (il primo giro) si leggono come un unico alone generico, non
    # come "qualcosa di colorato che trapela" - il lotto chiede almeno tre,
    # con colori diversi (vedi --halo-1/2/3 in :root).
    m = re.search(r"(?<!\[data-app=\"mac\"\]\s)body::before\s*\{([^}]*)\}", testo_senza_commenti)
    prova(f"{FOGLIO}: body::before è dichiarato", bool(m), "selettore non trovato")
    if m:
        n = len(re.findall(r"radial-gradient", m.group(1)))
        prova(f"{FOGLIO}: body::before ha almeno tre radial-gradient", n >= 3, str(n))
    m_mac = re.search(r'html\[data-app="mac"\]\s+body::before\s*\{([^}]*)\}', testo_senza_commenti)
    spento = bool(m_mac) and bool(re.search(r"display:\s*none\s*;", m_mac.group(1)))
    prova('web/style.css: html[data-app="mac"] body::before è spento (display: none) - '
          "il materiale nativo fa già da sfondo",
          spento, "")


def _prova_aloni_colori_alfa(prova, testo, testo_senza_commenti):
    # L4-VETRO-2, correzione del critico (secondo giro): il critico ha
    # lanciato glass.py del primo giro sul commit di partenza (9fd94bc,
    # estratto con git archive) e sia "body::before ha almeno tre
    # radial-gradient" sia la prova sul bottone di .riprendi-background
    # (qui sotto) risultavano VERDI ANCHE SENZA la correzione: la base aveva
    # già tre gradient (--amber-soft più due --info-soft, tutti diversi solo
    # nel VALORE, non nella VARIABILE) e già il bottone corretto. Contare i
    # gradient non basta a dimostrare che i TRE COLORI distinti (--halo-1/2/
    # 3) siano davvero lì, né che le loro alfa cadano nelle fasce che il
    # lotto chiede (18-24% ambra / 12-18% blu-viola sullo scuro, 30-40% sul
    # chiaro) - un ritorno ai due --info-soft di prima passerebbe questa
    # prova aggirando quella su "almeno tre radial-gradient" con qualunque
    # variabile ripetuta tre volte. Questa prova guarda le VARIABILI, non il
    # conteggio dei gradient.
    m_body = re.search(r"(?<!\[data-app=\"mac\"\]\s)body::before\s*\{([^}]*)\}", testo_senza_commenti)
    prova(f"{FOGLIO}: body::before è dichiarato", bool(m_body), "selettore non trovato")
    if m_body:
        corpo = m_body.group(1)
        for nome in ("--halo-1", "--halo-2", "--halo-3"):
            prova(f"{FOGLIO}: body::before usa {nome} (tre colori distinti, non due "
                  "ripetizioni dello stesso alone)",
                  f"var({nome})" in corpo, corpo.strip())

    # Le alfa vivono nelle dichiarazioni rgba(...) di --halo-1/2/3, non nel
    # gradient: si guardano :root (scuro) e html[data-resolved="light"]
    # (chiaro) separatamente, con le fasce che il lotto scrive nel punto 1.
    def fascia(nome_blocco, testo_blocco, basso, alto, nome_tema):
        for nome in ("--halo-1", "--halo-2", "--halo-3"):
            m = re.search(re.escape(nome) + r":\s*rgba\([^,]+,[^,]+,[^,]+,\s*([\d.]+)\s*\)", testo_blocco)
            prova(f"{FOGLIO}: {nome} è dichiarata in {nome_blocco} come rgba(...)", bool(m), "")
            if not m:
                continue
            alfa = float(m.group(1))
            prova(f"{FOGLIO}: {nome} ({nome_tema}) ha alfa fra {basso} e {alto} "
                  f"(fascia del lotto, punto 1)",
                  basso <= alfa <= alto, f"alfa={alfa}")

    m_root = re.search(r":root\s*\{(.*?)\n\}", testo, re.S)
    if m_root:
        fascia(":root", m_root.group(1), 0.12, 0.24, "scuro")
    m_light = re.search(r'html\[data-resolved="light"\]\s*\{(.*?)\n\}', testo, re.S)
    if m_light:
        fascia('html[data-resolved="light"]', m_light.group(1), 0.30, 0.40, "chiaro")


def _prova_riprendi_stato_bottone(prova, testo_senza_commenti):
    # L4-VETRO-2, correzione del critico (secondo giro): stesso problema di
    # _prova_aloni_colori_alfa qui sopra - sul commit di partenza di questo
    # giro (9fd94bc) il bottone di stato era GIÀ corretto (testo --text,
    # min-height 42px, niente filo fisso a sinistra: lo aveva già messo il
    # riparatore del primo giro), quindi qualunque prova che si limitasse a
    # controllare "non c'è più il vecchio filo ambra" sarebbe passata anche
    # tornando a quei valori per un motivo sbagliato. Questa prova fissa il
    # contratto vero del punto 4 del lotto sul bottone .riprendi.riprendi-
    # stato stesso (non sul suo ::before, che è il punto ambra dichiarato a
    # parte): colore del testo in --text, altezza minima nella fascia
    # 40-44px, nessun border-left con --amber sulla dichiarazione DI BASE
    # (il bordo ambra intero arriva solo su :hover, vedi la regola qui
    # sotto - un filo fisso a sinistra tornerebbe a rendere il bottone "una
    # riga", non "il pulsante primario del drawer").
    m = re.search(r"(?m)^\.riprendi\.riprendi-stato\s*\{([^}]*)\}", testo_senza_commenti)
    prova(f"{FOGLIO}: .riprendi.riprendi-stato è dichiarato", bool(m), "selettore non trovato")
    if not m:
        return
    corpo = m.group(1)
    prova(f"{FOGLIO}: .riprendi.riprendi-stato ha color: var(--text) (non più ambra)",
          bool(re.search(r"color:\s*var\(--text\)\s*;", corpo)), corpo.strip())
    mm = re.search(r"min-height:\s*(\d+)px", corpo)
    prova(f"{FOGLIO}: .riprendi.riprendi-stato ha min-height fra 40 e 44px "
          "(fascia del punto 4 del lotto)",
          bool(mm) and 40 <= int(mm.group(1)) <= 44,
          mm.group(0) if mm else "min-height non trovata")
    prova(f"{FOGLIO}: .riprendi.riprendi-stato (dichiarazione di base, non :hover) "
          "non ha border-left con var(--amber) - il filo fisso a sinistra del primo giro",
          not bool(re.search(r"border-left[^;]*var\(--amber\)", corpo)), corpo.strip())


def _prova_glass_line_light(prova, testo):
    # Bianco a bassa opacità su un fondo bianco è invisibile: il filetto va
    # ridichiarato nel tema chiaro con un valore che si veda su --ink-1/2
    # bianchi.
    m_root = re.search(r":root\s*\{([^}]*)\}", testo, re.S)
    m_light = re.search(r'html\[data-resolved="light"\]\s*\{([^}]*)\}', testo, re.S)
    prova(f"{FOGLIO}: --glass-line è dichiarata in :root",
          bool(m_root) and "--glass-line:" in m_root.group(1), "")
    prova(f'{FOGLIO}: --glass-line è ridichiarata anche in html[data-resolved="light"] '
          "(altrimenti il bianco 12% di :root è invisibile su fondo bianco)",
          bool(m_light) and "--glass-line:" in m_light.group(1), "")


def _prova_overlay_chiaro(prova, testo_senza_commenti):
    # L4-VETRO-2: il critico ha misurato che --surface-1 (60%, il valore di
    # :root) sopra lo scrim scuro invariante di .drawer/.palette scendeva
    # sotto 4,5:1 di contrasto per --muted nel tema chiaro. Qui si verifica
    # solo che l'opacità degli overlay sul chiaro sia dentro la fascia
    # 85-90% chiesta dal critico; il contrasto vero (che dipende anche dallo
    # scrim e dal fondo dietro) è misurato a video nel rapporto, non qui:
    # questo file guarda solo il sorgente, niente browser.
    m = re.search(
        r'html\[data-resolved="light"\]\s+\.palette-box,\s*\n?\s*'
        r'html\[data-resolved="light"\]\s+\.drawer-panel\s*\{([^}]*)\}',
        testo_senza_commenti)
    prova(f'{FOGLIO}: html[data-resolved="light"] .palette-box/.drawer-panel è dichiarato',
          bool(m), "regola non trovata")
    if not m:
        return
    corpo = m.group(1)
    mm = re.search(r"color-mix\(in srgb,\s*var\(--elev\)\s*(\d+)%,\s*transparent\)", corpo)
    prova(f"{FOGLIO}: l'opacità degli overlay sul chiaro è fra 85% e 90% di --elev "
          "(fascia chiesta dal critico per il contrasto di --muted)",
          bool(mm) and 85 <= int(mm.group(1)) <= 90,
          corpo.strip())


def _prova_riprendi_background_primario(prova, testo_senza_commenti):
    # L4-VETRO-2, addendum del coordinatore: il pulsante "In background"
    # (button.primary dentro il form .riprendi-background, markup di
    # L3-RIPRENDI-UI) restava ambra pieno e a tutta larghezza - più vistoso
    # del Riprendi sopra di lui, mentre l'addendum vuole l'ambra "solo come
    # accento". Qui si verifica solo che la regola sia dichiarata: il colore
    # e il flex-column arrivano dal form vero, che vive in L3-RIPRENDI-UI,
    # non qui - per questo il controllo guarda che non resti ambra piena
    # (niente background: var(--amber) diretto) e che si allinei a sinistra.
    m = re.search(r"\.riprendi-background button\.primary\s*\{([^}]*)\}", testo_senza_commenti)
    prova(f"{FOGLIO}: .riprendi-background button.primary è dichiarato", bool(m), "selettore non trovato")
    if not m:
        return
    corpo = m.group(1)
    # L4-VETRO-2, seconda passata: la richiesta del lotto è "niente
    # background: var(--amber)/var(--accent) pieno" - --accent è l'alias di
    # --amber dichiarato in :root (vedi web/style.css), un futuro ritocco
    # potrebbe passare per l'alias invece del nome diretto e sfuggire a un
    # controllo che guarda solo --amber.
    prova(f"{FOGLIO}: .riprendi-background button.primary non resta ambra pieno "
          "(background: var(--amber)/var(--accent) diretto)",
          "background: var(--amber)" not in corpo and "background: var(--accent)" not in corpo,
          corpo.strip())
    prova(f"{FOGLIO}: .riprendi-background button.primary non si allunga a tutta larghezza "
          "(align-self: flex-start, dentro il form flex-column di L3-RIPRENDI-UI)",
          "align-self: flex-start" in corpo, corpo.strip())


def _prova_recap_sans(prova, testo_senza_commenti):
    # L4-VETRO-2, punto 5 del lotto: il riepilogo di Oggi era un paragrafo
    # intero in Fraunces (var(--serif)) - il verdetto del coordinatore
    # riserva il serif a h1/h2/titoli delle card/"prossimo passo", non a un
    # blocco di testo lungo quanto un paragrafo.
    m = re.search(r"^\.recap-testo\s*\{([^}]*)\}", testo_senza_commenti, re.M)
    prova(f"{FOGLIO}: .recap-testo è dichiarato", bool(m), "selettore non trovato")
    if not m:
        return
    corpo = m.group(1)
    prova(f"{FOGLIO}: .recap-testo non usa var(--serif) (torna al sans, il serif resta "
          "su h1/h2/titoli delle card/\"prossimo passo\")",
          "var(--serif)" not in corpo, corpo.strip())


def _prova_percentuali_superficie(prova, testo):
    # L4-VETRO-2, punto 2 del lotto: sul primo giro --surface-1 era al 60%
    # di ink (colonna transparent al 40%) - il coordinatore ha guardato le
    # fotografie e non si leggeva come vetro, troppo ink dentro il
    # color-mix. Il lotto chiede --surface-1 scuro (quello di :root, non la
    # ridichiarazione sotto html[data-resolved="light"]) a percentuale <=46.
    m_root = re.search(r":root\s*\{(.*?)\n\}", testo, re.S)
    prova(f"{FOGLIO}: :root è dichiarato", bool(m_root), "")
    if not m_root:
        return
    mm = re.search(r"--surface-1:\s*color-mix\(in srgb,\s*var\(--elev\)\s*(\d+)%,\s*transparent\)",
                    m_root.group(1))
    prova(f"{FOGLIO}: --surface-1 scuro (:root) ha percentuale di ink <= 46 "
          "(fascia 38-46 chiesta dal lotto, misurata sulle fotografie del primo giro)",
          bool(mm) and int(mm.group(1)) <= 46,
          mm.group(0) if mm else "--surface-1 non trovata in :root")


def _prova_vetro_luce_bordo(prova, testo_senza_commenti):
    # L4-VETRO-2, punto 2 del lotto: --vetro-luce (il riflesso in alto) e
    # --vetro-bordo (il filo che cattura la luce) dichiarate una volta e
    # riusate, non i valori ripetuti riga per riga - e usate davvero sulle
    # cinque superfici che il lotto elenca esplicitamente. --vetro-bordo si
    # verifica come SECONDO valore di box-shadow (si aggiunge all'ombra di
    # elevazione, non la sostituisce), quindi il controllo cerca solo che
    # compaia nella dichiarazione, non che sia l'unico valore.
    for nome in ("--vetro-luce", "--vetro-bordo"):
        m = re.search(re.escape(nome) + r":\s*[^;]+;", testo_senza_commenti)
        prova(f"{FOGLIO}: {nome} è dichiarata", bool(m), "variabile non trovata")
    for selettore in (".card", ".panel", ".klane", ".drawer-panel", ".palette-box"):
        m = re.search(r"(?m)^" + re.escape(selettore) + r"\s*\{([^}]*)\}", testo_senza_commenti)
        prova(f"{FOGLIO}: {selettore} è dichiarato", bool(m), "selettore non trovato")
        if not m:
            continue
        corpo = m.group(1)
        prova(f"{FOGLIO}: {selettore} usa --vetro-luce (background-image)",
              "var(--vetro-luce)" in corpo, corpo.strip())
        prova(f"{FOGLIO}: {selettore} usa --vetro-bordo (in box-shadow)",
              "var(--vetro-bordo)" in corpo, corpo.strip())


def _prova_surface_app_mac(prova, testo_senza_commenti):
    # L4-VETRO-3, primo giro: il tester di L4-VETRO-2 ha misurato 1,9-2,4:1
    # sulle etichette dei pannelli (RIEPILOGO, CHIEDI) dentro la simulazione
    # html[data-app="mac"] sopra una scrivania sfocata molto colorata -
    # --surface-1/-2 di :root (38-46%/55-62%, tarate su --bg fermo) non
    # bastano quando dietro c'è il materiale nativo. Il primo giro le aveva
    # portate a 84%/86% scuro e 76%/78% chiaro (misurato senza nessun'altra
    # protezione dietro).
    # L4-VETRO-3, secondo giro (punto 2 del lotto): con il velo dietro TUTTA
    # la colonna di contenuto (html[data-app="mac"] #view, vedi
    # _prova_velo_app_mac) a fare parte del lavoro di attenuare la
    # scrivania, --surface-1/-2 non devono più reggere da sole: sono scese
    # verso la fascia 64-72% indicata dal lotto per ENTRAMBI i temi (prima
    # il chiaro era già lì, lo scuro no) - misurato di nuovo su pixel veri
    # con misura.py, sopra soglia su ogni combinazione dei due sfondi/temi
    # provati (vedi la tabella del rapporto). Il blocco scuro è
    # html[data-app="mac"] da solo (si applica con qualunque data-resolved,
    # il chiaro lo sovrascrive sotto); quello chiaro è la combinazione dei
    # due attributi sullo stesso html.
    m_scuro = re.search(r'html\[data-app="mac"\]\s*\{([^}]*)\}', testo_senza_commenti)
    prova(f'{FOGLIO}: html[data-app="mac"] {{...}} è dichiarato (surface più piene, scuro)',
          bool(m_scuro), "selettore non trovato")
    if m_scuro:
        corpo = m_scuro.group(1)
        for nome in ("--surface-1", "--surface-2"):
            mm = re.search(re.escape(nome) + r":\s*color-mix\(in srgb,\s*var\(--elev\)\s*(\d+)%,\s*transparent\)",
                            corpo)
            prova(f"{FOGLIO}: html[data-app=\"mac\"] ridichiara {nome} fra 64% e 72% "
                  "(fascia del punto 2 del lotto, secondo giro - scesa da 84-86% col velo "
                  "dietro a fare parte del lavoro, vedi il commento in web/style.css)",
                  bool(mm) and 64 <= int(mm.group(1)) <= 72,
                  mm.group(0) if mm else f"{nome} non trovata in html[data-app=\"mac\"]")
    m_chiaro = re.search(r'html\[data-app="mac"\]\[data-resolved="light"\]\s*\{([^}]*)\}',
                          testo_senza_commenti)
    prova(f'{FOGLIO}: html[data-app="mac"][data-resolved="light"] è dichiarato (surface più piene, chiaro)',
          bool(m_chiaro), "selettore non trovato")
    if m_chiaro:
        corpo = m_chiaro.group(1)
        for nome in ("--surface-1", "--surface-2"):
            mm = re.search(re.escape(nome) + r":\s*color-mix\(in srgb,\s*var\(--elev\)\s*(\d+)%,\s*transparent\)",
                            corpo)
            prova(f"{FOGLIO}: html[data-app=\"mac\"][data-resolved=\"light\"] ridichiara {nome} "
                  "fra 64% e 72% (fascia del punto 2 del lotto, secondo giro)",
                  bool(mm) and 64 <= int(mm.group(1)) <= 72,
                  mm.group(0) if mm else f"{nome} non trovata")


def _prova_etichetta_pannello_app_mac(prova, testo_senza_commenti):
    # L4-VETRO-3: anche al valore più pieno misurato per --surface-1 (84%),
    # --faint (il colore di base di .panel > header h3, cioè RIEPILOGO/
    # CHIEDI) misurava 4,47:1 sulla foto scura peggiore - un pelo sotto la
    # soglia di 4,5:1. --muted, lo stesso grigio che .view-head p usa già per
    # "aggiornato"/la data, è più chiaro di --faint (vedi --text-3 in :root)
    # e sullo stesso sfondo misura 4,86-8,7:1: l'ultimo margine per portare
    # l'etichetta sopra soglia è il colore del testo, non altro vetro
    # (misurato: oltre un certo punto saturate(1.4) sul backdrop-filter
    # rimette dentro colore alla stessa velocità con cui --surface-1 lo
    # toglie).
    m = re.search(r'html\[data-app="mac"\]\s+\.panel\s*>\s*header\s+h3\s*\{([^}]*)\}',
                   testo_senza_commenti)
    prova(f'{FOGLIO}: html[data-app="mac"] .panel > header h3 è dichiarato', bool(m), "selettore non trovato")
    if not m:
        return
    corpo = m.group(1)
    prova(f'{FOGLIO}: html[data-app="mac"] .panel > header h3 usa color: var(--muted) '
          "(più chiaro di --faint, l'ultimo margine di contrasto misurato sulla foto peggiore)",
          "color: var(--muted)" in corpo, corpo.strip())


def _prova_view_head_app_mac(prova, testo_senza_commenti):
    # L4-VETRO-3, punto 2 del lotto: "aggiornato N min fa" e la data accanto
    # al titolo sono dentro .view-head, che non è mai innestata in un
    # pannello - fuori dall'app siede su --bg fermo, dentro l'app siede
    # direttamente sulla scrivania di Eugenio (chiara o scura, colorata a
    # piacere). Serve una base leggibile SOLO dentro l'app (fuori non cambia
    # niente, il lotto lo chiede esplicitamente): questa prova verifica la
    # scelta scritta nel commento sopra la regola in web/style.css, una
    # fascia di vetro con le stesse variabili di ogni altro pannello di primo
    # livello, non i valori ripetuti a mano.
    m = re.search(r'html\[data-app="mac"\]\s+\.view-head\s*\{([^}]*)\}', testo_senza_commenti)
    prova(f'{FOGLIO}: html[data-app="mac"] .view-head è dichiarato', bool(m), "selettore non trovato")
    if not m:
        return
    corpo = m.group(1)
    prova(f'{FOGLIO}: html[data-app="mac"] .view-head usa var(--surface-1) come sfondo '
          "(una base leggibile dietro al testo che sta direttamente sul materiale)",
          "background: var(--surface-1)" in corpo, corpo.strip())
    prova(f'{FOGLIO}: html[data-app="mac"] .view-head usa --vetro-luce e --vetro-bordo '
          "(stesse variabili di ogni altro pannello, non un'ombra o un colore inventati qui)",
          "var(--vetro-luce)" in corpo and "var(--vetro-bordo)" in corpo, corpo.strip())
    prova(f'{FOGLIO}: html[data-app="mac"] .view-head usa border-radius: var(--r-panel) '
          "(raggio dei pannelli, coerente col resto del vetro di primo livello)",
          "border-radius: var(--r-panel)" in corpo, corpo.strip())


def _prova_velo_app_mac(prova, testo_senza_commenti):
    # L4-VETRO-3, secondo giro (punto 1 del lotto): un velo uniforme dietro
    # TUTTA la colonna di contenuto (#view, non il rail: vedi #app piu' in
    # alto nel foglio, #view e' il secondo binario della griglia), non piu'
    # rattoppi vista per vista. Deve essere uniforme (niente blur: il
    # materiale nativo dietro tutta la finestra lo fa gia' - un secondo
    # backdrop-filter qui sarebbe un livello di vetro sopra un livello di
    # vetro, la stessa regola che _prova_inversa_livelli verifica altrove) e
    # semitrasparente (contiene "transparent"). La fascia 60-80% e' quella
    # DAVVERO misurata su pixel veri con misura.py (vedi il commento sopra
    # #view in web/style.css): .empty/.label non hanno nessun altro vetro
    # sotto, quindi a 40-55%/45-60% (l'indicazione iniziale del lotto)
    # restavano sotto 4,5:1 sul punto peggiore (foto neon), la stessa
    # dinamica gia' vista con --surface-1/-2 nel primo giro di L4-VETRO-3.
    m_scuro = re.search(r'html\[data-app="mac"\]\s+#view\s*\{([^}]*)\}', testo_senza_commenti)
    prova(f'{FOGLIO}: html[data-app="mac"] #view è dichiarato (il velo, scuro)',
          bool(m_scuro), "selettore non trovato")
    if m_scuro:
        corpo = m_scuro.group(1)
        prova(f"{FOGLIO}: il velo scuro non ha backdrop-filter (niente blur: il materiale "
              "nativo dietro tutta la finestra lo fa già, un secondo blur sarebbe un livello "
              "di vetro sopra un livello di vetro)",
              "backdrop-filter" not in corpo, corpo.strip())
        mm = re.search(r"background:\s*color-mix\(in srgb,\s*var\(--elev\)\s*(\d+)%,\s*transparent\)",
                        corpo)
        prova(f"{FOGLIO}: il velo scuro è semitrasparente (color-mix con var(--elev)) fra 60% "
              "e 80% (fascia misurata su pixel veri, punto 1 del lotto - più piena "
              "dell'indicazione iniziale 40-55%, vedi il commento in web/style.css)",
              bool(mm) and 60 <= int(mm.group(1)) <= 80,
              mm.group(0) if mm else "background del velo scuro non trovato")
    m_chiaro = re.search(r'html\[data-app="mac"\]\[data-resolved="light"\]\s+#view\s*\{([^}]*)\}',
                          testo_senza_commenti)
    prova(f'{FOGLIO}: html[data-app="mac"][data-resolved="light"] #view è dichiarato (il velo, chiaro)',
          bool(m_chiaro), "selettore non trovato")
    if m_chiaro:
        corpo = m_chiaro.group(1)
        prova(f"{FOGLIO}: il velo chiaro non ha backdrop-filter (niente blur)",
              "backdrop-filter" not in corpo, corpo.strip())
        mm = re.search(r"background:\s*color-mix\(in srgb,\s*white\s*(\d+)%,\s*transparent\)", corpo)
        prova(f"{FOGLIO}: il velo chiaro è semitrasparente (color-mix con white) fra 60% e 80% "
              "(fascia misurata su pixel veri, più piena dell'indicazione iniziale 45-60%)",
              bool(mm) and 60 <= int(mm.group(1)) <= 80,
              mm.group(0) if mm else "background del velo chiaro non trovato")

    # I due testi nudi che il tester ha trovato senza NESSUN vetro sotto
    # (.empty di Cerca senza query, .label/p della Guida): il velo da solo
    # non bastava a portarli sopra 4,5:1 su ogni combinazione (misurato:
    # 3,87-4,44:1 al bordo alto della fascia indicativa), --muted invece di
    # --faint è l'ultimo passo, stesso margine già dato a RIEPILOGO nel primo
    # giro di questo lotto.
    m_empty = re.search(r'html\[data-app="mac"\]\s+\.empty,\s*\n\s*html\[data-app="mac"\]\s+\.label\s*\{([^}]*)\}',
                         testo_senza_commenti)
    prova(f'{FOGLIO}: html[data-app="mac"] .empty, html[data-app="mac"] .label è dichiarato',
          bool(m_empty), "selettore non trovato")
    if m_empty:
        prova(f"{FOGLIO}: .empty/.label dentro l'app usano color: var(--muted) (non --faint, "
              "l'ultimo passo che il velo da solo non copriva sempre con margine)",
              "color: var(--muted)" in m_empty.group(1), m_empty.group(1).strip())


def _prova_cella_quiet_app_mac(prova, testo_senza_commenti):
    # L4-VETRO-3, secondo giro (punto 3 del lotto): .cell.quiet (TOKEN 30
    # GIORNI, POST IN CODA su Oggi) mette background: transparent
    # sull'INTERO elemento in :root - fuori dall'app va bene (--bg dietro è
    # fermo), ma dentro l'app quello stesso transparent toglie l'unica
    # protezione che il numero aveva, ed è proprio quello che il tester ha
    # misurato sparire (il testo "1 pubblicati" illeggibile). La richiesta
    # del lotto è "niente opacità sull'intero elemento dentro l'app": qui
    # significa che html[data-app="mac"] .cell.quiet NON deve ridichiarare
    # background: transparent (l'override di :root, se lasciato solo,
    # continuerebbe a vincere per cascata) e deve tornare alla stessa
    # superficie delle altre celle (--surface-1), lasciando che sia SOLO
    # --muted su .cell.quiet .v (invariato, non toccato da questo lotto) a
    # fare l'attenuazione.
    m = re.search(r'html\[data-app="mac"\]\s+\.cell\.quiet\s*\{([^}]*)\}', testo_senza_commenti)
    prova(f'{FOGLIO}: html[data-app="mac"] .cell.quiet è dichiarato', bool(m), "selettore non trovato")
    if not m:
        return
    corpo = m.group(1)
    prova(f"{FOGLIO}: html[data-app=\"mac\"] .cell.quiet non lascia background: transparent "
          "(l'override di :root che dentro l'app spoglia il numero della sua protezione)",
          "transparent" not in corpo, corpo.strip())
    prova(f"{FOGLIO}: html[data-app=\"mac\"] .cell.quiet usa var(--surface-1) come le altre celle "
          "(stessa superficie, l'attenuazione resta solo sul colore del testo)",
          "background: var(--surface-1)" in corpo, corpo.strip())

    # L'attenuazione via colore (non tocca), verificata di nuovo qui perché è
    # la metà del contratto del punto 3: .cell.quiet .v resta --muted, non
    # diventa --faint o qualcos'altro solo perché la superficie è tornata.
    m_v = re.search(r"\.cell\.quiet \.v\s*\{([^}]*)\}", testo_senza_commenti)
    prova(f"{FOGLIO}: .cell.quiet .v è dichiarato", bool(m_v), "selettore non trovato")
    if m_v:
        prova(f"{FOGLIO}: .cell.quiet .v usa color: var(--muted) (l'attenuazione resta sul "
              "testo, non sull'intera superficie)",
              "color: var(--muted)" in m_v.group(1), m_v.group(1).strip())


def _prova_truncate_kcard_foot(prova, testo):
    # Trabocco Social (segnalato dal tester di L1-FONT, 16/09): non è del
    # lotto L4-VETRO, non si tocca, ma resta verificato qui perché vive
    # nello stesso file di prove.
    m = re.search(r"\.truncate\s*\{([^}]*)\}", testo)
    prova(f"{FOGLIO}: .truncate dichiara min-width: 0",
          bool(m) and bool(re.search(r"min-width:\s*0\b", m.group(1))),
          m.group(1).strip() if m else ".truncate non trovato")
    m2 = re.search(r"\.kcard \.foot\.truncate\s*\{([^}]*)\}", testo)
    prova(f"{FOGLIO}: .kcard .foot.truncate riporta display: block (il trabocco vero: "
          "text-overflow non si applica a .kcard .foot, che è flex e più specifico di .truncate)",
          bool(m2) and bool(re.search(r"display:\s*block\b", m2.group(1))),
          m2.group(1).strip() if m2 else ".kcard .foot.truncate non trovato")


def _prova_swift(prova, radice):
    testo = (radice / FOGLIO_SWIFT).read_text(encoding="utf-8")
    # Stringhe specifiche del punto 4 del lotto (non spariscono con L4-VETRO,
    # restano invariate rispetto a L2-GLASS).
    controlli = (
        ('web.setValue(false, forKey: "drawsBackground")', 'web.setValue(false, forKey: "drawsBackground")'),
        ("#available(macOS 26", "#available(macOS 26"),
        ("window.isOpaque = false", "window.isOpaque = false"),
        ("window.backgroundColor = .clear", "window.backgroundColor = .clear"),
        # Nuovo in L4-VETRO: il ramo else usa ancora NSVisualEffectView, ma
        # ora deve dichiarare blendingMode = .behindWindow esplicitamente
        # accanto al materiale nativo a piena finestra (prima la stessa
        # proprietà c'era già, questa prova la rende esplicita e non più
        # solo dedotta dal commento).
        ("blendingMode = .behindWindow", "blendingMode = .behindWindow"),
    )
    for frammento, nome in controlli:
        prova(f"{FOGLIO_SWIFT}: contiene {nome}", frammento in testo, "")

    # Decisione 18/09: il materiale nativo non è più largo solo quanto il
    # rail (Self.railW), ma prende il bounds del contentView e segue il
    # ridimensionamento della finestra su entrambi gli assi.
    m_glass_frame = re.search(r"NSGlassEffectView\(\s*frame:\s*([\w.]+)\s*\)", testo)
    prova(f"{FOGLIO_SWIFT}: NSGlassEffectView prende il frame dal bounds del contentView "
          "(non più largo solo del rail)",
          bool(m_glass_frame) and m_glass_frame.group(1).endswith(".bounds"),
          m_glass_frame.group(1) if m_glass_frame else "NSGlassEffectView non trovato")
    m_ns_frame = re.search(r"NSVisualEffectView\(\s*frame:\s*([\w.]+)\s*\)", testo)
    prova(f"{FOGLIO_SWIFT}: NSVisualEffectView prende il frame dal bounds del contentView",
          bool(m_ns_frame) and m_ns_frame.group(1).endswith(".bounds"),
          m_ns_frame.group(1) if m_ns_frame else "NSVisualEffectView non trovato")

    m_resize = re.search(r"\w+\.autoresizingMask\s*=\s*\[([^\]]+)\]\s*\n\s*\n?\s*let contenuto", testo)
    # L'autoresizingMask del materiale nativo (qualunque nome di variabile
    # gli sia stato dato) deve avere sia .width sia .height: a piena
    # finestra deve seguire il ridimensionamento su entrambi gli assi, non
    # solo in altezza come quando era largo solo Self.railW.
    m_resize_generico = None
    for m in re.finditer(r"(\w+)\.autoresizingMask\s*=\s*\[([^\]]+)\]", testo):
        if m.group(1) not in ("web",):
            m_resize_generico = m
            break
    prova(f"{FOGLIO_SWIFT}: il materiale nativo ha autoresizingMask con .width e .height "
          "(prima era solo .height, largo un numero fisso)",
          bool(m_resize_generico)
          and ".width" in m_resize_generico.group(2)
          and ".height" in m_resize_generico.group(2),
          m_resize_generico.group(0) if m_resize_generico else "autoresizingMask non trovato")

    # NSGlassEffectView sta nel ramo #available(macOS 26, *); NSVisualEffectView
    # con blendingMode = .behindWindow nel ramo else. Non un semplice "compare
    # nel file": deve stare nel blocco giusto.
    m_if = re.search(r"#available\(macOS 26,[^)]*\)\s*\{([^{}]*)\}\s*else\s*\{([^{}]*)\}", testo, re.S)
    prova(f"{FOGLIO_SWIFT}: if #available(macOS 26, *) {{ ... }} else {{ ... }} è dichiarato per intero",
          bool(m_if), "")
    if m_if:
        ramo_26, ramo_else = m_if.group(1), m_if.group(2)
        prova(f"{FOGLIO_SWIFT}: NSGlassEffectView sta nel ramo #available(macOS 26, *)",
              "NSGlassEffectView" in ramo_26, ramo_26.strip())
        prova(f"{FOGLIO_SWIFT}: NSVisualEffectView con blendingMode = .behindWindow sta nel ramo else",
              "NSVisualEffectView" in ramo_else and "blendingMode = .behindWindow" in ramo_else,
              ramo_else.strip())
        # Punto 6 del lotto L4-VETRO-2: style esplicito a .regular su
        # NSGlassEffectView, non lasciato al default implicito - .clear è
        # per un elemento piccolo e isolato, .regular per lo sfondo di
        # un'intera finestra (vedi il commento sopra vetro.style in Swift).
        prova(f"{FOGLIO_SWIFT}: NSGlassEffectView ha style = .regular nel ramo #available(macOS 26, *)",
              bool(re.search(r"\.style\s*=\s*\.regular", ramo_26)), ramo_26.strip())

    # Tema dell'app e tema della pagina (L4-VETRO-2, punto 7 del lotto,
    # consigliata del critico del primo giro, contratto con L4-MEMORIA su
    # web/app.js): il materiale nativo deve seguire il tema che la pagina ha
    # risolto, non restare fermo sull'aspetto di sistema quando plancia-theme
    # forza il contrario. Statica: guarda solo che l'handler sia registrato
    # con name: "tema" e che da qualche parte nel file window.appearance
    # venga assegnato a partire da un NSAppearance - non lancia una WKWebView
    # vera, quindi non può verificare che il messaggio arrivi davvero.
    prova(f'{FOGLIO_SWIFT}: userContentController.add(...) registra un handler name: "tema"',
          bool(re.search(r'userContentController\.add\([^)]*name:\s*"tema"\s*\)', testo)), "")
    prova(f"{FOGLIO_SWIFT}: contiene func userContentController(_:didReceive:) "
          "(il metodo di WKScriptMessageHandler che riceve il messaggio 'tema')",
          bool(re.search(r"func userContentController\([^)]*didReceive[^)]*\)", testo)), "")
    # L4-VETRO-2, correzione del critico (secondo giro): il primo giro
    # assegnava window.appearance, che è l'antenato di cui web/app.js legge
    # prefers-color-scheme via matchMedia per risolvere 'auto' - forzarlo da
    # Swift rompe 'auto' al primo messaggio (vedi il commento sopra
    # costruisciFinestra() in main.swift). Il gestore deve assegnare
    # .appearance sul MATERIALE (fratello della WKWebView), non sulla
    # finestra: questa prova guarda esplicitamente "materiale.appearance",
    # non un window.appearance qualunque, e sul commit di partenza di questo
    # giro (che assegnava window.appearance) risulta rossa.
    prova(f"{FOGLIO_SWIFT}: materiale.appearance viene assegnato a un NSAppearance(named: ...) "
          "(il MATERIALE segue il tema che la pagina manda via 'tema', non la finestra: "
          "window.appearance è quello che matchMedia legge dentro la pagina per 'auto')",
          bool(re.search(r"materiale\.appearance\s*=\s*NSAppearance\(named:", testo)), "")
    prova(f"{FOGLIO_SWIFT}: window.appearance NON viene mai assegnato "
          "(romperebbe 'auto': vedi il commento sopra)",
          "window.appearance =" not in testo, "")
    prova(f"{FOGLIO_SWIFT}: AppDelegate dichiara la conformità a WKScriptMessageHandler",
          bool(re.search(r"class AppDelegate[^{]*WKScriptMessageHandler", testo)), "")
    return testo


def esegui(prova, radice) -> None:
    testo = (radice / FOGLIO).read_text(encoding="utf-8")
    testo_senza_commenti = _rimuovi_commenti(testo)
    _prova_surface_glass(prova, testo)
    _prova_pannelli_vetro(prova, testo_senza_commenti)
    _prova_livelli_vetro(prova, testo_senza_commenti)
    _prova_inversa_livelli(prova, testo_senza_commenti)
    _prova_percentuali_superficie(prova, testo)
    _prova_vetro_luce_bordo(prova, testo_senza_commenti)
    _prova_html_app_mac(prova, testo)
    _prova_body_aloni(prova, testo_senza_commenti)
    _prova_aloni_colori_alfa(prova, testo, testo_senza_commenti)
    _prova_glass_line_light(prova, testo)
    _prova_overlay_chiaro(prova, testo_senza_commenti)
    _prova_gerarchia_testo_chiaro(prova, testo)
    _prova_riprendi_background_primario(prova, testo_senza_commenti)
    _prova_riprendi_stato_bottone(prova, testo_senza_commenti)
    _prova_recap_sans(prova, testo_senza_commenti)
    _prova_surface_app_mac(prova, testo_senza_commenti)
    _prova_etichetta_pannello_app_mac(prova, testo_senza_commenti)
    _prova_view_head_app_mac(prova, testo_senza_commenti)
    _prova_velo_app_mac(prova, testo_senza_commenti)
    _prova_cella_quiet_app_mac(prova, testo_senza_commenti)
    _prova_truncate_kcard_foot(prova, testo)
    _prova_swift(prova, radice)


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
