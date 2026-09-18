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
SETTINGS_FILE = "/data/settings.json"
LOCAL_LOG_FILE = "/data/dbskiosk-install.log"
if not os.path.exists("/data"):
    SETTINGS_FILE = os.path.join(os.path.dirname(__file__), "settings.json")
    LOCAL_LOG_FILE = os.path.join(os.path.dirname(__file__), "dbskiosk-install.log")

# Queue for real-time log streaming
log_queue = queue.Queue(maxsize=1000)
is_provisioning = False


def load_settings():
    """Load stored Pi connection settings."""
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "host": "",
        "port": 22,
        "username": "pi",
        "password": "",
        "api_port": 8088
    }


def save_settings(data):
    """Save Pi connection settings."""
    try:
        os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
    except Exception:
        pass
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def get_pi_auth(settings):
    """Returns requests HTTP basic auth tuple."""
    return (settings.get("username", "pi"), settings.get("password", ""))


def get_pi_api_base(settings):
    """Returns base URL for the Pi REST API."""
    host = settings.get("host", "127.0.0.1")
    port = settings.get("api_port", 8088)
    return f"http://{host}:{port}"


# ------------------------------------------------------------------------------
# Frontend Views
# ------------------------------------------------------------------------------
@app.route("/")
def index():
    ingress_path = request.headers.get("X-Ingress-Path", "")
    settings = load_settings()
    masked = dict(settings)
    if masked.get("password"):
        masked["has_password"] = True
        masked["password"] = "••••••••"
    else:
        masked["has_password"] = False
    return render_template("index.html", ingress_path=ingress_path, settings=masked)


# ------------------------------------------------------------------------------
# Settings Endpoints
# ------------------------------------------------------------------------------
@app.route("/api/settings", methods=["GET", "POST"])
def handle_settings():
    if request.method == "POST":
        data = request.json or {}
        current = load_settings()
        current["host"] = data.get("host", "").strip()
        current["port"] = int(data.get("port", 22))
        current["username"] = data.get("username", "pi").strip()
        # Keep old password if not updated
        if data.get("password") and data.get("password") != "••••••••":
            current["password"] = data["password"]
        current["api_port"] = int(data.get("api_port", 8088))
        save_settings(current)
        return jsonify({"success": True, "message": "Einstellungen gespeichert"})

    settings = load_settings()
    masked = dict(settings)
    masked["has_password"] = bool(settings.get("password"))
    masked["password"] = "••••••••" if masked["has_password"] else ""
    return jsonify(masked)


# ------------------------------------------------------------------------------
# Remote SSH Provisioning
# ------------------------------------------------------------------------------
@app.route("/api/test-ssh", methods=["POST"])
def test_ssh():
    data = request.json or {}
    settings = load_settings()
    host = data.get("host") or settings.get("host")
    port = int(data.get("port") or settings.get("port", 22))
    username = data.get("username") or settings.get("username", "pi")
    password = data.get("password")
    if not password or password == "••••••••":
        password = settings.get("password", "")

    if not host:
        return jsonify({"success": False, "error": "Bitte IP-Adresse eingeben"}), 400

    provisioner = SSHProvisioner(host=host, port=port, username=username, password=password)
    result = provisioner.test_connection()
    if result.get("success"):
        settings["host"] = host
        settings["port"] = port
        settings["username"] = username
        if password and password != "••••••••":
            settings["password"] = password
        save_settings(settings)

        # Falls dbs-api auf dem Pi existiert, stelle sicher, dass die neue Version aktiv ist und Auth passt
        try:
            client = provisioner.connect(timeout=6)
            stdin, stdout, stderr = client.exec_command("[ -f /usr/local/bin/dbs-api ] && echo 'exists'")
            if stdout.read().decode().strip() == "exists":
                # api_auth.conf anlegen für zuverlässige HTTP Basic Auth
                if password:
                    client.exec_command(f"echo '{username}:{password}' | sudo tee /etc/dbskiosk/api_auth.conf >/dev/null && sudo chmod 600 /etc/dbskiosk/api_auth.conf")
                
                # Aktualisiertes dbs-api.py übertragen (ohne cgi Modul für Python 3.13)
                pkg_api = os.path.join(os.path.dirname(__file__), "..", "package", "files", "dbs-api.py")
                if not os.path.exists(pkg_api):
                    pkg_api = "/app/package/files/dbs-api.py"
                if os.path.exists(pkg_api):
                    sftp = client.open_sftp()
                    sftp.put(pkg_api, "/tmp/dbs-api.py")
                    sftp.close()
                    client.exec_command("sudo cp /tmp/dbs-api.py /usr/local/bin/dbs-api && sudo chmod 755 /usr/local/bin/dbs-api && sudo systemctl restart dbs-api.service")
            client.close()
        except Exception:
            pass

    return jsonify(result)


