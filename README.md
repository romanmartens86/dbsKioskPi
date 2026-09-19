# dbsKioskPi 🖥️

Vollautomatisches, schlüsselfertiges Kiosk-System auf Basis von **Raspberry Pi OS Lite (64-Bit)**, **Wayland (Cage)**, **Chromium** und **HDMI-CEC TV-Steuerung**.

Das Repository richtet ein frisches Raspberry Pi OS Lite vollständig per Ein-Befehl-Installation ein. Es erfordert keine grafische Desktop-Umgebung (Desktop Environment) und spart dadurch maximale Ressourcen. Nach der Installation steht ein interaktives Terminal-Tool (`dbs-config`) bereit, um das System bequem per SSH zu verwalten (z. B. WLAN einrichten, Ziel-URL ändern, Fernseher-Zeiten steuern).

---

## 📋 Features

- 🚀 **Leichtgewichtig & Schnell:** Läuft auf *Raspberry Pi OS Lite* ohne ressourcenhungrigen X11/Desktop.
- 🪟 **Wayland Kiosk Compositor (Cage):** Startet Chromium direkt im Kiosk-Modus und blendet den Mauszeiger automatisch aus.
- 📺 **HDMI-CEC TV-Automatisierung:**
  - Schaltet den Fernseher täglich automatisch um **07:00 Uhr** an und wählt den Pi als aktive HDMI-Quelle (`on 0` + `as`).
  - Schaltet den Fernseher täglich um **19:00 Uhr** in den Standby-Modus (`standby 0`).
- 🔔 **Schulglocken-Audiosystem (MP3):**
  - Spielt hinterlegte Schulgong-MP3s (`mpg123`) mit präziser Lautstärkeregelung ab.
  - Testbar direkt über die Konsole (`dbs-bell play`) oder das SSH-Menü.
- 🏠 **Home Assistant Integration:**
  - Eigene Custom Integration (`homeassistant/custom_components/dbs_kiosk/`) für Home Assistant.
  - Verbindet sich per IP-Adresse, Benutzername & Passwort mit dem KioskPi.
  - Steuert den Fernseher direkt aus Home Assistant (An/Aus & Timer).
  - Ermöglicht MP3-Upload direkt aus Home Assistant und zeitgesteuertes Läuten der Schulglocke über Home Assistant Automationen!
- ⚡ **Optimierte Performance:**
  - `gpu_mem=128` für flüssiges Hardware-Rendering.
  - `zram-tools` mit LZ4-Komprimierung (50% RAM-Swap) zur Schonung der MicroSD-Karte.
  - Browser-Cache liegt flüchtig im RAM (`/tmp/chromium-cache`).
- 🔒 **Sicher & Datensparsam:** Keine privaten Daten, Passwörter oder sensiblen Tokens im Repository hinterlegt.
- 🛠️ **Integriertes SSH-Konfigurationstool (`dbs-config`):**
  - WLAN-Netzwerke in Reichweite scannen und per Menü verbinden.
  - Kiosk-URL im laufenden Betrieb anpassen.
  - TV-Einschalt- und Standby-Zeiten ändern und CEC live testen.
  - Schulglocke testen & Lautstärke einstellen.
  - System-Logs und Dienststatus auf Knopfdruck ansehen.

---

## 📦 Systemanforderungen

- **Hardware:** Raspberry Pi 4, Pi 400 oder Pi 5 (auch lauffähig auf Pi 3B+)
- **Betriebssystem:** Raspberry Pi OS Lite (64-Bit, Debian Bookworm empfohlen)
- **Verbindung:** HDMI-Kabel zum Fernseher (am Fernseher muss CEC bzw. Anynet+, Bravia Sync, SimpLink o. ä. aktiviert sein)
- **Netzwerk:** Ethernet oder WLAN für die Ersteinrichtung

---

## 🚀 Schnellstart & Installation

### 1. Auf dem Raspberry Pi einloggen
Verbinde dich per SSH oder lokaler Tastatur mit dem frisch installierten Raspberry Pi:
```bash
ssh pi@<raspberry-pi-ip>
```

### 2. Repository klonen & Installation starten
Führe die folgenden Befehle aus:

```bash
git clone https://github.com/romanmartens86/dbsKioskPi.git
cd dbsKioskPi
sudo bash install.sh
```

