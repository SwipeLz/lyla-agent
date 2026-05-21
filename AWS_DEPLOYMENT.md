# AWS Deployment — Lyla / Taskbot

Production deployment runbook for the FastAPI backend, the Vite frontend, and the ESP32-S3 device. The target architecture is one EC2 instance with Caddy as the public TLS reverse proxy, the FastAPI app behind it, the React bundle served as static files, and the ESP32 talking to the same public domain.

This is the smallest possible production-shape deployment that still satisfies the Phase 12 requirements: HTTPS for the dashboard, `Secure` cookies, and `X-Device-Token` enforced.

---

## Target topology

```
                           +-------------------+
  Browser  ─── HTTPS ─────►|                   |
                           |  Caddy (80/443)   |
  ESP32    ─── HTTPS ─────►|  TLS termination  |
                           +---------+---------+
                                     │  reverse proxy (HTTP)
                                     ▼
                           +-------------------+
                           |  uvicorn          |
                           |  app.main:app     |
                           |  127.0.0.1:8765   |
                           +---------+---------+
                                     │
                                     ▼
                              SQLite file
                              (/srv/lyla/data/taskbot.db)
```

Single VM. SQLite is fine for the single-user / single-device MVP. PostgreSQL migration is a later phase.

---

## Prerequisites

1. AWS account with permission to launch EC2.
2. A domain you control (e.g. `lyla.example.com`). Point an A record to the EC2 elastic IP.
3. Local copy of the repo with `python -m pytest -q` green.

---

## 1. Provision EC2

| Setting | Value |
|---|---|
| AMI | Ubuntu 24.04 LTS (arm64 if you pick Graviton, otherwise x86_64) |
| Instance type | `t4g.small` (2 vCPU, 2 GB RAM) — enough for MVP |
| Storage | 20 GB gp3 |
| Security group inbound | 22 (your IP), 80 (0.0.0.0/0), 443 (0.0.0.0/0) |
| Elastic IP | Allocate + associate |

DNS: `A lyla.example.com → <elastic ip>`. Wait until `dig lyla.example.com` resolves before continuing — Caddy needs DNS to mint a cert.

---

## 2. System packages

SSH in:

```bash
ssh -i ~/.ssh/your-key.pem ubuntu@lyla.example.com
sudo apt update && sudo apt -y upgrade
sudo apt -y install python3.12 python3.12-venv python3-pip git nodejs npm sqlite3 ufw
```

Firewall:

```bash
sudo ufw allow 22
sudo ufw allow 80
sudo ufw allow 443
sudo ufw --force enable
```

Install Caddy:

```bash
sudo apt -y install debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | \
  sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | \
  sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update
sudo apt -y install caddy
```

---

## 3. Deploy backend

```bash
sudo mkdir -p /srv/lyla
sudo chown ubuntu:ubuntu /srv/lyla
cd /srv/lyla
git clone https://github.com/<your-org>/lyla-agent.git app
cd app

python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

mkdir -p /srv/lyla/data
cp .env.example .env
```

Edit `/srv/lyla/app/.env` with production values:

```dotenv
APP_ENV=production
DATABASE_URL=sqlite:////srv/lyla/data/taskbot.db
TIMEZONE=Asia/Jakarta

# Real Gemini if you have a key. Leave empty for fake mode.
GOOGLE_API_KEY=
GOOGLE_ADK_MODEL=gemini-3-flash-preview
AGENT_MODE=

# Auth (Phase 12). Production = Secure cookies.
DASHBOARD_USERNAME=admin
DASHBOARD_PASSWORD_SCRYPT=<paste from scripts.hash_dashboard_password>
SESSION_TTL_HOURS=24
COOKIE_SECURE=true
LOGIN_RATE_LIMIT_MAX_FAILS=5
LOGIN_RATE_LIMIT_WINDOW_SECONDS=300

# Device gate (production = ON).
REQUIRE_DEVICE_TOKEN=true

# Public URL embedded into config_json on /devices/pair.
BASE_URL=https://lyla.example.com
MVP_USER_EMAIL=demo@taskbot.local

# Audio. Set to gemini if you have GOOGLE_API_KEY.
AUDIO_STT_MODE=gemini
AUDIO_TTS_MODE=gemini

# Scheduler.
SCHEDULER_ENABLED=true
SCHEDULER_INTERVAL_SECONDS=60
```

Generate the password hash and paste it back in:

```bash
python -m scripts.hash_dashboard_password --password '<your-strong-password>'
# Copy the salt:hash and paste as DASHBOARD_PASSWORD_SCRYPT
```

Migrate + seed:

```bash
python -m alembic upgrade head
python -m scripts.seed_dev   # prints demo user_id + device_id; save them
```

Smoke:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8765
# Ctrl+C after curl http://127.0.0.1:8765/healthz works
```

---

## 4. systemd service for uvicorn

`/etc/systemd/system/lyla-backend.service`:

```ini
[Unit]
Description=Lyla FastAPI backend
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/srv/lyla/app
EnvironmentFile=/srv/lyla/app/.env
ExecStart=/srv/lyla/app/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8765 --workers 1
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
```

`--workers 1` is intentional. The Phase 12 session store and login rate limiter are in-memory per process (`app/auth/session.py`, `app/api/_rate_limit.py`). Running multiple workers means a login cookie issued by worker A is unknown to worker B, so requests round-robined to the wrong worker fail with "Sesi habis" (401). For the single-user MVP one async worker handles hundreds of concurrent connections — bumping to multiple workers requires moving the session store to Redis or the database first.

Activate:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now lyla-backend
sudo systemctl status lyla-backend
```

