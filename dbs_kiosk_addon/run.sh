#!/usr/bin/env bash
set -e

echo "[INFO] Starting dbsKioskPi Manager Add-on on port 8099..."
exec python3 /app/main.py