Das Skript erledigt alle Schritte automatisch:
1. Aktualisiert die Paketquellen und installiert `cage`, `chromium`, `seatd`, `cec-utils`, `zram-tools` und Hilfstools.
2. Weist dem Benutzer die notwendigen Hardware-Gruppen (`video`, `render`, `seat` etc.) zu.
3. Konfiguriert den GPU-Speicher (`gpu_mem=128`) in der Boot-Konfiguration.
4. Richtet den Systemd-Kiosk-Dienst auf `tty1` ein.
5. Aktiviert die Systemd-Timer für die tägliche TV-Steuerung.
6. Installiert das Steuerungstool `/usr/local/bin/dbs-config`.

### 3. Neustart
Nach Abschluss der Installation das System einmal neustarten:
```bash
sudo reboot
```

Nach dem Booten startet der Kiosk auf TTY1 automatisch und lädt die hinterlegte Informationsseite.

---

## 🛠️ Konfiguration über SSH (`dbs-config`)

Sobald das System eingerichtet ist, kannst du alle Einstellungen jederzeit über das menügeführte Konsolen-Tool verwalten.

Verbinde dich einfach per SSH mit dem Pi und starte:
```bash
sudo dbs-config
```

### Verfügbare Menüpunkte:
1. **WLAN einrichten (Scan & Verbinden):**
   - Sucht automatisch nach verfügbaren WLAN-Netzwerken.
   - Zeigt Signalstärke und Verschlüsselung an.
   - Passwort eingeben und direkt verbinden (inkl. manueller Eingabe versteckter SSIDs).
2. **Kiosk Ziel-URL ändern:**
   - Zeigt die aktuelle URL (Standard: `https://dbs.edupage.org/infoscreen/7?scaletowidth=1920`).
   - Neue URL eingeben und auf Wunsch den Kiosk sofort neu laden.
3. **HDMI-CEC TV-Steuerung & Zeitplan:**
   - Einschaltzeit (Standard: `07:00`) und Standby-Zeit (Standard: `19:00`) anpassen.
   - Live-Test: TV sofort anschalten (`on 0` + `as`) oder ausschalten (`standby 0`).
   - Stromstatus des Fernsehers abfragen.
4. **Kiosk-Dienst verwalten:**
   - Dienst neu starten (`systemctl restart kiosk.service`).
   - Status und Live-Logs (`journalctl`) ansehen.
5. **System- & Netzwerkstatus:**
   - Übersicht über aktuelle IP-Adressen, Hostname, Uptime, RAM/zRAM-Belegung und CPU-Temperatur.
6. **Neustart & Herunterfahren.**

---

## ⚙️ Manuelle Konfiguration (`/etc/dbskiosk/kiosk.conf`)

Die Einstellungen werden in der Datei `/etc/dbskiosk/kiosk.conf` gespeichert:

```bash
# Ziel-URL des Kiosk-Browsers
KIOSK_URL="https://dbs.edupage.org/infoscreen/7?scaletowidth=1920"

# HDMI-CEC TV-Steuerung aktivieren (true/false)
CEC_ENABLED="true"

# Tägliche Einschaltzeit für den Fernseher (HH:MM)
CEC_ON_TIME="07:00"

# Tägliche Standby-Zeit für den Fernseher (HH:MM)
CEC_OFF_TIME="19:00"

# Zusätzliche Chromium-Parameter (optional)
EXTRA_CHROMIUM_FLAGS=""
```

Nach manueller Bearbeitung der URL genügt ein:
```bash
sudo systemctl restart kiosk.service
```

---

## 🚀 Das Home Assistant Add-on: "dbsKioskPi Manager" 🛠️

Neben der manuellen Installation bietet das Repository ein vollwertiges **Home Assistant Add-on** mit Weboberfläche (Ingress) in der Seitenleiste:

### 🌟 Die Zero-Touch Remote-Einrichtung:
1. **Raspberry Pi vorbereiten:**
   Flashe ein nacktes **Raspberry Pi OS Lite (64-Bit)** mit dem Raspberry Pi Imager.
   Aktiviere dort lediglich **SSH** (mit Benutzername/Passwort) und das Netzwerk (WLAN oder LAN).