---

## 5. Build + deploy frontend

On the SAME EC2:

```bash
cd /srv/lyla/app/frontend
cp .env.example .env
```

Edit `frontend/.env`:

```
VITE_API_BASE_URL=        # leave empty — frontend and backend share origin
VITE_DEMO_USER_ID=<uuid printed by seed_dev>
VITE_DEMO_DEVICE_ID=<uuid printed by seed_dev>
```

Build:

```bash
npm ci
npm run build
```

Output is in `/srv/lyla/app/frontend/dist`. Caddy will serve this directory.

---

## 6. Caddy reverse proxy + static files

`/etc/caddy/Caddyfile`:

```caddyfile
lyla.example.com {
    encode zstd gzip

    # Backend API paths go to uvicorn
    @api {
        path /agent* /auth* /dashboard* /devices* /observability* /healthz
    }
    handle @api {
        reverse_proxy 127.0.0.1:8765
    }

    # Everything else = static React SPA
    handle {
        root * /srv/lyla/app/frontend/dist
        try_files {path} /index.html
        file_server
    }
}
```

Reload:

```bash
sudo systemctl reload caddy
sudo systemctl status caddy
```

Caddy automatically obtains and renews a Let's Encrypt cert.

Smoke test:

```bash
curl -I https://lyla.example.com/healthz
# expect 200
curl -I https://lyla.example.com/
# expect 200 with HTML
```

---

## 7. First-time pairing for ESP32

1. Visit `https://lyla.example.com`, login with `admin` + the password you hashed.
2. Go to **Devices → Pair New Device**, name it (e.g. "Lyla Demo Unit").
3. Copy the printed `config_json`. It already contains `base_url=https://lyla.example.com` and `device_token`.
4. Edit the JSON locally and fill in `wifi.ssid` + `wifi.password`.
5. Save as `/sd/config.json` on the microSD card. Insert into the ESP, power on.
6. Confirm in **Observability → Devices** that the heartbeat lands within 60s.

Detailed firmware flashing: [`firmware/README.md`](firmware/README.md).

---

## 8. Updates / redeploys

```bash
ssh ubuntu@lyla.example.com
cd /srv/lyla/app
git pull
source .venv/bin/activate
pip install -r requirements.txt
python -m alembic upgrade head
sudo systemctl restart lyla-backend

cd frontend
npm ci
npm run build
sudo systemctl reload caddy
```

No downtime windows planned for MVP — uvicorn restart is sub-second; Caddy reload is graceful.

---

## 9. Backups

The whole production state is one SQLite file:

```bash
sudo cp /srv/lyla/data/taskbot.db /srv/lyla/data/taskbot.db.$(date +%F).bak
```

Cron daily + S3 sync is enough for MVP:

```bash
sudo crontab -e
0 3 * * * aws s3 cp /srv/lyla/data/taskbot.db s3://lyla-backups/taskbot-$(date +\%F).db
```

---

## 10. Operations checklist

| Concern | Action |
|---|---|
| `/healthz` 5xx | `journalctl -u lyla-backend -n 200` |
| TLS handshake errors | `journalctl -u caddy -n 200`, confirm DNS + ports 80/443 |
| Cookie not set on login | Confirm `COOKIE_SECURE=true`, request really came via `https://...` |
| ESP can't reach backend | Confirm `https://lyla.example.com/healthz` from a phone on the same WiFi |
| ESP getting 401 on `/agent/audio` | Token mismatch — pair the device again, rewrite SD card |
| Login rate-limited | `LOGIN_RATE_LIMIT_*` settings; rate-limit state is per-process and resets on restart |

---

## 11. Hardening checklist (post-MVP)

- Move SQLite → managed PostgreSQL (RDS).
- Move static files to CloudFront + S3.
- ALB in front of multiple uvicorn workers; pin sessions to Redis.
- Replace stdlib scrypt with passlib + argon2 if multi-user lands.
- Replace `setInsecure()` on ESP with bundled root CA.
- Restrict EC2 outbound to `*.googleapis.com` + Caddy ACME endpoints.
- Add structured log shipping (CloudWatch / Loki).

These are deliberately out of scope for the MVP.

---

## 12. Common deployment failures

| Symptom | Fix |
|---|---|
| `caddy: error obtaining certificate` | DNS not pointing to EIP yet; wait for propagation |
| `sqlite3.OperationalError: unable to open database file` | `/srv/lyla/data` not writable by `ubuntu` user |
| `502 Bad Gateway` from Caddy | uvicorn down: `sudo systemctl status lyla-backend` |
| Login works in Postman but not browser | Cookie blocked. Check `COOKIE_SECURE`, browser DevTools → Application → Cookies |
| Frontend build complains about missing `VITE_*` | Set them in `frontend/.env` BEFORE `npm run build`; Vite bakes them at build time |

---

## 13. Where to read next

- [`README.md`](README.md) — localhost runbook + dev tips.
- [`docs/ESP32_INTEGRATION_CONTRACT.md`](docs/ESP32_INTEGRATION_CONTRACT.md) — normative ESP ↔ backend contract.
- [`firmware/README.md`](firmware/README.md) — firmware build / flash / SD card.
