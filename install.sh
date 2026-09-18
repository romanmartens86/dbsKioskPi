#!/bin/bash
# ==============================================================================
# dbsKioskPi - Vollautomatisches Installationsskript
# Schlüsselfertiges Setup für Raspberry Pi OS Lite (64-Bit)
# ==============================================================================

set -euo pipefail

# Farbausgaben für das Terminal
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[OK]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[FEHLER]${NC} $1" >&2
}

# ------------------------------------------------------------------------------
# 1. Root- und System-Prüfung
# ------------------------------------------------------------------------------
if [ "$(id -u)" -ne 0 ]; then
    log_error "Dieses Skript muss mit Administratorrechten ausgeführt werden!"
    echo "Bitte starte die Installation wie folgt:"
    echo "  sudo bash install.sh"
    exit 1
fi

log_info "Starte dbsKioskPi Installation..."

# Ermittle den Zielbenutzer (der Benutzer, der 'sudo' aufgerufen hat)
TARGET_USER="${SUDO_USER:-}"
if [ -z "$TARGET_USER" ] || [ "$TARGET_USER" = "root" ]; then
    # Fallback: Erster User mit UID 1000 oder pi
    TARGET_USER=$(id -un 1000 2>/dev/null || echo "pi")
fi

if ! id "$TARGET_USER" >/dev/null 2>&1; then
    log_error "Zielbenutzer '$TARGET_USER' konnte nicht im System gefunden werden!"
    exit 1
fi

TARGET_UID=$(id -u "$TARGET_USER")
TARGET_GID=$(id -g "$TARGET_USER")
TARGET_HOME=$(getent passwd "$TARGET_USER" | cut -d: -f6)

log_info "Konfiguriere Kiosk für Benutzer: $TARGET_USER (UID: $TARGET_UID, Home: $TARGET_HOME)"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ------------------------------------------------------------------------------
# 2. Paketinstallation & Repository-Update
# ------------------------------------------------------------------------------
log_info "Aktualisiere Paketquellen..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -y

log_info "Installiere Kernkomponenten (Cage, Wayland, seatd, cec-utils, zram-tools, etc.)..."
PACKAGES=(
    cage
    seatd
    fonts-liberation
    libgl1-mesa-dri
    cec-utils
    zram-tools
    whiptail
    network-manager
    mpg123
    alsa-utils
    python3
)

apt-get install -y --no-install-recommends "${PACKAGES[@]}"

# Chromium installieren (Prüfe Paketname)
log_info "Installiere Chromium Browser..."
if apt-cache show chromium >/dev/null 2>&1; then
    apt-get install -y chromium
elif apt-cache show chromium-browser >/dev/null 2>&1; then
    apt-get install -y chromium-browser
else
    log_error "Konnte weder 'chromium' noch 'chromium-browser' in den Paketquellen finden!"
    exit 1
fi

log_success "Paketinstallation abgeschlossen."

# ------------------------------------------------------------------------------
# 3. Benutzer- und Gruppenkonfiguration
# ------------------------------------------------------------------------------
log_info "Konfiguriere Benutzergruppen für '$TARGET_USER'..."

# Stelle sicher, dass die Gruppen existieren
for grp in video audio render input seat; do
    if ! getent group "$grp" >/dev/null 2>&1; then
        groupadd "$grp" 2>/dev/null || true
    fi
    usermod -a -G "$grp" "$TARGET_USER"
done
log_success "Benutzer '$TARGET_USER' zu video, audio, render, input und seat hinzugefügt."

# seatd-Dienst aktivieren & starten
log_info "Aktiviere und starte seatd.service..."
systemctl enable --now seatd.service || true

# ------------------------------------------------------------------------------
# 4. Systemoptimierung (GPU Memory & zramswap)
# ------------------------------------------------------------------------------
log_info "Prüfe und konfiguriere GPU-Speicher (gpu_mem=128)..."
CONFIG_TXT="/boot/firmware/config.txt"
if [ ! -f "$CONFIG_TXT" ]; then
    CONFIG_TXT="/boot/config.txt"
fi

if [ -f "$CONFIG_TXT" ]; then
    if grep -q "^gpu_mem=" "$CONFIG_TXT"; then
        sed -i 's/^gpu_mem=.*/gpu_mem=128/' "$CONFIG_TXT"
        log_success "gpu_mem in $CONFIG_TXT auf 128 MB gesetzt."
    else
        echo "" >> "$CONFIG_TXT"
        echo "# dbsKioskPi GPU Speicherzuweisung" >> "$CONFIG_TXT"
        echo "gpu_mem=128" >> "$CONFIG_TXT"
        log_success "gpu_mem=128 zu $CONFIG_TXT hinzugefügt."
    fi
else
    log_warn "Keine config.txt unter /boot/firmware oder /boot gefunden. Überspringe GPU-Speichereintrag."
fi

log_info "Konfiguriere komprimierten RAM-Swap (zramswap: ALGO=lz4, PERCENT=50)..."
if [ -f "/etc/default/zramswap" ]; then
    sed -i 's/^#*ALGO=.*/ALGO=lz4/' /etc/default/zramswap
    sed -i 's/^#*PERCENT=.*/PERCENT=50/' /etc/default/zramswap
else
    mkdir -p /etc/default
    cat << 'EOF' > /etc/default/zramswap
# /etc/default/zramswap
ALGO=lz4
PERCENT=50
PRIORITY=100
EOF
fi
systemctl restart zramswap.service 2>/dev/null || true
log_success "zramswap konfiguriert und neu gestartet."

