#!/bin/bash
# Costruisce Plancia.app. Serve solo Xcode, niente progetto e niente pacchetti.
#
#   ./mac/build.sh              costruisce in mac/build
#   ./mac/build.sh --install    e la copia in /Applications
#   ./mac/build.sh --run        la costruisce e la apre

set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
BUILD="$ROOT/mac/build"
APP="$BUILD/Plancia.app"
NOME="Plancia"
VERSIONE="1.1.0"
BUNDLE_ID="sh.plancia.app"

installa=0
esegui=0
for arg in "$@"; do
  case "$arg" in
    --install) installa=1 ;;
    --run) esegui=1 ;;
  esac
done

if ! xcrun --find swiftc >/dev/null 2>&1; then
  echo "Serve Xcode o gli strumenti da riga di comando: xcode-select --install" >&2
  exit 1
fi

echo "· compilo"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
xcrun swiftc \
  -swift-version 5 \
  -O -whole-module-optimization \
  -target "$(uname -m)-apple-macosx13.0" \
  -o "$APP/Contents/MacOS/$NOME" \
  "$ROOT/mac/Sources/main.swift" "$ROOT/mac/Sources/jarvis.swift"

echo "· icona"
ICONSET="$BUILD/Plancia.iconset"
rm -rf "$ICONSET"
if xcrun swift "$ROOT/mac/makeicon.swift" "$ICONSET" >/dev/null 2>&1 && \
   iconutil -c icns "$ICONSET" -o "$APP/Contents/Resources/Plancia.icns" 2>/dev/null; then
  ICONA="<key>CFBundleIconFile</key><string>Plancia</string>"
else
  echo "  (icona non generata, l'app userà quella di sistema)"
  ICONA=""
fi
rm -rf "$ICONSET"

echo "· manifesto"
cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>$NOME</string>
  <key>CFBundleDisplayName</key><string>$NOME</string>
  <key>CFBundleExecutable</key><string>$NOME</string>
  <key>CFBundleIdentifier</key><string>$BUNDLE_ID</string>
  <key>CFBundleShortVersionString</key><string>$VERSIONE</string>
  <key>CFBundleVersion</key><string>$VERSIONE</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>LSMinimumSystemVersion</key><string>13.0</string>
  <key>NSHighResolutionCapable</key><true/>
  $ICONA
  <key>PlanciaExecutable</key><string>$ROOT/bin/plancia</string>
  <key>NSMicrophoneUsageDescription</key>
  <string>Per farti fare domande a voce sul tuo lavoro.</string>
  <key>NSSpeechRecognitionUsageDescription</key>
  <string>Per capire le domande che fai a voce. Il riconoscimento resta sul Mac.</string>
  <key>CFBundleURLTypes</key>
  <array>
    <dict>
      <key>CFBundleURLName</key><string>$BUNDLE_ID</string>
      <key>CFBundleURLSchemes</key><array><string>plancia</string></array>
    </dict>
  </array>
  <key>NSAppTransportSecurity</key>
  <dict>
    <key>NSExceptionDomains</key>
    <dict>
      <key>127.0.0.1</key>
      <dict>
        <key>NSExceptionAllowsInsecureHTTPLoads</key><true/>
        <key>NSIncludesSubdomains</key><true/>
      </dict>
      <key>localhost</key>
      <dict>
        <key>NSExceptionAllowsInsecureHTTPLoads</key><true/>
      </dict>
    </dict>
  </dict>
</dict>
</plist>
PLIST

# La firma decide anche i permessi. macOS lega il consenso a microfono e
# dettatura all'identità con cui l'app è firmata: con la firma ad hoc l'impronta
# cambia a ogni compilazione, quindi il sistema li richiede da capo ogni volta e
# Jarvis riparte muto. Se in portachiavi c'è un certificato stabile (Developer
# ID, o uno auto firmato che ti sei fatto e chiamato Plancia) si usa quello, e il
# consenso resta dato.
# Il `|| true` non è pigrizia: senza certificati `grep` esce con 1 e con
# `set -e` la compilazione si fermerebbe proprio dove non serve.
FIRMA="${FIRMA:-$(security find-identity -v -p codesigning 2>/dev/null \
  | grep -E "Developer ID Application|Plancia" | head -1 | sed -E 's/.*"(.*)"/\1/' || true)}"

if [ -n "$FIRMA" ]; then
  echo "· firma: $FIRMA"
  codesign --force --deep --options runtime --timestamp \
           --entitlements "$ROOT/mac/Plancia.entitlements" \
           --sign "$FIRMA" "$APP" 2>/dev/null || \
    codesign --force --deep --sign "$FIRMA" "$APP" 2>/dev/null || \
    echo "  (firma non riuscita)"
else
  echo "· firma locale, ad hoc"
  echo "  i permessi del microfono verranno richiesti a ogni ricompilazione:"
  echo "  per non ripeterli:  ./tools/certificato.sh"
  codesign --force --deep --sign - "$APP" 2>/dev/null || \
    echo "  (firma non riuscita, l'app funziona lo stesso in locale)"
fi

echo "· fatto: $APP"

if [ "$installa" = "1" ]; then
  DEST="/Applications/Plancia.app"
  if [ -w /Applications ]; then
    rm -rf "$DEST" && cp -R "$APP" "$DEST" && echo "· installata in $DEST"
  else
    DEST="$HOME/Applications/Plancia.app"
    mkdir -p "$HOME/Applications"
    rm -rf "$DEST" && cp -R "$APP" "$DEST" && echo "· installata in $DEST"
  fi
  APP="$DEST"
fi

if [ "$esegui" = "1" ]; then
  open "$APP"
fi
