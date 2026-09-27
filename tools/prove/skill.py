"""Prove per plancia/setup_claude.py: il testo della skill "plancia", in due lingue.

La skill descrive come un agente riprende un task Plancia (`plancia` con
`azione="riprendi"` e `id`; `send_message` dell'app desktop per una sessione
viva; il comando da aprire per una chiusa; la spiegazione per una persa) e
non parla più di mandare un lavoro a un agente in modo headless (`cantiere`,
`plancia_manda`). Qui si guarda solo il testo che produce
`setup_claude.skill_text()`, mai scrivendo in ~/.claude o in ~/.plancia:
`install_skill()` è provata spostando `SKILL_DIR` (e `config.CLAUDE_DIR`, da
cui è calcolato all'import) e tutta la cartella dati (`config.DATA_DIR`,
`QUEUE_DIR`, `CONFIG_FILE`) su una cartella temporanea, come
`tools/prove/sessione.py` fa per `config.CLAUDE_DIR`. Le due lingue devono
avere la stessa struttura di sezioni, non solo lo stesso contenuto tradotto a
metà: stessi identificatori fra backtick sezione per sezione (tranne Jarvis e
Comandi, dove la stringa d'esempio e i commenti bash sono tradotti) e stesso
numero di elenchi puntati.

Le prove che controllano l'assenza di un testo (`not in`) sono deboli da
sole: passano anche su un testo che non ha mai contenuto quella frase, quindi
non provano che il lotto l'abbia tolta. Qui vanno sempre insieme a una prova
positiva sulla stessa area (i tre stati, `send_message`, i nomi delle azioni
di coda) cosi' un ripristino accidentale del vecchio paragrafo fa cadere
comunque qualcosa.
"""

import re
import shutil
import tempfile
from pathlib import Path

SEZIONE = re.compile(r"^## (.+)$", re.M)
BACKTICK = re.compile(r"`([^`\n]+)`")
BULLET = re.compile(r"^- ", re.M)

# Le due sezioni dove le due lingue divergono di proposito: l'esempio vocale
# ("frase"/"sentence") e i commenti del blocco Comandi. Indici nell'elenco di
# SEZIONE, uguale in entrambe le lingue (11 sezioni, stesso ordine).
SEZIONI_TRADOTTE_A_MANO = (8, 10)  # Jarvis, Comandi


def _sezioni(testo):
    return SEZIONE.findall(testo)


def _corpi(testo):
    # Il primo pezzo (prima del primo "## ") è il frontmatter + l'introduzione:
    # non è una sezione, non entra nel confronto per sezione.
    return re.split(r"^## .+$", testo, flags=re.M)[1:]


