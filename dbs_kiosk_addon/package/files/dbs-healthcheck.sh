#!/usr/bin/env bash
# ==============================================================================
# dbsKioskPi - System Healthcheck & Post-Install Diagnose
# Analysiert den gesamten Raspberry Pi Zustand nach Installation und Neustart
# ==============================================================================

set -u

LOG_FILE="/var/log/dbskiosk-healthcheck.log"
mkdir -p "$(dirname "$LOG_FILE")"
touch "$LOG_FILE"
chmod 644 "$LOG_FILE" 2>/dev/null || true

# Ausgabe gleichzeitig in Konsole und Datei schreiben
exec > >(tee "$LOG_FILE") 2>&1

TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

echo "================================================================================"
echo "          dbsKioskPi - SYSTEM HEALTHCHECK & DIAGNOSE BERICHT                    "
echo "================================================================================"
echo "Zeitstempel: $TIMESTAMP"
echo "Hostname:    $(hostname)"
echo ""

TOTAL_CHECKS=0
PASSED_CHECKS=0
WARNINGS=0
ERRORS=0

check_status() {
    local name="$1"
    local status="$2" # 0 = OK, 1 = WARN, 2 = ERROR
    local details="$3"

    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
    if [ "$status" -eq 0 ]; then
        PASSED_CHECKS=$((PASSED_CHECKS + 1))
        echo -e "[ OK ]   $name: $details"
    elif [ "$status" -eq 1 ]; then
        WARNINGS=$((WARNINGS + 1))
        echo -e "[WARN]   $name: $details"
    else
        ERRORS=$((ERRORS + 1))
        echo -e "[FAIL]   $name: $details"
    fi
}

echo "--- 1. HARDWARE & BETRIEBSSYSTEM ---"
# Raspberry Pi Modell
if [ -f /proc/device-tree/model ]; then
    RPI_MODEL=$(tr -d '\0' < /proc/device-tree/model)
    check_status "Hardware Modell" 0 "$RPI_MODEL"
else
    check_status "Hardware Modell" 1 "Kein Standard-Pi Device-Tree gefunden"
fi

# OS Release
if [ -f /etc/os-release ]; then
    OS_NAME=$(grep '^PRETTY_NAME=' /etc/os-release | cut -d= -f2 | tr -d '"')
    check_status "Betriebssystem" 0 "$OS_NAME ($(uname -m), Kernel $(uname -r))"
fi

# CPU Temperatur
TEMP_C="unbekannt"
if command -v vcgencmd >/dev/null 2>&1; then
    TEMP_RAW=$(vcgencmd measure_temp 2>/dev/null || true)
    if [ -n "$TEMP_RAW" ]; then
        TEMP_C=$(echo "$TEMP_RAW" | grep -oE '[0-9]+\.[0-9]+' || echo "$TEMP_RAW")
    fi
elif [ -f /sys/class/thermal/thermal_zone0/temp ]; then
    MILLI_TEMP=$(cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null || echo "0")
    TEMP_C=$(awk "BEGIN {print $MILLI_TEMP/1000}")
fi

if [ "$TEMP_C" != "unbekannt" ]; then
    TEMP_INT=${TEMP_C%.*}
    if [ "$TEMP_INT" -lt 70 ]; then
        check_status "CPU Temperatur" 0 "${TEMP_C}°C (Optimal)"
    elif [ "$TEMP_INT" -lt 82 ]; then
        check_status "CPU Temperatur" 1 "${TEMP_C}°C (Erhöht, Kühlung prüfen)"
    else
        check_status "CPU Temperatur" 2 "${TEMP_C}°C (Drosselung droht! Kühler erforderlich)"
    fi
fi

# Throttling Check (Raspberry Pi Undervoltage / Throttled)
if command -v vcgencmd >/dev/null 2>&1; then
    THROTTLED=$(vcgencmd get_throttled 2>/dev/null || true)
    if [ -n "$THROTTLED" ]; then
        if [ "$THROTTLED" = "throttled=0x0" ]; then
            check_status "Spannungsversorgung" 0 "Stabil (Keine Unterspannung / kein Throttling)"
        else
            check_status "Spannungsversorgung" 1 "Hinweis: $THROTTLED (Netzteil prüfen)"
        fi
    fi
fi

