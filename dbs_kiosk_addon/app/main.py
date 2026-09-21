#!/usr/bin/env python3
"""
dbsKioskPi Manager - Home Assistant Ingress Web Application
Provides zero-touch remote SSH setup, playlist/rotation management,
school bell schedule builder, and CEC hardware control.
"""

import os
import sys
import json
import time
import queue
import threading
import requests
from flask import Flask, render_template, request, jsonify, Response
from provisioner import SSHProvisioner

app = Flask(__name__)
DATA_DIR = "/data"
if not os.path.exists(DATA_DIR):
    DATA_DIR = os.path.dirname(__file__)

DEVICES_FILE = os.path.join(DATA_DIR, "devices.json")
OLD_SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
LOCAL_LOG_FILE = os.path.join(DATA_DIR, "dbskiosk-install.log")

# Queue for real-time log streaming
log_queue = queue.Queue(maxsize=1000)
is_provisioning = False


def load_fleet_data():
    """Load stored fleet devices data, migrating old settings.json if needed."""
    if os.path.exists(DEVICES_FILE):
        try:
            with open(DEVICES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    # Migration from old settings.json
    devices = []
    active_id = "kiosk_1"
    if os.path.exists(OLD_SETTINGS_FILE):
        try:
            with open(OLD_SETTINGS_FILE, "r", encoding="utf-8") as f:
                old = json.load(f)
                if old.get("host"):
                    devices.append({
                        "id": "kiosk_1",
                        "name": "Kiosk 1 (Standard)",
                        "host": old.get("host", ""),
                        "port": int(old.get("port", 22)),
                        "username": old.get("username", "dbsadmin"),
                        "password": old.get("password", ""),
                        "api_port": int(old.get("api_port", 8088)),
                        "bell_enabled": True,
                        "bell_volume": 80
                    })
        except Exception:
            pass

    if not devices:
        devices.append({
            "id": "kiosk_1",
            "name": "Kiosk 1",
            "host": "",
            "port": 22,
            "username": "dbsadmin",
            "password": "",
            "api_port": 8088,
            "bell_enabled": True,
            "bell_volume": 80
        })

    fleet_data = {
        "active_device_id": active_id,
        "central_bell_schedule": [],
        "devices": devices
    }
    save_fleet_data(fleet_data)
    return fleet_data


def save_fleet_data(data):
    """Save fleet devices data."""
    try:
        os.makedirs(os.path.dirname(DEVICES_FILE), exist_ok=True)
    except Exception:
        pass
    with open(DEVICES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def get_active_device(fleet_data=None, device_id=None):
    """Get the currently selected or specified device."""
    if not fleet_data:
        fleet_data = load_fleet_data()
    target_id = device_id or fleet_data.get("active_device_id")
    devices = fleet_data.get("devices", [])
    for dev in devices:
        if dev.get("id") == target_id:
            return dev
    if devices:
        return devices[0]
    return {
        "id": "kiosk_1",
        "name": "Kiosk 1",
        "host": "",
        "port": 22,
        "username": "dbsadmin",
        "password": "",
        "api_port": 8088,
        "bell_enabled": True,
        "bell_volume": 80
    }


def mask_device(dev):
    """Return a copy of device dictionary with masked password."""
    masked = dict(dev)
    has_pwd = bool(masked.get("password"))
    masked["has_password"] = has_pwd
    masked["password"] = "••••••••" if has_pwd else ""
    return masked


def get_pi_auth(device):
    """Returns requests HTTP basic auth tuple."""
    return (device.get("username", "dbsadmin"), device.get("password", ""))


def get_pi_api_base(device):
    """Returns base URL for the Pi REST API."""
    host = device.get("host", "127.0.0.1")
    port = device.get("api_port", 8088)
    return f"http://{host}:{port}"


# ------------------------------------------------------------------------------
# Frontend Views
# ------------------------------------------------------------------------------
@app.route("/")
def index():
    ingress_path = request.headers.get("X-Ingress-Path", "")
    fleet = load_fleet_data()
    active_dev = get_active_device(fleet)
    masked_dev = mask_device(active_dev)
    masked_devices = [mask_device(d) for d in fleet.get("devices", [])]
    return render_template(
        "index.html",
        ingress_path=ingress_path,
        settings=masked_dev,
        devices=masked_devices,
        active_device_id=fleet.get("active_device_id", "kiosk_1")
    )


# ------------------------------------------------------------------------------
# Fleet & Device Management Endpoints
# ------------------------------------------------------------------------------
@app.route("/api/devices", methods=["GET", "POST"])
def handle_devices():
    fleet = load_fleet_data()
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        dev_id = data.get("id", "").strip()
        name = data.get("name", "").strip() or "Neuer Kiosk"
        host = data.get("host", "").strip()
        port = int(data.get("port", 22))
        username = data.get("username", "dbsadmin").strip()
        password = data.get("password", "")
        api_port = int(data.get("api_port", 8088))
        bell_enabled = bool(data.get("bell_enabled", True))
        bell_volume = int(data.get("bell_volume", 80))

        # Check if updating existing device
        existing = None
        for dev in fleet.get("devices", []):
            if dev.get("id") == dev_id:
                existing = dev
                break

        if existing:
            existing["name"] = name
            existing["host"] = host
            existing["port"] = port
            existing["username"] = username
            if password and password != "••••••••":
                existing["password"] = password
            existing["api_port"] = api_port
            existing["bell_enabled"] = bell_enabled
            existing["bell_volume"] = bell_volume
        else:
            # Create new device
            import uuid
            new_id = dev_id if dev_id else f"kiosk_{uuid.uuid4().hex[:6]}"
            new_dev = {
                "id": new_id,
                "name": name,
                "host": host,
                "port": port,
                "username": username,
                "password": password if password != "••••••••" else "",
                "api_port": api_port,
                "bell_enabled": bell_enabled,
                "bell_volume": bell_volume
            }
            fleet.setdefault("devices", []).append(new_dev)
            fleet["active_device_id"] = new_id

        save_fleet_data(fleet)
        return jsonify({"success": True, "message": "Gerät gespeichert", "devices": [mask_device(d) for d in fleet["devices"]]})

    # GET: Return all devices
    masked = [mask_device(d) for d in fleet.get("devices", [])]
    return jsonify({
        "active_device_id": fleet.get("active_device_id"),
        "devices": masked
    })


@app.route("/api/devices/select", methods=["POST"])
def select_device():
    data = request.get_json(silent=True) or {}
    dev_id = data.get("id")
    fleet = load_fleet_data()
    found = any(d.get("id") == dev_id for d in fleet.get("devices", []))
    if not found:
        return jsonify({"success": False, "error": "Gerät nicht gefunden"}), 404
    fleet["active_device_id"] = dev_id
    save_fleet_data(fleet)
    active = get_active_device(fleet, dev_id)
    return jsonify({"success": True, "active_device": mask_device(active)})


@app.route("/api/devices/delete", methods=["POST"])
def delete_device():
    data = request.get_json(silent=True) or {}
    dev_id = data.get("id")
    fleet = load_fleet_data()
    devices = fleet.get("devices", [])
    if len(devices) <= 1:
        return jsonify({"success": False, "error": "Mindestens ein Gerät muss erhalten bleiben"}), 400

    new_devices = [d for d in devices if d.get("id") != dev_id]
    if len(new_devices) == len(devices):
        return jsonify({"success": False, "error": "Gerät nicht gefunden"}), 404

    fleet["devices"] = new_devices
    if fleet.get("active_device_id") == dev_id:
        fleet["active_device_id"] = new_devices[0]["id"]

    save_fleet_data(fleet)
    return jsonify({"success": True, "devices": [mask_device(d) for d in new_devices]})


@app.route("/api/fleet/status")
def fleet_status():
    """Poll live status for all devices in parallel for the fleet overview."""
    fleet = load_fleet_data()
    devices = fleet.get("devices", [])
    results = []

    def check_dev(dev):
        masked = mask_device(dev)
        host = dev.get("host")
        if not host:
            masked["status"] = "unconfigured"
            masked["online"] = False
            return masked

        base_url = get_pi_api_base(dev)
        try:
            resp = requests.get(f"{base_url}/api/status", auth=get_pi_auth(dev), timeout=2.5)
            if resp.status_code == 200:
                data = resp.json()
                masked["online"] = True
                masked["status"] = "online"
                masked["live_status"] = data
            else:
                masked["online"] = False
                masked["status"] = "error"
        except Exception:
            masked["online"] = False
            masked["status"] = "offline"
        return masked

    threads = []
    res_queue = queue.Queue()
    for dev in devices:
        t = threading.Thread(target=lambda d: res_queue.put(check_dev(d)), args=(dev,))
        threads.append(t)
        t.start()
    for t in threads:
        t.join(timeout=3.0)

    while not res_queue.empty():
        results.append(res_queue.get())

    # Keep original order
    ordered = []
    for dev in devices:
        for r in results:
            if r.get("id") == dev.get("id"):
                ordered.append(r)
                break

    return jsonify({"devices": ordered, "active_device_id": fleet.get("active_device_id")})


def trigger_device_power_action(device, action="shutdown"):
    """
    Triggers shutdown or reboot on a device.
    Uses REST-API and SSH (with sudo -S and aggressive flags) to guarantee execution.
    """
    host = device.get("host")
    if not host:
        return {"success": False, "error": "Keine IP-Adresse hinterlegt"}

    action_label = "Herunterfahren" if action == "shutdown" else "Neustarten"
    api_endpoint = "/api/system/shutdown" if action == "shutdown" else "/api/system/reboot"
    password = device.get("password", "")
    username = device.get("username", "dbsadmin")
    port = int(device.get("port", 22))

    if action == "shutdown":
        ssh_inner = f"echo '{password}' | sudo -S systemctl poweroff -i --no-block 2>/dev/null || echo '{password}' | sudo -S poweroff -f 2>/dev/null || echo '{password}' | sudo -S shutdown -h now 2>/dev/null || echo '{password}' | sudo -S sh -c 'echo 1 > /proc/sys/kernel/sysrq && echo o > /proc/sysrq-trigger' 2>/dev/null"
    else:
        ssh_inner = f"echo '{password}' | sudo -S systemctl reboot -i --no-block 2>/dev/null || echo '{password}' | sudo -S reboot -f 2>/dev/null || echo '{password}' | sudo -S shutdown -r now 2>/dev/null || echo '{password}' | sudo -S sh -c 'echo 1 > /proc/sys/kernel/sysrq && echo b > /proc/sysrq-trigger' 2>/dev/null"

    # 1. Try REST API
    api_worked = False
    try:
        base_url = get_pi_api_base(device)
        resp = requests.post(f"{base_url}{api_endpoint}", auth=get_pi_auth(device), timeout=3)
        if resp.status_code == 200:
            api_worked = True
    except Exception:
        pass

    # 2. Also trigger via SSH if password is known to guarantee the power action takes effect
    # (crucial if an older daemon is on the Pi or inhibitor locks blocked systemd)
    ssh_worked = False
    if password:
        try:
            import paramiko
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(hostname=host, port=port, username=username, password=password, timeout=4)
            client.exec_command(f"nohup sh -c 'sleep 1; {ssh_inner}' >/dev/null 2>&1 &")
            client.close()
            ssh_worked = True
        except Exception:
            pass

    if api_worked or ssh_worked:
        method = "API & SSH" if (api_worked and ssh_worked) else ("API" if api_worked else "SSH")
        return {
            "success": True,
            "method": method,
            "message": f"Gerät '{device.get('name')}' wird per {method} {action_label.lower()}."
        }

    return {"success": False, "error": f"Gerät '{device.get('name')}' konnte weder per API noch per SSH erreicht werden"}


@app.route("/api/fleet/action", methods=["POST"])
def fleet_action():
    """Execute action across all devices (screen_on, screen_off, reload, shutdown, reboot)."""
    data = request.get_json(silent=True) or {}
    action = data.get("action")
    target_ids = data.get("device_ids")

    fleet = load_fleet_data()
    devices = fleet.get("devices", [])
    if target_ids:
        devices = [d for d in devices if d.get("id") in target_ids]

    def do_action(dev):
        base_url = get_pi_api_base(dev)
        auth = get_pi_auth(dev)
        try:
            if action == "screen_on":
                requests.post(f"{base_url}/api/screen", json={"state": "on"}, auth=auth, timeout=4)
            elif action == "screen_off":
                requests.post(f"{base_url}/api/screen", json={"state": "off"}, auth=auth, timeout=4)
            elif action == "reload":
                requests.post(f"{base_url}/api/kiosk/reload", json={}, auth=auth, timeout=4)
            elif action == "restart_kiosk":
                requests.post(f"{base_url}/api/kiosk/restart", json={}, auth=auth, timeout=4)
            elif action == "shutdown":
                trigger_device_power_action(dev, "shutdown")
            elif action == "reboot":
                trigger_device_power_action(dev, "reboot")
        except Exception:
            pass

    for dev in devices:
        threading.Thread(target=do_action, args=(dev,), daemon=True).start()

    return jsonify({"success": True, "message": f"Aktion '{action}' an {len(devices)} Displays gesendet"})



@app.route("/api/kiosk/copy-playlist", methods=["POST"])
def copy_playlist():
    """Copy playlist from source device to target devices."""
    data = request.get_json(silent=True) or {}
    source_id = data.get("source_device_id")
    target_ids = data.get("target_device_ids", [])

    if not source_id or not target_ids:
        return jsonify({"success": False, "error": "Quelle und Ziele müssen angegeben werden"}), 400

    fleet = load_fleet_data()
    source_dev = get_active_device(fleet, source_id)
    if not source_dev:
        return jsonify({"success": False, "error": "Quellgerät nicht gefunden"}), 404

    base_url = get_pi_api_base(source_dev)
    try:
        resp = requests.get(f"{base_url}/api/kiosk/playlist", auth=get_pi_auth(source_dev), timeout=5)
        if resp.status_code != 200:
            return jsonify({"success": False, "error": "Konnte Playlist von Quellgerät nicht laden"}), 502
        playlist_data = resp.json()
    except Exception as e:
        return jsonify({"success": False, "error": f"Verbindungsfehler zur Quelle: {e}"}), 502

    copied = 0
    errors = []
    for dev in fleet.get("devices", []):
        if dev.get("id") in target_ids and dev.get("id") != source_id:
            try:
                t_base = get_pi_api_base(dev)
                t_resp = requests.post(f"{t_base}/api/kiosk/playlist", json=playlist_data, auth=get_pi_auth(dev), timeout=5)
                if t_resp.status_code == 200:
                    copied += 1
                else:
                    errors.append(f"{dev.get('name')}: Status {t_resp.status_code}")
            except Exception as e:
                errors.append(f"{dev.get('name')}: {e}")

    return jsonify({
        "success": True,
        "copied": copied,
        "errors": errors,
        "message": f"Playlist erfolgreich auf {copied} Display(s) übertragen"
    })


# Compatibility endpoint
@app.route("/api/settings", methods=["GET", "POST"])
def handle_settings():
    fleet = load_fleet_data()
    dev = get_active_device(fleet)
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        if data.get("name"):
            dev["name"] = data.get("name").strip()
        dev["host"] = data.get("host", "").strip()
        dev["port"] = int(data.get("port", 22))
        dev["username"] = data.get("username", "dbsadmin").strip()
        if data.get("password") and data.get("password") != "••••••••":
            dev["password"] = data["password"]
        dev["api_port"] = int(data.get("api_port", 8088))
        if "bell_enabled" in data:
            dev["bell_enabled"] = bool(data["bell_enabled"])
        if "bell_volume" in data:
            dev["bell_volume"] = int(data["bell_volume"])
        save_fleet_data(fleet)
        return jsonify({"success": True, "message": "Einstellungen gespeichert"})

    return jsonify(mask_device(dev))


# ------------------------------------------------------------------------------
# Remote SSH Provisioning
# ------------------------------------------------------------------------------
@app.route("/api/test-ssh", methods=["POST"])
def test_ssh():
    data = request.get_json(silent=True) or {}
    fleet = load_fleet_data()
    dev_id = data.get("device_id")
    device = get_active_device(fleet, dev_id)

    host = data.get("host") or device.get("host")
    port = int(data.get("port") or device.get("port", 22))
    username = data.get("username") or device.get("username", "dbsadmin")
    password = data.get("password")
    if not password or password == "••••••••":
        password = device.get("password", "")

    if not host:
        return jsonify({"success": False, "error": "Bitte IP-Adresse eingeben"}), 400

    provisioner = SSHProvisioner(host=host, port=port, username=username, password=password)
    result = provisioner.test_connection()
    if result.get("success"):
        device["host"] = host
        device["port"] = port
        device["username"] = username
        if password and password != "••••••••":
            device["password"] = password
        if data.get("name"):
            device["name"] = data.get("name").strip()
        save_fleet_data(fleet)

        # Automatische Aktualisierung des dbs-api Dienstes auf dem Zielsystem
        deploy_latest_dbs_api(device)

    return jsonify(result)


@app.route("/api/provision/start", methods=["POST"])
def start_provisioning():
    global is_provisioning
    if is_provisioning:
        return jsonify({"success": False, "error": "Eine Installation läuft bereits!"}), 400

    data = request.get_json(silent=True) or {}
    fleet = load_fleet_data()
    dev_id = data.get("device_id")
    device = get_active_device(fleet, dev_id)

    host = data.get("host") or device.get("host")
    port = int(data.get("port") or device.get("port", 22))
    username = data.get("username") or device.get("username", "dbsadmin")
    password = data.get("password")
    if not password or password == "••••••••":
        password = device.get("password", "")

    if not host or not password:
        return jsonify({"success": False, "error": "IP-Adresse und Passwort sind erforderlich"}), 400

    device["host"] = host
    device["port"] = port
    device["username"] = username
    device["password"] = password
    if data.get("name"):
        device["name"] = data.get("name").strip()
    save_fleet_data(fleet)

    # Empty queue
    while not log_queue.empty():
        try:
            log_queue.get_nowait()
        except Exception:
            break

    try:
        with open(LOCAL_LOG_FILE, "w", encoding="utf-8") as f:
            f.write(f"=== dbsKioskPi Installation gestartet am {time.strftime('%Y-%m-%d %H:%M:%S')} für {device.get('name')} ({host}) ===\n")
    except Exception:
        pass

    def run_worker():
        global is_provisioning
        is_provisioning = True

        def log_cb(msg):
            log_queue.put(msg)
            try:
                with open(LOCAL_LOG_FILE, "a", encoding="utf-8") as f:
                    f.write(f"{msg}\n")
            except Exception:
                pass

        log_cb(f"[START] Starte Remote-Provisioning für {device.get('name')} ({host})...")
        prov = SSHProvisioner(host=host, port=port, username=username, password=password)
        res = prov.run_installation(log_callback=log_cb)

        if res.get("success"):
            log_cb("[FERTIG] Provisioning erfolgreich abgeschlossen! System rebootet.")
        else:
            log_cb(f"[ABBRUCH] Fehler: {res.get('error')}")

        is_provisioning = False
        log_queue.put("__DONE__")

    thread = threading.Thread(target=run_worker, daemon=True)
    thread.start()

    return jsonify({"success": True, "message": "Installation gestartet"})


@app.route("/api/provision/download-log")
def download_provision_log():
    """Download the local log created during provisioning."""
    if os.path.exists(LOCAL_LOG_FILE):
        try:
            with open(LOCAL_LOG_FILE, "rb") as f:
                content = f.read()
            return Response(
                content,
                mimetype="text/plain; charset=utf-8",
                headers={"Content-Disposition": "inline; filename=dbskiosk-install.txt"}
            )
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    return "Noch kein Installationslog vorhanden.", 404


@app.route("/api/pi/download-install-log")
def download_pi_install_log():
    """Download the actual installation log from the target Raspberry Pi."""
    fleet = load_fleet_data()
    dev_id = request.args.get("device_id")
    device = get_active_device(fleet, dev_id)

    host = device.get("host")
    port = int(device.get("port", 22))
    username = device.get("username", "dbsadmin")
    password = device.get("password", "")
    api_port = int(device.get("api_port", 8088))

    if not host:
        return jsonify({"error": "Keine IP-Adresse konfiguriert"}), 400

    # 1. Versuch: Über REST-API (Port 8088)
    try:
        url = f"http://{host}:{api_port}/api/logs/install"
        resp = requests.get(url, auth=(username, password), timeout=4)
        if resp.status_code == 200 and resp.content:
            return Response(
                resp.content,
                mimetype="text/plain; charset=utf-8",
                headers={"Content-Disposition": f"inline; filename=dbskiosk-install-{device.get('id')}.txt"}
            )
    except Exception:
        pass

    # 2. Versuch: Über SSH/SFTP direkt von /var/log/dbskiosk-install.log
    if password:
        try:
            import paramiko
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(hostname=host, port=port, username=username, password=password, timeout=6)
            sftp = client.open_sftp()
            with sftp.open("/var/log/dbskiosk-install.log", "r") as f:
                content = f.read()
            sftp.close()
            client.close()
            return Response(
                content,
                mimetype="text/plain; charset=utf-8",
                headers={"Content-Disposition": f"inline; filename=dbskiosk-install-{device.get('id')}.txt"}
            )
        except Exception:
            pass

    # 3. Fallback auf das lokale Provisioning-Log
    if os.path.exists(LOCAL_LOG_FILE):
        try:
            with open(LOCAL_LOG_FILE, "rb") as f:
                content = f.read()
            return Response(
                content,
                mimetype="text/plain; charset=utf-8",
                headers={"Content-Disposition": "inline; filename=dbskiosk-install.txt"}
            )
        except Exception:
            pass

    return jsonify({"error": "Installationslog konnte nicht gefunden werden"}), 404


@app.route("/api/pi/download-config-log")
def download_pi_config_log():
    """Download the configuration change log from the Raspberry Pi (/var/log/dbskiosk-config.log)."""
    fleet = load_fleet_data()
    dev_id = request.args.get("device_id")
    device = get_active_device(fleet, dev_id)

    host = device.get("host")
    port = int(device.get("port", 22))
    username = device.get("username", "dbsadmin")
    password = device.get("password", "")
    api_port = int(device.get("api_port", 8088))

    if not host:
        return jsonify({"error": "Keine IP-Adresse konfiguriert"}), 400

    try:
        url = f"http://{host}:{api_port}/api/logs/config"
        resp = requests.get(url, auth=(username, password), timeout=4)
        if resp.status_code == 200 and resp.content:
            return Response(
                resp.content,
                mimetype="text/plain; charset=utf-8",
                headers={"Content-Disposition": f"attachment; filename=dbskiosk-config-{device.get('id')}.log"}
            )
    except Exception:
        pass

    if password:
        try:
            import paramiko
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(hostname=host, port=port, username=username, password=password, timeout=6)
            sftp = client.open_sftp()
            with sftp.open("/var/log/dbskiosk-config.log", "r") as f:
                content = f.read()
            sftp.close()
            client.close()
            return Response(
                content,
                mimetype="text/plain; charset=utf-8",
                headers={"Content-Disposition": f"attachment; filename=dbskiosk-config-{device.get('id')}.log"}
            )
        except Exception as e:
            return jsonify({"error": f"Konfigurationslog nicht verfügbar: {e}"}), 404

    return jsonify({"error": "Konfigurationslog nicht verfügbar"}), 404


def deploy_latest_dbs_api(device):
    """
    Deploys the latest dbs-api and dbs-healthcheck onto the target Pi via SSH/SFTP
    and restarts dbs-api.service.
    """
    host = device.get("host")
    port = int(device.get("port", 22))
    username = device.get("username", "dbsadmin")
    password = device.get("password", "")

    if not host or not password:
        return {"success": False, "error": "IP-Adresse oder Passwort fehlt"}

    try:
        import paramiko
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(hostname=host, port=port, username=username, password=password, timeout=8)

        # Update api_auth.conf
        client.exec_command(f"echo '{password}' | sudo -S sh -c \"echo '{username}:{password}' > /etc/dbskiosk/api_auth.conf && chmod 600 /etc/dbskiosk/api_auth.conf\"")

        # Find dbs-api.py
        candidates_api = [
            os.path.join(os.path.dirname(__file__), "..", "package", "files", "dbs-api.py"),
            os.path.join(os.path.dirname(__file__), "..", "..", "files", "dbs-api.py"),
            "/app/package/files/dbs-api.py"
        ]
        pkg_api = next((p for p in candidates_api if os.path.exists(p)), None)

        if pkg_api:
            sftp = client.open_sftp()
            sftp.put(pkg_api, "/tmp/dbs-api.py")
            sftp.close()
            client.exec_command(f"echo '{password}' | sudo -S cp /tmp/dbs-api.py /usr/local/bin/dbs-api && echo '{password}' | sudo -S chmod 755 /usr/local/bin/dbs-api && echo '{password}' | sudo -S systemctl restart dbs-api.service")

        # Find dbs-healthcheck.sh
        candidates_hc = [
            os.path.join(os.path.dirname(__file__), "..", "package", "files", "dbs-healthcheck.sh"),
            os.path.join(os.path.dirname(__file__), "..", "..", "files", "dbs-healthcheck.sh"),
            "/app/package/files/dbs-healthcheck.sh"
        ]
        pkg_hc = next((p for p in candidates_hc if os.path.exists(p)), None)
        if pkg_hc:
            sftp = client.open_sftp()
            sftp.put(pkg_hc, "/tmp/dbs-healthcheck.sh")
            sftp.close()
            client.exec_command(f"echo '{password}' | sudo -S cp /tmp/dbs-healthcheck.sh /usr/local/bin/dbs-healthcheck && echo '{password}' | sudo -S chmod 755 /usr/local/bin/dbs-healthcheck")

        client.close()
        return {"success": True, "message": f"dbs-api Hintergrunddienst auf '{device.get('name')}' ({host}) erfolgreich aktualisiert und neu gestartet."}
    except Exception as e:
        return {"success": False, "error": f"SSH Fehler beim Aktualisieren von dbs-api: {str(e)}"}


@app.route("/api/pi/update-agent", methods=["POST"])
def update_pi_agent():
    """Uploads the latest dbs-api and restarts the service on the target Raspberry Pi."""
    fleet = load_fleet_data()
    data = request.get_json(silent=True) or {}
    dev_id = data.get("device_id") or request.args.get("device_id")
    device = get_active_device(fleet, dev_id)
    res = deploy_latest_dbs_api(device)
    return jsonify(res), (200 if res.get("success") else 500)


@app.route("/api/pi/download-comm-log")
def download_pi_comm_log():
    """Download the recent communication log from the Raspberry Pi (default: last 10 minutes)."""
    fleet = load_fleet_data()
    dev_id = request.args.get("device_id")
    minutes = request.args.get("minutes", "10")
    try:
        minutes_int = int(minutes)
    except Exception:
        minutes_int = 10

    device = get_active_device(fleet, dev_id)
    host = device.get("host")
    port = int(device.get("port", 22))
    username = device.get("username", "dbsadmin")
    password = device.get("password", "")
    api_port = int(device.get("api_port", 8088))

    if not host:
        return jsonify({"error": "Keine IP-Adresse konfiguriert"}), 400

    filename = f"dbskiosk-comm-{device.get('id', 'kiosk')}-last{minutes_int}min.log"

    # 1. Versuch: Über REST-API (Port 8088)
    try:
        url = f"http://{host}:{api_port}/api/logs/communication?minutes={minutes_int}"
        resp = requests.get(url, auth=get_pi_auth(device), timeout=5)
        if resp.status_code == 200 and resp.content:
            return Response(
                resp.content,
                mimetype="text/plain; charset=utf-8",
                headers={"Content-Disposition": f"inline; filename={filename}"}
            )
    except Exception:
        pass

    # 2. Versuch: Über SSH/SFTP direkt von /var/log/dbskiosk-comm.log
    if password:
        try:
            import paramiko
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(hostname=host, port=port, username=username, password=password, timeout=6)
            sftp = client.open_sftp()
            full_log = ""
            try:
                with sftp.open("/var/log/dbskiosk-comm.log", "r") as f:
                    full_log = f.read().decode("utf-8", errors="replace")
            except Exception:
                pass
            sftp.close()
            client.close()

            if full_log:
                if minutes_int > 0:
                    from datetime import datetime, timedelta
                    cutoff = datetime.now() - timedelta(minutes=minutes_int)
                    filtered_lines = []
                    for line in full_log.splitlines():
                        if line.startswith("[") and len(line) >= 21 and line[20] == "]":
                            try:
                                t = datetime.strptime(line[1:20], "%Y-%m-%d %H:%M:%S")
                                if t >= cutoff:
                                    filtered_lines.append(line)
                            except Exception:
                                filtered_lines.append(line)
                        else:
                            if filtered_lines:
                                filtered_lines.append(line)
                    out_text = f"=== dbsKioskPi Kommunikationsprotokoll (SSH-Fallback, letzte {minutes_int} Minuten) ===\n\n"
                    out_text += "\n".join(filtered_lines) if filtered_lines else f"(Keine Einträge in den letzten {minutes_int} Minuten gefunden)\n"
                else:
                    out_text = full_log

                return Response(
                    out_text.encode("utf-8"),
                    mimetype="text/plain; charset=utf-8",
                    headers={"Content-Disposition": f"inline; filename={filename}"}
                )
        except Exception:
            pass

    return jsonify({"error": f"Kommunikationslog der letzten {minutes_int} Minuten für '{device.get('name')}' nicht verfügbar"}), 404


@app.route("/api/pi/healthcheck")
def download_pi_healthcheck():
    """Download or view the system healthcheck diagnostic report."""
    fleet = load_fleet_data()
    dev_id = request.args.get("device_id")
    device = get_active_device(fleet, dev_id)

    host = device.get("host")
    port = int(device.get("port", 22))
    username = device.get("username", "dbsadmin")
    password = device.get("password", "")
    api_port = int(device.get("api_port", 8088))

    if not host:
        return jsonify({"error": "Keine IP-Adresse konfiguriert"}), 400

    # 1. Versuche über REST-API
    try:
        url = f"http://{host}:{api_port}/api/healthcheck"
        resp = requests.get(url, auth=(username, password), timeout=6)
        if resp.status_code == 200 and resp.content:
            return Response(
                resp.content,
                mimetype="text/plain; charset=utf-8",
                headers={"Content-Disposition": f"inline; filename=dbskiosk-healthcheck-{device.get('id')}.txt"}
            )
    except Exception:
        pass

    # 2. Versuche über SSH
    if password:
        try:
            import paramiko
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(hostname=host, port=port, username=username, password=password, timeout=8)
            content = None

            sftp = client.open_sftp()
            try:
                with sftp.open("/var/log/dbskiosk-healthcheck.log", "r") as f:
                    content = f.read()
            except Exception:
                pass
            sftp.close()

            if not content:
                # Prüfe und installiere ggf. dbs-healthcheck
                stdin, stdout, stderr = client.exec_command("[ -x /usr/local/bin/dbs-healthcheck ] && echo 'exists'")
                if stdout.read().decode().strip() != "exists":
                    pkg_hc = os.path.join(os.path.dirname(__file__), "..", "package", "files", "dbs-healthcheck.sh")
                    if not os.path.exists(pkg_hc):
                        pkg_hc = "/app/package/files/dbs-healthcheck.sh"
                    if os.path.exists(pkg_hc):
                        sftp = client.open_sftp()
                        sftp.put(pkg_hc, "/tmp/dbs-healthcheck.sh")
                        sftp.close()
                        client.exec_command(f"echo '{password}' | sudo -S cp /tmp/dbs-healthcheck.sh /usr/local/bin/dbs-healthcheck && echo '{password}' | sudo -S chmod 755 /usr/local/bin/dbs-healthcheck")

                stdin, stdout, stderr = client.exec_command(f"echo '{password}' | sudo -S /usr/local/bin/dbs-healthcheck", timeout=25)
                content = stdout.read()

            client.close()
            if content:
                return Response(
                    content,
                    mimetype="text/plain; charset=utf-8",
                    headers={"Content-Disposition": f"inline; filename=dbskiosk-healthcheck-{device.get('id')}.txt"}
                )
        except Exception as e:
            return jsonify({"error": f"Healthcheck nicht erreichbar: {e}"}), 500

    return jsonify({"error": "Healthcheck-Bericht nicht verfügbar"}), 404


@app.route("/api/pi/healthcheck/run", methods=["POST", "GET"])
def run_pi_healthcheck():
    """Trigger a fresh live healthcheck run on the target Raspberry Pi."""
    fleet = load_fleet_data()
    data = request.get_json(silent=True) or {}
    dev_id = data.get("device_id") or request.args.get("device_id")
    device = get_active_device(fleet, dev_id)

    host = device.get("host")
    port = int(device.get("port", 22))
    username = device.get("username", "dbsadmin")
    password = device.get("password", "")
    api_port = int(device.get("api_port", 8088))

    if not host:
        return jsonify({"success": False, "error": "Keine IP-Adresse konfiguriert"}), 400

    # 1. Versuche über REST-API
    try:
        url = f"http://{host}:{api_port}/api/healthcheck/run"
        resp = requests.post(url, auth=(username, password), timeout=25)
        if resp.status_code == 200:
            api_data = resp.json()
            if api_data.get("success") and api_data.get("output"):
                return jsonify(api_data)
    except Exception:
        pass

    # 2. Versuche über SSH
    if password:
        try:
            import paramiko
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(hostname=host, port=port, username=username, password=password, timeout=8)

            # Prüfe ob /usr/local/bin/dbs-healthcheck auf dem Pi existiert, andernfalls hochladen
            stdin, stdout, stderr = client.exec_command("[ -x /usr/local/bin/dbs-healthcheck ] && echo 'exists'")
            if stdout.read().decode().strip() != "exists":
                pkg_hc = os.path.join(os.path.dirname(__file__), "..", "package", "files", "dbs-healthcheck.sh")
                if not os.path.exists(pkg_hc):
                    pkg_hc = "/app/package/files/dbs-healthcheck.sh"
                if os.path.exists(pkg_hc):
                    sftp = client.open_sftp()
                    sftp.put(pkg_hc, "/tmp/dbs-healthcheck.sh")
                    sftp.close()
                    client.exec_command(f"echo '{password}' | sudo -S cp /tmp/dbs-healthcheck.sh /usr/local/bin/dbs-healthcheck && echo '{password}' | sudo -S chmod 755 /usr/local/bin/dbs-healthcheck")

            # Healthcheck via SSH ausführen (mit sudo-Passwort Übergabe)
            cmd = f"echo '{password}' | sudo -S /usr/local/bin/dbs-healthcheck"
            stdin, stdout, stderr = client.exec_command(cmd, timeout=30)
            output = stdout.read().decode("utf-8", errors="replace")
            err_output = stderr.read().decode("utf-8", errors="replace")

            # Falls stdout leer, versuche direkt das Logfile zu lesen
            if not output.strip():
                try:
                    sftp = client.open_sftp()
                    with sftp.open("/var/log/dbskiosk-healthcheck.log", "r") as f:
                        output = f.read().decode("utf-8", errors="replace")
                    sftp.close()
                except Exception:
                    pass

            client.close()

            if output.strip():
                return jsonify({"success": True, "output": output})
            else:
                err_msg = err_output.strip() or "Healthcheck lieferte keine Ausgabe"
                return jsonify({"success": False, "error": err_msg}), 500
        except Exception as e:
            return jsonify({"success": False, "error": f"SSH Fehler: {str(e)}"}), 500

    return jsonify({"success": False, "error": "Keine Verbindung zum Pi möglich (weder per API noch per SSH)"}), 500


@app.route("/api/provision/stream")
def provision_stream():
    """SSE Stream providing real-time installation logs."""
    def event_stream():
        while True:
            try:
                line = log_queue.get(timeout=25)
                if line == "__DONE__":
                    yield "data: [SYSTEM] PROVISIONING_COMPLETE\n\n"
                    break
                yield f"data: {line}\n\n"
            except queue.Empty:
                yield ": keepalive\n\n"

    return Response(event_stream(), mimetype="text/event-stream")


# ------------------------------------------------------------------------------
# Proxy Endpoints to Raspberry Pi REST-API
# ------------------------------------------------------------------------------
@app.route("/api/kiosk/status")
def get_kiosk_status():
    fleet = load_fleet_data()
    dev_id = request.args.get("device_id")
    device = get_active_device(fleet, dev_id)
    base_url = get_pi_api_base(device)
    try:
        resp = requests.get(f"{base_url}/api/status", auth=get_pi_auth(device), timeout=4)
        return Response(resp.content, status=resp.status_code, content_type="application/json")
    except Exception as e:
        return jsonify({"error": "Pi nicht erreichbar", "details": str(e), "status": "offline"}), 503


@app.route("/api/kiosk/playlist", methods=["GET", "POST"])
def handle_playlist():
    fleet = load_fleet_data()
    dev_id = request.args.get("device_id")
    payload = []
    if request.method == "POST":
        data = request.get_json(silent=True)
        if isinstance(data, dict):
            dev_id = data.get("device_id") or dev_id
            payload = data.get("playlist", data)
        elif isinstance(data, list):
            payload = data
        else:
            payload = []
    device = get_active_device(fleet, dev_id)
    base_url = get_pi_api_base(device)
    try:
        if request.method == "POST":
            resp = requests.post(f"{base_url}/api/kiosk/playlist", json=payload, auth=get_pi_auth(device), timeout=8)
        else:
            resp = requests.get(f"{base_url}/api/kiosk/playlist", auth=get_pi_auth(device), timeout=4)

        try:
            resp_data = resp.json()
            return jsonify(resp_data), resp.status_code
        except Exception:
            if resp.status_code == 200:
                return jsonify({"success": True, "message": resp.text[:200]}), 200
            else:
                return jsonify({
                    "success": False,
                    "error": f"Display antwortete mit HTTP {resp.status_code}: {resp.text[:200]}"
                }), resp.status_code
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 503


@app.route("/api/bell/schedule", methods=["GET", "POST"])
def handle_bell_schedule():
    fleet = load_fleet_data()
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        fleet["central_bell_schedule"] = data.get("schedule", [])
        save_fleet_data(fleet)

        # Distribute schedule to all fleet devices that have bell_enabled
        synced = 0
        for dev in fleet.get("devices", []):
            if dev.get("bell_enabled", True) and dev.get("host"):
                try:
                    b_url = get_pi_api_base(dev)
                    requests.post(f"{b_url}/api/bell/schedule", json=data, auth=get_pi_auth(dev), timeout=4)
                    synced += 1
                except Exception:
                    pass

        return jsonify({"success": True, "message": f"Glockenplan gespeichert und an {synced} Display(s) verteilt", "schedule": fleet["central_bell_schedule"]})

    # GET: If central schedule exists return it, otherwise try to load from active device
    if fleet.get("central_bell_schedule"):
        return jsonify({"schedule": fleet["central_bell_schedule"]})

    dev_id = request.args.get("device_id")
    device = get_active_device(fleet, dev_id)
    base_url = get_pi_api_base(device)
    try:
        resp = requests.get(f"{base_url}/api/bell/schedule", auth=get_pi_auth(device), timeout=4)
        if resp.status_code == 200:
            sched = resp.json().get("schedule", [])
            fleet["central_bell_schedule"] = sched
            save_fleet_data(fleet)
        return Response(resp.content, status=resp.status_code, content_type="application/json")
    except Exception as e:
        return jsonify({"error": str(e), "schedule": []}), 200


@app.route("/api/bell/play", methods=["POST"])
def play_bell():
    fleet = load_fleet_data()
    data = request.get_json(silent=True) or {}
    dev_id = data.get("device_id") or request.args.get("device_id")
    device = get_active_device(fleet, dev_id)
    base_url = get_pi_api_base(device)
    try:
        resp = requests.post(f"{base_url}/api/bell/play", json=data, auth=get_pi_auth(device), timeout=5)
        return Response(resp.content, status=resp.status_code, content_type="application/json")
    except Exception as e:
        return jsonify({"error": str(e)}), 503


@app.route("/api/bell/upload", methods=["POST"])
def upload_bell():
    if "file" not in request.files:
        return jsonify({"error": "Keine Audiodatei übergeben"}), 400
    file = request.files["file"]
    file_bytes = file.read()
    file_name = file.filename
    file_type = file.content_type

    fleet = load_fleet_data()
    # Upload sound to ALL reachable devices in fleet so audio files are available everywhere
    uploaded = 0
    for dev in fleet.get("devices", []):
        if dev.get("host"):
            try:
                base_url = get_pi_api_base(dev)
                files = {"file": (file_name, file_bytes, file_type)}
                requests.post(f"{base_url}/api/bell/upload", files=files, auth=get_pi_auth(dev), timeout=12)
                uploaded += 1
            except Exception:
                pass

    return jsonify({"success": True, "message": f"Audiodatei auf {uploaded} Display(s) hochgeladen"})


@app.route("/api/cec/screen", methods=["POST"])
def control_screen():
    fleet = load_fleet_data()
    data = request.get_json(silent=True) or {}
    dev_id = data.get("device_id") or request.args.get("device_id")
    device = get_active_device(fleet, dev_id)
    base_url = get_pi_api_base(device)
    try:
        resp = requests.post(f"{base_url}/api/screen", json=data, auth=get_pi_auth(device), timeout=5)
        return Response(resp.content, status=resp.status_code, content_type="application/json")
    except Exception as e:
        return jsonify({"error": str(e)}), 503


@app.route("/api/cec/schedule", methods=["POST"])
def set_cec_schedule():
    fleet = load_fleet_data()
    data = request.get_json(silent=True) or {}
    dev_id = data.get("device_id") or request.args.get("device_id")
    device = get_active_device(fleet, dev_id)
    base_url = get_pi_api_base(device)
    try:
        resp = requests.post(f"{base_url}/api/schedule", json=data, auth=get_pi_auth(device), timeout=5)
        return Response(resp.content, status=resp.status_code, content_type="application/json")
    except Exception as e:
        return jsonify({"error": str(e)}), 503


@app.route("/api/pi/shutdown", methods=["POST"])
def pi_shutdown():
    fleet = load_fleet_data()
    data = request.get_json(silent=True) or {}
    dev_id = data.get("device_id") or request.args.get("device_id")
    device = get_active_device(fleet, dev_id)
    result = trigger_device_power_action(device, "shutdown")
    status_code = 200 if result.get("success") else 500
    return jsonify(result), status_code


@app.route("/api/pi/reboot", methods=["POST"])
def pi_reboot():
    fleet = load_fleet_data()
    data = request.get_json(silent=True) or {}
    dev_id = data.get("device_id") or request.args.get("device_id")
    device = get_active_device(fleet, dev_id)
    result = trigger_device_power_action(device, "reboot")
    status_code = 200 if result.get("success") else 500
    return jsonify(result), status_code


@app.route("/api/kiosk/restart", methods=["POST"])
def restart_kiosk_browser():
    fleet = load_fleet_data()
    data = request.get_json(silent=True) or {}
    dev_id = data.get("device_id") or request.args.get("device_id")
    device = get_active_device(fleet, dev_id)
    base_url = get_pi_api_base(device)
    try:
        resp = requests.post(f"{base_url}/api/kiosk/restart", auth=get_pi_auth(device), timeout=5)
        return Response(resp.content, status=resp.status_code, content_type="application/json")
    except Exception as e:
        password = device.get("password")
        if password:
            try:
                import paramiko
                client = paramiko.SSHClient()
                client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                client.connect(hostname=device.get("host"), port=int(device.get("port", 22)), username=device.get("username", "dbsadmin"), password=password, timeout=5)
                client.exec_command("sudo systemctl restart kiosk.service")
                client.close()
                return jsonify({"success": True, "message": "Kiosk-Dienst per SSH neu gestartet"})
            except Exception:
                pass
        return jsonify({"error": str(e)}), 503


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8099)
