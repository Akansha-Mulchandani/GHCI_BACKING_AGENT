from datetime import datetime, timedelta
import os
import secrets
from typing import Optional

from google.adk.agents import Agent
from google.adk.tools.tool_context import ToolContext
# Import transfer tool to allow auto-completing pending transfers after validation
try:
    from ..transaction_agent.agent import transfer_funds
except Exception:
    transfer_funds = None

# Import storage tools for database sync (optional)
try:
    import sys
    import os as os_module
    # Add parent directories to path for imports
    sys.path.insert(0, os_module.path.dirname(os_module.path.dirname(os_module.path.dirname(os_module.path.dirname(__file__)))))
    from storage_tools import sync_state_with_db, save_auth_token_to_db
    _HAS_DB_STORAGE = True
    print(f"[VERIFICATION_AGENT] Successfully imported storage_tools")
except Exception as e:
    sync_state_with_db = None
    save_auth_token_to_db = None
    _HAS_DB_STORAGE = False
    print(f"[VERIFICATION_AGENT] Failed to import storage_tools: {e}")

# Import user validation tool for checking user existence
try:
    from .user_validation import check_user_exists
    _HAS_USER_VALIDATION = True
    print(f"[VERIFICATION_AGENT] Successfully imported user_validation")
except Exception as e:
    check_user_exists = None
    _HAS_USER_VALIDATION = False
    print(f"[VERIFICATION_AGENT] Failed to import user_validation: {e}")

# Try to import the Twilio adapter; Twilio is REQUIRED for OTP verification.
try:
    from .twilio_adapter import send_verification_code, check_verification_code
    _HAS_TWILIO = True
    print(f"[VERIFICATION_AGENT] Successfully imported Twilio adapter")
except Exception as e:
    send_verification_code = None
    check_verification_code = None
    _HAS_TWILIO = False
    print(f"[VERIFICATION_AGENT] ❌ CRITICAL: Twilio adapter not available: {e}")





def check_user_exists(tool_context: ToolContext, phone_number: str) -> dict:
    """Check if a user exists in the database WITHOUT creating them.
    
    Args:
        tool_context: ToolContext containing mutable session state.
        phone_number: The phone number to check (e.g., "+919999999999").
    
    Returns:
        dict with status (exists/not_found) and user info if found
    """
    try:
        print(f"[VERIFICATION_AGENT] check_user_exists() called for {phone_number}")
        
        if _HAS_DB_STORAGE:
            from storage_tools import load_user_profile_from_db
            user_data = load_user_profile_from_db(phone_number)
            
            if user_data.get("found"):
                print(f"[VERIFICATION_AGENT] User found: {phone_number}")
                return {
                    "status": "exists",
                    "message": f"User {phone_number} exists in our system",
                    "user_id": user_data.get("user_id"),
                    "phone_number": phone_number
                }
            else:
                print(f"[VERIFICATION_AGENT] User NOT found: {phone_number}")
                return {
                    "status": "not_found",
                    "message": f"User {phone_number} not found. You can register as a new user.",
                    "phone_number": phone_number
                }
        else:
            # DB storage not available
            return {
                "status": "error",
                "message": "Database not available for user lookup"
            }
    except Exception as e:
        print(f"[VERIFICATION_AGENT ERROR] check_user_exists failed: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": f"Failed to check user: {str(e)}"}


