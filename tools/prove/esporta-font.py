"""Prove per L1-FONT, lato server: il mime dei woff2 e l'export senza rete.

`_static` in plancia/api.py deve rispondere ai font con `font/woff2` (Python
3.9 non lo conosce da solo) e continuare a rifiutare le sottocartelle;
`plancia esporta` deve incorporare i font in base64, mai con un url(http...).
Funzione pubblica `esegui(prova)`, stessa forma di tools/prova.py:32 (vedi
tools/prove/README.md). Il server di prova è tutto suo, su una porta
scelta dal sistema operativo (0), per non litigare con quello che
tools/prova.py apre già sulla 7791 né con quelli degli altri lotti.
"""

import re
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer


def _prova_mime_e_sottocartelle(prova):
    from plancia import api

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), api.Handler)
    porta = httpd.server_address[1]
    filo = threading.Thread(target=httpd.serve_forever, daemon=True)
    filo.start()
    try:
        try:
            with urllib.request.urlopen(
                    f"http://127.0.0.1:{porta}/plex-sans.woff2", timeout=10) as r:
                stato = r.status
                ctype = r.headers.get("Content-Type")
        except urllib.error.HTTPError as e:
            # Il rosso al commit base è "il file non esiste" (404), non un
            # Content-Type sbagliato: un NO leggibile, non un traceback.
            stato = e.code
            ctype = None
        prova("GET /plex-sans.woff2 risponde 200", stato == 200, str(stato))
        prova("GET /plex-sans.woff2 ha Content-Type font/woff2",
              ctype == "font/woff2", str(ctype))

        # Su questo Mac /etc/apache2/mime.types insegna già .woff2 a
        # mimetypes: senza un ramo esplicito in _static, questa prova
        # passerebbe anche se quel ramo sparisse. Si spegne la tabella di
        # sistema (mimetypes.guess_type -> (None, None), quello che
        # succederebbe su un Python 3.9 "nudo" senza voci font/*
        # nell'/etc locale) e si verifica che l'header resti comunque
        # font/woff2: senza il ramo arriverebbe application/octet-stream.
        originale = api.mimetypes.guess_type
        api.mimetypes.guess_type = lambda *a, **k: (None, None)
        try:
            with urllib.request.urlopen(
                    f"http://127.0.0.1:{porta}/plex-mono-400.woff2", timeout=10) as r:
                ctype_senza_tabella = r.headers.get("Content-Type")
        except urllib.error.HTTPError as e:
            ctype_senza_tabella = None
        finally:
            api.mimetypes.guess_type = originale
        prova("Content-Type font/woff2 anche con la tabella mime di sistema spenta",
              ctype_senza_tabella == "font/woff2", str(ctype_senza_tabella))

        # Il layout a sottocartelle del sito (site/font/*.woff2) è esattamente
        # quello che _static deve rifiutare quando serve web/*.woff2: stessa
        # richiesta, stesso file, con un solo slash in più nel percorso.
        try:
            urllib.request.urlopen(
                f"http://127.0.0.1:{porta}/font/plex-sans.woff2", timeout=10)
            fuggito = True
            codice = 200
        except urllib.error.HTTPError as e:
            fuggito = False
            codice = e.code
        prova("una richiesta con slash nel percorso resta rifiutata (404)",
              not fuggito and codice == 404, f"fuggito={fuggito} codice={codice}")
    finally:
        httpd.shutdown()
        httpd.server_close()


def _prova_esporta_senza_rete(prova):
    from plancia import esporta

    dati = {"memorie": [], "progetti": [], "task": [], "quando": "ora"}
    pagina = esporta.costruisci(dati)

    prova("l'export incorpora i font in base64",
          "data:font/woff2" in pagina, "")

    # Stesso criterio di tools/prova.py: si segnala ogni url(...) il cui
    # contenuto, tolti apici e spazi, non comincia con "data:" (case
    # insensitivo), non solo quelli con "http" dentro.
    senza_dati = re.sub(r"const DATI = .*?;\n", "", pagina, flags=re.S)
    urls_remoti = [u for u in re.findall(r"url\(([^)]*)\)", senza_dati)
                   if not u.strip().strip("'\"").lower().startswith("data:")]
    prova("nessun url( remoto dopo l'incorporazione dei font",
          not urls_remoti, str(urls_remoti))


def esegui(prova) -> None:
    _prova_mime_e_sottocartelle(prova)
    _prova_esporta_senza_rete(prova)


if __name__ == "__main__":
    import os
    import sys
    import tempfile
    from pathlib import Path

    RADICE = Path(__file__).resolve().parent.parent.parent
    sys.path.insert(0, str(RADICE))

    CASA = Path(tempfile.mkdtemp(prefix="plancia-prova-esporta-font-"))
    os.environ["PLANCIA_HOME"] = str(CASA)

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

    esegui(prova)
    print(f"\n{passati} passate, {len(falliti)} fallite")
    if falliti:
        for f in falliti:
            print(f"  - {f}")
        sys.exit(1)
