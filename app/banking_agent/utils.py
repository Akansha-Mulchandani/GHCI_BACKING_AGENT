from datetime import datetime

from google.genai import types


def update_interaction_history(session_service, app_name, user_id, session_id, entry):
    try:
        session = session_service.get_session(app_name=app_name, user_id=user_id, session_id=session_id)
        interaction_history = session.state.get("interaction_history", [])

        if "timestamp" not in entry:
            entry["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        interaction_history.append(entry)

        updated_state = session.state.copy()
        updated_state["interaction_history"] = interaction_history

        session_service.create_session(app_name=app_name, user_id=user_id, session_id=session_id, state=updated_state)
    except Exception as e:
        print(f"Error updating interaction history: {e}")


def add_user_query_to_history(session_service, app_name, user_id, session_id, query):
    update_interaction_history(
        session_service,
        app_name,
        user_id,
        session_id,
        {"action": "user_query", "query": query},
    )


def add_agent_response_to_history(session_service, app_name, user_id, session_id, agent_name, response):
    update_interaction_history(
        session_service,
        app_name,
        user_id,
        session_id,
        {"action": "agent_response", "agent": agent_name, "response": response},
    )


async def process_agent_response(event):
    final_response = None
    if event.content and event.content.parts:
        for part in event.content.parts:
            if hasattr(part, "text") and part.text and not part.text.isspace():
                final_response = part.text.strip()
                print(f"Agent: {final_response}")
    return final_response


async def call_agent_async(runner, user_id, session_id, query):
    content = types.Content(role="user", parts=[types.Part(text=query)])
    final_response_text = None
    agent_name = None

    try:
        async for event in runner.run_async(user_id=user_id, session_id=session_id, new_message=content):
            if event.author:
                agent_name = event.author

            response = await process_agent_response(event)
            if response:
                final_response_text = response
    except Exception as e:
        print(f"ERROR during agent run: {e}")

    if final_response_text and agent_name:
        add_agent_response_to_history(runner.session_service, runner.app_name, user_id, session_id, agent_name, final_response_text)

    return final_response_text


# --- Simple rule-based NLU and action performer for deterministic CLI flows ---
from typing import Tuple, Dict, Any


class SimpleToolContext:
    def __init__(self, state: dict):
        # Tools expect an object with a .state attribute
        self.state = state


def simple_nlu(text: str) -> Tuple[str, Dict[str, Any]]:
    """Very small rule-based NLU returning (intent, entities).

    Intents supported: balance, show_accounts, request_otp, validate_otp, transfer
    For transfer we try to extract amount and a target account id like 'acc-002'.
    """
    t = text.lower()
    if "balance" in t:
        return "balance", {}
    if "show account" in t or "accounts" in t:
        return "show_accounts", {}
    if ("request otp" in t) or ("request" in t and "otp" in t):
        return "request_otp", {}
    if "validate otp" in t or ("validate" in t and "otp" in t) or ("confirm otp" in t):
        # attempt to extract a numeric code after the phrase, e.g. "validate otp 123456"
        import re

        m_code = re.search(r"(?:validate|confirm)\s+(?:otp\s*)?(\d{4,8})", t)
        entities = {}
        if m_code:
            entities["code"] = m_code.group(1)
        return "validate_otp", entities
    # very simple transfer parsing: look for a number and an account id
    if "transfer" in t or "pay" in t or "send" in t:
        # extract amount (digits) and account id like acc-002
        entities: Dict[str, Any] = {}
        # naive amount extraction
        import re

        m = re.search(r"(\d+[\.,]?\d*)", text.replace(',', ''))
        if m:
            try:
                entities["amount"] = float(m.group(1))
            except Exception:
                pass
        acc = re.search(r"acc[-_ ]?\d+", t)
        if acc:
            entities["to_account"] = acc.group(0).replace(' ', '').replace('_', '-')
        return "transfer", entities

    # set phone: detect explicit phone-setting phrases or a plain phone number
    import re
    m_phone_phrase = re.search(r"(?:my phone is|my number is|phone is)\s*(\+?\d{7,15})", t)
    if m_phone_phrase:
        return "set_phone", {"phone": m_phone_phrase.group(1)}
    # bare phone number as input
    m_phone_only = re.fullmatch(r"\+?\d{7,15}", text.strip())
    if m_phone_only:
        return "set_phone", {"phone": text.strip()}

    return "unknown", {}


def perform_action(session_service, app_name, user_id, session_id, intent: str, entities: dict) -> Tuple[str, dict]:
    """Perform the deterministic action for recognized intents.

    Returns (user_facing_message, result_dict)
    """
    # lazy imports to avoid circulars at module import time
    from banking_agent.sub_agents.transaction_agent.agent import get_balance, transfer_funds
    from banking_agent.sub_agents.verification_agent.agent import request_otp, validate_otp

    session = session_service.get_session(app_name=app_name, user_id=user_id, session_id=session_id)
    state = session.state
    ctx = SimpleToolContext(state)

    if intent == "balance" or intent == "show_accounts":
        res = get_balance(ctx)
        
        # CRITICAL: Check for authentication error FIRST
        if res.get("status") == "error":
            msg = res.get("message", "Failed to retrieve balance.")
            return msg, res
        
        # Prepare a user-facing message
        accounts = res.get("accounts", [])
        lines = []
        for a in accounts:
            lines.append(f"{a.get('type').capitalize()} ({a.get('id')}): {a.get('available_balance')} {a.get('currency')}")
        msg = "\n".join(lines) if lines else "No accounts found."
        return msg, res

    if intent == "request_otp":
        res = request_otp(ctx)
        # Persist state changes made by tool to the session service
        try:
            session_service.create_session(app_name=app_name, user_id=user_id, session_id=session_id, state=state)
        except Exception:
            # session_service may not be available in this scope in some tests; ignore if so
            pass
        # If Twilio was used we don't reveal the OTP; inform the user the SMS was sent.
        if res.get("method") == "twilio" or res.get("via") == "twilio" or res.get("twilio_result") is not None:
            msg = "An SMS with a verification code was sent to your phone. Please enter the code using: validate otp <code>"
        else:
            msg = f"An OTP has been generated. It is {res.get('otp')} and will expire on {res.get('expiry')}."
        return msg, res

    if intent == "set_phone":
        phone = entities.get("phone") if entities else None
        if not phone:
            return ("I didn't understand the phone number. Please send in E.164 format like +15551234567.", {} )
        state["user_phone"] = phone
        try:
            session_service.create_session(app_name=app_name, user_id=user_id, session_id=session_id, state=state)
        except Exception:
            pass
        return (f"Thanks — I'll use {phone} for verification. When you're ready, ask me to perform the action.", {"status":"ok","user_phone":phone})

    if intent == "validate_otp":
        # pass through any extracted code from NLU
        code = entities.get("code") if entities else None
        res = validate_otp(ctx, code=code)
        # Persist state changes (auth token) back into session storage
        try:
            session_service.create_session(app_name=app_name, user_id=user_id, session_id=session_id, state=state)
        except Exception:
            pass
        if res.get("status") == "success":
            msg = f"The OTP has been validated. Here is your auth token: {res.get('auth_token')}. It will expire at {res.get('expires_at')}."
            # If the validation auto-executed a pending transfer, include that result in the message
            auto = res.get("auto_transfer")
            if auto is not None:
                if auto.get("status") == "success":
                    msg += f"\nYour pending transfer completed. Transaction ID: {auto.get('transaction_id')}."
                else:
                    msg += f"\nI attempted the pending transfer but it failed: {auto.get('message', 'unknown error')}."
        else:
            msg = res.get("message", "OTP validation failed.")
        return msg, res

    if intent == "transfer":
        # place transfer_request in state so the tool can read it
        transfer_request = {
            "amount": entities.get("amount", None) or 100.0,
            "to_account": entities.get("to_account", None) or (state.get("accounts", [None, None])[1].get("id") if len(state.get("accounts", [])) > 1 else None),
            "from_account": state.get("accounts", [])[0].get("id") if state.get("accounts") else None,
            "idempotency_key": f"ik-{int(datetime.now().timestamp())}",
            # auth_token expected to be present in state from validation step
            "auth_token": state.get("auth_token", {}).get("token") if state.get("auth_token") else None,
        }
        # If user has no auth token yet, start verification and store pending transfer
        if not transfer_request.get("auth_token"):
            state["pending_transfer"] = transfer_request
            # trigger OTP request (will use user_phone from state)
            otp_res = request_otp(ctx)
            try:
                session_service.create_session(app_name=app_name, user_id=user_id, session_id=session_id, state=state)
            except Exception:
                pass
            if otp_res.get("status") == "ok":
                # Twilio OTP has been sent via SMS
                msg = "I've sent a verification code to your phone via SMS — please reply with: validate otp <code>"
                return msg, {"status":"pending_verification", "otp_res": otp_res}
            else:
                return ("I couldn't send an OTP right now — please try again later.", {"status":"error","detail":otp_res})

        # If auth token exists, perform the transfer immediately
        state["transfer_request"] = transfer_request
        res = transfer_funds(ctx)
        # Persist state changes after transfer (balances, interaction_history, idempotency store)
        try:
            session_service.create_session(app_name=app_name, user_id=user_id, session_id=session_id, state=state)
        except Exception:
            pass
        if res.get("status") == "success":
            msg = f"OK. I have transferred the funds. The transaction ID is {res.get('transaction_id')}."
        else:
            msg = res.get("message", "Transfer failed.")
        return msg, res

    return ("I'm not sure how to help with that.", {})
