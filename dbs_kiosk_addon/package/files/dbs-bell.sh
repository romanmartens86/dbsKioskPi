#!/bin/bash
# ==============================================================================
# dbsKioskPi - Schulglocken- und Audio-Wiedergabeskript
# ==============================================================================

set -euo pipefail

SOUNDS_DIR="/var/lib/dbskiosk/sounds"
DEFAULT_BELL="$SOUNDS_DIR/bell.mp3"
CONFIG_FILE="/etc/dbskiosk/kiosk.conf"

if [ -f "$CONFIG_FILE" ]; then
    # shellcheck disable=SC1090
    source "$CONFIG_FILE"
fi

BELL_FILE="${BELL_SOUND_PATH:-$DEFAULT_BELL}"
DEFAULT_VOLUME="${BELL_VOLUME:-100}"
AUDIO_DEVICE="${AUDIO_DEVICE:-default}"

ACTION="${1:-play}"
VOLUME="${2:-$DEFAULT_VOLUME}"

# Lautstärkefaktor berechnen für mpg123 (Bereich: 1-100% -> scale 327 bis 32768)
calculate_gain() {
    local vol="$1"
    if [ "$vol" -lt 0 ]; then vol=0; fi
    if [ "$vol" -gt 100 ]; then vol=100; fi
    echo "$((vol * 327))"
}

# Sichere Wiedergabe mit optionaler Soundkarten-Auswahl
play_mp3() {
    local file="$1"
    local gain="${2:-}"
    local dev="${AUDIO_DEVICE:-default}"
    local -a mpg_opts=("-q")
    if [ -n "$gain" ]; then
        mpg_opts+=("-f" "$gain")
    fi
    if [ -n "$dev" ] && [ "$dev" != "default" ]; then
        mpg_opts+=("-a" "$dev")
    fi
    mpg_opts+=("$file")
    mpg123 "${mpg_opts[@]}" || mpg123 -q "$file"
}

case "$ACTION" in
    play)
        if [ -f "$BELL_FILE" ]; then
            GAIN=$(calculate_gain "$VOLUME")
            echo "[Audio] Spiele Schulglocke: $BELL_FILE (Lautstärke: ${VOLUME}%, Ausgang: ${AUDIO_DEVICE})..."
            play_mp3 "$BELL_FILE" "$GAIN"
        else
            echo "[Audio] Keine MP3-Glockendatei unter $BELL_FILE gefunden. Spiele synthetischen Testton..."
            if command -v speaker-test >/dev/null 2>&1; then
                speaker-test -t sine -f 880 -l 1 -p 500 >/dev/null 2>&1 || true
            else
                echo -e "\a"
            fi
        fi
        ;;
    test)
        echo "[Audio] Teste Audioausgabe (Ausgang: ${AUDIO_DEVICE})..."
        if [ -f "$BELL_FILE" ]; then
            play_mp3 "$BELL_FILE" ""
        else
            echo "Keine MP3 vorhanden. Bitte lade eine MP3 via Home Assistant oder 'dbs-bell set <datei>' hoch."
        fi
        ;;
    devices)
        echo "[Audio] Verfügbare Soundkarten & Wiedergabegeräte (aplay -l):"
        if command -v aplay >/dev/null 2>&1; then
            aplay -l 2>/dev/null || echo "Keine ALSA-Audiogeräte gefunden."
        else
            echo "aplay nicht installiert."
        fi
        echo ""
        echo "Aktuell ausgewählt: ${AUDIO_DEVICE:-default}"
        ;;
    set)
        NEW_SOUND="${2:-}"
        if [ -z "$NEW_SOUND" ] || [ ! -f "$NEW_SOUND" ]; then
            echo "FEHLER: Datei '$NEW_SOUND' nicht gefunden!" >&2
            exit 1
        fi
        mkdir -p "$SOUNDS_DIR"
        cp "$NEW_SOUND" "$DEFAULT_BELL"
        echo "[Audio] Neue Schulglocke erfolgreich unter $DEFAULT_BELL hinterlegt."
        ;;
    status)
        echo "Glockendatei: $BELL_FILE"
        if [ -f "$BELL_FILE" ]; then
            echo "Status: Datei existiert ($(du -h "$BELL_FILE" | cut -f1))"
        else
            echo "Status: Keine Datei vorhanden (wird synthetisch simuliert)"
        fi
        echo "Standard-Lautstärke: ${DEFAULT_VOLUME}%"
        echo "Audioausgang (Gerät): ${AUDIO_DEVICE:-default}"
        ;;
    *)
        echo "Verwendung: $0 {play [volume]|test|devices|set <pfad_zu_mp3>|status}"
        exit 1
        ;;
esac
