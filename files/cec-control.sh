#!/bin/bash
# ==============================================================================
# dbsKioskPi - HDMI-CEC Control Helper Script
# ==============================================================================

set -euo pipefail

CONFIG_FILE="/etc/dbskiosk/kiosk.conf"
if [ -f "$CONFIG_FILE" ]; then
    # shellcheck disable=SC1090
    source "$CONFIG_FILE"
fi

ACTION="${1:-}"

if [ "${CEC_ENABLED:-true}" != "true" ] && [ "$ACTION" != "force-on" ] && [ "$ACTION" != "force-off" ]; then
    echo "HDMI-CEC ist in $CONFIG_FILE deaktiviert. Überspringe Aktion."
    exit 0
fi

if ! command -v cec-client >/dev/null 2>&1; then
    echo "FEHLER: 'cec-client' (cec-utils) ist nicht installiert!" >&2
    exit 1
fi

# Raspberry Pi HDMI-Power aktivieren
if command -v vcgencmd >/dev/null 2>&1; then
    vcgencmd display_power 1 >/dev/null 2>&1 || true
fi

cec_wake() {
    # 1. Moderne Linux-Kernel CEC-Schnittstelle (cec-ctl)
    if command -v cec-ctl >/dev/null 2>&1; then
        echo "[CEC] Konfiguriere CEC-Adapter via cec-ctl..."
        cec-ctl -d /dev/cec0 --playback --osd-name KioskPi >/dev/null 2>&1 || true
        echo "[CEC] Sende Image View On & Active Source via cec-ctl..."
        cec-ctl -d /dev/cec0 --to 0 --image-view-on >/dev/null 2>&1 || true
        cec-ctl -d /dev/cec0 --to 0 --user-control-pressed ui-cmd=power-on-function >/dev/null 2>&1 || true
        cec-ctl -d /dev/cec0 --to 0 --user-control-released >/dev/null 2>&1 || true
        cec-ctl -d /dev/cec0 --active-source phys-addr=1.0.0.0 >/dev/null 2>&1 || true
    fi

    # 2. cec-client Fallback / Ergänzung (sendet Standard-CEC-Pakete)
    if command -v cec-client >/dev/null 2>&1; then
        echo "[CEC] Sende on 0 und as via cec-client..."
        printf "on 0\nas\n" | timeout 8 cec-client -s -d 1 >/dev/null 2>&1 || true
    fi

    # 3. Zweiter Active-Source Impuls nach kurzer Pause (für TVs, die beim Hochfahren Zeit brauchen)
    sleep 3
    if command -v cec-ctl >/dev/null 2>&1; then
        cec-ctl -d /dev/cec0 --active-source phys-addr=1.0.0.0 >/dev/null 2>&1 || true
    fi
    if command -v cec-client >/dev/null 2>&1; then
        echo "as" | timeout 5 cec-client -s -d 1 >/dev/null 2>&1 || true
    fi
}

cec_standby() {
    if command -v cec-ctl >/dev/null 2>&1; then
        echo "[CEC] Sende Standby via cec-ctl..."
        cec-ctl -d /dev/cec0 --playback --osd-name KioskPi >/dev/null 2>&1 || true
        cec-ctl -d /dev/cec0 --to 0 --standby >/dev/null 2>&1 || true
        cec-ctl -d /dev/cec0 --to 0 --user-control-pressed ui-cmd=power-off-function >/dev/null 2>&1 || true
        cec-ctl -d /dev/cec0 --to 0 --user-control-released >/dev/null 2>&1 || true
    fi
    if command -v cec-client >/dev/null 2>&1; then
        echo "[CEC] Sende standby 0 via cec-client..."
        echo "standby 0" | timeout 8 cec-client -s -d 1 >/dev/null 2>&1 || true
    fi
}

case "$ACTION" in
    on|force-on)
        echo "[CEC] Schalte TV ein..."
        cec_wake
        echo "[CEC] TV Einschaltbefehle erfolgreich gesendet."
        ;;
    off|standby|force-off)
        echo "[CEC] Schalte TV in Standby..."
        cec_standby
        echo "[CEC] TV in Standby geschaltet."
        ;;
    status)
        echo "[CEC] Frage Stromstatus des TV ab..."
        if command -v cec-ctl >/dev/null 2>&1; then
            cec-ctl -d /dev/cec0 --playback --osd-name KioskPi >/dev/null 2>&1 || true
            pstat=$(timeout 5 cec-ctl -d /dev/cec0 --to 0 --give-device-power-status 2>/dev/null | grep -iE "pwr-state|power status" || true)
            if [ -n "$pstat" ]; then
                echo "$pstat"
                exit 0
            fi
        fi
        if command -v cec-client >/dev/null 2>&1; then
            echo "pow 0" | timeout 8 cec-client -s -d 1 | grep -i "power status" || echo "Keine Statusantwort empfangen."
        else
            echo "Kein CEC-Client vorhanden."
        fi
        ;;
    *)
        echo "Verwendung: $0 {on|off|standby|status|force-on|force-off}"
        exit 1
        ;;
esac