echo ""
echo "--- 2. SPEICHER & RESSOURCEN ---"
# RAM & zRAM
RAM_TOTAL=$(free -h | awk '/^Mem:/ {print $2}')
RAM_USED=$(free -h | awk '/^Mem:/ {print $3}')
RAM_AVAIL=$(free -h | awk '/^Mem:/ {print $7}')
check_status "Arbeitsspeicher (RAM)" 0 "Gesamt: $RAM_TOTAL | Belegt: $RAM_USED | Frei: $RAM_AVAIL"

# zRAM Status
if command -v zramctl >/dev/null 2>&1 && zramctl >/dev/null 2>&1; then
    ZRAM_INFO=$(zramctl --noheadings --output NAME,ALGORITHM,DISKSIZE 2>/dev/null | head -n 1)
    if [ -n "$ZRAM_INFO" ]; then
        check_status "zRAM Swap" 0 "Aktiv ($ZRAM_INFO)"
    else
        check_status "zRAM Swap" 1 "Nicht aktiv oder keine zRAM-Geräte"
    fi
else
    check_status "zRAM Swap" 1 "zramctl nicht verfügbar"
fi

# Festplattenspeicher (MicroSD)
DISK_USAGE=$(df -h / | awk 'NR==2 {print $5}' | tr -d '%')
DISK_FREE=$(df -h / | awk 'NR==2 {print $4}')
if [ -n "$DISK_USAGE" ]; then
    if [ "$DISK_USAGE" -lt 85 ]; then
        check_status "Speicherplatz (/)" 0 "Frei: $DISK_FREE (Belegt: ${DISK_USAGE}%)"
    elif [ "$DISK_USAGE" -lt 95 ]; then
        check_status "Speicherplatz (/)" 1 "Knapp: Nur noch $DISK_FREE frei (${DISK_USAGE}%)"
    else
        check_status "Speicherplatz (/)" 2 "Fast voll: ${DISK_USAGE}% belegt!"
    fi
fi

echo ""
echo "--- 3. NETZWERK & VERBINDUNGEN ---"
# IP-Adressen
IPV4_LIST=$(ip -4 -o addr show scope global | awk '{print $2 ": " $4}' | paste -sd ", " -)
if [ -n "$IPV4_LIST" ]; then
    check_status "IP-Adressen" 0 "$IPV4_LIST"
else
    check_status "IP-Adressen" 2 "Keine globale IPv4-Adresse zugewiesen"
fi

# Gateway / Internet Ping
if ping -c 1 -W 2 8.8.8.8 >/dev/null 2>&1; then
    check_status "Internet (Ping 8.8.8.8)" 0 "Erreichbar"
elif ping -c 1 -W 2 1.1.1.1 >/dev/null 2>&1; then
    check_status "Internet (Ping 1.1.1.1)" 0 "Erreichbar"
else
    check_status "Internet (Ping)" 1 "Nicht erreichbar (Offline oder ICMP blockiert)"
fi

# DNS Namensauflösung
if host -W 2 google.com >/dev/null 2>&1 || getent hosts google.com >/dev/null 2>&1; then
    check_status "DNS-Auflösung" 0 "Funktionsfähig (google.com aufgelöst)"
else
    check_status "DNS-Auflösung" 1 "DNS-Lookup fehlgeschlagen"
fi

echo ""
echo "--- 4. SYSTEMDIENSTE & KIOSK STATUS ---"
# Kiosk Service
if systemctl is-active --quiet kiosk.service; then
    check_status "kiosk.service" 0 "Aktiv (running)"
else
    check_status "kiosk.service" 2 "Inaktiv oder Fehler (systemctl status kiosk.service)"
fi

# Wayland Compositor (Cage)
if pgrep -x cage >/dev/null 2>&1; then
    check_status "Wayland (Cage)" 0 "Läuft (PID: $(pgrep -x cage | head -n 1))"
else
    check_status "Wayland (Cage)" 2 "Nicht gefunden - Kiosk Compositor läuft nicht"
fi

# Chromium Browser
if pgrep -f "chromium.*--kiosk" >/dev/null 2>&1; then
    check_status "Chromium Browser" 0 "Läuft im Kiosk-Modus"
else
    check_status "Chromium Browser" 2 "Nicht im Kiosk-Modus aktiv"
fi

