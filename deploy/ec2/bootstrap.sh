#!/usr/bin/env bash
# SignalSDR EC2 bootstrap (Amazon Linux 2023, us-east-1, Hackathon_VPC).
# Run as ec2-user after cloning the repo to ~/neatlogs.
set -euo pipefail

APP_DIR="${APP_DIR:-$HOME/neatlogs}"
cd "$APP_DIR"

echo "==> Swap (2G) — important on t2.micro"
if ! swapon --show | grep -q .; then
  sudo dd if=/dev/zero of=/swapfile bs=1M count=2048 status=progress
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile
  sudo swapon /swapfile
  if ! grep -q '/swapfile' /etc/fstab; then
    echo '/swapfile swap swap defaults 0 0' | sudo tee -a /etc/fstab
  fi
fi

echo "==> System packages"
sudo dnf install -y git python3.11 python3.11-pip python3.11-devel gcc || \
  sudo yum install -y git python3.11 python3.11-pip python3.11-devel gcc

echo "==> Python venv"
python3.11 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -U pip
pip install -e .

if [[ ! -f .env ]]; then
  echo "Copy .env.example → .env and fill Bedrock (personal keys), Crustdata, Hunter, secrets."
  echo "Set API_HOST=0.0.0.0 CORS_ORIGINS=http://localhost:3000,https://YOUR.vercel.app"
  echo "Set UI_BASE_URL and GOOGLE_CALENDAR_REDIRECT_URI to the Vercel HTTPS URL."
  cp -n .env.example .env || true
fi

echo "==> systemd unit"
sudo cp deploy/ec2/signalsdr-api.service /etc/systemd/system/signalsdr-api.service
# Fix paths if not ec2-user
sudo sed -i "s|/home/ec2-user/neatlogs|$APP_DIR|g" /etc/systemd/system/signalsdr-api.service
sudo sed -i "s|User=ec2-user|User=$USER|g" /etc/systemd/system/signalsdr-api.service
sudo systemctl daemon-reload
sudo systemctl enable signalsdr-api
sudo systemctl restart signalsdr-api

sleep 2
curl -sf "http://127.0.0.1:8000/api/health" && echo " health ok" || echo "WARN: health check failed — see journalctl -u signalsdr-api -f"

echo "Done. Open SG inbound TCP 8000 for Vercel rewrite. Stop/terminate instance after the video."
