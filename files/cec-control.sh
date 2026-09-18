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

case "$ACTION" in
    on|force-on)
        echo "[CEC] Schalte TV ein (on 0)..."
        echo "on 0" | cec-client -s -d 1 || true
        sleep 2
        echo "[CEC] Setze Raspberry Pi als aktive HDMI-Quelle (as)..."
        echo "as" | cec-client -s -d 1 || true
        echo "[CEC] TV eingeschaltet und Quelle aktiviert."
        ;;
    off|standby|force-off)
        echo "[CEC] Schalte TV in Standby (standby 0)..."
        echo "standby 0" | cec-client -s -d 1 || true
        echo "[CEC] TV in Standby geschaltet."
        ;;
    status)
        echo "[CEC] Frage Stromstatus des TV ab (pow 0)..."
        echo "pow 0" | cec-client -s -d 1 | grep -i "power status" || echo "Keine Statusantwort empfangen."
        ;;
    *)
        echo "Verwendung: $0 {on|off|standby|status|force-on|force-off}"
        exit 1
        ;;
esac
