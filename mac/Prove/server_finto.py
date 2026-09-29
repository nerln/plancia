#!/usr/bin/env python3
"""Un server finto per tools/prova-mac.sh: serve le fixture di mac/Prove/fixture alle
rotte vere, scrive ogni richiesta in un registro, e come il server vero rifiuta le
scritture senza il token giusto. Ascolta solo su 127.0.0.1.

    server_finto.py <porta> <cartella fixture> <registro> <token>
"""
import json
import os
import re
import sys
import urllib.parse
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORTA, FIXTURE, REGISTRO, TOKEN = int(sys.argv[1]), sys.argv[2], sys.argv[3], sys.argv[4]

ROTTE = {
    "/api/status": "status", "/api/overview": "overview", "/api/prossimi": "prossimi",
    "/api/tasks": "tasks_status_tutti", "/api/posts": "posts", "/api/sessions": "sessions",
    "/api/events": "events", "/api/eventi": "eventi", "/api/knowledge": "knowledge",
    "/api/memoria/mappa": "memoria_mappa", "/api/proposte": "proposte", "/api/runs": "runs",
    "/api/search": "search_q_plancia", "/api/recap": "recap_solo_cache_1", "/api/lavagna": "lavagna",
}


# Le prove di concorrenza hanno bisogno di un server lento e che risponda a piu' richieste
# insieme: ThreadingHTTPServer, e un ritardo (in ms) che la prova scrive nel file
# <registro>.ritardo e che si applica a ogni lettura. /api/lento?ms=N ritarda solo se stessa.
RITARDO = REGISTRO + ".ritardo"
LUCCHETTO = threading.Lock()


def ritardo_ms():
    try:
        with open(RITARDO, encoding="utf-8") as f:
            return int(f.read().strip() or 0)
    except (OSError, ValueError):
        return 0


class Gestore(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _registra(self, parsed):
        with LUCCHETTO:
            with open(REGISTRO, "a", encoding="utf-8") as f:
                f.write("%s %s?%s token=%s\n" % (self.command, parsed.path, parsed.query,
                                                 self.headers.get("X-Plancia-Token") or "-"))

    def _json(self, dati, codice=200):
        corpo = json.dumps(dati, ensure_ascii=False).encode("utf-8")
        self.send_response(codice)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def _fixture(self, nome):
        with open(os.path.join(FIXTURE, nome + ".json"), encoding="utf-8") as f:
            return json.load(f)

    def do_GET(self):
        p = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(p.query)
        self._registra(p)
        if p.path == "/api/lento":
            time.sleep(int((q.get("ms") or ["0"])[0]) / 1000.0)
            return self._json(self._fixture("status"))
        pausa = ritardo_ms()
        if pausa:
            time.sleep(pausa / 1000.0)
        if p.path == "/api/compartimenti":
            return self._json({"attivo": True, "elenco": ["predefinito", "Lavoro"],
                               "scelto": (q.get("compartimento") or ["predefinito"])[0],
                               "predefinito": "predefinito"})
        if p.path == "/api/projects":
            return self._json(self._fixture("projects_albero_1" if q.get("albero") else "projects"))
        m = re.match(r"^/api/projects/([^/]+)$", p.path)
        if m:
            return self._json(self._fixture("project_detail"))
        if p.path in ROTTE:
            return self._json(self._fixture(ROTTE[p.path]))
        return self._json({"errore": "rotta inesistente"}, 404)

    def _scrittura(self):
        p = urllib.parse.urlparse(self.path)
        self._registra(p)
        n = int(self.headers.get("Content-Length") or 0)
        if n:
            self.rfile.read(n)
        if self.headers.get("X-Plancia-Token") != TOKEN:
            return self._json({"errore": "token mancante o non valido"}, 403)
        return self._json({"ok": True})

    do_POST = do_PATCH = do_DELETE = _scrittura


ThreadingHTTPServer(("127.0.0.1", PORTA), Gestore).serve_forever()
