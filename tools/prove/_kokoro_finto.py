"""Un finto lavoratore Kokoro per le prove: niente modello, niente onnxruntime.

Non e' una prova (comincia con `_`, `tools/prova.py` non la scopre). Parla lo stesso
protocollo di `plancia/voce_kokoro.py` (righe JSON su stdin e stdout) e scrive un WAV
minimo (0,3 s di tono a 24 kHz, piu' il silenzio chiesto in `pausa`).

Lo lancia un piccolo eseguibile scritto dalla prova (il "Python finto" di `kokoro_python`),
che chiama `main(argv, percorso_controllo)`. Il file di controllo e' un JSON riletto a ogni
richiesta, cosi' la prova puo' cambiare il comportamento mentre il lavoratore e' vivo:

    registro             file dove ogni evento aggiunge una riga "<epoca> <EVENTO> <pid> ..."
    carica_s             secondi prima di dire "pronto" (un modello lento)
    guasto_avvio         un testo: invece di "pronto" scrive l'errore ed esce
    latenza_s            secondi di lavoro per ogni frase
    muori_alla_richiesta n: alla richiesta numero n (da 0) il processo muore senza rispondere
    tace_su              una parola: una frase che la contiene non riceve mai risposta
    rifiuta              una parola: una frase che la contiene riceve ok:false

Eventi nel registro: AVVIO, PRONTO, RICH (testo | voce | velocita | pausa), USCITA.
"""
import json
import math
import os
import sys
import time
import wave


def _leggi(ctl):
    try:
        with open(ctl, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _registro(ctl, evento, extra=""):
    percorso = _leggi(ctl).get("registro")
    if not percorso:
        return
    with open(percorso, "a", encoding="utf-8") as f:
        f.write("%.3f %s %d %s\n" % (time.time(), evento, os.getpid(), extra))


def _wav(percorso, pausa):
    hz = 24000
    campioni = [int(6000 * math.sin(2 * math.pi * 220 * i / hz)) for i in range(int(hz * 0.3))]
    campioni += [0] * int(hz * pausa)
    dati = b"".join(c.to_bytes(2, "little", signed=True) for c in campioni)
    with wave.open(percorso + ".part", "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(hz)
        w.writeframes(dati)
    os.replace(percorso + ".part", percorso)
    return len(campioni) / float(hz)


def _dici(oggetto):
    sys.stdout.write(json.dumps(oggetto) + "\n")
    sys.stdout.flush()


def main(argv, ctl):
    _registro(ctl, "AVVIO", " ".join(argv[2:]))
    if "--controlla" in argv:
        _dici({"controllo": True, "kokoro_onnx": "0.5.0", "onnxruntime": "finto",
               "numpy": "finto", "python": "3.12.0"})
        return 0
    c = _leggi(ctl)
    time.sleep(float(c.get("carica_s", 0)))
    if c.get("guasto_avvio"):
        _dici({"pronto": False, "errore": c["guasto_avvio"]})
        _registro(ctl, "USCITA", "guasto all'avvio")
        return 2
    _dici({"pronto": True, "ms": 5, "voci": 3, "hz": 24000, "picco_mb": 1})
    _registro(ctl, "PRONTO")
    n = 0
    for riga in sys.stdin:
        riga = riga.strip()
        if not riga:
            continue
        r = json.loads(riga)
        if r.get("cmd") == "ping":
            _dici({"id": r.get("id"), "ok": True, "picco_mb": 1})
            continue
        if r.get("cmd") == "esci":
            _dici({"id": r.get("id"), "ok": True})
            break
        c = _leggi(ctl)
        testo = r.get("testo", "")
        _registro(ctl, "RICH", "%s | %s | %s | %s" % (testo, r.get("voce"), r.get("velocita"),
                                                     r.get("pausa")))
        if c.get("muori_alla_richiesta") == n:
            _registro(ctl, "MORTE")
            os._exit(3)
        n += 1
        if c.get("tace_su") and c["tace_su"] in testo:
            time.sleep(600)
            continue
        time.sleep(float(c.get("latenza_s", 0)))
        if c.get("rifiuta") and c["rifiuta"] in testo:
            _dici({"id": r.get("id"), "ok": False, "errore": "rifiutata dal finto"})
            continue
        durata = _wav(r["uscita"], float(r.get("pausa") or 0))
        _dici({"id": r.get("id"), "ok": True, "file": r["uscita"], "durata": round(durata, 3),
               "ms": 5, "hz": 24000})
    _registro(ctl, "USCITA", "stdin chiuso o esci")
    return 0
