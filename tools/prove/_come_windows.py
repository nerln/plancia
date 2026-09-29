"""Lancia uno script di `bin/` come se il sistema fosse Windows: non e' una prova.

Comincia con `_`, quindi `tools/prova.py` non lo scopre. Si usa cosi':

    [sys.executable, "tools/prove/_come_windows.py", "bin/plancia-guardiano", ...]

Gli script di `bin/` decidono se sono su Windows da `os.name == "nt"` e da nient'altro:
non guardano `PLANCIA_PIATTAFORMA`, perche' quella variabile la scrive chiunque possa
scrivere un `settings.json` (vedi `plancia/compartimenti._ENV_PERICOLOSE`), e una
sessione non deve poter spegnere il guardiano con una riga di configurazione. Per provare
il ramo di Windows su un altro sistema resta un solo modo onesto: far credere allo script
che `os.name` sia `nt`.

Lo fa questo lanciatore, per il solo tempo dello script. Prima carica i moduli della
libreria standard che guardano `os.name` quando si importano (o quando si usano) e che lo
script potrebbe importare: dopo, `os.name` e' `nt` ma `os.path` e' ancora `posixpath`,
quindi i percorsi di prova (`/tmp/...`) restano validi. Il limite: uno script che dopo il
cambio istanziasse `pathlib.Path` cadrebbe (`WindowsPath` non si crea su un sistema POSIX);
i due script che lo usano (il guardiano e l'hook, nei loro rami di Windows) non lo fanno.
Su un Windows vero non serve e non si usa.
"""

import os
import runpy
import sys

# I moduli che leggono `os.name` all'importazione: vanno caricati prima del cambio.
import glob  # noqa: F401
import importlib.util  # noqa: F401
import json  # noqa: F401
import pathlib  # noqa: F401
import re  # noqa: F401
import shutil  # noqa: F401
import sqlite3  # noqa: F401
import subprocess  # noqa: F401
import tempfile  # noqa: F401
import time  # noqa: F401


def main() -> None:
    if len(sys.argv) < 2:
        sys.stderr.write("uso: _come_windows.py <script> [argomenti...]\n")
        sys.exit(2)
    script = sys.argv[1]
    sys.argv = [script] + sys.argv[2:]
    os.name = "nt"
    runpy.run_path(script, run_name="__main__")


if __name__ == "__main__":
    main()
