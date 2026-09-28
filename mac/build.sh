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
# Due strade, nell'ordine.
#  1. Liquid Glass (macOS 26+): mac/icona/Plancia.icon e' un documento di Icon
#     Composer (uno sfondo e due strati SVG). actool 26 o piu' recente lo compila
#     in Assets.car + Plancia.icns, e il sistema applica vetro, riflessi e
#     profondita' strato per strato, anche nelle versioni scura e "tinted".
#     Il manifesto porta CFBundleIconName (per Assets.car: da macOS 13 in su,
#     con CFBundleIconName, il sistema legge quello, e ci sono le Icon Image
#     appiattite) e CFBundleIconFile (per l'icns di actool, che arriva solo a
#     256 px: e' un ripiego per gli strumenti che leggono l'icns direttamente).
#  2. Ripiego: un Mac senza Xcode 26+, o con un actool che rifiuta il .icon,
#     disegna la stessa forma con un vetro imitato (mac/makeicon.swift) e la
#     trasforma in icns con `iconutil`. Il manifesto porta solo CFBundleIconFile.
#  Se falliscono tutte e due, l'app resta senza icona propria e si costruisce lo stesso.
ICONA_SRC="$ROOT/mac/icona/Plancia.icon"
ICONA_TMP="$BUILD/icona"
ICONA=""
rm -rf "$ICONA_TMP"
mkdir -p "$ICONA_TMP"

# La versione maggiore di actool, letta dal suo plist: "27.0" -> 27
ACTOOL_MAGGIORE="$(xcrun actool --version 2>/dev/null \
  | sed -n 's:.*<string>\([0-9][0-9]*\)\.[0-9.]*</string>.*:\1:p' | head -1 || true)"

if [ -d "$ICONA_SRC" ] && [ "${ACTOOL_MAGGIORE:-0}" -ge 26 ] 2>/dev/null && \
   xcrun actool "$ICONA_SRC" --compile "$ICONA_TMP" \
     --platform macosx --target-device mac --minimum-deployment-target 13.0 \
     --app-icon Plancia --include-all-app-icons --enable-on-demand-resources NO \
     --development-region en \
     --output-partial-info-plist "$ICONA_TMP/parziale.plist" >/dev/null 2>&1 && \
   [ -f "$ICONA_TMP/Assets.car" ] && [ -f "$ICONA_TMP/Plancia.icns" ]; then
  cp "$ICONA_TMP/Assets.car" "$ICONA_TMP/Plancia.icns" "$APP/Contents/Resources/"
  ICONA="<key>CFBundleIconFile</key><string>Plancia</string><key>CFBundleIconName</key><string>Plancia</string>"
  echo "  (Liquid Glass: Assets.car + icns da mac/icona/Plancia.icon)"
else
  if [ -d "$ICONA_SRC" ] && [ "${ACTOOL_MAGGIORE:-0}" -ge 26 ] 2>/dev/null; then
    echo "  (actool non ha compilato il .icon: uso l'icona disegnata a mano)"
  else
    echo "  (serve Xcode 26 o piu' recente per il Liquid Glass: uso l'icona disegnata a mano)"
  fi
  ICONSET="$BUILD/Plancia.iconset"
  rm -rf "$ICONSET"
  if xcrun swift "$ROOT/mac/makeicon.swift" "$ICONSET" >/dev/null 2>&1 && \
     iconutil -c icns "$ICONSET" -o "$APP/Contents/Resources/Plancia.icns" 2>/dev/null; then
    ICONA="<key>CFBundleIconFile</key><string>Plancia</string>"
  else
    echo "  (icona non generata, l'app userà quella di sistema)"
  fi
  rm -rf "$ICONSET"
fi
rm -rf "$ICONA_TMP"

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
