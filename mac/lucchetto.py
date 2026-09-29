#!/usr/bin/env python3
"""Esegue un comando tenendo un lucchetto: uso `lucchetto.py <file> <comando...>`.

Serve a non far partire due swiftc insieme (piu' agenti, o due terminali, sulla stessa
macchina): la seconda compilazione aspetta la prima, invece di consumare la memoria in
due. Il lucchetto e' un flock sul file, quindi lo rilascia il sistema anche se il
processo muore.
"""
import fcntl
import subprocess
import sys

with open(sys.argv[1], "w") as f:
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("  (un altro swiftc e' in corso, aspetto il mio turno)", flush=True)
        fcntl.flock(f, fcntl.LOCK_EX)
    sys.exit(subprocess.call(sys.argv[2:]))
