#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LOG_DIR="$ROOT_DIR/paper1/data/runs"
LOG_FILE="$LOG_DIR/fix-docker-network-for-swebench.log"
mkdir -p "$LOG_DIR"

exec > >(tee "$LOG_FILE") 2>&1

echo "[info] log: $LOG_FILE"
echo "[info] this script must run on the Linux server you SSH into."
echo "[info] not on your Mac, not inside Docker."
echo

PROXY_HOST="${PROXY_HOST:-100.72.121.78}"
PROXY_PORT="${PROXY_PORT:-7890}"
PROXY_URL="http://${PROXY_HOST}:${PROXY_PORT}"

echo "[info] proxy: $PROXY_URL"
echo "[info] date: $(date -Is)"
echo

echo "[check] host proxy env"
env | grep -Ei '^(http|https|all|no)_proxy=|^(HTTP|HTTPS|ALL|NO)_PROXY=' || true
echo

echo "[check] host network through proxy"
curl -I --max-time 15 https://www.google.com | head -20
curl -I --max-time 15 http://archive.ubuntu.com/ubuntu/ | head -20
echo

echo "[write] docker systemd proxy config"
sudo mkdir -p /etc/systemd/system/docker.service.d
sudo tee /etc/systemd/system/docker.service.d/http-proxy.conf >/dev/null <<EOF
[Service]
Environment="HTTP_PROXY=${PROXY_URL}"
Environment="HTTPS_PROXY=${PROXY_URL}"
Environment="NO_PROXY=localhost,127.0.0.1,::1"
EOF

echo "[write] docker daemon dns config"
sudo python3 - <<'PY'
import json
from pathlib import Path

p = Path("/etc/docker/daemon.json")
obj = json.loads(p.read_text()) if p.exists() and p.read_text().strip() else {}
obj.setdefault(
    "registry-mirrors",
    [
        "https://docker.m.daocloud.io",
        "https://docker.1ms.run",
        "https://docker.xuanyuan.me",
    ],
)
obj["dns"] = ["8.8.8.8", "1.1.1.1", "223.5.5.5"]
p.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")
PY

echo "[restart] docker"
sudo systemctl daemon-reload
sudo systemctl restart docker
echo

echo "[check] docker daemon environment"
systemctl show docker --property=Environment
echo

echo "[check] /etc/docker/daemon.json"
cat /etc/docker/daemon.json
echo

echo "[check] docker container dns and apt"
docker run --rm ubuntu:22.04 bash -lc '
set -e
cat /etc/resolv.conf
getent hosts archive.ubuntu.com
apt update
'

echo
echo "[ok] Docker network works for SWE-bench official evaluation."
echo "[ok] log: $LOG_FILE"
