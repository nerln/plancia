"""Un finto Pocket-TTS per le prove del pannello Jarvis: niente modelli, niente audio vero.

Non e' una prova (comincia con `_`, `tools/prova.py` non la scopre). Uso:

    python3 tools/prove/_pocket_finto.py <porta> <registro>

Parla come il vero Pocket (plancia/voice.py): `GET /health` risponde 200 e
`POST /tts` (multipart, campo `text`) risponde un file WAV. Ogni frase ricevuta finisce nel
registro come `<secondi dall'epoca> <testo>`, cosi' una prova puo' dire QUANDO e' arrivata
ogni richiesta (la sintesi della frase dopo deve partire mentre la prima suona).

Il WAV e' un tono breve (0,8 s, mono, 16 kHz). Una frase che contiene "guasto" fa
rispondere 500: serve a provare il ripiego sulla voce di sistema.
"""
import http.server
import io
import math
import re
import sys
import time
import wave

PORTA = int(sys.argv[1])
REGISTRO = sys.argv[2]
DURATA = 0.8


def wav() -> bytes:
    ritmo = 16000
    dati = b"".join(
        int(6000 * math.sin(2 * math.pi * 220 * i / ritmo)).to_bytes(2, "little", signed=True)
        for i in range(int(ritmo * DURATA)))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(ritmo)
        w.writeframes(dati)
    return buf.getvalue()


class Gestore(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        self.send_response(200 if self.path == "/health" else 404)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"ok")

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        corpo = self.rfile.read(n).decode("utf-8", "replace")
        m = re.search(r'name="text"\r\n\r\n(.*?)\r\n--', corpo, re.S)
        testo = m.group(1) if m else ""
        with open(REGISTRO, "a", encoding="utf-8") as f:
            f.write("%.3f %s\n" % (time.time(), testo.replace("\n", " ")))
        if "guasto" in testo:
            self.send_response(500)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        time.sleep(0.15)
        dati = wav()
        self.send_response(200)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Content-Length", str(len(dati)))
        self.end_headers()
        self.wfile.write(dati)


http.server.ThreadingHTTPServer(("127.0.0.1", PORTA), Gestore).serve_forever()
