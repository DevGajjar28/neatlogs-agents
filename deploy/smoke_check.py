"""Pre-video smoke checks (run from laptop or EC2).

Usage:
  python deploy/smoke_check.py
  python deploy/smoke_check.py --api http://EC2_PUBLIC_IP:8000
  python deploy/smoke_check.py --api https://YOUR.vercel.app
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request


def get_json(url: str) -> tuple[int, object]:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        return exc.code, (exc.read().decode("utf-8", errors="replace")[:300])
    except Exception as exc:  # noqa: BLE001
        return 0, str(exc)


def main() -> int:
    parser = argparse.ArgumentParser(description="SignalSDR deploy smoke checks")
    parser.add_argument(
        "--api",
        default="http://127.0.0.1:8000",
        help="API origin (EC2 :8000 or Vercel origin if using /api rewrite)",
    )
    args = parser.parse_args()
    base = args.api.rstrip("/")
    # Accept either http://host:8000 or https://vercel.app (same-origin /api)
    if base.endswith("/api"):
        api = base
        root = base[: -len("/api")] or base
    else:
        api = f"{base}/api"
        root = base

    ok = True
    print(f"Checking {api}/health …")
    status, body = get_json(f"{api}/health")
    if status == 200 and isinstance(body, dict) and body.get("ok") is True:
        print("  OK health")
    else:
        print(f"  FAIL health status={status} body={body!r}")
        ok = False

    print(f"Checking {api}/system/status …")
    status, body = get_json(f"{api}/system/status")
    if status == 200 and isinstance(body, dict):
        hunter = (body.get("hunter") or {}).get("configured")
        mail_err = body.get("mail_account_error")
        print(f"  OK status hunter={hunter} mail_account_error={mail_err}")
        if mail_err:
            print("  WARN: re-verify mail account in Settings before filming")
    else:
        print(f"  FAIL status status={status} body={body!r}")
        ok = False

    print(f"Checking {api}/campaigns …")
    status, body = get_json(f"{api}/campaigns")
    if status == 200:
        n = len(body) if isinstance(body, list) else "?"
        print(f"  OK campaigns ({n})")
    else:
        print(f"  FAIL campaigns status={status} body={body!r}")
        ok = False

    print()
    print("Manual (after Vercel + EC2):")
    print(f"  1. Open UI: {root if 'vercel' in root else 'https://YOUR.vercel.app'}")
    print("  2. Company research drawer + system sidebar")
    print("  3. systemctl status signalsdr-api  # worker must be active")
    print("  4. Stop/terminate EC2 after the video")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