# ------------------------------------------------------------------------------
# 5. Kiosk-Konfiguration & Hilfsskripte
# ------------------------------------------------------------------------------
log_info "Erstelle Konfigurationsverzeichnisse /etc/dbskiosk und /var/lib/dbskiosk/sounds..."
mkdir -p /etc/dbskiosk
mkdir -p /var/lib/dbskiosk/sounds
chown -R "$TARGET_USER:$TARGET_USER" /var/lib/dbskiosk 2>/dev/null || true

if [ ! -f "/etc/dbskiosk/kiosk.conf" ]; then
    cp "$SCRIPT_DIR/files/kiosk.conf" /etc/dbskiosk/kiosk.conf
    log_success "Standard-Konfiguration nach /etc/dbskiosk/kiosk.conf kopiert."
else
    log_info "Bestehende /etc/dbskiosk/kiosk.conf beibehalten (kein Überschreiben)."
fi
chmod 644 /etc/dbskiosk/kiosk.conf

# Startskript installieren
log_info "Installiere Kiosk-Startskript (/usr/local/bin/dbs-kiosk)..."
cp "$SCRIPT_DIR/files/kiosk-start.sh" /usr/local/bin/dbs-kiosk
chmod 755 /usr/local/bin/dbs-kiosk

# CEC-Hilfsskript installieren
log_info "Installiere CEC-Hilfsskript (/usr/local/bin/dbs-cec)..."
cp "$SCRIPT_DIR/files/cec-control.sh" /usr/local/bin/dbs-cec
chmod 755 /usr/local/bin/dbs-cec

# Schulglocken-Audio-Skript installieren
log_info "Installiere Schulglocken-Audioskript (/usr/local/bin/dbs-bell)..."
cp "$SCRIPT_DIR/files/dbs-bell.sh" /usr/local/bin/dbs-bell
chmod 755 /usr/local/bin/dbs-bell

# REST-API Daemon für Home Assistant installieren
log_info "Installiere REST-API Daemon (/usr/local/bin/dbs-api)..."
cp "$SCRIPT_DIR/files/dbs-api.py" /usr/local/bin/dbs-api
chmod 755 /usr/local/bin/dbs-api

# Interaktives CLI-Tool installieren
log_info "Installiere CLI-Konfigurationstool (/usr/local/bin/dbs-config)..."
cp "$SCRIPT_DIR/bin/dbs-config" /usr/local/bin/dbs-config
chmod 755 /usr/local/bin/dbs-config

# ------------------------------------------------------------------------------
# 6. Systemd-Dienste und Timer
# ------------------------------------------------------------------------------
log_info "Richte Systemd-Dienste ein..."

# kiosk.service vorbereiten und Benutzer einsetzen
sed -e "s|@KIOSK_USER@|$TARGET_USER|g" \
    -e "s|@KIOSK_UID@|$TARGET_UID|g" \
    "$SCRIPT_DIR/files/kiosk.service" > /etc/systemd/system/kiosk.service
chmod 644 /etc/systemd/system/kiosk.service

# CEC Units kopieren
cp "$SCRIPT_DIR/files/kiosk-cec-on.service" /etc/systemd/system/
cp "$SCRIPT_DIR/files/kiosk-cec-on.timer" /etc/systemd/system/
cp "$SCRIPT_DIR/files/kiosk-cec-off.service" /etc/systemd/system/
cp "$SCRIPT_DIR/files/kiosk-cec-off.timer" /etc/systemd/system/
chmod 644 /etc/systemd/system/kiosk-cec*

# REST-API Service für Home Assistant kopieren
cp "$SCRIPT_DIR/files/dbs-api.service" /etc/systemd/system/
chmod 644 /etc/systemd/system/dbs-api.service

systemctl daemon-reload

# Boot-Target auf graphical.target setzen
log_info "Setze Boot-Target auf graphical.target..."
systemctl set-default graphical.target

# Dienste und Timer aktivieren
log_info "Aktiviere Kiosk-Dienst, CEC-Timer und API-Dienst..."
systemctl enable kiosk.service
systemctl enable --now kiosk-cec-on.timer
systemctl enable --now kiosk-cec-off.timer
systemctl enable --now dbs-api.service

# ------------------------------------------------------------------------------
# 7. Abschluss & Zusammenfassung
# ------------------------------------------------------------------------------
echo ""
echo -e "${GREEN}======================================================================${NC}"
echo -e "${GREEN}       dbsKioskPi Installation erfolgreich abgeschlossen!            ${NC}"
echo -e "${GREEN}======================================================================${NC}"
echo ""
echo "Folgende Komponenten wurden eingerichtet:"
echo " - Cage Wayland Compositor + Chromium Kiosk (/usr/local/bin/dbs-kiosk)"
echo " - Autostart-Dienst auf TTY1 (kiosk.service)"
echo " - HDMI-CEC Automatisierung (07:00 Ein / 19:00 Aus)"
echo " - zRAM Swap mit LZ4 Komprimierung (50% RAM)"
echo " - Interaktives Konfigurationsmenü (Befehl: sudo dbs-config)"
echo ""
echo -e "${YELLOW}HINWEIS FÜR SSH:${NC}"
echo " Du kannst das System jederzeit via SSH über folgenden Befehl verwalten:"
echo -e "   ${BLUE}sudo dbs-config${NC}"
echo " Dort kannst du WLAN konfigurieren, die URL ändern, CEC testen und Logs prüfen."
echo ""
echo "Empfohlener nächster Schritt:"
echo " Starte den Raspberry Pi neu, um die neue Sitzung und GPU-Einstellungen zu aktivieren:"
echo -e "   ${BLUE}sudo reboot${NC}"
echo ""
