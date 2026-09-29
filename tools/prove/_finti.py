"""Materiale di supporto per le prove che lanciano processi: non e' una prova.

Comincia con `_`, quindi `tools/prova.py` non lo scopre. Un modulo lo importa cosi':

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import _finti

Raccoglie le tre cose che cambiano da un sistema all'altro quando una prova
costruisce un ambiente finto per un processo figlio:

- dove sta la casa di un processo (`HOME` su macOS e Linux, `USERPROFILE` su
  Windows: `Path.home()` di Python su Windows ignora `HOME`);
- come si compone un `PATH` (i due punti su POSIX, il punto e virgola su Windows,
  dove inoltre servono le cartelle di sistema perche' `git` e `python` restino
  raggiungibili);
- come si scrive un programma finto che `subprocess` sa lanciare: su macOS e Linux
  un file con lo shebang, su Windows uno script `.cmd` (uno script senza estensione
  non si esegue: WinError 193).

Su macOS e Linux ogni funzione qui torna esattamente quello che le prove
scrivevano a mano prima: non cambia niente di quello che si prova li'.
"""

import os
import sys
from pathlib import Path

#: Si gira su Windows davvero (non solo con `PLANCIA_PIATTAFORMA=windows`).
WIN = os.name == "nt"

#: Le variabili senza le quali un Python figlio su Windows non parte o non trova
#: niente (`SYSTEMROOT` manca -> "failed to get random numbers"): si copiano da
#: chi lancia in un ambiente costruito da zero.
_DI_SISTEMA_WINDOWS = ("SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "PATHEXT",
                       "TEMP", "TMP", "PROCESSOR_ARCHITECTURE", "NUMBER_OF_PROCESSORS")


def casa_finta(env: dict, casa) -> dict:
    """Sposta la casa di `env` su `casa`. Su macOS e Linux e' solo `HOME`. Su
    Windows anche `USERPROFILE`, `HOMEDRIVE`/`HOMEPATH` e le due cartelle dei dati
    dell'applicazione, che stanno sotto la casa."""
    casa = str(casa)
    env["HOME"] = casa
    if WIN:
        unita, resto = os.path.splitdrive(casa)
        env["USERPROFILE"] = casa
        env["HOMEDRIVE"] = unita
        env["HOMEPATH"] = resto or "\\"
        env["APPDATA"] = os.path.join(casa, "AppData", "Roaming")
        env["LOCALAPPDATA"] = os.path.join(casa, "AppData", "Local")
    return env


def variabili_di_sistema(env: dict) -> dict:
    """Su Windows aggiunge a un ambiente costruito da zero le variabili che un
    processo figlio si aspetta di trovare. Su macOS e Linux non fa niente."""
    if WIN:
        for nome in _DI_SISTEMA_WINDOWS:
            if nome in os.environ:
                env.setdefault(nome, os.environ[nome])
    return env


def path_con(*davanti, minimo: str = "/usr/bin:/bin:/usr/sbin:/sbin") -> str:
    """Un `PATH` con `davanti` in testa. Su macOS e Linux le cartelle di sistema
    in `minimo` (com'e' sempre stato: il `claude` vero, altrove, non si trova).
    Su Windows il `PATH` di chi lancia: senza, il processo figlio non troverebbe
    `git` ne' le DLL di sistema; un programma finto davanti vince comunque sul
    vero, perche' la ricerca scorre le cartelle nell'ordine."""
    resto = os.environ.get("PATH", "") if WIN else minimo
    return os.pathsep.join([str(d) for d in davanti] + ([resto] if resto else []))


def sorgente_python_finto(sorgente: str) -> str:
    """Il testo di un programma finto scritto in Python: sempre lo stesso su ogni
    sistema, con la riga dello shebang che a Windows non serve e non nuoce."""
    interprete = sys.executable if " " not in sys.executable else "/usr/bin/env python3"
    return "#!%s\n%s" % (interprete, sorgente.lstrip("\n"))


def crea_finto(cartella, nome: str, sorgente: str) -> str:
    """Un programma finto che `subprocess` lancia da solo, scritto in Python
    (la stessa logica su ogni sistema). Torna il percorso da mettere nell'argv, o
    da dare a `PLANCIA_TERMINALE`.

    macOS e Linux: un file `nome` con lo shebang e il permesso di esecuzione.
    Windows: `nome.py` piu' `nome.cmd`, che lo lancia con questo stesso
    interprete e gli passa gli argomenti cosi' come arrivano. Il programma sta in
    una cartella SUA, che `crea_finto` non cancella: la cancella chi l'ha data."""
    cartella = Path(cartella)
    cartella.mkdir(parents=True, exist_ok=True)
    if WIN:
        py = cartella / (nome + ".py")
        py.write_text(sorgente.lstrip("\n"), encoding="utf-8")
        cmd = cartella / (nome + ".cmd")
        cmd.write_bytes(('@echo off\r\n"%s" "%s" %%*\r\n' % (sys.executable, py))
                        .encode("utf-8"))
        return str(cmd)
    percorso = cartella / nome
    percorso.write_text(sorgente_python_finto(sorgente), encoding="utf-8")
    percorso.chmod(0o755)
    return str(percorso)