@app.route("/api/provision/start", methods=["POST"])
def start_provisioning():
    global is_provisioning
    if is_provisioning:
        return jsonify({"success": False, "error": "Eine Installation läuft bereits!"}), 400

    data = request.json or {}
    settings = load_settings()
    host = data.get("host") or settings.get("host")
    port = int(data.get("port") or settings.get("port", 22))
    username = data.get("username") or settings.get("username", "pi")
    password = data.get("password")
    if not password or password == "••••••••":
        password = settings.get("password", "")

    if not host or not password:
        return jsonify({"success": False, "error": "IP-Adresse und Passwort sind erforderlich"}), 400

    # Save connection settings
    settings["host"] = host
    settings["port"] = port
    settings["username"] = username
    settings["password"] = password
    save_settings(settings)

    # Empty queue
    while not log_queue.empty():
        try:
            log_queue.get_nowait()
        except Exception:
            break

    try:
        with open(LOCAL_LOG_FILE, "w", encoding="utf-8") as f:
            f.write(f"=== dbsKioskPi Installation gestartet am {time.strftime('%Y-%m-%d %H:%M:%S')} für {host} ===\n")
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

        log_cb("[START] Starte Remote-Provisioning für dbsKioskPi...")
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
    """Download the actual installation log from the Raspberry Pi (/var/log/dbskiosk-install.log)."""
    settings = load_settings()
    host = settings.get("host")
    port = int(settings.get("port", 22))
    username = settings.get("username", "pi")
    password = settings.get("password", "")
    api_port = int(settings.get("api_port", 8088))

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
                headers={"Content-Disposition": "inline; filename=dbskiosk-install.txt"}
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
                headers={"Content-Disposition": "inline; filename=dbskiosk-install.txt"}
            )
        except Exception:
            pass

    # 3. Fallback auf das lokale Provisioning-Log, falls vorhanden
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

    return jsonify({"error": "Installationslog konnte weder vom Raspberry Pi noch lokal gefunden werden"}), 404


@app.route("/api/pi/download-config-log")
def download_pi_config_log():
    """Download the configuration change log from the Raspberry Pi (/var/log/dbskiosk-config.log)."""
    settings = load_settings()
    host = settings.get("host")
    port = int(settings.get("port", 22))
    username = settings.get("username", "pi")
    password = settings.get("password", "")
    api_port = int(settings.get("api_port", 8088))

    if not host:
        return jsonify({"error": "Keine IP-Adresse konfiguriert"}), 400

    try:
        url = f"http://{host}:{api_port}/api/logs/config"
        resp = requests.get(url, auth=(username, password), timeout=4)
        if resp.status_code == 200 and resp.content:
            return Response(
                resp.content,
                mimetype="text/plain; charset=utf-8",
                headers={"Content-Disposition": "attachment; filename=dbskiosk-config.log"}
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
                headers={"Content-Disposition": "attachment; filename=dbskiosk-config.log"}
            )
        except Exception as e:
            return jsonify({"error": f"Konfigurationslog nicht verfügbar: {e}"}), 404

    return jsonify({"error": "Konfigurationslog nicht verfügbar"}), 404


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
                # Keep-alive heartbeat
                yield ": keepalive\n\n"

    return Response(event_stream(), mimetype="text/event-stream")


