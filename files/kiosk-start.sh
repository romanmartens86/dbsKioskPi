#!/bin/bash
# ==============================================================================
# dbsKioskPi - Kiosk Startup Script (Cage + Chromium)
# ==============================================================================

set -u

# Wayland / wlroots Optimierung für Raspberry Pi
export WLR_SCENE_DISABLE_DIRECT_SCANOUT=1

# Mauszeiger auf Wayland / wlroots vollständig unsichtbar machen
export XCURSOR_THEME=""
export XCURSOR_SIZE=0

# Lade Konfiguration, falls vorhanden
CONFIG_FILE="/etc/dbskiosk/kiosk.conf"
if [ -f "$CONFIG_FILE" ]; then
    # shellcheck disable=SC1090
    source "$CONFIG_FILE"
fi

# Fallback-URL falls nicht konfiguriert
TARGET_URL="${KIOSK_URL:-https://dbs.edupage.org/infoscreen/7?scaletowidth=1920}"
EXTRA_FLAGS="${EXTRA_CHROMIUM_FLAGS:-}"

# Prüfe verfügbare Chromium-Binary
if command -v chromium >/dev/null 2>&1; then
    BROWSER_BIN="chromium"
elif command -v chromium-browser >/dev/null 2>&1; then
    BROWSER_BIN="chromium-browser"
else
    echo "FEHLER: Weder 'chromium' noch 'chromium-browser' wurde gefunden!" >&2
    exit 1
fi

# Bereite Cache- und Profildirektorien im RAM / tmp vor
CACHE_DIR="/tmp/chromium-cache"
PROFILE_DIR="${HOME:-/tmp}/.config/dbskiosk-browser"
mkdir -p "$CACHE_DIR" "$PROFILE_DIR"

# Verhindere 'Wiederherstellen'-Meldungen nach unsauberem Herunterfahren
if [ -f "$PROFILE_DIR/Default/Preferences" ]; then
    sed -i -E 's/"exit_type":"[^"]*"/"exit_type":"Normal"/' "$PROFILE_DIR/Default/Preferences" 2>/dev/null || true
    sed -i -E 's/"exited_cleanly":false/"exited_cleanly":true/' "$PROFILE_DIR/Default/Preferences" 2>/dev/null || true
fi

# Zusammengestellte Chromium-Flags
CHROMIUM_ARGS=(
    "--kiosk"
    "--noerrdialogs"
    "--disable-infobars"
    "--no-first-run"
    "--ozone-platform=wayland"
    "--enable-features=OverlayScrollbar"
    "--autoplay-policy=no-user-gesture-required"
    "--check-for-update-interval=31536000"
    "--disk-cache-dir=$CACHE_DIR"
    "--disk-cache-size=33554432"
    "--user-data-dir=$PROFILE_DIR"
    "--disable-translate"
    "--disable-features=Translate"
    "--disable-component-update"
    "--password-store=basic"
    "--touch-events=enabled"
    "--disable-pinch"
)

# Optionale zusätzliche Benutzer-Flags anhängen
if [ -n "$EXTRA_FLAGS" ]; then
    # shellcheck disable=SC2206
    CHROMIUM_ARGS+=($EXTRA_FLAGS)
fi

# Cage Wayland Compositor starten mit automatischem Ausblenden des Mauszeigers (-d)
echo "Starte Kiosk mit Cage und $BROWSER_BIN auf URL: $TARGET_URL"
exec cage -d -- "$BROWSER_BIN" "${CHROMIUM_ARGS[@]}" "$TARGET_URL"
