#!/usr/bin/env python3
"""Il lavoratore Kokoro di Jarvis: una voce neurale che resta in memoria.

Questo file NON importa Plancia e non gira col Python di Plancia (che e' solo
libreria standard): lo lancia `plancia/kokoro.py` con un Python esterno, quello del
venv di `plancia voce installa` (o quello scelto con `kokoro_python` in config.json),
dove ci sono `kokoro_onnx`, `onnxruntime` e `numpy`. Carica il modello UNA volta e
poi serve richieste finche' il suo stdin resta aperto: quando Plancia lo chiude (o il
processo di Plancia muore) il lavoratore esce da solo.

Il protocollo e' a righe JSON, una per riga, solo ASCII:

    stdin   {"id": 3, "testo": "...", "voce": "if_sara", "velocita": 1.0,
             "pausa": 0.18, "uscita": "/percorso/frase.wav"}
            {"id": 4, "cmd": "ping"}       risponde subito, per sapere che e' vivo
            {"id": 5, "cmd": "esci"}       risponde e chiude

    stdout  {"pronto": true, "ms": 1830, "voci": 54, "hz": 24000, "picco_mb": 640}
            {"pronto": false, "errore": "..."}                  e poi esce
            {"id": 3, "ok": true, "file": "...", "durata": 4.52, "ms": 736, "hz": 24000}
            {"id": 3, "ok": false, "errore": "..."}

Tutto il resto (i messaggi delle librerie) va su stderr: stdout e' solo protocollo.

    voce      un nome del catalogo Kokoro (if_sara, im_nicola, af_heart, ef_dora...).
              La prima lettera dice la lingua da fonemizzare; `lingua` nella richiesta
              la sostituisce se serve.
    velocita  1.0 e' la voce normale; Kokoro accetta da 0.5 a 2.0.
    pausa     secondi di silenzio da aggiungere in fondo. Serve quando la frase e' un
              pezzo tagliato a una virgola: le due meta' suonano una dopo l'altra come
              in una frase sola, invece che attaccate.
    uscita    il WAV: 24 kHz, mono, 16 bit. Si scrive prima come `.part` e poi si
              rinomina, cosi' un lavoratore ucciso a meta' non lascia un file rotto.

Opzioni: --modelli CARTELLA (kokoro-v1.0.onnx e voices-v1.0.bin), --thread N (4 di
serie: sopra non si guadagna niente), --controlla (importa le librerie, dice le versioni
ed esce, senza caricare il modello), --senza-riscaldo (non fa la frase di prova prima di
dire "pronto").
"""

import json
import os
import signal
import sys
import time
import wave

MODELLO = "kokoro-v1.0.onnx"
VOCI = "voices-v1.0.bin"

# La prima lettera del nome della voce e' la lingua che espeak-ng deve fonemizzare.
FONEMI = {"a": "en-us", "b": "en-gb", "e": "es", "f": "fr-fr", "h": "hi",
          "i": "it", "j": "ja", "p": "pt-br", "z": "cmn"}

TETTO_PICCO = 0.98

_uscita = None


def rispondi(oggetto):
    _uscita.write(json.dumps(oggetto) + "\n")
    _uscita.flush()


def memoria_mb():
    """Il picco di memoria residente di questo processo, in MB (solo dove c'e' `resource`)."""
    try:
        import resource
        m = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    except (ImportError, ValueError):
        return None
    # macOS lo da' in byte, Linux in kilobyte
    return int(m / (1024 * 1024) if sys.platform == "darwin" else m / 1024)


def fonemi_per(voce, lingua=None):
    if lingua:
        return lingua
    return FONEMI.get(voce[:1], "en-us")