def set_user_phone(tool_context: ToolContext, phone_number: str) -> dict:
    """Set the user's phone number in session state for verification purposes.
    
    Args:
        tool_context: ToolContext containing mutable session state.
        phone_number: The phone number (can be 10 digits or +91XXXXXXXXXX format).
    """
    try:
        print(f"\n[VERIFICATION_AGENT] ========== SET USER PHONE ==========")
        print(f"[VERIFICATION_AGENT] set_user_phone() called with: {phone_number}")
        if not phone_number:
            print(f"[VERIFICATION_AGENT] ❌ ERROR: Phone number is empty")
            return {"status": "error", "message": "Phone number cannot be empty."}
        
        # Format phone number: add +91 if only 10 digits
        from storage_tools import format_phone_number
        formatted_phone = format_phone_number(phone_number)
        print(f"[VERIFICATION_AGENT] Formatted phone: '{phone_number}' → '{formatted_phone}'")
        
        # tool_context.state is a google.adk.sessions.state.State object (dict-like)
        # We can read/write using [] notation
        state = tool_context.state
        state["user_phone"] = formatted_phone
        print(f"[VERIFICATION_AGENT] ✅ Phone stored in state: {formatted_phone}")
        print(f"[VERIFICATION_AGENT] Verifying state contains: {state.get('user_phone')}")
        
        # CRITICAL: Sync user data from database now that we have the phone number
        print(f"[VERIFICATION_AGENT] Attempting DB sync for existing user data")
        if _HAS_DB_STORAGE and sync_state_with_db:
            try:
                print(f"[VERIFICATION_AGENT] Calling sync_state_with_db({formatted_phone})")
                sync_result = sync_state_with_db(state, formatted_phone)
                print(f"[VERIFICATION_AGENT] sync_state_with_db returned: {sync_result}")
                if sync_result:
                    state["db_synced"] = True
                    print(f"[VERIFICATION_AGENT] ✅ Successfully loaded existing user data from database")
                else:
                    print(f"[VERIFICATION_AGENT] ℹ️  User not in database yet (sync returned False) - will be created later")
            except Exception as sync_err:
                print(f"[VERIFICATION_AGENT] ⚠️  DB sync warning: {type(sync_err).__name__}: {sync_err}")
                import traceback
                traceback.print_exc()
        
        print(f"[VERIFICATION_AGENT] ========== SET USER PHONE COMPLETE ==========\n")
        return {"status": "ok", "message": f"Phone number set to {formatted_phone}", "user_phone": formatted_phone}
    except Exception as e:
        print(f"[VERIFICATION_AGENT ERROR] set_user_phone failed: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        print(f"[VERIFICATION_AGENT] ========== SET USER PHONE COMPLETE (ERROR) ==========\n")
        return {"status": "error", "message": f"Failed to set phone: {str(e)}"}


def create_new_user_account(tool_context: ToolContext, phone_number: str) -> dict:
    """Create a new user account with default checking and savings accounts.
    
    IMPORTANT: This should ONLY be called after check_user_exists confirms the user does NOT exist!
    
    Args:
        tool_context: ToolContext containing mutable session state.
        phone_number: The phone number (can be 10 digits or +91XXXXXXXXXX format).
    
    Returns:
        Status dict with user_id and account information if successful.
    """
    try:
        print(f"\n[VERIFICATION_AGENT] ========== CREATE NEW USER ACCOUNT ==========")
        print(f"[VERIFICATION_AGENT] create_new_user_account() called with: {phone_number}")
        
        # Format phone number
        from storage_tools import format_phone_number, create_user_profile_in_db
        formatted_phone = format_phone_number(phone_number)
        print(f"[VERIFICATION_AGENT] Formatted phone to: {formatted_phone}")
        
        if not _HAS_DB_STORAGE:
            print(f"[VERIFICATION_AGENT] ❌ ERROR: Database storage not available")
            return {"status": "error", "message": "Database storage not available"}
        
        # Create the user in database
        print(f"[VERIFICATION_AGENT] Calling create_user_profile_in_db()")
        result = create_user_profile_in_db(formatted_phone, name="User", email=None)
        print(f"[VERIFICATION_AGENT] create_user_profile_in_db() returned: {result}")
        
        if not result.get("success"):
            print(f"[VERIFICATION_AGENT] ❌ Failed to create user: {result.get('message')}")
            print(f"[VERIFICATION_AGENT] ========== CREATE NEW USER ACCOUNT COMPLETE (FAILED) ==========\n")
            return {"status": "error", "message": f"Failed to create account: {result.get('message', 'Unknown error')}"}
        
        print(f"[VERIFICATION_AGENT] ✅ New user created successfully with user_id: {result.get('user_id')}")
        
        # Now sync to state
        state = tool_context.state
        state["user_phone"] = formatted_phone
        print(f"[VERIFICATION_AGENT] Set user_phone in state: {formatted_phone}")
        
        # Sync from database to get the created user's data
        print(f"[VERIFICATION_AGENT] Calling sync_state_with_db()")
        if sync_state_with_db:
            try:
                sync_result = sync_state_with_db(state, formatted_phone)
                print(f"[VERIFICATION_AGENT] sync_state_with_db() returned: {sync_result}")
                if sync_result:
                    state["db_synced"] = True
                    print(f"[VERIFICATION_AGENT] ✅ Successfully synced new user data to state")
                else:
                    print(f"[VERIFICATION_AGENT] ⚠️  sync_state_with_db returned False")
            except Exception as sync_err:
                print(f"[VERIFICATION_AGENT] ⚠️  DB sync warning: {type(sync_err).__name__}: {sync_err}")
                import traceback
                traceback.print_exc()
        
        print(f"[VERIFICATION_AGENT] ========== CREATE NEW USER ACCOUNT COMPLETE (SUCCESS) ==========\n")
        return {
            "status": "ok",
            "message": f"Account created successfully for {formatted_phone}",
            "user_phone": formatted_phone,
            "user_id": result.get("user_id"),
            "created": True
        }
    except Exception as e:
        print(f"[VERIFICATION_AGENT ERROR] create_new_user_account failed: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": f"Failed to create account: {str(e)}"}


def set_user_phone(tool_context: ToolContext, phone_number: str) -> dict:
    """Set the user's phone number in session state for verification purposes.
    
    Args:
        tool_context: ToolContext containing mutable session state.
        phone_number: The phone number (can be 10 digits or +91XXXXXXXXXX format).
    """
    try:
        print(f"[VERIFICATION_AGENT] set_user_phone() called with: {phone_number}")
        if not phone_number:
            print(f"[VERIFICATION_AGENT] ERROR: Phone number is empty")
            return {"status": "error", "message": "Phone number cannot be empty."}
        
        # Format phone number: add +91 if only 10 digits
        from storage_tools import format_phone_number
        formatted_phone = format_phone_number(phone_number)
        print(f"[VERIFICATION_AGENT] Formatted phone from '{phone_number}' to '{formatted_phone}'")
        
        # tool_context.state is a google.adk.sessions.state.State object (dict-like)
        # We can read/write using [] notation
        state = tool_context.state
        state["user_phone"] = formatted_phone
        print(f"[VERIFICATION_AGENT] Phone number stored in state: {formatted_phone}")
        print(f"[VERIFICATION_AGENT] Verifying state contains: {state.get('user_phone')}")
        
        # CRITICAL: Sync user data from database now that we have the phone number
        if _HAS_DB_STORAGE and sync_state_with_db:
            try:
                print(f"[VERIFICATION_AGENT] Attempting DB sync for {formatted_phone}")
                sync_result = sync_state_with_db(state, formatted_phone)
                print(f"[VERIFICATION_AGENT] DB sync completed: {sync_result}")
                if sync_result:
                    state["db_synced"] = True
                    print(f"[VERIFICATION_AGENT] Successfully loaded user data from database")
            except Exception as sync_err:
                print(f"[VERIFICATION_AGENT] DB sync warning (not critical): {sync_err}")
        
        return {"status": "ok", "message": f"Phone number set to {formatted_phone}", "user_phone": formatted_phone}
    except Exception as e:
        print(f"[VERIFICATION_AGENT ERROR] set_user_phone failed: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": f"Failed to set phone: {str(e)}"}

def request_otp(tool_context: ToolContext, phone_number: str) -> dict:
    """Request an OTP via Twilio Verify. This requires TWILIO credentials to be configured.

    Args:
        tool_context: ToolContext containing mutable session state.
        phone_number: Phone number to send the OTP to (can be 10 digits or +91XXXXXXXXXX).
    
    Returns:
        dict with status and OTP details from Twilio
    """
    try:
        state = tool_context.state
        
        # Format phone number: add +91 if only 10 digits
        from storage_tools import format_phone_number
        to = phone_number or state.get("user_phone")
        if not to:
            return {"status": "error", "message": "No phone number provided for OTP."}
        to = format_phone_number(to)
        print(f"[VERIFICATION_AGENT] request_otp() formatted phone to: {to}")
        
        # TWILIO ONLY - No mock fallback
        if not _HAS_TWILIO:
            print(f"[VERIFICATION_AGENT] ❌ TWILIO NOT AVAILABLE - cannot send OTP")
            return {
                "status": "error",
                "message": "Twilio Verify is not configured. Please ensure TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, and TWILIO_VERIFY_SERVICE_SID are set."
            }
        
        if not os.getenv("TWILIO_ACCOUNT_SID") or not os.getenv("TWILIO_AUTH_TOKEN") or not os.getenv("TWILIO_VERIFY_SERVICE_SID"):
            print(f"[VERIFICATION_AGENT] ❌ TWILIO CREDENTIALS MISSING")
            return {
                "status": "error",
                "message": "Twilio credentials are not configured. Please set environment variables: TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_VERIFY_SERVICE_SID"
            }
        
        # Send OTP via Twilio
        print(f"[VERIFICATION_AGENT] Sending OTP via Twilio to {to}")
        res = send_verification_code(to)
        print(f"[VERIFICATION_AGENT] Twilio response: {res}")
        
        if res.get("status") in ["error", "unavailable"]:
            print(f"[VERIFICATION_AGENT] ❌ Twilio failed to send OTP: {res}")
            return {
                "status": "error",
                "message": f"Failed to send verification code: {res.get('error', 'Twilio service unavailable')}"
            }
        
        # Store lightweight pending entry for audit (don't store the actual OTP code)
        expiry = (datetime.now() + timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
        pending_data = {"method": "twilio", "to": to, "expiry": expiry, "sid": res.get("sid")}
        state["pending_otp"] = pending_data
        
        print(f"[VERIFICATION_AGENT] ✅ OTP sent successfully via Twilio")
        return {
            "status": "ok",
            "via": "twilio",
            "to": to,
            "expiry": expiry,
            "message": f"Verification code sent to {to}. Please check your SMS."
        }
    except Exception as e:
        print(f"[ERROR request_otp] {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": f"Failed to request OTP: {str(e)}"}


def validate_otp(tool_context: ToolContext, code: str) -> dict:
    """Validate an OTP code via Twilio Verify. This requires Twilio credentials.
    
    Args:
        tool_context: ToolContext containing mutable session state.
        code: The OTP code to validate (as provided by user)
    
    Returns:
        dict with auth_token if successful, error message otherwise
    """
    try:
        state = tool_context.state
        user_phone = state.get("user_phone", "")
        pending_otp = state.get("pending_otp", {})
        
        print(f"\n[VALIDATE_OTP] Tool called: phone={user_phone}, code={code}")
        
        # TWILIO ONLY - No mock fallback
        if not _HAS_TWILIO:
            print(f"[VALIDATE_OTP] ❌ TWILIO NOT AVAILABLE - cannot validate OTP")
            return {
                "status": "error",
                "message": "Twilio Verify is not configured. Cannot validate OTP."
            }
        
        if not os.getenv("TWILIO_ACCOUNT_SID") or not os.getenv("TWILIO_AUTH_TOKEN") or not os.getenv("TWILIO_VERIFY_SERVICE_SID"):
            print(f"[VALIDATE_OTP] ❌ TWILIO CREDENTIALS MISSING")
            return {
                "status": "error",
                "message": "Twilio credentials are not configured. Cannot validate OTP."
            }
        
        if not user_phone:
            print(f"[VALIDATE_OTP] ❌ No phone number in state")
            return {"status": "error", "message": "No phone number found. Please set phone number first."}
        
        if not code:
            print(f"[VALIDATE_OTP] ❌ No code provided")
            return {"status": "error", "message": "No verification code provided."}
        
        # Validate via Twilio
        print(f"[VALIDATE_OTP] Validating code with Twilio for {user_phone}")
        check = check_verification_code(user_phone, code)
        print(f"[VALIDATE_OTP] Twilio response: {check}")
        
        # Parse Twilio response
        status = None
        if isinstance(check, dict):
            status = check.get("status")
        else:
            status = getattr(check, "status", None)
        
        # Handle error statuses
        if status in ["error", "unavailable"]:
            print(f"[VALIDATE_OTP] ❌ OTP validation service error. Status: {status}")
            return {
                "status": "error",
                "message": "Verification service temporarily unavailable. Please try again later."
            }
        
        if status != "approved":
            print(f"[VALIDATE_OTP] ❌ OTP validation failed. Status: {status}")
            return {
                "status": "error",
                "message": "Invalid verification code. Please try again."
            }
        
        print(f"[VALIDATE_OTP] ✅ OTP validation successful via Twilio")
        
        # Issue auth token
        token = secrets.token_urlsafe(16)
        expires_at = (datetime.now() + timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")
        state["auth_token"] = {"token": token, "expires_at": expires_at}
        state["is_authenticated"] = True
        
        # Record in history
        history = state.get("interaction_history", [])
        history.append({"action": "validate_otp", "method": "twilio", "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
        state["interaction_history"] = history
        
        # Sync user data from database after successful authentication
        if _HAS_DB_STORAGE and sync_state_with_db:
            try:
                phone_number = state.get("user_phone")
                print(f"[VALIDATE_OTP] Syncing user data from database for {phone_number}")
                if phone_number:
                    result = sync_state_with_db(state, phone_number)
                    print(f"[VALIDATE_OTP] sync_state_with_db returned: {result}")
                    state["db_synced"] = True
                    db_user_id = state.get("db_user_id")
                    print(f"[VALIDATE_OTP] ✅ Successfully synced user data, db_user_id={db_user_id}")
                    
                    # Save auth token to database
                    if save_auth_token_to_db and db_user_id:
                        try:
                            save_result = save_auth_token_to_db(db_user_id, token, expires_at)
                            print(f"[VALIDATE_OTP] Auth token saved to DB: {save_result}")
                        except Exception as token_err:
                            print(f"[VALIDATE_OTP] Warning: Failed to save auth token to DB: {token_err}")
                    
                    # Update last login
                    try:
                        from db_manager import DBManager
                        DBManager.update_last_login(phone_number)
                        print(f"[VALIDATE_OTP] ✅ Last login updated for {phone_number}")
                    except Exception as login_err:
                        print(f"[VALIDATE_OTP] Warning: Failed to update last login: {login_err}")
            except Exception as sync_error:
                print(f"[VALIDATE_OTP] Warning: Failed to sync user data: {sync_error}")
        
        return {
            "status": "success",
            "auth_token": token,
            "expires_at": expires_at,
            "message": "✅ OTP validated successfully",
            "user_phone": user_phone
        }
    except Exception as e:
        print(f"[VALIDATE_OTP] ❌ ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()


verification_agent = Agent(
    name="verification_agent",
    model="gemini-2.0-flash-exp",
    description="Handles OTP/passcode verification and issues short-lived auth tokens (Twilio Verify only).",
    instruction="""
    You are the Verification Agent for AK Bank. Your role is to handle user authentication using Twilio Verify OTP.
    
    CRITICAL REQUIREMENTS:
    - Twilio Verify is REQUIRED - no mock OTP fallback
    - All OTP codes are sent and validated via Twilio
    - Users must have valid Twilio credentials configured
    
    AUTHENTICATION FLOW:
    
    1. REQUEST PHONE NUMBER
       - Ask: "What's your 10-digit phone number?"
       - User provides: 9876543210 or +919876543210
    
    2. SET PHONE NUMBER
       - Call: set_user_phone(phone_number="<user provided>")
    
    3. SEND OTP VIA TWILIO
       - Call: request_otp(phone_number="<formatted phone>")
       - Say: "I've sent a verification code to your phone via SMS. Please enter the code."
       - NOTE: This uses Twilio Verify - actual SMS will be sent
    
    4. VALIDATE CODE VIA TWILIO
       - User provides code (e.g., "123456")
       - Call: validate_otp(code="<user provided>")
       - Twilio validates the code
    
    5. SUCCESS
       - If validation succeeds: "Your identity has been verified. How can I help?"
       - If validation fails: "Invalid code. Please try again."
    
    ERROR HANDLING:
    - If Twilio credentials are missing: Inform user Twilio must be configured
    - If SMS sending fails: Return Twilio error to user
    - If code validation fails: Ask user to request a new code
    
    PHONE FORMAT HANDLING:
    - Accept 10 digits: 9876543210 → +919876543210
    - Accept full format: +919876543210 → unchanged
    - Always confirm: "Just to confirm, is it +919876543210?"
    
    NO MOCK OTP - ALL CODES GO THROUGH TWILIO VERIFY
    """,
    tools=[check_user_exists, set_user_phone, create_new_user_account, request_otp, validate_otp] if check_user_exists else [set_user_phone, create_new_user_account, request_otp, validate_otp],
)
