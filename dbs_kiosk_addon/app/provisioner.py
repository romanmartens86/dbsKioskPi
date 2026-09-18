"""
Remote SSH Provisioner for dbsKioskPi.
Connects to a fresh/naked Raspberry Pi OS installation,
transfers the setup package, and executes the automated installation.
"""

import os
import sys
import time
import socket
import paramiko
from scp import SCPClient


class SSHProvisioner:
    """Manages remote setup via SSH."""

    def __init__(self, host, port=22, username="pi", password=""):
        self.host = host
        self.port = int(port)
        self.username = username
        self.password = password
        self.client = None

    def connect(self, timeout=10):
        """Establish SSH connection."""
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            hostname=self.host,
            port=self.port,
            username=self.username,
            password=self.password,
            timeout=timeout,
            banner_timeout=15,
            look_for_keys=False,
            allow_agent=False,
        )
        self.client = client
        return client

    def test_connection(self):
        """Tests SSH connectivity and detects OS version."""
        try:
            client = self.connect(timeout=8)
            stdin, stdout, stderr = client.exec_command("cat /etc/os-release", timeout=10)
            os_info = stdout.read().decode("utf-8")
            stdin, stdout, stderr = client.exec_command("uname -m", timeout=5)
            arch = stdout.read().decode("utf-8").strip()
            client.close()

            # Parse pretty name
            name = "Raspberry Pi OS"
            for line in os_info.splitlines():
                if line.startswith("PRETTY_NAME="):
                    name = line.split("=", 1)[1].strip('"')
                    break

            return {
                "success": True,
                "os": name,
                "arch": arch,
                "message": f"Verbindung erfolgreich ({name}, {arch})"
            }
        except socket.timeout:
            return {"success": False, "error": "Zeitüberschreitung beim Verbindungsaufbau (IP prüfen)"}
        except paramiko.AuthenticationException:
            return {"success": False, "error": "Authentifizierungsfehler (Benutzername oder Passwort falsch)"}
        except Exception as e:
            return {"success": False, "error": f"Verbindungsfehler: {str(e)}"}

    def upload_package(self, local_pkg_dir="/app/package", remote_dir="/tmp/dbsKioskPi", log_callback=None):
        """Uploads files via SFTP/SCP."""
        if log_callback:
            log_callback("[PROVISION] Erstelle temporäres Verzeichnis auf Zielsystem...")

        # Erstelle Zielordner
        stdin, stdout, stderr = self.client.exec_command(f"rm -rf {remote_dir} && mkdir -p {remote_dir}")
        stdout.channel.recv_exit_status()

        sftp = self.client.open_sftp()

        def put_dir(local_path, remote_path):
            if log_callback:
                log_callback(f"[PROVISION] Übertrage Ordner: {os.path.basename(local_path)}...")
            try:
                sftp.mkdir(remote_path)
            except Exception:
                pass
            for item in os.listdir(local_path):
                s_item = os.path.join(local_path, item)
                d_item = f"{remote_path}/{item}"
                if os.path.isdir(s_item):
                    put_dir(s_item, d_item)
                else:
                    sftp.put(s_item, d_item)

        if os.path.exists(local_pkg_dir):
            put_dir(local_pkg_dir, remote_dir)
        else:
            if log_callback:
                log_callback("[WARN] Lokales Paketverzeichnis nicht gefunden, versuche Git-Clone auf Ziel...")
            stdin, stdout, stderr = self.client.exec_command(
                f"git clone https://github.com/romanmartens86/dbsKioskPi.git {remote_dir}"
            )
            stdout.channel.recv_exit_status()

        sftp.close()
        if log_callback:
            log_callback("[PROVISION] Alle Installationsdateien erfolgreich übertragen.")

    def run_installation(self, log_callback=None, local_pkg_dir="/app/package"):
        """Executes the full installation process remotely."""
        try:
            if log_callback:
                log_callback(f"[PROVISION] Verbinde mit {self.host}:{self.port} als '{self.username}'...")

            self.connect(timeout=15)

            if log_callback:
                log_callback("[PROVISION] SSH-Verbindung aufgebaut. Starte Datenübertragung...")

            remote_dir = "/tmp/dbsKioskPi"
            self.upload_package(local_pkg_dir=local_pkg_dir, remote_dir=remote_dir, log_callback=log_callback)

            # Starte Installation mit sudo
            cmd = f"cd {remote_dir} && sudo -S bash install.sh"
            if log_callback:
                log_callback(f"[PROVISION] Führe Installationsskript aus: {cmd}")

            channel = self.client.get_transport().open_session()
            channel.get_pty()
            channel.exec_command(cmd)

            # Sende Passwort falls sudo danach fragt
            if self.password:
                channel.send(f"{self.password}\n")

            while True:
                if channel.recv_ready():
                    data = channel.recv(1024).decode("utf-8", errors="replace")
                    for line in data.splitlines():
                        clean_line = line.strip()
                        if clean_line and log_callback:
                            log_callback(clean_line)

                if channel.exit_status_ready():
                    break
                time.sleep(0.1)

            exit_code = channel.recv_exit_status()

            if exit_code == 0:
                if log_callback:
                    log_callback("[OK] ========================================================")
                    log_callback("[OK] Installation erfolgreich abgeschlossen!")
                    log_callback("[OK] Starte den Raspberry Pi jetzt neu...")
                    log_callback("[OK] ========================================================")

                # Reboot ausführen
                try:
                    self.client.exec_command("sudo reboot")
                except Exception:
                    pass

                return {"success": True, "message": "Installation erfolgreich! System startet neu."}
            else:
                if log_callback:
                    log_callback(f"[FEHLER] Installation beendet mit Exit-Code {exit_code}")
                return {"success": False, "error": f"Fehler bei Installation (Exit-Code: {exit_code})"}

        except Exception as e:
            if log_callback:
                log_callback(f"[FEHLER] Ausnahme während Provisioning: {str(e)}")
            return {"success": False, "error": str(e)}
        finally:
            if self.client:
                try:
                    self.client.close()
                except Exception:
                    pass
