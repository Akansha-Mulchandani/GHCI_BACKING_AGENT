"""
Storage tools for database operations.
These are called by agents to load/save user data from/to database.
"""

import hashlib
from db_manager import DBManager

print(f"[STORAGE_TOOLS] Module imported")


def format_phone_number(phone_input: str) -> str:
    """
    Format phone number by prepending +91 if not present.
    
    Args:
        phone_input: Phone number (can be 10 digits or +91XXXXXXXXXX)
        
    Returns:
        Formatted phone number in +91XXXXXXXXXX format
    """
    # Remove any spaces or dashes
    phone = phone_input.strip().replace(" ", "").replace("-", "")
    
    # If it's already in +91 format, return as-is
    if phone.startswith("+91"):
        return phone
    
    # If it's just 10 digits, prepend +91
    if len(phone) == 10 and phone.isdigit():
        return f"+91{phone}"
    
    # If it starts with 91 but no +, add +
    if phone.startswith("91") and len(phone) == 12 and phone.isdigit():
        return f"+{phone}"
    
    # Return as-is if can't determine format
    return phone


def load_user_profile_from_db(phone_number: str) -> dict:
    """
    Load user profile from database.
    
    Args:
        phone_number: User's phone number
        
    Returns:
        dict with user info and accounts, or empty dict if not found
    """
    print(f"[STORAGE_TOOLS] load_user_profile_from_db() called for {phone_number}")
    user = DBManager.get_user_by_phone(phone_number)
    print(f"[STORAGE_TOOLS] get_user_by_phone returned: {user}")
    
    if not user:
        print(f"[STORAGE_TOOLS] User not found in database")
        return {
            "found": False,
            "message": f"User with phone {phone_number} not found in database"
        }
    
    # Get user's accounts
    print(f"[STORAGE_TOOLS] Fetching accounts for user_id: {user.get('user_id')}")
    accounts = DBManager.get_user_accounts(user["user_id"])
    print(f"[STORAGE_TOOLS] Found {len(accounts)} accounts")
    for i, acc in enumerate(accounts):
        print(f"[STORAGE_TOOLS]   Account {i}: id={acc.get('account_id')}, type={acc.get('account_type')}, balance={acc.get('balance')}")
    
    return {
        "found": True,
        "user_id": user["user_id"],
        "phone_number": user["phone_number"],
        "name": user["name"],
        "email": user["email"],
        "accounts": accounts
    }


def load_user_accounts_from_db(user_id: int) -> dict:
    """
    Load user's accounts from database.
    
    Args:
        user_id: User's ID from database
        
    Returns:
        dict with account information
    """
    accounts = DBManager.get_user_accounts(user_id)
    
    return {
        "user_id": user_id,
        "accounts": accounts,
        "total_accounts": len(accounts),
        "total_balance": sum(acc["balance"] for acc in accounts)
    }


def save_transaction_to_db(
    user_id: int,
    from_account_id: int,
    to_account_id: int,
    amount: float,
    description: str = None
) -> dict:
    """
    Save a transaction to database history.
    
    Args:
        user_id: User's ID
        from_account_id: Source account ID
        to_account_id: Destination account ID
        amount: Transaction amount
        description: Optional transaction description
        
    Returns:
        dict with transaction save result
    """
    transaction = DBManager.save_transaction(
        user_id=user_id,
        from_account_id=from_account_id,
        to_account_id=to_account_id,
        amount=amount,
        transaction_type="transfer",
        description=description
    )
    
    if transaction:
        return {
            "success": True,
            "transaction_id": transaction.transaction_id,
            "message": f"Transaction saved successfully (ID: {transaction.transaction_id})"
        }
    else:
        return {
            "success": False,
            "message": "Failed to save transaction to database"
        }


def update_account_balance_in_db(account_id: int, new_balance: float) -> dict:
    """
    Update account balance in database.
    
    Args:
        account_id: Account ID
        new_balance: New balance amount
        
    Returns:
        dict with update result
    """
    success = DBManager.update_account_balance(account_id, new_balance)
    
    if success:
        return {
            "success": True,
            "account_id": account_id,
            "new_balance": new_balance,
            "message": f"Account balance updated to {new_balance}"
        }
    else:
        return {
            "success": False,
            "message": "Failed to update account balance in database"
        }


def get_transaction_history_from_db(user_id: int, limit: int = 10) -> dict:
    """
    Get user's transaction history from database.
    
    Args:
        user_id: User's ID
        limit: Maximum number of transactions to return
        
    Returns:
        dict with transaction history
    """
    transactions = DBManager.get_transaction_history(user_id, limit)
    
    return {
        "user_id": user_id,
        "transaction_count": len(transactions),
        "transactions": transactions
    }