2. **Add-on in Home Assistant installieren:**
   - Gehe zu: **Einstellungen -> Add-ons -> Add-on Store -> Repositories** (drei Punkte oben rechts).
   - Füge die GitHub-URL dieses Repositories hinzu.
   - Installiere das Add-on **dbsKioskPi Manager** und starte es.
3. **Remote-Installation mit einem Klick ausführen:**
   - Öffne das Add-on über die Seitenleiste von Home Assistant.
   - Gib im Tab **"Remote-Setup"** die IP-Adresse, den Benutzer (`pi`) und das Passwort ein.
   - Klicke auf **"KioskPi vollautomatisch installieren"**.
   - Das Add-on verbindet sich per SSH, überträgt alle Dateien, installiert alle Komponenten und streamt die Terminal-Ausgabe live in dein Dashboard. Nach Abschluss startet der KioskPi neu – fertig!

### 🎛️ Alle Kiosk-Einstellungen im Add-on Web-Dashboard:
- **Webseiten & Playlist (Rotation):** Trage beliebig viele URLs ein (z. B. Vertretungsplan für 30s, Speiseplan für 15s, News für 10s). Der Kiosk wechselt die Seiten nahtlos ohne Flackern.
- **Schulglocken-Planer:**
  - Lade MP3-Dateien per Drag & Drop direkt im Browser hoch.
  - Baue den Stundenplan für automatische Pausengongs (Uhrzeit, Mo–Fr, Lautstärke).
  - Teste die Glocke mit dem Button **"Glocke jetzt läuten"**.
- **HDMI-CEC TV-Steuerung:** Passe die morgendlichen Einschalt- und abendlichen Standby-Zeiten an oder schalte das Display per Knopfdruck an/aus.

---

## 🏠 Home Assistant Custom Integration & Entitäten 🔔

