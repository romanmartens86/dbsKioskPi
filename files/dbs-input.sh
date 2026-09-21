#!/bin/bash
# ==============================================================================
# dbsKioskPi - Input Device Lock Control Helper
# ==============================================================================

set -euo pipefail

RULES_FILE="/etc/udev/rules.d/99-dbskiosk-input.rules"
CONFIG_FILE="/etc/dbskiosk/kiosk.conf"
LOG_FILE="/var/log/dbskiosk-config.log"

log_msg() {
    local msg="$1"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [INPUT] $msg" | tee -a "$LOG_FILE" 2>/dev/null || echo "[INPUT] $msg"
}

set_config_val() {
    local key="$1"
    local val="$2"
    if [ -f "$CONFIG_FILE" ]; then
        if grep -q "^${key}=" "$CONFIG_FILE"; then
            sed -i "s|^${key}=.*|${key}=\"${val}\"|" "$CONFIG_FILE"
        else
            echo "${key}=\"${val}\"" >> "$CONFIG_FILE"
        fi
    fi
}

ACTION="${1:-status}"

case "$ACTION" in
    status)
        if [ -f "$RULES_FILE" ]; then
            echo "Eingabeschnittstelle: GESPERRT (Tastatur & Maus blockiert)"
            exit 0
        else
            echo "Eingabeschnittstelle: ENTSPERRT (Tastatur & Maus aktiv)"
            exit 0
        fi
        ;;

    lock)
        cat << 'EOF' > "$RULES_FILE"
# ==============================================================================
# dbsKioskPi - Input Device Lock Rules
# ==============================================================================
ACTION!="remove", KERNEL=="event*", ENV{ID_INPUT_KEYBOARD}=="1", ENV{LIBINPUT_IGNORE_DEVICE}="1"
ACTION!="remove", KERNEL=="event*", ENV{ID_INPUT_KEY}=="1", ENV{LIBINPUT_IGNORE_DEVICE}="1"
ACTION!="remove", KERNEL=="event*", ENV{ID_INPUT_MOUSE}=="1", ENV{LIBINPUT_IGNORE_DEVICE}="1"
ACTION!="remove", KERNEL=="event*", ENV{ID_INPUT_POINTINGSTICK}=="1", ENV{LIBINPUT_IGNORE_DEVICE}="1"
EOF
        chmod 644 "$RULES_FILE"
        udevadm control --reload-rules || true
        udevadm trigger || true
        set_config_val "BLOCK_KEYBOARD" "true"
        set_config_val "BLOCK_MOUSE" "true"
        log_msg "Tastatur- und Mauseingaben gesperrt (udev-Regel aktiviert)"
        echo "Tastatur- und Mauseingaben erfolgreich gesperrt."
        ;;

    unlock)
        rm -f "$RULES_FILE"
        udevadm control --reload-rules || true
        udevadm trigger || true
        set_config_val "BLOCK_KEYBOARD" "false"
        set_config_val "BLOCK_MOUSE" "false"
        log_msg "Tastatur- und Mauseingaben entsperrt (udev-Regel entfernt)"
        echo "Tastatur- und Mauseingaben entsperrt (Geräte können lokal bedient werden)."
        ;;

    apply)
        BLOCK_KBD="true"
        BLOCK_MOU="true"
        if [ -f "$CONFIG_FILE" ]; then
            # shellcheck disable=SC1090
            source "$CONFIG_FILE"
            BLOCK_KBD="${BLOCK_KEYBOARD:-true}"
            BLOCK_MOU="${BLOCK_MOUSE:-true}"
        fi

        if [ "$BLOCK_KBD" = "true" ] || [ "$BLOCK_MOU" = "true" ]; then
            cat << EOF > "$RULES_FILE"
# ==============================================================================
# dbsKioskPi - Input Device Lock Rules
# ==============================================================================
EOF
            if [ "$BLOCK_KBD" = "true" ]; then
                cat << 'EOF' >> "$RULES_FILE"
ACTION!="remove", KERNEL=="event*", ENV{ID_INPUT_KEYBOARD}=="1", ENV{LIBINPUT_IGNORE_DEVICE}="1"
ACTION!="remove", KERNEL=="event*", ENV{ID_INPUT_KEY}=="1", ENV{LIBINPUT_IGNORE_DEVICE}="1"
EOF
            fi
            if [ "$BLOCK_MOU" = "true" ]; then
                cat << 'EOF' >> "$RULES_FILE"
ACTION!="remove", KERNEL=="event*", ENV{ID_INPUT_MOUSE}=="1", ENV{LIBINPUT_IGNORE_DEVICE}="1"
ACTION!="remove", KERNEL=="event*", ENV{ID_INPUT_POINTINGSTICK}=="1", ENV{LIBINPUT_IGNORE_DEVICE}="1"
EOF
            fi
            chmod 644 "$RULES_FILE"
            udevadm control --reload-rules || true
            udevadm trigger || true
            log_msg "Eingabekonfiguration angewendet (Tastatur: $BLOCK_KBD, Maus: $BLOCK_MOU)"
        else
            rm -f "$RULES_FILE"
            udevadm control --reload-rules || true
            udevadm trigger || true
            log_msg "Eingabekonfiguration angewendet (Alle Geräte entsperrt)"
        fi
        ;;

    *)
        echo "Verwendung: $0 {status|lock|unlock|apply}"
        exit 1
        ;;
esac
