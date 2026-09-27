#!/bin/bash
# Prepara una release di Plancia: compila, firma, notarizza, impacchetta.
#
#   ./tools/rilascia.sh 0.3.0
#
# Senza certificato fa comunque tutto il resto e te lo dice: il DMG esce non
# firmato, buono per provarlo, non per venderlo.
#
# Cosa serve per la parte firmata, una volta sola:
#   1. iscrizione all'Apple Developer Program
#   2. un certificato "Developer ID Application" nel portachiavi
#   3. una password per app su appleid.apple.com, messa nel portachiavi con:
#        xcrun notarytool store-credentials plancia-notarizzazione \
#          --apple-id TUA@MAIL --team-id ILTUOTEAMID --password xxxx-xxxx-xxxx-xxxx
#
# Le variabili che puoi impostare:
#   FIRMA    il nome esatto del certificato (default: il primo Developer ID Application)
#   PROFILO  il nome del profilo notarytool (default: plancia-notarizzazione)

set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"

VERSIONE="${1:-}"
if [ -z "$VERSIONE" ]; then
  echo "uso: ./tools/rilascia.sh <versione>   (esempio: 0.3.0)" >&2
  exit 1
fi

PROFILO="${PROFILO:-plancia-notarizzazione}"
FUORI="$ROOT/dist"
APP="$ROOT/mac/build/Plancia.app"
DMG="$FUORI/Plancia-$VERSIONE.dmg"

echo "==> versione $VERSIONE"

# 1. la versione sta scritta in tre file (mac/build.sh, plancia/__init__.py,
#    pyproject.toml, controllati insieme da tools/prove/sito.py): qui si
#    propaga a tutti e tre, cosi' non resta mai un numero indietro.
sed -i '' "s/^VERSIONE=\".*\"/VERSIONE=\"$VERSIONE\"/" mac/build.sh
python3 - "$VERSIONE" <<'PY'
import io, re, sys
v = sys.argv[1]
p = "plancia/__init__.py"
try:
    s = io.open(p, encoding="utf-8").read()
except OSError:
    s = ""
if "__version__" in s:
    s = re.sub(r'__version__ = ".*"', f'__version__ = "{v}"', s)
else:
    s = (s.rstrip() + f'\n\n__version__ = "{v}"\n').lstrip()
io.open(p, "w", encoding="utf-8").write(s)

p = "pyproject.toml"
s = io.open(p, encoding="utf-8").read()
s = re.sub(r'(?m)^version\s*=\s*".*"', f'version = "{v}"', s, count=1)
io.open(p, "w", encoding="utf-8").write(s)
print(f"    plancia/__init__.py -> {v}")
PY

# 2. i controlli che non costano niente e che ti salvano una release
echo "==> controlli"
python3 -m compileall -q plancia >/dev/null
node --check web/app.js 2>/dev/null || echo "    (node non c'è, salto il controllo di app.js)"
python3 tools/prova.py || { echo "il collaudo non passa: non si rilascia" >&2; exit 1; }

# 3. la app
echo "==> compilo"
./mac/build.sh >/dev/null
mkdir -p "$FUORI"

# 4. firma
# Il `|| true` serve: senza certificati `grep` esce con 1, e con `set -e` la
# release si fermava qui, subito dopo aver compilato e senza dire perché.
CERT="${FIRMA:-$(security find-identity -v -p codesigning 2>/dev/null \
  | grep "Developer ID Application" | head -1 | sed -E 's/.*"(.*)"/\1/' || true)}"

if [ -n "$CERT" ]; then
  echo "==> firmo con: $CERT"
  # --options runtime serve alla notarizzazione; senza, Apple rifiuta
  codesign --force --deep --options runtime --timestamp \
           --entitlements mac/Plancia.entitlements \
           --sign "$CERT" "$APP"
  codesign --verify --strict --verbose=2 "$APP"
else
  echo "==> nessun certificato Developer ID: salto firma e notarizzazione"
fi

# 5. il DMG
echo "==> impacchetto"
STAGE="$(mktemp -d)"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
rm -f "$DMG"
hdiutil create -volname "Plancia" -srcfolder "$STAGE" -ov -format ULFO "$DMG" >/dev/null
rm -rf "$STAGE"

# 6. notarizzazione: si manda il DMG, si aspetta, si grappa l'esito dentro
if [ -n "$CERT" ]; then
  codesign --force --sign "$CERT" --timestamp "$DMG"
  echo "==> notarizzo (ci vogliono alcuni minuti)"
  if xcrun notarytool submit "$DMG" --keychain-profile "$PROFILO" --wait; then
    xcrun stapler staple "$DMG"
    xcrun stapler validate "$DMG"
    echo "==> notarizzato e grappato"
  else
    echo "!! notarizzazione fallita: xcrun notarytool log <id> --keychain-profile $PROFILO" >&2
  fi
fi

# 7. l'impronta da pubblicare accanto al file
shasum -a 256 "$DMG" | tee "$DMG.sha256"

echo
echo "pronto: $DMG"
echo
echo "poi:"
echo "  git tag v$VERSIONE && git push origin v$VERSIONE"
echo "  gh release create v$VERSIONE '$DMG' '$DMG.sha256' --notes-file docs/note-$VERSIONE.md"
