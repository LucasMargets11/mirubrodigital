#!/usr/bin/env python3
"""
simulate_mp_webhook.py
======================
Send a simulated Mercado Pago webhook to the local/staging API.
Useful for E2E staging validation without waiting for a real MP event.

Usage:
    python scripts/simulate_mp_webhook.py [OPTIONS]

Options:
    --url       Base URL of the API (default: http://localhost:8000)
    --topic     Webhook topic: subscription_preapproval | payment  (default: subscription_preapproval)
    --data-id   MP resource ID (preapproval ID or payment ID)
    --secret    MP_WEBHOOK_SECRET value (if unset, no x-signature sent — DEV mode)
    --verbose   Print full response body

Examples:
    # Simulate a subscription_preapproval webhook for a preapproval ID
    python scripts/simulate_mp_webhook.py --data-id 2c938084746d3318017478c2360b0000

    # Simulate a payment webhook
    python scripts/simulate_mp_webhook.py --topic payment --data-id 123456789

    # Against staging
    python scripts/simulate_mp_webhook.py --url https://api.myapp.com --data-id ...

    # Via docker exec (from infra/):
    #   docker compose exec api python scripts/simulate_mp_webhook.py --data-id <id>
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import sys
import time
import uuid

try:
    import requests
except ImportError:
    print("requests library not found. Install it: pip install requests")
    sys.exit(1)


def build_signature(secret: str, data_id: str, request_id: str, ts: str) -> str:
    """Compute the x-signature header value as MP does."""
    manifest = f"id:{data_id};request-id:{request_id};ts:{ts}"
    sig = hmac.new(
        secret.encode("utf-8"),
        manifest.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"ts={ts},v1={sig}"


def simulate(
    base_url: str,
    topic: str,
    data_id: str,
    secret: str | None,
    verbose: bool,
) -> int:
    """
    Send a simulated webhook POST and return the HTTP status code.
    """
    webhook_url = f"{base_url.rstrip('/')}/api/v1/billing/mercadopago/webhook"
    request_id = str(uuid.uuid4())
    ts = str(int(time.time()))

    payload = {
        "action": "updated",
        "api_version": "v1",
        "data": {"id": data_id},
        "date_created": "2026-01-01T00:00:00Z",
        "id": int(data_id) if data_id.isdigit() else 0,
        "live_mode": False,
        "type": topic,
        "user_id": "999999999",
    }

    headers = {
        "Content-Type": "application/json",
        "x-request-id": request_id,
    }

    if secret:
        headers["x-signature"] = build_signature(secret, data_id, request_id, ts)
        print(f"[sim] Signed with MP_WEBHOOK_SECRET (ts={ts})")
    else:
        print("[sim] No secret — signature omitted (DEV bypass mode)")

    print(f"[sim] POST {webhook_url}")
    print(f"[sim] topic={topic}  data_id={data_id}  request_id={request_id}")

    try:
        resp = requests.post(webhook_url, json=payload, headers=headers, timeout=15)
    except requests.exceptions.ConnectionError as exc:
        print(f"[sim] ERROR: Could not connect to {webhook_url}: {exc}")
        return 1

    print(f"[sim] Response: HTTP {resp.status_code}")
    if verbose or resp.status_code >= 400:
        try:
            print(json.dumps(resp.json(), indent=2, ensure_ascii=False))
        except Exception:
            print(resp.text[:500])

    if resp.status_code == 200:
        print("[sim] SUCCESS — webhook accepted (HTTP 200)")
        return 0
    else:
        print(f"[sim] UNEXPECTED status {resp.status_code}")
        return 1


def main():
    parser = argparse.ArgumentParser(
        description="Simulate a Mercado Pago webhook for staging/local testing.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--url", default="http://localhost:8000", help="API base URL")
    parser.add_argument(
        "--topic",
        default="subscription_preapproval",
        choices=["subscription_preapproval", "payment"],
        help="Webhook topic",
    )
    parser.add_argument(
        "--data-id",
        required=True,
        dest="data_id",
        help="MP resource ID (preapproval ID or payment ID)",
    )
    parser.add_argument(
        "--secret",
        default=None,
        help="MP_WEBHOOK_SECRET for signature computation (omit for DEV bypass)",
    )
    parser.add_argument("--verbose", action="store_true", help="Print full response body")

    args = parser.parse_args()
    sys.exit(simulate(args.url, args.topic, args.data_id, args.secret, args.verbose))


if __name__ == "__main__":
    main()
