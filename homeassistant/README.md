# dbsKioskPi - Home Assistant Integration 🏠🔔

Diese Integration verbindet deinen **dbsKioskPi** nahtlos mit **Home Assistant**.

## ✨ Funktionen in Home Assistant

- 📺 **HDMI TV Steuerung (CEC):**
  - Bildschirm direkt ein- oder ausschalten (`switch.hdmi_tv_bildschirm`).
  - Tägliche Einschalt- und Ausschaltzeiten (z. B. 07:00 / 19:00 Uhr) über Entitäten anpassen (`time.tv_einschaltzeit`, `time.tv_standby_zeit`).
- 🔔 **Schulglocke (MP3 Audio-System):**
  - MP3-Datei direkt von Home Assistant auf den KioskPi hochladen (`dbs_kiosk.upload_bell`).
  - Schulglocke per Tastendruck läuten (`button.schulglocke_lauten`).
  - Vollständig in Home Assistant Automationen integrierbar (z. B. zu Unterrichts- und Pausenzeiten).
- 📊 **Status-Sensoren:**
  - Kiosk-Dienststatus, Kiosk-URL und MP3-Glockendatei-Status.

---

## 📥 1. Installation in Home Assistant

### Option A: Manuelle Installation
1. Kopiere den Ordner `custom_components/dbs_kiosk` aus diesem Verzeichnis in das Verzeichnis deines Home Assistant Servers:
   ```
   /config/custom_components/dbs_kiosk/
   ```
   *(Du kannst dafür das Samba-Share Add-on, File Editor oder SSH nutzen)*
2. Starte Home Assistant neu (**Entwicklerwerkzeuge -> YAML -> Neu starten**).

---

## ⚙️ 2. Integration hinzufügen

1. Gehe in Home Assistant auf:
   **Einstellungen** -> **Geräte & Dienste** -> **Integration hinzufügen**
2. Suche nach **dbsKioskPi**.
3. Gib die Verbindungsdaten ein:
   - **IP-Adresse / Hostname:** Die IP des Raspberry Pi (z. B. `192.168.1.120`)
   - **Port:** `8088` (Standard)
   - **Benutzername:** Dein Linux-Benutzer auf dem Pi (z. B. `pi`)
   - **Passwort:** Dein Passwort für diesen Benutzer
4. Klicke auf **Absenden**. Home Assistant stellt die Verbindung her und richtet alle Entitäten automatisch ein.

---

## 🔔 3. Schulglocke MP3 einrichten

### Schritt 1: MP3 in Home Assistant ablegen
Lege deine gewünschte Glocken-MP3 (z. B. `schulglocke.mp3`) in den `/media` oder `/config` Ordner deines Home Assistant Systems.

### Schritt 2: MP3 auf den KioskPi übertragen
Gehe in Home Assistant auf **Entwicklerwerkzeuge** -> **Aktionen (Services)** und rufe folgenden Dienst auf:

```yaml
action: dbs_kiosk.upload_bell
data:
  file_path: "/media/schulglocke.mp3"
```
Die Datei wird sofort auf den Raspberry Pi nach `/var/lib/dbskiosk/sounds/bell.mp3` übertragen.

### Schritt 3: Testen
Drücke in deinem Home Assistant Dashboard einfach auf die Entität:
`button.schulglocke_lauten`
Die MP3 wird nun über den HDMI-Ausgang bzw. Audio-Port des Raspberry Pi abgespielt.

---

## ⏰ 4. Automations-Beispiel: Schulgong zu Unterrichtszeiten

Erstelle eine Automation in Home Assistant, um die Glocke montags bis freitags zu festen Zeiten automatisch läuten zu lassen:

```yaml
alias: "Schule: Schulglocke Pausengong"
description: "Läutet die Schulglocke zu festen Unterrichts- und Pausenzeiten"
trigger:
  - trigger: time
    at:
      - "07:55:00"  # Erster Gong vor Unterrichtsbeginn
      - "08:00:00"  # Unterrichtsbeginn 1. Stunde
      - "08:45:00"  # Ende 1. Stunde
      - "09:35:00"  # Beginn große Pause
      - "09:55:00"  # Ende große Pause
      - "11:30:00"  # Mittagspause
      - "13:00:00"  # Nachmittagsunterricht
condition:
  - condition: time
    weekday:
      - mon
      - tue
      - wed
      - thu
      - fri
action:
  - action: dbs_kiosk.play_bell
    data:
      volume: 100
mode: single
```

---

## 📺 5. Automations-Beispiel: Bildschirm morgens ein- und abends ausschalten

Obwohl der KioskPi über eigene interne Systemd-Timer verfügt (07:00 / 19:00 Uhr), kannst du den Bildschirm auch komplett flexibel über Home Assistant steuern:

```yaml
alias: "Kiosk: Bildschirm zu Schulzeiten steuern"
trigger:
  - trigger: time
    at: "07:00:00"
    id: "morgens"
  - trigger: time
    at: "18:00:00"
    id: "abends"
action:
  - choose:
      - conditions:
          - condition: trigger
            id: "morgens"
        sequence:
          - action: switch.turn_on
            target:
              entity_id: switch.hdmi_tv_bildschirm
      - conditions:
          - condition: trigger
            id: "abends"
        sequence:
          - action: switch.turn_off
            target:
              entity_id: switch.hdmi_tv_bildschirm
```
