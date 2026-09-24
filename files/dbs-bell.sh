#!/bin/bash
# ==============================================================================
# dbsKioskPi - Schulglocken- und Audio-Wiedergabeskript
# ==============================================================================

set -euo pipefail

SOUNDS_DIR="/var/lib/dbskiosk/sounds"
DEFAULT_BELL="$SOUNDS_DIR/bell.mp3"
FALLBACK_BELL="$SOUNDS_DIR/default_chime.wav"
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

# ALSA-Mixer entmuten (HDMI IEC958 und Master/PCM Lautstärke)
unmute_alsa() {
    if command -v amixer >/dev/null 2>&1; then
        amixer -c vc4hdmi0 sset 'IEC958' on >/dev/null 2>&1 || true
        amixer -c vc4hdmi1 sset 'IEC958' on >/dev/null 2>&1 || true
        amixer sset 'PCM' unmute 100% >/dev/null 2>&1 || true
        amixer sset 'Master' unmute 100% >/dev/null 2>&1 || true
        amixer sset 'Headphone' unmute 100% >/dev/null 2>&1 || true
    fi
}

# Generiert bei Bedarf automatisch einen melodischen 2-Ton-Gong (WAV, 48kHz Stereo)
ensure_fallback_sound() {
    mkdir -p "$SOUNDS_DIR"
    if [ ! -f "$FALLBACK_BELL" ] && [ ! -f "$DEFAULT_BELL" ]; then
        if command -v python3 >/dev/null 2>&1; then
            python3 -c "
import wave, math, struct
tones = [(659.25, 0.7), (523.25, 1.1)]
sample_rate = 48000
frames = []
for freq, dur in tones:
    n = int(sample_rate * dur)
    for i in range(n):
        t = i / sample_rate
        env = math.exp(-3.5 * t / dur)
        val = (0.8 * math.sin(2 * math.pi * freq * t) + 0.2 * math.sin(2 * math.pi * freq * 2 * t)) * env
        s = int(val * 32767 * 0.85)
        frames.append((s, s))
with wave.open('$FALLBACK_BELL', 'wb') as wf:
    wf.setnchannels(2)
    wf.setsampwidth(2)
    wf.setframerate(sample_rate)
    for l, r in frames:
        wf.writeframes(struct.pack('<hh', l, r))
" >/dev/null 2>&1 || true
        fi
    fi
}

# Sichere Wiedergabe mit Soundkarten-Auswahl & Fallback
play_audio_file() {
    local file="$1"
    local gain="${2:-}"
    local dev="${AUDIO_DEVICE:-default}"
    
    unmute_alsa

    # Wenn es eine WAV-Datei ist: Zuerst per aplay versuchen (Standard für ALSA)
    if [[ "$file" == *.wav ]] && command -v aplay >/dev/null 2>&1; then
        local -a aplay_opts=("-q")
        if [ -n "$dev" ] && [ "$dev" != "default" ]; then
            aplay_opts+=("-D" "$dev")
        fi
        aplay_opts+=("$file")
        if aplay "${aplay_opts[@]}" 2>/dev/null; then
            return 0
        fi
    fi

    # mpg123: Explizit ALSA-Treiber und 48kHz Stereo Resampling (vom HDMI-Treiber verlangt)
    if command -v mpg123 >/dev/null 2>&1; then
        local -a mpg_opts=("-q" "-o" "alsa" "--stereo" "-r" "48000")
        if [ -n "$gain" ]; then
            mpg_opts+=("-f" "$gain")
        fi
        if [ -n "$dev" ] && [ "$dev" != "default" ]; then
            mpg_opts+=("-a" "$dev")
        fi
        mpg_opts+=("$file")
        
        # 1. Versuch: Mit gewähltem Device & Resampling
        if mpg123 "${mpg_opts[@]}" 2>/dev/null; then
            return 0
        fi

        # 2. Versuch: mpg123 mit Standard-ALSA Treiber
        if mpg123 -q -o alsa "$file" 2>/dev/null; then
            return 0
        fi

        # 3. Versuch: mpg123 Standard
        mpg123 -q "$file" 2>/dev/null || true
    fi
}

case "$ACTION" in
    play)
        ensure_fallback_sound
        GAIN=$(calculate_gain "$VOLUME")
        if [ -f "$BELL_FILE" ]; then
            echo "[Audio] Spiele Schulglocke: $BELL_FILE (Lautstärke: ${VOLUME}%, Ausgang: ${AUDIO_DEVICE})..."
            play_audio_file "$BELL_FILE" "$GAIN"
        elif [ -f "$FALLBACK_BELL" ]; then
            echo "[Audio] Keine eigene MP3 vorhanden - spiele Standard-Gong: $FALLBACK_BELL (Lautstärke: ${VOLUME}%, Ausgang: ${AUDIO_DEVICE})..."
            play_audio_file "$FALLBACK_BELL" "$GAIN"
        else
            echo "[Audio] Keine Sounddatei gefunden. Spiele synthetischen Testton auf Ausgang: ${AUDIO_DEVICE}..."
            unmute_alsa
            local dev="${AUDIO_DEVICE:-default}"
            if command -v speaker-test >/dev/null 2>&1; then
                if [ -n "$dev" ] && [ "$dev" != "default" ]; then
                    speaker-test -D "$dev" -c 2 -r 48000 -t sine -f 880 -l 1 >/dev/null 2>&1 || speaker-test -t sine -f 880 -l 1 >/dev/null 2>&1 || true
                else
                    speaker-test -t sine -f 880 -l 1 >/dev/null 2>&1 || true
                fi
            else
                echo -e "\a"
            fi
        fi
        ;;
    test)
        echo "[Audio] Teste Audioausgabe (Ausgang: ${AUDIO_DEVICE})..."
        ensure_fallback_sound
        if [ -f "$BELL_FILE" ]; then
            play_audio_file "$BELL_FILE" ""
        elif [ -f "$FALLBACK_BELL" ]; then
            play_audio_file "$FALLBACK_BELL" ""
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
        elif [ -f "$FALLBACK_BELL" ]; then
            echo "Status: Standard-Gong vorhanden ($(du -h "$FALLBACK_BELL" | cut -f1))"
        else
            echo "Status: Keine Datei vorhanden (wird automatisch erzeugt)"
        fi
        echo "Standard-Lautstärke: ${DEFAULT_VOLUME}%"
        echo "Audioausgang (Gerät): ${AUDIO_DEVICE:-default}"
        ;;
    *)
        echo "Verwendung: $0 {play [volume]|test|devices|set <pfad_zu_mp3>|status}"
        exit 1
        ;;
esac
