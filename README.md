# SignalSDR

Outbound agent for neatHack 2026. It researches a seller, finds lookalike buyers, and drafts email that can be sent only when each factual claim has a source. Demo mode never delivers to a real prospect.

## Setup

Python 3.11 or newer.

```bash
py -3.11 -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
copy .env.example .env
```

Fill `.env` locally. `AWS_PROFILE` and `AWS_REGION` select the Bedrock profile. `LLM_MODEL_STRONG` and `LLM_MODEL_FAST` are Bedrock model IDs. No access keys belong in code or in git.

```bash
python cli.py --help
pytest
```

After `.env` is filled, `python cli.py ping-llm` sends one short Bedrock call through neatlogs.

`DATA_MODE=replay` and `DEMO_MODE=true` are the defaults. Replay does not call Crustdata. Demo mode will only hand mail to a local SMTP catcher on `SMTP_HOST` / `SMTP_PORT` (default `localhost:1025`). Docker is not required.

## Commands

```bash
python cli.py run --n 10
python cli.py approve <campaign_id> --yes
python cli.py serve-ui
python cli.py run --narrow-icp   # force planner replan.widen_icp
```

`run` stops at the ICP human gate; `approve` resumes. UI: `http://127.0.0.1:8080/campaigns/<id>/icp`.

## Team

DevGajjar28

## Evidence

- neatlogs: workflow traces for `llm-smoke`, `doctor-crustdata`, and `outbound-v0` (campaign `v0-posthog-live2`)
- Entire checkpoint: https://entire.io/gh/DevGajjar28/neatlogs-agents/commit/fbc6a690a2013e1288666f3a5e75a8e1c9261aa9 (checkpoint ID: `01M4K32PNHG5B8VRZ6Z7Q2NKVK`)
- Best submission pick: prefer a recovery commit that links a neatlogs failure trace ID in the message (`[trace: <id>]`)

## Limitations

This is a hackathon build. It is not legal advice on outreach. Rules such as GDPR and India's DPDP Act vary by region. Nothing is sent until a verifier and a person approve it, and demo sends stay on the local catcher.