Möchtest du Kiosk und Schulglocke lieber über native Home Assistant Entitäten und Automationen steuern?
Das Repository beinhaltet zusätzlich die **Custom Integration** ([`homeassistant/custom_components/dbs_kiosk`](file:///c:/Users/romem/dev/dbsKioskPi/homeassistant/custom_components/dbs_kiosk)):

1. **Ordner kopieren:**
   Kopiere `homeassistant/custom_components/dbs_kiosk` nach `/config/custom_components/dbs_kiosk`.
2. **Integration hinzufügen:**
   - Unter **Einstellungen -> Geräte & Dienste -> Integration hinzufügen -> dbsKioskPi**.
   - Gib IP, Benutzer und Passwort ein.
3. **Verfügbare Entitäten:**
   - `switch.hdmi_tv_bildschirm`: Fernseher an/aus (HDMI-CEC).
   - `time.tv_einschaltzeit` & `time.tv_standby_zeit`: Zeiteinheiten für automatische TV-Schaltung.
   - `button.schulglocke_lauten`: Gong manuell auslösen.
   - `button.kiosk_neu_starten`: Kiosk-Browserdienst neu starten.
   - `button.system_neu_starten_reboot`: Raspberry Pi OS komplett neu starten.
   - `button.system_herunterfahren`: Raspberry Pi OS sicher ausschalten (Shutdown).
   - Dienste: `dbs_kiosk.play_bell`, `dbs_kiosk.upload_bell`, `dbs_kiosk.set_screen_schedule`.

Detaillierte Beispiele und Vorlagen findest du in der [Home Assistant Anleitung](file:///c:/Users/romem/dev/dbsKioskPi/homeassistant/README.md).

---

## 📂 Projektstruktur

```
dbsKioskPi/
├── repository.yaml                # Home Assistant Add-on Repository Metadaten
├── dbs_kiosk_addon/               # Home Assistant Add-on (Web-UI & Remote-Provisioner)
│   ├── config.yaml                # Add-on Konfiguration (Ingress: true)
│   ├── Dockerfile                 # Container-Build (Python 3.11, OpenSSH, Paramiko)
│   ├── run.sh                     # Startskript für Add-on
│   └── app/                       # Web-Dashboard & SSH-Engine
│       ├── main.py                # Flask Backend (SSE Log-Streaming)
│       ├── provisioner.py         # Remote SSH Provisioning Engine
│       ├── requirements.txt
│       ├── templates/index.html   # Web-UI (Provisioner, Playlist, Glocke, TV)
│       └── static/                # CSS & JavaScript
├── install.sh                     # Idempotentes Hauptinstallationsskript
├── bin/
│   └── dbs-config                 # Interaktives CLI/TUI Konfigurationstool (Whiptail)
├── files/
│   ├── kiosk.conf                 # Standard-Konfigurationsvorlage
│   ├── kiosk-start.sh             # Startskript für Cage & Chromium mit allen Flags
│   ├── kiosk.service              # Systemd Service-Unit für Cage auf TTY1
│   ├── cec-control.sh             # Hilfsskript für CEC-Befehle (on, standby, status)
│   ├── dbs-bell.sh                # Schulglocken-Audioskript (mpg123)
│   ├── dbs-api.py                 # REST-API Daemon für Home Assistant (Port 8088)
│   ├── dbs-api.service            # Systemd Service für REST-API Daemon
│   ├── kiosk-cycler.html          # HTML5 Playlist-Rotator (nahtloser URL-Wechsel)
│   ├── kiosk-cec-on.service       # Service zum Anschalten des TVs
│   ├── kiosk-cec-on.timer         # Timer: Täglich um 07:00 Uhr
│   ├── kiosk-cec-off.service      # Service für TV-Standby
│   └── kiosk-cec-off.timer        # Timer: Täglich um 19:00 Uhr
├── homeassistant/                 # Home Assistant Custom Component & Dokumentation
│   ├── README.md                  # Ausführliche Anleitung & Automationsvorlagen
│   └── custom_components/
│       └── dbs_kiosk/             # Das fertige Home Assistant Plugin
├── .gitattributes                 # Plattformübergreifende LF-Normalisierung
├── .gitignore                     # Ausschluss temporärer Dateien & Caches
└── README.md                      # Projektdokumentation
```

---

## 🔧 Nützliche Konsolenbefehle

### Kiosk-Dienst
```bash
# Status des Kiosk prüfen
sudo systemctl status kiosk.service

# Kiosk neu starten
sudo systemctl restart kiosk.service

# Live-Logs des Kiosks verfolgen
sudo journalctl -u kiosk.service -f
```

### HDMI-CEC TV-Steuerung manuell testen
```bash
# TV manuell einschalten und auf Raspberry Pi umschalten
sudo dbs-cec on

# TV manuell in Standby schalten
sudo dbs-cec off

# Stromstatus des TVs abfragen
sudo dbs-cec status

# Status der automatischen CEC-Timer anzeigen
systemctl list-timers | grep kiosk-cec
```

---

## 🔍 Fehlerbehebung (Troubleshooting)

### 1. Fernseher schaltet nicht per HDMI-CEC ein/aus
- Prüfe im Einstellungsmenü des Fernsehers, ob HDMI-CEC aktiviert ist (heißt je nach Hersteller: *Samsung Anynet+*, *Sony BRAVIA Sync*, *LG SimpLink*, *Philips EasyLink*, *Panasonic Viera Link*).
- Einige Fernseher unterstützen CEC nur an bestimmten HDMI-Ports (oft HDMI 1 oder ARC/eARC-Port).
- Teste die Kommunikation direkt in der Konsole:
  ```bash
  echo "scan" | cec-client -s -d 1
  ```
- Falls der Fernseher im Tiefschlaf ist, teste:
  ```bash
  sudo dbs-cec force-on
  ```

### 2. Bildschirm bleibt nach dem Booten schwarz
- Prüfe den Status des Kiosk-Dienstes:
  ```bash
  sudo systemctl status kiosk.service
  ```
- Prüfe, ob der Benutzer in der `seat` und `render` Gruppe ist:
  ```bash
  groups
  ```
- Stelle sicher, dass `seatd.service` läuft:
  ```bash
  sudo systemctl status seatd.service
  ```

### 3. WLAN verbindet sich nicht
- Nutze das Tool:
  ```bash
  sudo dbs-config
  ```
  und wähle Menüpunkt `1`.
- Alternativ per NetworkManager CLI:
  ```bash
  sudo nmcli dev wifi list
  sudo nmcli dev wifi connect "MEIN_WLAN" password "MEIN_PASSWORT"
  ```

---

## 📄 Lizenz
MIT License. Frei zur Nutzung und Anpassung für Bildungs- und Informationssysteme.
