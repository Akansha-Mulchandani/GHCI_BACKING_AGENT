"""Small Twilio Verify adapter used by the verification agent.

This module provides thin wrappers around Twilio Verify API calls and returns
small dicts so the calling agent can inspect statuses safely.

CRITICAL: Twilio is REQUIRED for OTP verification. There is no fallback to mock OTP.

Environment variables required:
  - TWILIO_ACCOUNT_SID
  - TWILIO_AUTH_TOKEN
  - TWILIO_VERIFY_SERVICE_SID

If any of these are missing or Twilio is unavailable, OTP verification will fail.
No fallback mechanisms are available.
"""
import os
from typing import Dict, Optional

try:
    from twilio.rest import Client
except Exception:
    Client = None


def _client() -> Optional[Client]:
    if not Client:
        print("[DEBUG _client] Twilio Client not imported")
        return None
    acct = os.getenv("TWILIO_ACCOUNT_SID")
    token = os.getenv("TWILIO_AUTH_TOKEN")
    print(f"[DEBUG _client] acct={acct is not None}, token={token is not None}")
    if not acct or not token:
        print("[DEBUG _client] Missing credentials")
        return None
    return Client(acct, token)


def send_verification_code(phone_number: str, channel: str = "sms") -> Dict:
    """Trigger a Twilio Verify verification to the given phone number.

    Returns a minimal dict describing the attempt. If Twilio is not available or
    required env vars are missing, returns {"status": "unavailable"}.
    """
    svc = os.getenv("TWILIO_VERIFY_SERVICE_SID")
    client = _client()
    if not client or not svc:
        print(f"[DEBUG send_verification_code] No client or svc. client={client is not None}, svc={svc is not None}")
        return {"status": "unavailable"}

    try:
        print(f"[DEBUG send_verification_code] Sending to {phone_number} via {channel} using service {svc}")
        verification = client.verify.services(svc).verifications.create(to=phone_number, channel=channel)
        result = {"sid": getattr(verification, "sid", None), "status": getattr(verification, "status", None)}
        print(f"[DEBUG send_verification_code] Result: {result}")
        return result
    except Exception as e:
        print(f"[ERROR send_verification_code] {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "error": str(e)}


def check_verification_code(phone_number: str, code: str) -> Dict:
    """Check a verification code with Twilio Verify.

    Returns a dict with status. Example: {"status": "approved"}.
    If Twilio is not available returns {"status": "unavailable"}.
    """
    svc = os.getenv("TWILIO_VERIFY_SERVICE_SID")
    client = _client()
    if not client or not svc:
        print(f"[DEBUG check_verification_code] No client or svc. client={client is not None}, svc={svc is not None}")
        return {"status": "unavailable"}

    try:
        print(f"[DEBUG check_verification_code] Checking code {code} for {phone_number} using service {svc}")
        verification_check = client.verify.services(svc).verification_checks.create(to=phone_number, code=code)
        result = {"sid": getattr(verification_check, "sid", None), "status": getattr(verification_check, "status", None)}
        print(f"[DEBUG check_verification_code] Result: {result}")
        return result
    except Exception as e:
        print(f"[ERROR check_verification_code] {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "error": str(e)}

