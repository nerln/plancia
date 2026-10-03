"""Prova del motore che `/api/jarvis` prevede prima di sintetizzare (22-RIPARAZIONE).

Il server dice subito, nella risposta, con che motore parlera' la voce: il chiamante che
ha la sua voce di sistema (`voce_nativa`) la usa solo se il motore previsto e' `say`.
Con Kokoro come primo motore neurale, la previsione guardava solo Voicebox: con Kokoro
acceso e Voicebox spento diceva `say`, e chi aveva la voce nativa parlava con quella di
sistema invece che con Kokoro. Ora la previsione e' `voice.voce_neurale()`, nell'ordine
Kokoro, Pocket, Voicebox, e `say` solo se nessuna risponde.

Il server gira in un processo figlio con casa, archivio e PATH finti; nessun motore vero.

Per lanciare da sola: `python3 tools/prove/jarvis-motore-previsto.py`.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent.parent

_FIGLIO = r"""
import json, os, sys, threading, urllib.request
sys.path.insert(0, os.environ["RADICE_PROVA"])
from plancia import agente, api, config, recap, store, voice

recap.claude_bin = lambda: ""
agente.chiedi = lambda *a, **k: "Risposta di Jarvis di prova."
conn = store.connect(); store.init_db(conn); store.migrate(conn); conn.close()

httpd = api._Server(("127.0.0.1", 0), api.Handler)
porta = httpd.server_address[1]
threading.Thread(target=httpd.serve_forever, daemon=True).start()

def motore_previsto(neurali, nativa=True):
    # neurali: quali motori "rispondono" (kokoro, pocket, voicebox)
    voice.voce_neurale = lambda lang=None: neurali[0] if neurali else ""
    voice.voicebox_vivo = lambda *a, **k: "voicebox" in neurali
    voice.pocket_vivo = lambda *a, **k: "pocket" in neurali
    corpo = {"testo": "come sta andando", "lang": "it", "voce": False, "voce_nativa": nativa}
    req = urllib.request.Request(
        "http://127.0.0.1:%d/api/jarvis" % porta, data=json.dumps(corpo).encode("utf-8"),
        method="POST", headers={"Content-Type": "application/json",
                                "X-Plancia-Token": config.get_token()})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read()).get("motore")

visto = {
    "kokoro": motore_previsto(["kokoro"]),
    "pocket": motore_previsto(["pocket"]),
    "voicebox": motore_previsto(["voicebox"]),
    "nessuno": motore_previsto([]),
}
httpd.shutdown()
print("@@" + json.dumps(visto))
"""


def esegui(prova):
    casa = Path(tempfile.mkdtemp(prefix="plancia-prova-motore-previsto-"))
    env = dict(os.environ)
    env.update({"HOME": str(casa), "PLANCIA_HOME": str(casa / "plancia"),
                "CLAUDE_CONFIG_DIR": str(casa / "claude"), "CODEX_HOME": str(casa / "codex"),
                "TMPDIR": str(casa), "RADICE_PROVA": str(RADICE), "PYTHONDONTWRITEBYTECODE": "1"})
    try:
        r = subprocess.run([sys.executable, "-c", _FIGLIO], env=env, capture_output=True,
                           text=True, timeout=180)
        riga = [x for x in r.stdout.splitlines() if x.startswith("@@")]
        visto = json.loads(riga[-1][2:]) if riga else {}
        dettaglio = (r.stdout + r.stderr)[-600:]
    except subprocess.TimeoutExpired:
        visto, dettaglio = {}, "timeout"
    finally:
        import shutil
        shutil.rmtree(casa, ignore_errors=True)

    prova("motore previsto: con Kokoro acceso e Voicebox spento e' kokoro, non say",
          visto.get("kokoro") == "kokoro", dettaglio + str(visto))
    prova("motore previsto: con solo Pocket e' pocket", visto.get("pocket") == "pocket", str(visto))
    prova("motore previsto: con solo Voicebox e' voicebox", visto.get("voicebox") == "voicebox", str(visto))
    prova("motore previsto: senza nessuna voce neurale e' say", visto.get("nessuno") == "say", str(visto))


if __name__ == "__main__":
    risultati = []

    def _prova(nome, ok, extra=""):
        risultati.append(ok)
        print(("  ok   " if ok else "  NO   ") + nome + ("" if ok else "  " + str(extra)))

    esegui(_prova)
    sys.exit(0 if all(risultati) else 1)