def esegui(prova):
    from plancia import config, mcp, setup_claude

    it = setup_claude.skill_text("it")
    en = setup_claude.skill_text("en")

    for nome, testo in (("it", it), ("en", en)):
        prova(f"la skill ({nome}) parla di riprendere un task",
              "riprendi" in testo)
        prova(f"la skill ({nome}) cita send_message",
              "send_message" in testo)
        prova(f"la skill ({nome}) non parla più di mandare a un agente",
              "manda a un agente" not in testo)
        prova(f"la skill ({nome}) non cita il cantiere",
              "cantiere" not in testo)
        # Le due letterali davvero tolte dal lotto (non "manda a un agente",
        # che non è mai stata la frase nel testo vecchio): il tool
        # `plancia_manda` e il comando `plancia manda` nel blocco Comandi.
        prova(f"la skill ({nome}) non nomina più il tool plancia_manda",
              "plancia_manda" not in testo)
        prova(f"la skill ({nome}) non ha più il comando 'plancia manda' nei Comandi",
              "plancia manda" not in testo)
        prova(f"la skill ({nome}) non ha em dash",
              "—" not in testo)
        prova(f"la skill ({nome}) cita i tre stati di una sessione",
              all(stato in testo for stato in ("viva", "chiusa", "persa")))
        occorrenze = len(re.findall("in background", testo, re.I))
        prova(f"\"in background\" compare una sola volta nella skill ({nome})",
              occorrenze == 1, str(occorrenze))
        # Ogni azione dietro il dispatcher `plancia` (mcp.CODA) va chiamata
        # con `azione="<nome>"`, non con un tool `plancia_<nome>` che non
        # esiste: solo i sei di mcp.PRIMI sono tool di prima classe.
        fantasma = [az for az in sorted(mcp.CODA) if f"plancia_{az}" in testo]
        prova(f"la skill ({nome}) non nomina tool plancia_<azione> che non esistono",
              not fantasma, str(fantasma))

    # RIEPILOGO_SKILL_* (LOTTO-L4-SITO): come SKILL_IT/SKILL_EN sopra, con
    # `plancia_recap`/`plancia_speak` (tool diretti che non esistono: sono
    # l'azione "recap"/"speak" dietro il dispatcher `plancia`) al posto di
    # `plancia_<azione>` nel controllo fantasma.
    riepilogo = {"it": setup_claude.RIEPILOGO_SKILL_IT,
                 "en": setup_claude.RIEPILOGO_SKILL_EN}
    for nome, testo in riepilogo.items():
        prova(f"RIEPILOGO_SKILL ({nome}) non nomina più plancia_recap o plancia_speak "
              "come tool diretti",
              "plancia_recap" not in testo and "plancia_speak" not in testo)
        prova(f"RIEPILOGO_SKILL ({nome}) chiama il recap dal dispatcher",
              'azione="recap"' in testo)
        prova(f"RIEPILOGO_SKILL ({nome}) non parla più di plancia_manda",
              "plancia_manda" not in testo)
        prova(f"RIEPILOGO_SKILL ({nome}) non ha em dash",
              "—" not in testo)
        parola_autonomia = "autonomia" if nome == "it" else "on your own"
        prova(f"RIEPILOGO_SKILL ({nome}) dice comunque di riprendere il task, non di lanciare",
              "riprendi" in testo and parola_autonomia in testo.lower())
        fantasma = [az for az in sorted(mcp.CODA) if f"plancia_{az}" in testo]
        prova(f"RIEPILOGO_SKILL ({nome}) non nomina tool plancia_<azione> che non esistono",
              not fantasma, str(fantasma))

    prova("RIEPILOGO_SKILL_EN non è RIEPILOGO_SKILL_IT travestita",
          setup_claude.RIEPILOGO_SKILL_EN != setup_claude.RIEPILOGO_SKILL_IT)
    prova("riepilogo_skill_text ripiega sull'italiano per una lingua non scritta a mano",
          setup_claude.riepilogo_skill_text("fr") == setup_claude.RIEPILOGO_SKILL_IT)
    prova("riepilogo_skill_text(\"en\") torna il testo inglese",
          setup_claude.riepilogo_skill_text("en") == setup_claude.RIEPILOGO_SKILL_EN)
    prova("RIEPILOGO_SKILL resta l'alias italiano, per compatibilita'",
          setup_claude.RIEPILOGO_SKILL == setup_claude.RIEPILOGO_SKILL_IT)

    sezioni_it = _sezioni(it)
    sezioni_en = _sezioni(en)
    prova("le due lingue hanno lo stesso numero di sezioni",
          len(sezioni_it) == len(sezioni_en) and len(sezioni_it) > 0,
          f"it={sezioni_it} en={sezioni_en}")
    prova("le sezioni nuove sono in entrambe le lingue",
          any("iprend" in s for s in sezioni_it)
          and any("esum" in s for s in sezioni_en),
          f"it={sezioni_it} en={sezioni_en}")

    # Confronto sezione per sezione, non solo il conteggio: stesso insieme di
    # identificatori fra backtick (tranne le due sezioni tradotte a mano) e
    # stesso numero di elenchi puntati. Una traduzione fatta a metà, che
    # aggiunge o perde un `plancia_xxx` o un punto elenco in una sola lingua,
    # fa cadere questa prova anche se il conteggio delle sezioni resta uguale.
    corpi_it = _corpi(it)
    corpi_en = _corpi(en)
    if len(corpi_it) == len(corpi_en):
        for i, (cit, cen) in enumerate(zip(corpi_it, corpi_en)):
            titolo = sezioni_it[i] if i < len(sezioni_it) else f"#{i}"
            bic = len(BULLET.findall(cit))
            bec = len(BULLET.findall(cen))
            prova(f"sezione '{titolo}': stesso numero di elenchi puntati in it/en",
                  bic == bec, f"it={bic} en={bec}")
            if i not in SEZIONI_TRADOTTE_A_MANO:
                tic = set(BACKTICK.findall(cit))
                tec = set(BACKTICK.findall(cen))
                prova(f"sezione '{titolo}': stessi identificatori fra backtick in it/en",
                      tic == tec, f"solo it={tic - tec} solo en={tec - tic}")

    prova("una lingua non scritta a mano ripiega sull'italiano",
          setup_claude.skill_text("fr") == it)
    prova("l'inglese non è l'italiano travestito", en != it)

    # install_skill() non deve mai poter scrivere in ~/.claude né in
    # ~/.plancia: qui gira tutta su una cartella finta. SKILL_DIR è calcolato
    # una sola volta all'import di setup_claude (config.CLAUDE_DIR /
    # "skills" / "plancia"), quindi spostare solo config.CLAUDE_DIR non
    # basterebbe: va riassegnato anche l'attributo del modulo. Lo stesso vale
    # per load_config()/save_config(), che leggono e scrivono sempre
    # config.CONFIG_FILE (dentro config.DATA_DIR): senza spostare anche
    # quelli, il test scriverebbe "lingua: en" nel config.json vero la prima
    # volta che gira fuori da tools/prova.py (che imposta PLANCIA_HOME), come
    # misurato durante il lotto L2-SKILL-2 seguendo esattamente lo snippet di
    # tools/prove/README.md ("per lanciare solo il tuo modulo"), che non
    # imposta PLANCIA_HOME. Qui si spostano anche quelli, quindi il test è
    # isolato con o senza PLANCIA_HOME impostata da chi lo lancia, e basta il
    # rmtree della cartella finta per rimettere tutto a posto: niente viene
    # mai scritto nella cartella vera, quindi non c'è niente da ripristinare
    # lì.
    finta = Path(tempfile.mkdtemp(prefix="plancia-prova-skill-"))
    vecchio_claude_dir = config.CLAUDE_DIR
    vecchio_skill_dir = setup_claude.SKILL_DIR
    vecchio_data_dir = config.DATA_DIR
    vecchia_queue_dir = config.QUEUE_DIR
    vecchio_config_file = config.CONFIG_FILE
    try:
        config.CLAUDE_DIR = finta / "claude"
        setup_claude.SKILL_DIR = config.CLAUDE_DIR / "skills" / "plancia"
        config.DATA_DIR = finta / "plancia"
        config.QUEUE_DIR = config.DATA_DIR / "queue"
        config.CONFIG_FILE = config.DATA_DIR / "config.json"

        # La skill "riepilogo" (LOTTO-L4-SITO) vive in una cartella sorella,
        # calcolata a partire da config.CLAUDE_DIR e non da SKILL_DIR: va
        # letta con il suo percorso vero, non con setup_claude.SKILL_DIR (che
        # resta quello di "plancia"). Senza questa prova, rimettere
        # `RIEPILOGO_SKILL` al posto di `riepilogo_skill_text(lang)` alla
        # scrittura (com'era prima di questo lotto) passerebbe tutte le
        # prove esistenti: nessuna di esse legge mai questo file.
        riepilogo_dir = config.CLAUDE_DIR / "skills" / "riepilogo"

        msg_en = setup_claude.install_skill("en")
        scritto_en = (setup_claude.SKILL_DIR / "SKILL.md").read_text("utf-8")
        scritto_riepilogo_en = (riepilogo_dir / "SKILL.md").read_text("utf-8")
        prova("install_skill(\"en\") scrive il testo inglese nella cartella scelta",
              scritto_en == en and "en" in msg_en)
        prova("install_skill(\"en\") scrive anche la skill riepilogo in inglese",
              scritto_riepilogo_en == setup_claude.RIEPILOGO_SKILL_EN)

        msg_it = setup_claude.install_skill("it")
        scritto_it = (setup_claude.SKILL_DIR / "SKILL.md").read_text("utf-8")
        scritto_riepilogo_it = (riepilogo_dir / "SKILL.md").read_text("utf-8")
        prova("install_skill(\"it\") sovrascrive con il testo italiano",
              scritto_it == it and "it" in msg_it)
        prova("install_skill(\"it\") sovrascrive la skill riepilogo in italiano",
              scritto_riepilogo_it == setup_claude.RIEPILOGO_SKILL_IT)

        # La chiave vera è "lingua" (config.py, recap.py:24, api.py, voice.py,
        # l'app Mac), non "locale": "locale" in config.DEFAULTS non è scritta
        # né letta da nessun altro punto del programma. Con "lingua"="en" e
        # nessuna "locale" salvata, install_skill() senza argomento deve
        # scegliere l'inglese.
        cfg = config.load_config()
        cfg.pop("locale", None)
        cfg["lingua"] = "en"
        config.save_config(cfg)
        setup_claude.install_skill()
        scritto_auto = (setup_claude.SKILL_DIR / "SKILL.md").read_text("utf-8")
        scritto_riepilogo_auto = (riepilogo_dir / "SKILL.md").read_text("utf-8")
        prova("senza lingua esplicita, install_skill segue \"lingua\" da config.json",
              scritto_auto == en)
        prova("senza lingua esplicita, la skill riepilogo segue \"lingua\" da config.json",
              scritto_riepilogo_auto == setup_claude.RIEPILOGO_SKILL_EN)

        # Una lingua non scritta a mano (es. "fr") ripiega sull'italiano per
        # tutte e due le skill, e il messaggio deve dirlo: "(fr)" per un file
        # che e' in realta' italiano sarebbe la stessa bugia di prima.
        msg_fr = setup_claude.install_skill("fr")
        scritto_fr = (setup_claude.SKILL_DIR / "SKILL.md").read_text("utf-8")
        scritto_riepilogo_fr = (riepilogo_dir / "SKILL.md").read_text("utf-8")
        prova("install_skill(\"fr\") scrive comunque il testo italiano per entrambe le skill",
              scritto_fr == it and scritto_riepilogo_fr == setup_claude.RIEPILOGO_SKILL_IT)
        prova("install_skill(\"fr\") dice \"(it)\", non \"(fr)\", perché è quello che ha scritto",
              "(fr)" not in msg_fr and msg_fr.count("(it)") == 2, msg_fr)

        # Ripiego: chi ha scritto a mano la vecchia chiave "locale" e non ha
        # "lingua" continua a essere seguito, invece di rompersi in silenzio.
        cfg = config.load_config()
        cfg.pop("lingua", None)
        cfg["locale"] = "en"
        config.save_config(cfg)
        setup_claude.install_skill()
        scritto_ripiego = (setup_claude.SKILL_DIR / "SKILL.md").read_text("utf-8")
        prova("senza \"lingua\", install_skill ripiega su \"locale\"",
              scritto_ripiego == en)
    finally:
        config.CLAUDE_DIR = vecchio_claude_dir
        setup_claude.SKILL_DIR = vecchio_skill_dir
        config.DATA_DIR = vecchio_data_dir
        config.QUEUE_DIR = vecchia_queue_dir
        config.CONFIG_FILE = vecchio_config_file
        shutil.rmtree(finta, ignore_errors=True)
