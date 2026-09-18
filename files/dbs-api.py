#!/usr/bin/env python3
"""
dbsKioskPi - REST API Daemon for Home Assistant Integration
Provides secure endpoints for TV control (HDMI-CEC), Screen scheduling,
School bell (MP3 audio playback & upload), and system status.
"""

import sys
import os
import json
import base64
import subprocess
import cgi
import shutil
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

PORT = 8088
CONFIG_FILE = "/etc/dbskiosk/kiosk.conf"
AUTH_FILE = "/etc/dbskiosk/api_auth.conf"
SOUNDS_DIR = "/var/lib/dbskiosk/sounds"
BELL_PATH = os.path.join(SOUNDS_DIR, "bell.mp3")


def read_config():
    """Reads key-value config from kiosk.conf."""
    cfg = {
        "KIOSK_URL": "https://dbs.edupage.org/infoscreen/7?scaletowidth=1920",
        "CEC_ENABLED": "true",
        "CEC_ON_TIME": "07:00",
        "CEC_OFF_TIME": "19:00",
        "BELL_VOLUME": "100"
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        cfg[k.strip()] = v.strip().strip('"').strip("'")
        except Exception as e:
            print(f"[WARN] Error reading config: {e}", file=sys.stderr)
    return cfg


def save_config_value(key, value):
    """Updates or appends a key in kiosk.conf."""
    lines = []
    found = False
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()

    new_lines = []
    for line in lines:
        if line.strip().startswith(f"{key}="):
            new_lines.append(f'{key}="{value}"\n')
            found = True
        else:
            new_lines.append(line)

    if not found:
        new_lines.append(f'{key}="{value}"\n')

    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        f.writelines(new_lines)


def authenticate(username, password):
    """
    Authenticates against Linux system shadow or local api_auth.conf.
    """
    if not username or not password:
        return False

    # 1. Check local api_auth.conf if configured
    if os.path.exists(AUTH_FILE):
        try:
            with open(AUTH_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip() and not line.startswith("#"):
                        parts = line.strip().split(":", 1)
                        if len(parts) == 2 and parts[0] == username and parts[1] == password:
                            return True
        except Exception:
            pass

    # 2. Check /etc/shadow directly (daemon runs as root)
    if os.path.exists("/etc/shadow"):
        try:
            with open("/etc/shadow", "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    fields = line.strip().split(":")
                    if fields and fields[0] == username and len(fields) > 1:
                        stored_hash = fields[1]
                        if stored_hash in ("*", "!", ""):
                            return False
                        
                        # Use openssl to verify standard Linux crypt hash
                        if stored_hash.startswith("$"):
                            parts = stored_hash.split("$")
                            if len(parts) >= 4:
                                hash_type = parts[1]
                                salt = parts[2]
                                try:
                                    res = subprocess.run(
                                        ["openssl", "passwd", f"-{hash_type}", "-salt", salt, password],
                                        capture_output=True, text=True, check=True
                                    )
                                    if res.stdout.strip() == stored_hash:
                                        return True
                                except Exception:
                                    pass

                        # Fallback to python crypt if available
                        try:
                            import crypt
                            if crypt.crypt(password, stored_hash) == stored_hash:
                                return True
                        except Exception:
                            pass
        except Exception as e:
            print(f"[AUTH ERROR] Failed checking shadow: {e}", file=sys.stderr)

    return False


class KioskAPIHandler(BaseHTTPRequestHandler):

    def _send_json(self, data, code=200):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2).encode("utf-8"))

    def _check_auth(self):
        auth_header = self.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Basic "):
            return False

        try:
            encoded = auth_header[6:].strip()
            decoded = base64.b64decode(encoded).decode("utf-8")
            username, password = decoded.split(":", 1)
            return authenticate(username, password)
        except Exception:
            return False

    def _require_auth(self):
        if not self._check_auth():
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="dbsKioskPi API"')
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Unauthorized"}).encode("utf-8"))
            return False
        return True

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path == "/api/health":
            self._send_json({"status": "ok", "service": "dbsKioskPi"})
            return

        if not self._require_auth():
            return

        if path == "/api/status":
            cfg = read_config()
            
            # Kiosk service status
            kiosk_active = "unknown"
            try:
                res = subprocess.run(["systemctl", "is-active", "kiosk.service"], capture_output=True, text=True)
                kiosk_active = res.stdout.strip()
            except Exception:
                pass

            # CEC power status query
            cec_power = "unknown"
            try:
                res = subprocess.run(["/usr/local/bin/dbs-cec", "status"], capture_output=True, text=True, timeout=5)
                out = res.stdout.lower()
                if "on" in out or "power status: on" in out:
                    cec_power = "on"
                elif "standby" in out or "power status: standby" in out:
                    cec_power = "standby"
            except Exception:
                pass

            data = {
                "service": "dbsKioskPi",
                "version": "1.0.0",
                "kiosk_service": kiosk_active,
                "screen_power": cec_power,
                "cec_enabled": cfg.get("CEC_ENABLED", "true") == "true",
                "cec_on_time": cfg.get("CEC_ON_TIME", "07:00"),
                "cec_off_time": cfg.get("CEC_OFF_TIME", "19:00"),
                "kiosk_url": cfg.get("KIOSK_URL", ""),
                "bell": {
                    "sound_exists": os.path.exists(BELL_PATH),
                    "sound_size_bytes": os.path.getsize(BELL_PATH) if os.path.exists(BELL_PATH) else 0,
                    "volume": int(cfg.get("BELL_VOLUME", "100"))
                }
            }
            self._send_json(data)
            return

        elif path == "/api/bell/download":
            if not os.path.exists(BELL_PATH):
                self._send_json({"error": "No bell sound uploaded yet"}, 404)
                return
            try:
                with open(BELL_PATH, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "audio/mpeg")
                self.send_header("Content-Length", str(len(content)))
                self.send_header("Content-Disposition", 'attachment; filename="bell.mp3"')
                self.end_headers()
                self.wfile.write(content)
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
            return

        self._send_json({"error": "Not Found"}, 404)

    def do_POST(self):
        if not self._require_auth():
            return

        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        content_length = int(self.headers.get("Content-Length", 0))

        # ----------------------------------------------------------------------
        # Screen Control (ON / OFF / TOGGLE)
        # ----------------------------------------------------------------------
        if path == "/api/screen":
            body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
            try:
                req = json.loads(body)
            except Exception:
                req = {}

            action = req.get("action", "on").lower()
            if action in ("on", "force-on"):
                subprocess.Popen(["/usr/local/bin/dbs-cec", "force-on"])
                self._send_json({"success": True, "screen": "on"})
            elif action in ("off", "standby", "force-off"):
                subprocess.Popen(["/usr/local/bin/dbs-cec", "force-off"])
                self._send_json({"success": True, "screen": "off"})
            else:
                self._send_json({"error": f"Invalid screen action: {action}"}, 400)
            return

        # ----------------------------------------------------------------------
        # Schedule Setting (TV On & Off Times)
        # ----------------------------------------------------------------------
        elif path == "/api/schedule":
            body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
            try:
                req = json.loads(body)
            except Exception:
                self._send_json({"error": "Invalid JSON"}, 400)
                return

            on_time = req.get("on_time")
            off_time = req.get("off_time")

            if on_time:
                save_config_value("CEC_ON_TIME", on_time)
                os.makedirs("/etc/systemd/system/kiosk-cec-on.timer.d", exist_ok=True)
                with open("/etc/systemd/system/kiosk-cec-on.timer.d/override.conf", "w") as f:
                    f.write(f"[Timer]\nOnCalendar=\nOnCalendar=*-*-* {on_time}:00\n")

            if off_time:
                save_config_value("CEC_OFF_TIME", off_time)
                os.makedirs("/etc/systemd/system/kiosk-cec-off.timer.d", exist_ok=True)
                with open("/etc/systemd/system/kiosk-cec-off.timer.d/override.conf", "w") as f:
                    f.write(f"[Timer]\nOnCalendar=\nOnCalendar=*-*-* {off_time}:00\n")

            if on_time or off_time:
                subprocess.run(["systemctl", "daemon-reload"], check=False)
                if on_time:
                    subprocess.run(["systemctl", "restart", "kiosk-cec-on.timer"], check=False)
                if off_time:
                    subprocess.run(["systemctl", "restart", "kiosk-cec-off.timer"], check=False)

            self._send_json({"success": True, "on_time": on_time, "off_time": off_time})
            return

        # ----------------------------------------------------------------------
        # School Bell: Play Sound Now
        # ----------------------------------------------------------------------
        elif path == "/api/bell/play":
            body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
            try:
                req = json.loads(body)
            except Exception:
                req = {}

            volume = req.get("volume")
            args = ["/usr/local/bin/dbs-bell", "play"]
            if volume is not None:
                args.append(str(volume))

            subprocess.Popen(args)
            self._send_json({"success": True, "message": "School bell is ringing"})
            return

        # ----------------------------------------------------------------------
        # School Bell: Upload MP3 Audio File
        # ----------------------------------------------------------------------
        elif path == "/api/bell/upload":
            content_type = self.headers.get("Content-Type", "")
            os.makedirs(SOUNDS_DIR, exist_ok=True)

            if "multipart/form-data" in content_type:
                # Parse multipart
                form = cgi.FieldStorage(
                    fp=self.rfile,
                    headers=self.headers,
                    environ={'REQUEST_METHOD': 'POST', 'CONTENT_TYPE': content_type}
                )
                if "file" in form and form["file"].file:
                    with open(BELL_PATH, "wb") as f:
                        shutil.copyfileobj(form["file"].file, f)
                    self._send_json({"success": True, "message": "MP3 bell sound uploaded successfully", "size": os.path.getsize(BELL_PATH)})
                    return
                else:
                    self._send_json({"error": "No 'file' field in multipart form"}, 400)
                    return
            else:
                # Raw binary MP3 in body
                audio_data = self.rfile.read(content_length)
                if len(audio_data) < 100:
                    self._send_json({"error": "Uploaded data is too small or invalid"}, 400)
                    return
                with open(BELL_PATH, "wb") as f:
                    f.write(audio_data)
                self._send_json({"success": True, "message": "MP3 bell sound uploaded successfully", "size": len(audio_data)})
                return

        # ----------------------------------------------------------------------
        # Kiosk Service Control & URL Update
        # ----------------------------------------------------------------------
        elif path == "/api/kiosk/url":
            body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
            try:
                req = json.loads(body)
            except Exception:
                self._send_json({"error": "Invalid JSON"}, 400)
                return

            new_url = req.get("url")
            if new_url:
                save_config_value("KIOSK_URL", new_url)
                if req.get("restart", True):
                    subprocess.Popen(["systemctl", "restart", "kiosk.service"])
                self._send_json({"success": True, "url": new_url})
            else:
                self._send_json({"error": "Missing 'url' parameter"}, 400)
            return

        elif path == "/api/kiosk/restart":
            subprocess.Popen(["systemctl", "restart", "kiosk.service"])
            self._send_json({"success": True, "message": "Kiosk service restarting"})
            return

        self._send_json({"error": "Not Found"}, 404)


def run_server():
    os.makedirs(SOUNDS_DIR, exist_ok=True)
    server_address = ("", PORT)
    httpd = HTTPServer(server_address, KioskAPIHandler)
    print(f"[INFO] dbsKioskPi REST API running on port {PORT}...")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    httpd.server_close()


if __name__ == "__main__":
    run_server()
