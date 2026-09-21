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
import shutil
import threading
import time
import ctypes
import ctypes.util
from datetime import datetime
from http.server import HTTPServer, ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# Global cache for CEC power state to prevent blocking HTTP requests
CACHED_CEC_POWER = "unknown"
LAST_CEC_CHECK = 0

PORT = 8088
CONFIG_FILE = "/etc/dbskiosk/kiosk.conf"
AUTH_FILE = "/etc/dbskiosk/api_auth.conf"
PLAYLIST_FILE = "/etc/dbskiosk/playlist.json"
SCHEDULE_FILE = "/etc/dbskiosk/bell_schedule.json"
CYCLER_HTML = "/var/lib/dbskiosk/kiosk-cycler.html"
SOUNDS_DIR = "/var/lib/dbskiosk/sounds"
BELL_PATH = os.path.join(SOUNDS_DIR, "bell.mp3")
INSTALL_LOG_FILE = "/var/log/dbskiosk-install.log"
CONFIG_LOG_FILE = "/var/log/dbskiosk-config.log"
HEALTHCHECK_LOG_FILE = "/var/log/dbskiosk-healthcheck.log"


def log_config_event(action):
    """Appends an entry to the configuration log with timestamp."""
    try:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(CONFIG_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {action}\n")
    except Exception:
        pass


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
    log_config_event(f"Einstellung geändert: {key} = {value}")


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
                        
                        # Native glibc libcrypt (supports yescrypt $y$, sha512 $6$, sha256 $5$)
                        try:
                            lib_name = ctypes.util.find_library("crypt") or "libcrypt.so.1"
                            libcrypt = ctypes.cdll.LoadLibrary(lib_name)
                            libcrypt.crypt.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
                            libcrypt.crypt.restype = ctypes.c_char_p
                            res = libcrypt.crypt(password.encode("utf-8"), stored_hash.encode("utf-8"))
                            if res and res.decode("utf-8") == stored_hash:
                                return True
                        except Exception:
                            pass

                        # Fallback using openssl passwd
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

        if path == "/cycler":
            # Serve kiosk cycler HTML page (public for localhost browser)
            content = ""
            if os.path.exists(CYCLER_HTML):
                with open(CYCLER_HTML, "r", encoding="utf-8") as f:
                    content = f.read()
            else:
                content = "<h1>Cycler file not found</h1>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(content.encode("utf-8"))
            return

        if path == "/api/kiosk/playlist":
            # Return playlist
            if os.path.exists(PLAYLIST_FILE):
                try:
                    with open(PLAYLIST_FILE, "r", encoding="utf-8") as f:
                        self._send_json(json.load(f))
                        return
                except Exception:
                    pass
            cfg = read_config()
            self._send_json([{"url": cfg.get("KIOSK_URL", ""), "duration": 30}])
            return

        if not self._require_auth():
            return

        if path == "/api/logs/install":
            if os.path.exists(INSTALL_LOG_FILE):
                try:
                    with open(INSTALL_LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
                        data = f.read()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain; charset=utf-8")
                    self.send_header("Content-Disposition", 'attachment; filename="dbskiosk-install.log"')
                    self.end_headers()
                    self.wfile.write(data.encode("utf-8"))
                    return
                except Exception as e:
                    self._send_json({"error": str(e)}, status=500)
                    return
            else:
                self._send_json({"error": "Installationslog /var/log/dbskiosk-install.log nicht vorhanden"}, status=404)
                return

        if path == "/api/logs/config":
            if os.path.exists(CONFIG_LOG_FILE):
                try:
                    with open(CONFIG_LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
                        data = f.read()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain; charset=utf-8")
                    self.send_header("Content-Disposition", 'attachment; filename="dbskiosk-config.log"')
                    self.end_headers()
                    self.wfile.write(data.encode("utf-8"))
                    return
                except Exception as e:
                    self._send_json({"error": str(e)}, status=500)
                    return
            else:
                self._send_json({"error": "Konfigurationslog /var/log/dbskiosk-config.log nicht vorhanden"}, status=404)
                return

        if path in ("/api/healthcheck", "/api/logs/healthcheck"):
            if not os.path.exists(HEALTHCHECK_LOG_FILE):
                if os.path.exists("/usr/local/bin/dbs-healthcheck"):
                    subprocess.run(["/usr/local/bin/dbs-healthcheck"], capture_output=True)
            if os.path.exists(HEALTHCHECK_LOG_FILE):
                try:
                    with open(HEALTHCHECK_LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
                        data = f.read()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain; charset=utf-8")
                    self.send_header("Content-Disposition", 'inline; filename="dbskiosk-healthcheck.txt"')
                    self.end_headers()
                    self.wfile.write(data.encode("utf-8"))
                    return
                except Exception as e:
                    self._send_json({"error": str(e)}, status=500)
                    return
            else:
                self._send_json({"error": "Healthcheck-Log nicht vorhanden"}, status=404)
                return

        if path == "/api/bell/schedule":
            if os.path.exists(SCHEDULE_FILE):
                try:
                    with open(SCHEDULE_FILE, "r", encoding="utf-8") as f:
                        self._send_json(json.load(f))
                        return
                except Exception:
                    pass
            self._send_json([])
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

            # Non-blocking CEC power status query with background refresh
            global CACHED_CEC_POWER, LAST_CEC_CHECK
            now = time.time()
            if now - LAST_CEC_CHECK > 30:
                LAST_CEC_CHECK = now
                def refresh_cec():
                    global CACHED_CEC_POWER
                    try:
                        res = subprocess.run(["/usr/local/bin/dbs-cec", "status"], capture_output=True, text=True, timeout=8)
                        out = res.stdout.lower()
                        if "on" in out or "power status: on" in out:
                            CACHED_CEC_POWER = "on"
                        elif "standby" in out or "power status: standby" in out:
                            CACHED_CEC_POWER = "standby"
                    except Exception:
                        pass
                threading.Thread(target=refresh_cec, daemon=True).start()

            cec_power = CACHED_CEC_POWER

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
        # Healthcheck: Run diagnostics now
        # ----------------------------------------------------------------------
        elif path == "/api/healthcheck/run":
            try:
                res = subprocess.run(["/usr/local/bin/dbs-healthcheck"], capture_output=True, text=True, timeout=20)
                self._send_json({"success": True, "output": res.stdout})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, 500)
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

        # ----------------------------------------------------------------------
        # Playlist Management (Multi-URL Cycler)
        # ----------------------------------------------------------------------
        elif path == "/api/kiosk/playlist":
            body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "[]"
            try:
                items = json.loads(body)
                if not isinstance(items, list):
                    self._send_json({"error": "Playlist must be a JSON array"}, 400)
                    return
                with open(PLAYLIST_FILE, "w", encoding="utf-8") as f:
                    json.dump(items, f, indent=2)

                # Falls mehr als 1 Seite: Auf Cycler umstellen
                if len(items) > 1:
                    save_config_value("KIOSK_URL", f"http://localhost:{PORT}/cycler")
                elif len(items) == 1 and "url" in items[0]:
                    save_config_value("KIOSK_URL", items[0]["url"])

                subprocess.Popen(["systemctl", "restart", "kiosk.service"])
                self._send_json({"success": True, "count": len(items)})
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
            return

        # ----------------------------------------------------------------------
        # Bell Schedule Management
        # ----------------------------------------------------------------------
        elif path == "/api/bell/schedule":
            body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "[]"
            try:
                schedule = json.loads(body)
                if not isinstance(schedule, list):
                    self._send_json({"error": "Schedule must be an array"}, 400)
                    return
                with open(SCHEDULE_FILE, "w", encoding="utf-8") as f:
                    json.dump(schedule, f, indent=2)
                self._send_json({"success": True, "count": len(schedule)})
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
            return

        elif path == "/api/kiosk/restart":
            subprocess.Popen(["systemctl", "restart", "kiosk.service"])
            self._send_json({"success": True, "message": "Kiosk service restarting"})
            return

        elif path == "/api/system/shutdown":
            log_config_event("System wird heruntergefahren (Shutdown via API)")
            self._send_json({"success": True, "message": "System is shutting down now..."})
            def do_shutdown():
                time.sleep(1)
                cmds = [
                    ["systemctl", "poweroff", "-i", "--no-block"],
                    ["systemctl", "poweroff", "--force"],
                    ["/sbin/poweroff", "-f"],
                    ["/sbin/shutdown", "-h", "now"],
                    ["poweroff", "-f"],
                    ["shutdown", "-h", "now"]
                ]
                for cmd in cmds:
                    try:
                        res = subprocess.run(cmd, capture_output=True, timeout=5)
                        if res.returncode == 0:
                            break
                    except Exception:
                        pass
                try:
                    subprocess.run("echo 1 > /proc/sys/kernel/sysrq 2>/dev/null && echo o > /proc/sysrq-trigger 2>/dev/null", shell=True, timeout=2)
                except Exception:
                    pass

            threading.Thread(target=do_shutdown, daemon=True).start()
            return

        elif path == "/api/system/reboot":
            log_config_event("System wird neu gestartet (Reboot via API)")
            self._send_json({"success": True, "message": "System is rebooting now..."})
            def do_reboot():
                time.sleep(1)
                cmds = [
                    ["systemctl", "reboot", "-i", "--no-block"],
                    ["systemctl", "reboot", "--force"],
                    ["/sbin/reboot", "-f"],
                    ["/sbin/shutdown", "-r", "now"],
                    ["reboot", "-f"],
                    ["shutdown", "-r", "now"]
                ]
                for cmd in cmds:
                    try:
                        res = subprocess.run(cmd, capture_output=True, timeout=5)
                        if res.returncode == 0:
                            break
                    except Exception:
                        pass
                try:
                    subprocess.run("echo 1 > /proc/sys/kernel/sysrq 2>/dev/null && echo b > /proc/sysrq-trigger 2>/dev/null", shell=True, timeout=2)
                except Exception:
                    pass

            threading.Thread(target=do_reboot, daemon=True).start()
            return

        self._send_json({"error": "Not Found"}, 404)


def bell_scheduler_loop():
    """Background thread checking bell_schedule.json every 15 seconds."""
    last_triggered_minute = ""
    day_map = {0: "mon", 1: "tue", 2: "wed", 3: "thu", 4: "fri", 5: "sat", 6: "sun"}

    while True:
        try:
            now = datetime.now()
            current_hh_mm = now.strftime("%H:%M")
            current_day = day_map.get(now.weekday(), "")

            # Check once per minute
            minute_key = f"{current_day}_{current_hh_mm}"
            if minute_key != last_triggered_minute:
                if os.path.exists(SCHEDULE_FILE):
                    with open(SCHEDULE_FILE, "r", encoding="utf-8") as f:
                        schedule = json.load(f)

                    for entry in schedule:
                        t = entry.get("time")
                        days = entry.get("days", ["mon", "tue", "wed", "thu", "fri"])
                        # Match current time and weekday
                        if t == current_hh_mm and current_day in [d.lower() for d in days]:
                            volume = entry.get("volume", 100)
                            print(f"[SCHEDULER] Triggering scheduled bell: {entry.get('name', 'Gong')} at {current_hh_mm}")
                            subprocess.Popen(["/usr/local/bin/dbs-bell", "play", str(volume)])
                            last_triggered_minute = minute_key
                            break
        except Exception as e:
            print(f"[WARN] Error in bell scheduler: {e}", file=sys.stderr)

        time.sleep(15)


def run_server():
    os.makedirs(SOUNDS_DIR, exist_ok=True)
    os.makedirs("/var/lib/dbskiosk", exist_ok=True)

    # Start background scheduler thread
    scheduler_thread = threading.Thread(target=bell_scheduler_loop, daemon=True)
    scheduler_thread.start()

    server_address = ("", PORT)
    httpd = ThreadingHTTPServer(server_address, KioskAPIHandler)
    print(f"[INFO] dbsKioskPi REST API running on port {PORT}...")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    httpd.server_close()


if __name__ == "__main__":
    run_server()
