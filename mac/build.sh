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
VERSIONE="2.0.0"
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

# Poco spazio libero: swiftc scrive file temporanei grandi e a meta' strada il disco si
# riempie senza dire niente. Sotto 1 GB ci si ferma e lo si dice.
LIBERO_KB="$(df -k "$ROOT" | awk 'NR==2 {print $4}')"
if [ "${LIBERO_KB:-0}" -lt 1048576 ]; then
  echo "Spazio libero insufficiente: $((LIBERO_KB / 1024)) MB, ne servono almeno 1024." >&2
  exit 1
fi

# Tutti i sorgenti sotto mac/Sources, ricorsivamente. Ogni cartella ha un compito:
# Core (modelli, cliente, store, lingua), Guscio (finestra, menu, impostazioni),
# Sistema (server, barra dei menu, plancia://, voce), Viste (una per sezione).
# swiftc rifiuta due file con lo stesso nome anche in cartelle diverse.
SORGENTI=()
while IFS= read -r f; do SORGENTI+=("$f"); done < <(find "$ROOT/mac/Sources" -name '*.swift' | sort)
if [ "${#SORGENTI[@]}" -eq 0 ]; then
  echo "Nessun sorgente in mac/Sources" >&2
  exit 1
fi

# Un lucchetto intorno a swiftc: due compilazioni insieme (piu' agenti sulla stessa
# macchina, o due terminali) esauriscono la memoria. Chi arriva dopo aspetta.
# Lo stesso file per tutti (build.sh e tools/prova-mac.sh); PLANCIA_LUCCHETTO lo sposta.
LUCCHETTO="${PLANCIA_LUCCHETTO:-/tmp/plancia-swiftc-$(id -u).lock}"
mkdir -p "$(dirname "$LUCCHETTO")"
OTTIMIZZAZIONE="-O -whole-module-optimization"
[ "${PLANCIA_SENZA_OTTIMIZZAZIONE:-0}" = "1" ] && OTTIMIZZAZIONE="-Onone"

echo "· compilo (${#SORGENTI[@]} file)"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
python3 "$ROOT/mac/lucchetto.py" "$LUCCHETTO" xcrun swiftc \
  -swift-version 5 \
  -parse-as-library \
  $OTTIMIZZAZIONE \
  -target "$(uname -m)-apple-macosx26.0" \
  -o "$APP/Contents/MacOS/$NOME" \
  "${SORGENTI[@]}"

echo "· icona"
# Due strade, nell'ordine.
#  1. Liquid Glass (macOS 26+): mac/icona/Plancia.icon e' un documento di Icon
#     Composer (quattro strati PNG: legno, ottone, quadrante e leva, con il vetro di
#     sistema su tre). actool 26 o piu' recente lo compila in Assets.car +
#     Plancia.icns, e il sistema applica vetro, riflessi e profondita' strato per
#     strato, anche nelle versioni scura, "tinted" e "clear".
#     Il manifesto porta CFBundleIconName (per Assets.car: da macOS 13 in su,
#     con CFBundleIconName, il sistema legge quello, e ci sono le Icon Image
#     appiattite) e CFBundleIconFile (per l'icns di actool, che arriva solo a
#     256 px: e' un ripiego per gli strumenti che leggono l'icns direttamente).
#  2. Ripiego: un Mac senza Xcode 26+, o con un actool che rifiuta il .icon,
#     costruisce l'iconset dalla PNG committata mac/icona/Plancia-1024.png, che e'
#     la resa di ictool dello stesso .icon (si rifa' con mac/icona/ripiego.py):
#     sips la riduce alle dieci misure dell'iconset e `iconutil` la trasforma in
#     icns. E' la stessa icona per costruzione, senza un secondo disegno da tenere
#     allineato. Il manifesto porta solo CFBundleIconFile.
#  Se falliscono tutte e due, l'app resta senza icona propria e si costruisce lo stesso.
#  site/img/icon.png (apple-touch-icon del sito) e il favicon e il marchio delle
#  pagine NON li produce questo script: si rifanno con mac/icona/pagine.py quando
#  cambia il segno (icon.png e' RGB 512x512 senza alfa; tools/prove-front/icona.py
#  controlla che ci siano e che siano quelli).
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
     --platform macosx --target-device mac --minimum-deployment-target 26.0 \
     --app-icon Plancia --include-all-app-icons --enable-on-demand-resources NO \
     --development-region en \
     --output-partial-info-plist "$ICONA_TMP/parziale.plist" >/dev/null 2>&1 && \
   [ -f "$ICONA_TMP/Assets.car" ] && [ -f "$ICONA_TMP/Plancia.icns" ]; then
  cp "$ICONA_TMP/Assets.car" "$ICONA_TMP/Plancia.icns" "$APP/Contents/Resources/"
  ICONA="<key>CFBundleIconFile</key><string>Plancia</string><key>CFBundleIconName</key><string>Plancia</string>"
  echo "  (Liquid Glass: Assets.car + icns da mac/icona/Plancia.icon)"
else
  if [ -d "$ICONA_SRC" ] && [ "${ACTOOL_MAGGIORE:-0}" -ge 26 ] 2>/dev/null; then
    echo "  (actool non ha compilato il .icon: uso la PNG di ripiego)"
  else
    echo "  (serve Xcode 26 o piu' recente per il Liquid Glass: uso la PNG di ripiego)"
  fi
  ICONSET="$BUILD/Plancia.iconset"
  RIPIEGO="$ROOT/mac/icona/Plancia-1024.png"
  rm -rf "$ICONSET"
  mkdir -p "$ICONSET"
  iconset_ok=1
  [ -f "$RIPIEGO" ] || iconset_ok=0
  # pixel:nome nell'iconset (le misure @2x sono il doppio della misura base)
  for coppia in 16:16x16 32:16x16@2x 32:32x32 64:32x32@2x 128:128x128 256:128x128@2x \
                256:256x256 512:256x256@2x 512:512x512 1024:512x512@2x; do
    [ "$iconset_ok" = "1" ] || break
    px="${coppia%%:*}"
    nome="${coppia#*:}"
    sips -z "$px" "$px" "$RIPIEGO" --out "$ICONSET/icon_$nome.png" >/dev/null 2>&1 || iconset_ok=0
  done
  if [ "$iconset_ok" = "1" ] && \
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
  <key>LSMinimumSystemVersion</key><string>26.0</string>
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