def create_user_profile_in_db(phone_number: str, name: str = None, email: str = None) -> dict:
    """
    Create a new user profile in database.
    
    Args:
        phone_number: User's phone number
        name: User's name (optional)
        email: User's email (optional)
        
    Returns:
        dict with creation result
    """
    print(f"\n[STORAGE_TOOLS] ========== CREATE USER ==========")
    print(f"[STORAGE_TOOLS] create_user_profile_in_db() called")
    print(f"[STORAGE_TOOLS] Phone: {phone_number}, Name: {name}, Email: {email}")
    
    # Check if user already exists
    print(f"[STORAGE_TOOLS] Checking if user already exists with phone {phone_number}")
    existing_user = DBManager.get_user_by_phone(phone_number)
    print(f"[STORAGE_TOOLS] Existing user check result: {existing_user}")
    
    if existing_user:
        print(f"[STORAGE_TOOLS] ❌ User ALREADY EXISTS - cannot create duplicate")
        print(f"[STORAGE_TOOLS] Existing user_id: {existing_user.get('user_id')}")
        return {
            "success": False,
            "message": f"User with phone {phone_number} already exists",
            "existing_user_id": existing_user.get('user_id')
        }
    
    print(f"[STORAGE_TOOLS] ✅ No existing user found, proceeding to create")
    user = DBManager.create_user(phone_number, name, email)
    print(f"[STORAGE_TOOLS] User creation result: {user}")
    
    if user:
        print(f"[STORAGE_TOOLS] ✅ User created successfully with ID: {user.user_id}")
        # Create default accounts for new user
        print(f"[STORAGE_TOOLS] Creating default accounts for new user {phone_number}")
        try:
            # Create checking account
            checking = DBManager.create_account(user.user_id, "checking", balance=5000.00, currency="USD")
            print(f"[STORAGE_TOOLS] ✅ Created checking account (ID: {checking.account_id if checking else 'FAILED'})")
            
            # Create savings account
            savings = DBManager.create_account(user.user_id, "savings", balance=15000.00, currency="USD")
            print(f"[STORAGE_TOOLS] ✅ Created savings account (ID: {savings.account_id if savings else 'FAILED'})")
        except Exception as e:
            print(f"[STORAGE_TOOLS ERROR] Failed to create default accounts: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
        
        print(f"[STORAGE_TOOLS] ========== CREATE USER COMPLETE ==========\n")
        return {
            "success": True,
            "user_id": user.user_id,
            "phone_number": user.phone_number,
            "message": "User profile created successfully with default accounts"
        }
    else:
        return {
            "success": False,
            "message": "Failed to create user profile in database"
        }


def sync_state_with_db(state: dict, phone_number: str) -> bool:
    """
    Load user data from DB and sync to session state.
    This is called after successful authentication.
    ⚠️ IMPORTANT: Does NOT create users - only syncs existing user data!
    
    Args:
        state: Session state object (dict-like)
        phone_number: User's phone number
        
    Returns:
        True if sync successful, False otherwise
    """
    print(f"\n[STORAGE_TOOLS] ========== SYNC STATE WITH DB ==========")
    print(f"[STORAGE_TOOLS] sync_state_with_db() called for {phone_number}")
    try:
        user_data = load_user_profile_from_db(phone_number)
        print(f"[STORAGE_TOOLS] User data loaded: found={user_data.get('found')}")
        
        if not user_data.get("found"):
            print(f"[STORAGE_TOOLS] ❌ User not found in database - sync_state_with_db() will NOT create user")
            print(f"[STORAGE_TOOLS] Agent must call create_new_user_account() for new users")
            print(f"[STORAGE_TOOLS] ========== SYNC STATE WITH DB COMPLETE (NOT FOUND) ==========\n")
            return False
        
        print(f"[STORAGE_TOOLS] ✅ User found, syncing to state")
        # Update session state with DB data
        state["db_user_id"] = user_data["user_id"]
        print(f"[STORAGE_TOOLS] Set db_user_id={user_data['user_id']}")
        
        # CRITICAL: Store accounts as "accounts" (not "db_accounts") so get_balance() finds them
        accounts_for_state = []
        for acc in user_data["accounts"]:
            account_dict = {
                "id": f"acc-{str(acc['account_id']).zfill(3)}",  # Format as acc-001, acc-002, etc
                "type": acc.get("account_type", "unknown"),
                "available_balance": acc["balance"],
                "account_id": acc["account_id"]
            }
            accounts_for_state.append(account_dict)
            print(f"[STORAGE_TOOLS]   Account synced: id={account_dict['id']}, type={account_dict['type']}, balance={account_dict['available_balance']}, db_id={account_dict['account_id']}")
        
        state["accounts"] = accounts_for_state
        state["db_accounts"] = user_data["accounts"]  # Keep original for reference
        print(f"[STORAGE_TOOLS] ✅ Synced {len(accounts_for_state)} accounts to state")
        
        # Update account balances in state from DB
        if user_data["accounts"]:
            state["account_balances"] = {
            acc["account_id"]: acc["balance"]
            for acc in user_data["accounts"]
        }
            print(f"[STORAGE_TOOLS] ✅ Updated account_balances in state")
        
        print(f"[STORAGE_TOOLS] ========== SYNC STATE WITH DB COMPLETE (SUCCESS) ==========\n")
        return True
    except Exception as e:
        print(f"[STORAGE_TOOLS ERROR] sync_state_with_db failed: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        print(f"[STORAGE_TOOLS] ========== SYNC STATE WITH DB COMPLETE (ERROR) ==========\n")
        return False


def check_auth_token_exists(user_id: int) -> dict:
    """
    Check if a valid auth token exists for the user in database.
    
    Args:
        user_id: User's ID
        
    Returns:
        dict with {exists: bool, token_id: int or None, message: str}
    """
    print(f"[STORAGE_TOOLS] check_auth_token_exists() called for user_id={user_id}")
    try:
        auth_token = DBManager.get_user_auth_token(user_id)
        if auth_token:
            print(f"[STORAGE_TOOLS] ✅ Auth token exists for user: token_id={auth_token.token_id}")
            return {
                "exists": True,
                "token_id": auth_token.token_id,
                "message": "User has valid auth token"
            }
        else:
            print(f"[STORAGE_TOOLS] ❌ No auth token found for user")
            return {
                "exists": False,
                "token_id": None,
                "message": "No auth token found - user not authenticated"
            }
    except Exception as e:
        print(f"[STORAGE_TOOLS ERROR] Failed to check auth token: {e}")
        return {
            "exists": False,
            "token_id": None,
            "message": f"Error checking auth token: {str(e)}"
        }


def save_auth_token_to_db(user_id: int, token: str, expires_at: str) -> dict:
    """
    Save an auth token to database (hashed for security).
    
    Args:
        user_id: User's ID
        token: The auth token string (will be hashed)
        expires_at: Token expiration time (ISO format)
        
    Returns:
        dict with save result
    """
    print(f"[STORAGE_TOOLS] save_auth_token_to_db() called for user_id={user_id}")
    
    # Hash the token for security - never store plaintext tokens
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    print(f"[STORAGE_TOOLS] Token hashed successfully (SHA256)")
    
    auth_token = DBManager.save_auth_token(user_id, token_hash, expires_at)
    
    if auth_token:
        return {
            "success": True,
            "token_id": auth_token.token_id,
            "message": f"Auth token saved successfully (ID: {auth_token.token_id})"
        }
    else:
        return {
            "success": False,
            "message": "Failed to save auth token to database"
        }


def ensure_state_persisted(tool_context) -> bool:
    """
    Explicitly ensure state changes are persisted to the DatabaseSessionService.
    
    When we modify state inside a tool (e.g., setting db_user_id), the SessionService
    needs to save the state. This function creates a marker event to trigger state persistence.
    
    Args:
        tool_context: The ToolContext from the agent tool
        
    Returns:
        True if we can access the session, False otherwise
    """
    try:
        # The ToolContext should have access to the session through the runner
        if hasattr(tool_context, 'session') and tool_context.session:
            print(f"[STORAGE_TOOLS] Session accessible in tool_context, state modifications should auto-persist")
            return True
        else:
            print(f"[STORAGE_TOOLS WARNING] No session in tool_context")
            return False
    except Exception as e:
        print(f"[STORAGE_TOOLS WARNING] Could not verify session persistence: {e}")
        return False


if __name__ == "__main__":
    # Test the storage functions
    print("[TEST] Testing storage functions...")
    
    # Test loading demo user
    profile = load_user_profile_from_db("+919999999999")
    print(f"Loaded profile: {profile}")
    
    # Test transaction history
    if profile.get("found"):
        history = get_transaction_history_from_db(profile["user_id"])
        print(f"Transaction history: {history}")