# dbs-api REST Daemon (Port 8088)
if systemctl is-active --quiet dbs-api.service; then
    check_status "dbs-api.service" 0 "Aktiv (running)"
else
    check_status "dbs-api.service" 2 "Inaktiv oder Fehler"
fi

# Port 8088 Abfrage
API_TEST=$(curl -s -m 3 http://127.0.0.1:8088/api/health 2>/dev/null || echo "")
if echo "$API_TEST" | grep -q "status"; then
    check_status "Port 8088 (REST API)" 0 "Antwortet einwandfrei (health: ok)"
else
    check_status "Port 8088 (REST API)" 2 "Keine Antwort auf http://127.0.0.1:8088/api/health"
fi

# HDMI-CEC Steuerung & Timer
if systemctl is-active --quiet kiosk-cec-on.timer && systemctl is-active --quiet kiosk-cec-off.timer; then
    check_status "CEC Systemd Timer" 0 "Beide Timer aktiv (07:00 Ein / 19:00 Aus)"
else
    check_status "CEC Systemd Timer" 1 "Timer nicht vollständig aktiv"
fi

# Kiosk-Eingabesperre (Tastatur & Maus)
if [ -f /etc/udev/rules.d/99-dbskiosk-input.rules ]; then
    check_status "Kiosk-Eingabesperre" 0 "Aktiv (Tastatur & Maus gesperrt, Zeiger ausgeblendet)"
else
    check_status "Kiosk-Eingabesperre" 1 "Inaktiv (Eingabegeräte entsperrt)"
fi

if command -v cec-client >/dev/null 2>&1; then
    check_status "CEC Client Tool" 0 "cec-utils installiert (/usr/bin/cec-client)"
else
    check_status "CEC Client Tool" 1 "cec-utils nicht gefunden"
fi

# Schulglocken-Audio
if command -v mpg123 >/dev/null 2>&1; then
    check_status "Audiosystem (mpg123)" 0 "Installiert (/usr/bin/mpg123)"
else
    check_status "Audiosystem (mpg123)" 1 "mpg123 nicht installiert"
fi

if [ -f /var/lib/dbskiosk/sounds/bell.mp3 ]; then
    BELL_SIZE=$(du -h /var/lib/dbskiosk/sounds/bell.mp3 | awk '{print $1}')
    check_status "Schulgong-Datei" 0 "Vorhanden (/var/lib/dbskiosk/sounds/bell.mp3, Größe: $BELL_SIZE)"
else
    check_status "Schulgong-Datei" 0 "Noch keine benutzerdefinierte MP3 hinterlegt (optional)"
fi

echo ""
echo "--- 5. KIOSK KONFIGURATION ---"
if [ -f /etc/dbskiosk/kiosk.conf ]; then
    KIOSK_URL=$(grep '^KIOSK_URL=' /etc/dbskiosk/kiosk.conf 2>/dev/null | cut -d= -f2- | tr -d '"' || echo "nicht gesetzt")
    CEC_ON=$(grep '^CEC_ON_TIME=' /etc/dbskiosk/kiosk.conf 2>/dev/null | cut -d= -f2- | tr -d '"' || echo "07:00")
    CEC_OFF=$(grep '^CEC_OFF_TIME=' /etc/dbskiosk/kiosk.conf 2>/dev/null | cut -d= -f2- | tr -d '"' || echo "19:00")
    echo "  Ziel-URL:     $KIOSK_URL"
    echo "  TV An/Aus:    $CEC_ON Uhr / $CEC_OFF Uhr"
fi

echo ""
echo "================================================================================"
if [ "$ERRORS" -eq 0 ]; then
    if [ "$WARNINGS" -eq 0 ]; then
        echo -e "   ERGEBNIS: [GESUND / EXZELLENT] Alle $TOTAL_CHECKS Prüfungen bestanden!"
    else
        echo -e "   ERGEBNIS: [GUT MIT HINWEISEN] $PASSED_CHECKS bestanden, $WARNINGS Hinweis(e)."
    fi
else
    echo -e "   ERGEBNIS: [FEHLER GEFUNDEN] $ERRORS Prüfung(en) fehlgeschlagen! Bitte Details oben prüfen."
fi
echo "================================================================================"
echo "Bericht gespeichert unter: $LOG_FILE"
