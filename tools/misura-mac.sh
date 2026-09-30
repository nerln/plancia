#!/bin/bash
# Misura quanto tempo il thread principale dell'app Mac resta occupato (vedi
# mac/Sources/Core/Misura.swift): cambio di sezione, ricarica, scrittura, ricerca, ciclo di
# sottofondo. Costruisce l'app, la apre in modalita' --misura contro il server di prova e
# stampa la tabella.
#
#   PLANCIA_HOME=<casa di prova> HOME=<casa finta> CLAUDE_CONFIG_DIR=<...> CODEX_HOME=<...> \
#       ./tools/misura-mac.sh [--senza-build] [file-json-di-uscita]
#
# La casa di prova si prepara con tools/demo-data.py e tools/dati-grandi.py, il server con
# `bin/plancia serve --port <porta> --no-sync`, e la porta va scritta in
# $PLANCIA_HOME/config.json (chiave "port"). Lo script non avvia il server e si rifiuta di
# partire senza le quattro variabili o con PLANCIA_HOME sull'archivio vero.
set -euo pipefail

if [ "$(uname)" != "Darwin" ] || ! xcrun --find swiftc >/dev/null 2>&1; then
  echo "saltato: serve macOS con Xcode"
  exit 0
fi

RADICE="$(cd "$(dirname "$0")/.." && pwd)"
for v in PLANCIA_HOME HOME CLAUDE_CONFIG_DIR CODEX_HOME; do
  if [ -z "${!v:-}" ]; then
    echo "manca $v: per non toccare l'archivio vero servono tutte e quattro (vedi l'intestazione)" >&2
    exit 2
  fi
done
VERA="$(python3 -c 'import os, pwd; print(os.path.realpath(os.path.join(pwd.getpwuid(os.getuid()).pw_dir, ".plancia")))')"
if [ "$(python3 -c 'import os, sys; print(os.path.realpath(os.path.expanduser(sys.argv[1])))' "$PLANCIA_HOME")" = "$VERA" ]; then
  echo "PLANCIA_HOME e' l'archivio vero: mi fermo" >&2
  exit 2
fi

SENZA_BUILD=0
USCITA=""
for a in "$@"; do
  case "$a" in
    --senza-build) SENZA_BUILD=1 ;;
    *) USCITA="$a" ;;
  esac
done

PORTA="$(python3 -c 'import json, os; print(json.load(open(os.path.join(os.environ["PLANCIA_HOME"], "config.json"))).get("port", ""))')"
if [ -z "$PORTA" ] || [ "$PORTA" = "7773" ]; then
  echo "in $PLANCIA_HOME/config.json manca la porta di prova (mai la 7773)" >&2
  exit 2
fi
curl -fs -o /dev/null "http://127.0.0.1:$PORTA/api/status" || {
  echo "il server di prova non risponde sulla porta $PORTA" >&2
  exit 1
}

if [ "$SENZA_BUILD" != "1" ]; then
  "$RADICE/mac/build.sh" >/dev/null
fi

ARGS=(--misura)
[ -n "$USCITA" ] && ARGS+=(--misura-out "$USCITA")
"$RADICE/mac/build/Plancia.app/Contents/MacOS/Plancia" "${ARGS[@]}"
