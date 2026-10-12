# Deploy SignalSDR (Vercel UI + EC2 API)

Video URL should be the **Vercel** HTTPS link. The API runs on **one** EC2 instance in `us-east-1` / `Hackathon_VPC`.

## Architecture

```
Browser → https://YOUR.vercel.app  (Next.js)
        → /api/* rewrite (Vercel server)
        → http://EC2_PUBLIC_IP:8000/api  (FastAPI + worker + SQLite)
```

Hackathon AWS allows **EC2 / Lambda / IAM / LBs only**. Put **your own Bedrock keys** on the EC2 `.env` — not the neatHack IAM keys.

## 1. EC2 (us-east-1)

1. Terminate any existing team EC2 first (one-instance limit).
2. Launch Amazon Linux 2023, **t2.small** (preferred) or **t2.micro**, EBS ≤20 GB, public IP, **Hackathon_VPC**.
3. Security group: SSH 22 (your IP); **8000** from `0.0.0.0/0` (needed for Vercel server-side rewrite). Outbound all.
4. SSH in, clone the repo to `~/neatlogs`, fill `.env` (never commit it):

```bash
API_HOST=0.0.0.0
CORS_ORIGINS=http://localhost:3000,https://YOUR_PROJECT.vercel.app
UI_BASE_URL=https://YOUR_PROJECT.vercel.app
# Must match Google Cloud → OAuth client → Authorized redirect URIs (and Vercel rewrite).
GOOGLE_CALENDAR_REDIRECT_URI=https://YOUR_PROJECT.vercel.app/api/calendar/oauth/callback
# + Bedrock (personal), CRUSTDATA_*, HUNTER_API_KEY, SIGNALSDR_SECRET_KEY, etc.
# After changing redirect URI: restart systemd (`sudo systemctl restart signalsdr-api`)
# and reconnect Calendar in Settings. Local vs cloud use different redirect URIs —
# never mix localhost UI with a Vercel redirect_uri (causes ?calendar=error&reason=state|token).
```

5. Bootstrap:

```bash
chmod +x deploy/ec2/bootstrap.sh
./deploy/ec2/bootstrap.sh
```

6. Smoke on the box: `curl -s http://127.0.0.1:8000/api/health`  
   From your laptop: `curl -s http://EC2_PUBLIC_IP:8000/api/health`

Worker is included via `cli.py serve --with-worker` (systemd unit `signalsdr-api`).

## 2. Vercel

1. Import the GitHub repo; **Root Directory** = `web`.
2. Environment variables:

| Name | Value |
|------|--------|
| `NEXT_PUBLIC_API_BASE` | `/api` |
| `API_UPSTREAM` | `http://EC2_PUBLIC_IP:8000` |

3. Deploy. Open `https://YOUR_PROJECT.vercel.app`.

4. In Google Cloud OAuth client, add the Calendar redirect URI above; reconnect Calendar in Settings after deploy.

## 3. Video smoke checklist

- [ ] Vercel home + campaigns load
- [ ] Sidebar system status (credits / Hunter / model) loads
- [ ] Company name opens research drawer
- [ ] Settings → mail account **ok** (Verify if needed)
- [ ] IMAP worker: `systemctl status signalsdr-api` active
- [ ] Prefer `n=1` Live campaigns on t2.micro
- [ ] **Stop/terminate EC2** after filming (protect $25 + secrets)

## Local vs deploy

| | Local | Deploy |
|--|--------|--------|
| `NEXT_PUBLIC_API_BASE` | `http://127.0.0.1:8000/api` | `/api` |
| `API_UPSTREAM` | unset | `http://EC2:8000` |
| `API_HOST` | `127.0.0.1` | `0.0.0.0` |

## Edge cases

- **Mixed content:** never point the browser at `http://EC2` from HTTPS Vercel — always use `/api` + rewrite.
- **No API auth:** treat as temporary demo; stop the instance after.
- **OOM:** enable swap (bootstrap does this); use t2.small if you can.
- **Secrets:** only on EC2 `.env`, never in Vercel or git.
