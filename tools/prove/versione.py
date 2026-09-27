"""Prove per LOTTO-L5-RIFINITURA, punto 1: `plancia --version` e
`python3 -m plancia.cli --version` stampano la versione vera ed escono 0.

Oggi (sulla base) `sub.add_subparsers(dest="cmd", required=True)` rende il
sottocomando obbligatorio anche quando l'unica cosa chiesta e' la versione:
`plancia --version` esce 2 con "the following arguments are required: cmd"
invece di stampare qualcosa. La correzione e' un `--version` con
`action="version"` sul parser di livello alto, che argparse gestisce prima
di controllare i sottocomandi obbligatori.

Due sottoprocessi, non un import in-process: `action="version"` chiama
`parser.exit()`, che alzerebbe `SystemExit` dentro questo stesso processo di
prova. `bin/plancia` e `python3 -m plancia.cli` sono le due vie d'accesso
reali (la seconda e' quella che il resto della suite usa per il comando
"plancia", vedi tools/prove/README.md); il comando `plancia` installato sul
PATH di chi lancia la prova puo' puntare a un altro checkout, quindi non si
usa qui.
"""

import subprocess
import sys
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent.parent


def _versione_attesa():
    testo = (RADICE / "plancia" / "__init__.py").read_text(encoding="utf-8")
    import re
    m = re.search(r'__version__\s*=\s*"([^"]+)"', testo)
    return m.group(1) if m else None


def _lancia(argv):
    return subprocess.run(argv, cwd=str(RADICE), capture_output=True, text=True)


def esegui(prova):
    attesa = _versione_attesa()
    prova("plancia/__init__.py dichiara __version__", attesa is not None)
    if not attesa:
        return

    esito_modulo = _lancia([sys.executable, "-m", "plancia.cli", "--version"])
    prova("python3 -m plancia.cli --version esce 0",
          esito_modulo.returncode == 0,
          f"codice {esito_modulo.returncode}: {esito_modulo.stderr.strip()}")
    prova("python3 -m plancia.cli --version stampa plancia.__version__",
          attesa in esito_modulo.stdout, esito_modulo.stdout.strip())

    esito_bin = _lancia([sys.executable, str(RADICE / "bin" / "plancia"), "--version"])
    prova("bin/plancia --version esce 0",
          esito_bin.returncode == 0,
          f"codice {esito_bin.returncode}: {esito_bin.stderr.strip()}")
    prova("bin/plancia --version stampa plancia.__version__",
          attesa in esito_bin.stdout, esito_bin.stdout.strip())

    # Il sottocomando resta obbligatorio quando non si chiede la versione:
    # la correzione non deve allargare la guardia, solo aprire --version.
    esito_senza = _lancia([sys.executable, "-m", "plancia.cli"])
    prova("senza sottocomando e senza --version, plancia esce ancora con errore",
          esito_senza.returncode != 0, f"codice {esito_senza.returncode}")