# ------------------------------------------------------------------------------
# Proxy Endpoints to Raspberry Pi REST-API
# ------------------------------------------------------------------------------
@app.route("/api/kiosk/status")
def get_kiosk_status():
    settings = load_settings()
    base_url = get_pi_api_base(settings)
    try:
        resp = requests.get(f"{base_url}/api/status", auth=get_pi_auth(settings), timeout=4)
        return Response(resp.content, status=resp.status_code, content_type="application/json")
    except Exception as e:
        return jsonify({"error": "Pi nicht erreichbar", "details": str(e), "status": "offline"}), 503


@app.route("/api/kiosk/playlist", methods=["GET", "POST"])
def handle_playlist():
    settings = load_settings()
    base_url = get_pi_api_base(settings)
    try:
        if request.method == "POST":
            resp = requests.post(f"{base_url}/api/kiosk/playlist", json=request.json, auth=get_pi_auth(settings), timeout=8)
        else:
            resp = requests.get(f"{base_url}/api/kiosk/playlist", auth=get_pi_auth(settings), timeout=4)
        return Response(resp.content, status=resp.status_code, content_type="application/json")
    except Exception as e:
        return jsonify({"error": str(e)}), 503


@app.route("/api/bell/schedule", methods=["GET", "POST"])
def handle_bell_schedule():
    settings = load_settings()
    base_url = get_pi_api_base(settings)
    try:
        if request.method == "POST":
            resp = requests.post(f"{base_url}/api/bell/schedule", json=request.json, auth=get_pi_auth(settings), timeout=8)
        else:
            resp = requests.get(f"{base_url}/api/bell/schedule", auth=get_pi_auth(settings), timeout=4)
        return Response(resp.content, status=resp.status_code, content_type="application/json")
    except Exception as e:
        return jsonify({"error": str(e)}), 503


@app.route("/api/bell/play", methods=["POST"])
def play_bell():
    settings = load_settings()
    base_url = get_pi_api_base(settings)
    try:
        resp = requests.post(f"{base_url}/api/bell/play", json=request.json or {}, auth=get_pi_auth(settings), timeout=5)
        return Response(resp.content, status=resp.status_code, content_type="application/json")
    except Exception as e:
        return jsonify({"error": str(e)}), 503


@app.route("/api/bell/upload", methods=["POST"])
def upload_bell():
    if "file" not in request.files:
        return jsonify({"error": "Keine Audiodatei übergeben"}), 400
    file = request.files["file"]
    settings = load_settings()
    base_url = get_pi_api_base(settings)
    try:
        files = {"file": (file.filename, file.read(), file.content_type)}
        resp = requests.post(f"{base_url}/api/bell/upload", files=files, auth=get_pi_auth(settings), timeout=15)
        return Response(resp.content, status=resp.status_code, content_type="application/json")
    except Exception as e:
        return jsonify({"error": str(e)}), 503


@app.route("/api/cec/screen", methods=["POST"])
def control_screen():
    settings = load_settings()
    base_url = get_pi_api_base(settings)
    try:
        resp = requests.post(f"{base_url}/api/screen", json=request.json or {}, auth=get_pi_auth(settings), timeout=5)
        return Response(resp.content, status=resp.status_code, content_type="application/json")
    except Exception as e:
        return jsonify({"error": str(e)}), 503


@app.route("/api/cec/schedule", methods=["POST"])
def set_cec_schedule():
    settings = load_settings()
    base_url = get_pi_api_base(settings)
    try:
        resp = requests.post(f"{base_url}/api/schedule", json=request.json or {}, auth=get_pi_auth(settings), timeout=5)
        return Response(resp.content, status=resp.status_code, content_type="application/json")
    except Exception as e:
        return jsonify({"error": str(e)}), 503


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8099)
