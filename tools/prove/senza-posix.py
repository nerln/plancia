"""Plancia su un sistema senza le funzioni solo POSIX del modulo `os`.

Su Windows `os.getuid` non esiste. Il collaudo di GitHub su windows-latest ha
visto `tools/prova.py` cadere all'avvio con `AttributeError: module 'os' has no
attribute 'getuid'`: `compartimenti.Ambito` lo chiamava sempre, e ci passano il
briefing, il richiamo, l'MCP e la dashboard appena `config.json` esiste. Sul Mac
non si vede, perche' `os.getuid` c'e'.

Qui si toglie `os.getuid` per la durata della prova e si costruisce quello che
passa di li'. L'uid serve solo a riconoscere la cartella temporanea di Claude
Code sul Mac (`/private/tmp/claude-<uid>`): senza, resta `None`.

Per lanciare da sola: `python3 tools/prove/senza-posix.py`.
"""

import os
import sys
import tempfile
from pathlib import Path

RADICE = Path(__file__).resolve().parents[2]
if str(RADICE) not in sys.path:
    sys.path.insert(0, str(RADICE))


class _SenzaGetuid:
    """Toglie `os.getuid` (e `os.geteuid`) come su Windows, e li rimette."""

    def __enter__(self):
        self._tolti = {}
        for nome in ("getuid", "geteuid"):
            if hasattr(os, nome):
                self._tolti[nome] = getattr(os, nome)
                delattr(os, nome)
        return self

    def __exit__(self, *_):
        for nome, funzione in self._tolti.items():
            setattr(os, nome, funzione)
        return False


def esegui(prova):
    from plancia import compartimenti

    casa = tempfile.mkdtemp(prefix="plancia-prova-senza-posix-")
    comp = {"alfa": {"cartelle": [os.path.join(casa, "alfa")], "sessioni": [], "drive_ids": []}}
    with _SenzaGetuid():
        try:
            ambito = compartimenti.Ambito(comp, [], home=casa, data_dir=os.path.join(casa, "dati"),
                                          claude_dir=os.path.join(casa, ".claude"))
            errore = ""
        except Exception as e:  # noqa: BLE001
            ambito, errore = None, f"{type(e).__name__}: {e}"
    prova("senza os.getuid (Windows) i compartimenti si costruiscono lo stesso",
          ambito is not None, errore)
    prova("senza os.getuid l'uid resta vuoto invece di inventarne uno",
          ambito is not None and ambito.uid is None,
          "" if ambito is None else repr(ambito.uid))
    prova("con os.getuid (macOS, Linux) l'uid e' quello del processo",
          not hasattr(os, "getuid")
          or compartimenti.Ambito(comp, [], home=casa).uid == os.getuid())


if __name__ == "__main__":
    passate = fallite = 0

    def _prova(nome, esito, dettaglio=""):
        global passate, fallite
        if esito:
            passate += 1
            print(f"  ok   {nome}")
        else:
            fallite += 1
            print(f"  NO   {nome} {dettaglio}")

    esegui(_prova)
    print(f"\n{passate} passate, {fallite} fallite")
    sys.exit(1 if fallite else 0)
