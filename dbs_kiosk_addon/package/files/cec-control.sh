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

if ! command -v cec-ctl >/dev/null 2>&1 && ! command -v cec-client >/dev/null 2>&1; then
    echo "FEHLER: Weder 'cec-ctl' (v4l-utils) noch 'cec-client' (cec-utils) ist installiert!" >&2
    exit 1
fi

# Raspberry Pi HDMI-Power aktivieren
if command -v vcgencmd >/dev/null 2>&1; then
    vcgencmd display_power 1 >/dev/null 2>&1 || true
fi

# Stelle sicher, dass der DRM-HDMI-Connector aktiv ist
for st in /sys/class/drm/card*-HDMI-A-*/status; do
    if [ -f "$st" ] && [ "$(cat "$st" 2>/dev/null)" != "connected" ]; then
        echo on > "$st" 2>/dev/null || true
    fi
done

is_in_operating_hours() {
    local cur_hm on_hm off_hm
    cur_hm=$(date +%H:%M)
    on_hm="${CEC_ON_TIME:-07:00}"
    off_hm="${CEC_OFF_TIME:-19:00}"

    if [ "$on_hm" = "$off_hm" ]; then
        return 0
    fi

    # Wenn die aktuelle Uhrzeit exakt der Einschalt- oder Ausschaltzeit entspricht,
    # überlassen wir die Ausführung dem jeweiligen dedizierten Systemd-Timer
    if [ "$cur_hm" = "$on_hm" ] || [ "$cur_hm" = "$off_hm" ]; then
        return 1
    fi

    local cur_m on_m off_m
    cur_m=$(( 10#${cur_hm%:*} * 60 + 10#${cur_hm#*:} ))
    on_m=$(( 10#${on_hm%:*} * 60 + 10#${on_hm#*:} ))
    off_m=$(( 10#${off_hm%:*} * 60 + 10#${off_hm#*:} ))

    if [ "$on_m" -lt "$off_m" ]; then
        # Normalfall (z. B. 07:00 bis 19:00)
        if [ "$cur_m" -ge "$on_m" ] && [ "$cur_m" -lt "$off_m" ]; then
            return 0
        fi
    else
        # Nachtbetrieb über Mitternacht (z. B. 20:00 bis 06:00)
        if [ "$cur_m" -ge "$on_m" ] || [ "$cur_m" -lt "$off_m" ]; then
            return 0
        fi
    fi
    return 1
}

get_physical_address() {
    # 1. Manuelle Konfiguration in kiosk.conf hat Vorrang (z. B. CEC_PHYS_ADDR="2.0.0.0")
    if [ -n "${CEC_PHYS_ADDR:-}" ]; then
        echo "$CEC_PHYS_ADDR"
        return 0
    fi

    # 2. Dynamisch über cec-ctl ermitteln
    local pa=""
    if command -v cec-ctl >/dev/null 2>&1; then
        pa=$(cec-ctl -d /dev/cec0 2>/dev/null | awk -F': ' '/Physical Address/ {print $2; exit}' | tr -d '[:space:]' || true)
    fi

    # 3. Fallback auf 1.0.0.0 falls Adresse ungültig oder nicht lesbar
    if [ -z "$pa" ] || [ "$pa" = "f.f.f.f" ] || [ "$pa" = "0.0.0.0" ]; then
        pa="1.0.0.0"
    fi
    echo "$pa"
}

cec_wake() {
    local pa
    pa=$(get_physical_address)
    echo "[CEC] Verwende HDMI Physical Address: $pa"

    # 1. Moderne Linux-Kernel CEC-Schnittstelle (cec-ctl)
    if command -v cec-ctl >/dev/null 2>&1; then
        echo "[CEC] Konfiguriere CEC-Adapter via cec-ctl..."
        cec-ctl -d /dev/cec0 --playback --osd-name KioskPi >/dev/null 2>&1 || true
        echo "[CEC] Sende Image View On & Active Source (phys-addr: $pa)..."
        cec-ctl -d /dev/cec0 --to 0 --image-view-on >/dev/null 2>&1 || true
        cec-ctl -d /dev/cec0 --active-source phys-addr="$pa" >/dev/null 2>&1 || true

        # Zweiter Active-Source Impuls nach kurzer Pause:
        # Viele Smart-TVs (Samsung, LG, Google TV) booten im Hintergrund ihr OS und springen
        # nach einigen Sekunden ins Hauptmenü. Dieser Impuls schaltet den TV zuverlässig auf den HDMI-Port zurück.
        sleep 4
        echo "[CEC] Sende zweiten Active-Source Impuls (phys-addr: $pa)..."
        cec-ctl -d /dev/cec0 --active-source phys-addr="$pa" >/dev/null 2>&1 || true
    elif command -v cec-client >/dev/null 2>&1; then
        # 2. cec-client Fallback (nur wenn cec-ctl nicht vorhanden ist)
        echo "[CEC] Sende on 0 und as via cec-client..."
        printf "on 0\nas\n" | timeout 8 cec-client -s -d 1 >/dev/null 2>&1 || true
        sleep 4
        echo "as" | timeout 5 cec-client -s -d 1 >/dev/null 2>&1 || true
    fi
}

cec_keepalive() {
    local pa
    pa=$(get_physical_address)

    if command -v cec-ctl >/dev/null 2>&1; then
        echo "[CEC] Sende Keep-Alive via cec-ctl (phys-addr: $pa)..."
        cec-ctl -d /dev/cec0 --playback --osd-name KioskPi >/dev/null 2>&1 || true
        cec-ctl -d /dev/cec0 --to 0 --image-view-on >/dev/null 2>&1 || true
        cec-ctl -d /dev/cec0 --active-source phys-addr="$pa" >/dev/null 2>&1 || true
    elif command -v cec-client >/dev/null 2>&1; then
        echo "[CEC] Sende Active-Source via cec-client..."
        printf "on 0\nas\n" | timeout 8 cec-client -s -d 1 >/dev/null 2>&1 || true
    fi
}

cec_standby() {
    if command -v cec-ctl >/dev/null 2>&1; then
        echo "[CEC] Sende Standby via cec-ctl..."
        cec-ctl -d /dev/cec0 --playback --osd-name KioskPi >/dev/null 2>&1 || true
        cec-ctl -d /dev/cec0 --to 0 --standby >/dev/null 2>&1 || true
    elif command -v cec-client >/dev/null 2>&1; then
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
    keepalive)
        if ! is_in_operating_hours; then
            echo "[CEC] Außerhalb der Betriebszeiten (${CEC_ON_TIME:-07:00} - ${CEC_OFF_TIME:-19:00}). Kein Keep-Alive erforderlich."
            exit 0
        fi
        echo "[CEC] Sende stündliches Keep-Alive Signal an TV..."
        cec_keepalive
        echo "[CEC] Keep-Alive Signal erfolgreich gesendet."
        ;;
    force-keepalive)
        echo "[CEC] Sende erzwungenes Keep-Alive Signal an TV..."
        cec_keepalive
        echo "[CEC] Keep-Alive Signal erfolgreich gesendet."
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
        echo "Verwendung: $0 {on|off|standby|status|keepalive|force-keepalive|force-on|force-off}"
        exit 1
        ;;
esac