def scrivi_wav(percorso, audio, hz, pausa):
    """`audio` e' un array float32 mono. Ritorna la durata in secondi."""
    import numpy as np
    audio = np.asarray(audio, dtype=np.float32).reshape(-1)
    picco = float(np.max(np.abs(audio))) if audio.size else 0.0
    if picco > TETTO_PICCO:
        # una voce che supera il fondo scala (if_sara sfiora 1,01) viene tagliata dal 16
        # bit: si abbassa il pezzo che serve, senza un limitatore su tutto
        audio = audio * (TETTO_PICCO / picco)
    if pausa > 0:
        audio = np.concatenate([audio, np.zeros(int(hz * pausa), dtype=np.float32)])
    dati = (np.clip(audio, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()
    parziale = percorso + ".part"
    with wave.open(parziale, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(hz)
        w.writeframes(dati)
    os.replace(parziale, percorso)
    return audio.size / float(hz)


def sintetizza(kokoro, richiesta):
    testo = (richiesta.get("testo") or "").strip()
    if not testo:
        raise ValueError("testo vuoto")
    uscita = richiesta.get("uscita")
    if not uscita:
        raise ValueError("manca il file di uscita")
    voce = richiesta.get("voce") or "if_sara"
    if voce not in kokoro.voices:
        raise ValueError("voce sconosciuta: %s" % voce)
    velocita = min(2.0, max(0.5, float(richiesta.get("velocita") or 1.0)))
    pausa = min(2.0, max(0.0, float(richiesta.get("pausa") or 0.0)))
    audio, hz = kokoro.create(testo, voice=voce, speed=velocita,
                              lang=fonemi_per(voce, richiesta.get("lingua")))
    if getattr(audio, "size", len(audio)) == 0:
        raise ValueError("nessun audio da questo testo")
    return scrivi_wav(uscita, audio, int(hz), pausa), int(hz)


def carica(cartella, thread, riscalda):
    """Il modello in memoria. Ritorna (kokoro, millisecondi, numero di voci)."""
    inizio = time.perf_counter()
    import onnxruntime as rt
    from kokoro_onnx import Kokoro
    modello = os.path.join(cartella, MODELLO)
    voci = os.path.join(cartella, VOCI)
    for p in (modello, voci):
        if not os.path.isfile(p):
            raise FileNotFoundError("manca %s" % p)
    opzioni = rt.SessionOptions()
    opzioni.intra_op_num_threads = thread
    opzioni.inter_op_num_threads = 1
    sessione = rt.InferenceSession(modello, sess_options=opzioni,
                                   providers=["CPUExecutionProvider"])
    # Dopo ogni frase onnxruntime restituisce al sistema la memoria di lavoro che ha preso, invece
    # di tenersela: misurato su un M4 dopo 24 frasi di lunghezza varia, 470 MB invece di 1,1 GB,
    # alla stessa velocita'. Kokoro chiama `sessione.run(None, ingressi)`: lo si avvolge.
    try:
        opzioni_run = rt.RunOptions()
        opzioni_run.add_run_config_entry("memory.enable_memory_arena_shrinkage", "cpu:0")
        esegui_originale = sessione.run
        sessione.run = lambda nomi, ingressi, *a, **kw: esegui_originale(nomi, ingressi, opzioni_run)
    except Exception as exc:  # noqa: BLE001 - una versione vecchia di onnxruntime: si va avanti
        print("memoria: la riduzione dopo ogni frase non c'e' (%s)" % exc, file=sys.stderr)
    kokoro = Kokoro.from_session(sessione, voci)
    if riscalda:
        # il fonemizzatore e onnxruntime pagano la prima chiamata: meglio adesso, prima di
        # dire "pronto", che sulla prima frase vera di Jarvis
        voce = "if_sara" if "if_sara" in kokoro.voices else sorted(kokoro.voices)[0]
        kokoro.create("Va bene.", voice=voce, speed=1.0, lang=fonemi_per(voce))
    return kokoro, int((time.perf_counter() - inizio) * 1000), len(kokoro.voices)


def controlla():
    import numpy
    import onnxruntime
    import kokoro_onnx  # noqa: F401
    try:
        from importlib.metadata import version
        v = version("kokoro-onnx")
    except Exception:
        v = "?"
    rispondi({"controllo": True, "kokoro_onnx": v, "onnxruntime": onnxruntime.__version__,
              "numpy": numpy.__version__, "python": "%d.%d.%d" % sys.version_info[:3]})


def main(argv):
    global _uscita
    # stdout e' solo protocollo: le librerie che stampano vanno su stderr
    _uscita = sys.stdout
    sys.stdout = sys.stderr
    try:
        # Ctrl-C nel terminale di chi ha lanciato Plancia non deve uccidere la voce a
        # meta': ci pensa Plancia a chiuderla
        signal.signal(signal.SIGINT, signal.SIG_IGN)
    except (ValueError, OSError):
        pass
    cartella = None
    thread = 4
    riscalda = True
    solo_controllo = False
    i = 1
    while i < len(argv):
        a = argv[i]
        if a == "--modelli" and i + 1 < len(argv):
            cartella = argv[i + 1]
            i += 1
        elif a == "--thread" and i + 1 < len(argv):
            thread = max(1, int(argv[i + 1]))
            i += 1
        elif a == "--controlla":
            solo_controllo = True
        elif a == "--senza-riscaldo":
            riscalda = False
        i += 1
    if solo_controllo:
        try:
            controlla()
            return 0
        except Exception as exc:  # noqa: BLE001
            rispondi({"controllo": False, "errore": "%s: %s" % (type(exc).__name__, exc)})
            return 2
    if not cartella:
        rispondi({"pronto": False, "errore": "manca --modelli"})
        return 2
    try:
        kokoro, ms, quante = carica(cartella, thread, riscalda)
    except Exception as exc:  # noqa: BLE001 - qualunque guasto si dice a chi ci ha lanciato
        rispondi({"pronto": False, "errore": "%s: %s" % (type(exc).__name__, exc)})
        return 2
    rispondi({"pronto": True, "ms": ms, "voci": quante, "hz": 24000, "picco_mb": memoria_mb()})

    ingresso = sys.stdin
    try:
        ingresso.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    for riga in ingresso:
        riga = riga.strip()
        if not riga:
            continue
        try:
            r = json.loads(riga)
            if not isinstance(r, dict):
                raise ValueError("la richiesta non e' un oggetto")
        except ValueError as exc:
            rispondi({"id": None, "ok": False, "errore": "richiesta illeggibile: %s" % exc})
            continue
        ident = r.get("id")
        cmd = r.get("cmd")
        if cmd == "ping":
            rispondi({"id": ident, "ok": True, "picco_mb": memoria_mb()})
            continue
        if cmd == "esci":
            rispondi({"id": ident, "ok": True})
            return 0
        inizio = time.perf_counter()
        try:
            durata, hz = sintetizza(kokoro, r)
        except Exception as exc:  # noqa: BLE001 - una frase che non riesce non ferma le altre
            rispondi({"id": ident, "ok": False, "errore": "%s: %s" % (type(exc).__name__, exc)})
            continue
        rispondi({"id": ident, "ok": True, "file": r["uscita"], "durata": round(durata, 3),
                  "ms": int((time.perf_counter() - inizio) * 1000), "hz": hz})
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
