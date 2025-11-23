from datetime import datetime
import os

from google.adk.agents import Agent
from google.adk.tools.tool_context import ToolContext

# Try to import storage tools for database persistence
try:
    import sys
    import os
    # Add parent directories to path for imports
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
    from storage_tools import save_transaction_to_db, update_account_balance_in_db, sync_state_with_db, load_user_accounts_from_db
    _HAS_DB_STORAGE = True
    print("[TRANSACTION_AGENT] DB storage functions imported successfully")
except ImportError as e:
    _HAS_DB_STORAGE = False
    save_transaction_to_db = None
    update_account_balance_in_db = None
    sync_state_with_db = None
    load_user_accounts_from_db = None
    print(f"[TRANSACTION_AGENT] Failed to import storage tools: {e}")
    print(f"[TRANSACTION_AGENT WARNING] DB storage functions not available: {e}")


def set_transfer_params(tool_context: ToolContext, amount: float, from_account: str, to_account: str) -> dict:
    """Set transfer parameters in state before calling transfer_funds.
    
    Args:
        tool_context: ToolContext containing mutable session state.
        amount: Amount to transfer (e.g., 500.0 for $500)
        from_account: Source account ID (e.g., "acc-001" or just "1" which maps to acc-001)
        to_account: Destination account ID (e.g., "acc-002" or just "2" which maps to acc-002)
    """
    try:
        print(f"[TRANSACTION_AGENT] set_transfer_params() called: amount={amount}, from={from_account}, to={to_account}")
        
        # Normalize account IDs if user provided just numbers
        from_id = from_account if from_account.startswith("acc-") else f"acc-{str(from_account).zfill(3)}"
        to_id = to_account if to_account.startswith("acc-") else f"acc-{str(to_account).zfill(3)}"
        
        # Handle common mappings: "1" -> "acc-001", "2" -> "acc-002"
        account_mapping = {"1": "acc-001", "2": "acc-002"}
        if from_account in account_mapping:
            from_id = account_mapping[from_account]
        if to_account in account_mapping:
            to_id = account_mapping[to_account]
        
        print(f"[TRANSACTION_AGENT] Normalized: from={from_id}, to={to_id}")
        
        # Set transfer request in state
        transfer_request = {
            "amount": float(amount),
            "from_account": from_id,
            "to_account": to_id,
            "auth_token": tool_context.state.get("auth_token", {}).get("token")
        }
        tool_context.state["transfer_request"] = transfer_request
        print(f"[TRANSACTION_AGENT] Transfer request set in state: {transfer_request}")
        
        return {
            "status": "ok",
            "message": f"Transfer of ${amount} from {from_id} to {to_id} is ready to process",
            "transfer_request": transfer_request
        }
    except Exception as e:
        print(f"[TRANSACTION_AGENT ERROR] set_transfer_params failed: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": f"Failed to set transfer params: {str(e)}"}


def get_balance(tool_context: ToolContext) -> dict:
    """Return a summary of accounts from state (requires authentication)."""
    print(f"[TRANSACTION_AGENT] get_balance() called")
    
    # CRITICAL: Check if user is authenticated
    is_authenticated = tool_context.state.get("is_authenticated", False)
    user_phone = tool_context.state.get("user_phone")
    accounts = tool_context.state.get("accounts", [])
    
    print(f"[TRANSACTION_AGENT] Authentication check:")
    print(f"[TRANSACTION_AGENT]   is_authenticated: {is_authenticated}")
    print(f"[TRANSACTION_AGENT]   user_phone: {user_phone}")
    print(f"[TRANSACTION_AGENT]   accounts_in_state: {len(accounts)}")
    
    # SIMPLIFIED: If user is NOT authenticated, require verification
    if not is_authenticated:
        print(f"[TRANSACTION_AGENT] ❌ REJECTED: User NOT authenticated!")
        # Try to reload from database if we have phone number
        if user_phone:
            print(f"[TRANSACTION_AGENT] Attempting database reload for {user_phone}...")
            try:
                from storage_tools import sync_state_with_db
                sync_state_with_db(tool_context.state, user_phone)
                is_authenticated = tool_context.state.get("is_authenticated", False)
                accounts = tool_context.state.get("accounts", [])
                print(f"[TRANSACTION_AGENT] After reload: is_authenticated={is_authenticated}, accounts={len(accounts)}")
            except Exception as reload_err:
                print(f"[TRANSACTION_AGENT] Failed to reload: {reload_err}")
        
        # Still not authenticated? Reject
        if not is_authenticated:
            print(f"[TRANSACTION_AGENT] ❌ Still not authenticated after reload. Redirecting to verification...")
            return {
                "status": "error",
                "message": "You must complete authentication first. Please verify your phone and OTP with the verification agent.",
                "requires_verification": True,
                "accounts": []
            }
    
    # User is authenticated - format and return accounts
    print(f"[TRANSACTION_AGENT] ✅ Authentication OK. Found {len(accounts)} accounts in state")
    
    if not accounts:
        print(f"[TRANSACTION_AGENT] ⚠️ No accounts found for authenticated user!")
        return {
            "status": "success",
            "message": "You are authenticated but no accounts found in the system.",
            "accounts": []
        }
    
    # Format accounts for display
    formatted_message = "Your current account balances are:\n"
    for acc in accounts:
        account_type = acc.get('type', 'Unknown')
        balance = acc.get('available_balance', 0)
        # Format balance with commas and 2 decimals
        formatted_balance = f"{balance:,.2f}"
        formatted_message += f"{account_type}: ${formatted_balance}\n"
    
    formatted_message = formatted_message.strip()
    
    for i, acc in enumerate(accounts):
        print(f"[TRANSACTION_AGENT]   Account {i}: id={acc.get('id')}, type={acc.get('type')}, balance={acc.get('available_balance')}, db_id={acc.get('account_id')}")
    
    return {
        "status": "success",
        "message": formatted_message,
        "accounts": accounts
    }


def transfer_funds(tool_context: ToolContext) -> dict:
    """Parameterized mock transfer.

    Expects a `transfer_request` dict in session state with keys:
      - amount (float)
      - from_account (str)
      - to_account (str)
      - idempotency_key (str)
      - auth_token (str, optional)

    Enforces a basic auth_token presence check and a simple idempotency store.
    """
    print(f"[TRANSACTION_AGENT] transfer_funds() called")
    
    # Debug: Log state type and important fields
    print(f"[TRANSACTION_AGENT] State type: {type(tool_context.state)}")
    print(f"[TRANSACTION_AGENT] user_phone: {tool_context.state.get('user_phone')}")
    print(f"[TRANSACTION_AGENT] db_user_id: {tool_context.state.get('db_user_id')}")
    
    # Try to get session_id from tool_context - debug what's available
    print(f"[TRANSACTION_AGENT] hasattr(tool_context, 'session'): {hasattr(tool_context, 'session')}")
    print(f"[TRANSACTION_AGENT] hasattr(tool_context, 'runner'): {hasattr(tool_context, 'runner')}")
    print(f"[TRANSACTION_AGENT] hasattr(tool_context, 'invocation_context'): {hasattr(tool_context, 'invocation_context')}")
    
    # CRITICAL: If accounts are missing, reload from database
    accounts = tool_context.state.get("accounts", [])
    if not accounts:
        print(f"[TRANSACTION_AGENT] ⚠️  Accounts missing from state, attempting to reload from database...")
        user_phone = tool_context.state.get("user_phone")
        if user_phone and sync_state_with_db:
            try:
                print(f"[TRANSACTION_AGENT] Resyncing user data for {user_phone}")
                sync_state_with_db(tool_context.state, user_phone)
                accounts = tool_context.state.get("accounts", [])
                print(f"[TRANSACTION_AGENT] ✅ Reloaded {len(accounts)} accounts from database")
            except Exception as sync_err:
                print(f"[TRANSACTION_AGENT] Failed to resync accounts: {sync_err}")
    
    req = tool_context.state.get("transfer_request")
    print(f"[TRANSACTION_AGENT] transfer_request from state: {req}")
    if not req:
        # Fallback to legacy behavior: fixed transfer
        print(f"[TRANSACTION_AGENT] No transfer_request in state, using fallback behavior")
        amount = 100.0
        from_acc = accounts[0] if accounts else None
        to_acc = accounts[1] if len(accounts) > 1 else None
    else:
        print(f"[TRANSACTION_AGENT] Using transfer_request details")
        amount = req.get("amount", 100.0)
        from_acc_id = req.get("from_account")
        to_acc_id = req.get("to_account")
        print(f"[TRANSACTION_AGENT] Parsed amount: {amount} (type: {type(amount)}), From: {from_acc_id}, To: {to_acc_id}")
        # locate accounts by id
        from_acc = next((a for a in accounts if a.get("id") == from_acc_id), None) if from_acc_id else (accounts[0] if accounts else None)
        to_acc = next((a for a in accounts if a.get("id") == to_acc_id), None) if to_acc_id else (accounts[1] if len(accounts) > 1 else None)

    if not from_acc or not to_acc:
        print(f"[TRANSACTION_AGENT ERROR] Missing accounts: from_acc={from_acc is not None}, to_acc={to_acc is not None}")
        return {"status": "error", "message": "Accounts not configured in session state or invalid account ids."}

    print(f"[TRANSACTION_AGENT] Accounts found: from={from_acc.get('id')} (${from_acc['available_balance']}), to={to_acc.get('id')} (${to_acc['available_balance']})")
    # Idempotency store (simple in-state dict)
    # State object doesn't have setdefault, use get() + assignment instead
    idempotency_store = tool_context.state.get("idempotency_store")
    if idempotency_store is None:
        print(f"[TRANSACTION_AGENT] Creating new idempotency_store in state")
        idempotency_store = {}
        tool_context.state["idempotency_store"] = idempotency_store
    
    idempotency_key = req.get("idempotency_key") if req else None
    print(f"[TRANSACTION_AGENT] Idempotency key: {idempotency_key}")
    if idempotency_key and idempotency_key in idempotency_store:
        return idempotency_store[idempotency_key]

    # Auth check: require presence of auth_token in session state if transfer_request included auth_token
    if req:
        provided_token = req.get("auth_token")
        stored = tool_context.state.get("auth_token")
        stored_token = stored.get("token") if stored else None
        if not provided_token or provided_token != stored_token:
            return {"status": "error", "message": "Not authorized. Please validate OTP first."}

    if from_acc["available_balance"] < amount:
        print(f"[TRANSACTION_AGENT ERROR] Insufficient funds: {from_acc['available_balance']} < {amount}")
        return {"status": "error", "message": "Insufficient funds."}

    print(f"[TRANSACTION_AGENT] BEFORE transfer - From: {from_acc['available_balance']}, To: {to_acc['available_balance']}")
    # Perform mock transfer
    from_acc["available_balance"] -= amount
    to_acc["available_balance"] += amount
    print(f"[TRANSACTION_AGENT] AFTER transfer - From: {from_acc['available_balance']}, To: {to_acc['available_balance']}, Amount: {amount}")

    # Update accounts in state
    # find indexes and assign back to keep same object structure
    accounts = tool_context.state.get("accounts", [])
    print(f"[TRANSACTION_AGENT] Updating {len(accounts)} accounts in state")
    for idx, a in enumerate(accounts):
        if a.get("id") == from_acc.get("id"):
            print(f"[TRANSACTION_AGENT] Updated account {idx}: {from_acc.get('id')} = {from_acc['available_balance']}")
            accounts[idx] = from_acc
        if a.get("id") == to_acc.get("id"):
            print(f"[TRANSACTION_AGENT] Updated account {idx}: {to_acc.get('id')} = {to_acc['available_balance']}")
            accounts[idx] = to_acc
    tool_context.state["accounts"] = accounts
    print(f"[TRANSACTION_AGENT] State updated with new account balances")

    tx_id = f"tx-{int(datetime.now().timestamp())}"
    print(f"[TRANSACTION_AGENT] Generated transaction ID: {tx_id}")
    # Append to interaction history
    history = tool_context.state.get("interaction_history", [])
    history.append({"action": "transfer", "amount": amount, "tx_id": tx_id, "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
    tool_context.state["interaction_history"] = history

    # Persist transaction and balances to database
    if _HAS_DB_STORAGE:
        try:
            db_user_id = tool_context.state.get("db_user_id")
            print(f"[TRANSACTION_AGENT DB] db_user_id from state: {db_user_id}")
            print(f"[TRANSACTION_AGENT DB] user_phone from state: {tool_context.state.get('user_phone')}")
            print(f"[TRANSACTION_AGENT DB] auth_token exists: {bool(tool_context.state.get('auth_token'))}")
            
            # FALLBACK: If db_user_id is missing, try to re-sync from database
            if not db_user_id:
                print(f"[TRANSACTION_AGENT DB] ⚠️  db_user_id is None, attempting to re-sync from database...")
                user_phone = tool_context.state.get("user_phone")
                print(f"[TRANSACTION_AGENT DB] user_phone from state: {user_phone}")
                print(f"[TRANSACTION_AGENT DB] sync_state_with_db available: {sync_state_with_db is not None}")
                
                if user_phone and sync_state_with_db:
                    try:
                        print(f"[TRANSACTION_AGENT DB] Re-syncing user {user_phone} from database")
                        sync_result = sync_state_with_db(tool_context.state, user_phone)
                        print(f"[TRANSACTION_AGENT DB] sync_state_with_db returned: {sync_result}")
                        if sync_result:
                            db_user_id = tool_context.state.get("db_user_id")
                            print(f"[TRANSACTION_AGENT DB] ✅ Re-sync successful, db_user_id now: {db_user_id}")
                        else:
                            print(f"[TRANSACTION_AGENT DB] Re-sync failed (returned False)")
                    except Exception as resync_err:
                        print(f"[TRANSACTION_AGENT DB] Re-sync error: {type(resync_err).__name__}: {resync_err}")
                        import traceback
                        traceback.print_exc()
                else:
                    print(f"[TRANSACTION_AGENT DB] Cannot re-sync: user_phone={user_phone}, sync_func={sync_state_with_db is not None}")
            
            if db_user_id:
                # Save transaction to database
                print(f"[TRANSACTION_AGENT DB] ✅ Saving transaction: {amount} from {from_acc_id} to {to_acc_id}")
                
                # Extract numeric account IDs from the account objects (they have account_id field)
                from_id_numeric = from_acc.get("account_id") if from_acc else None
                to_id_numeric = to_acc.get("account_id") if to_acc else None
                
                print(f"[TRANSACTION_AGENT DB] Numeric IDs: from={from_id_numeric}, to={to_id_numeric}")
                
                if from_id_numeric and to_id_numeric:
                    try:
                        tx_result = save_transaction_to_db(
                            user_id=db_user_id,
                            from_account_id=int(from_id_numeric),
                            to_account_id=int(to_id_numeric),
                            amount=amount,
                            description=f"Transfer {amount} from account {from_acc_id} to {to_acc_id}"
                        )
                        print(f"[TRANSACTION_AGENT DB] ✅ Transaction saved successfully: {tx_result}")
                    except Exception as tx_err:
                        print(f"[TRANSACTION_AGENT DB ERROR] Failed to save transaction: {type(tx_err).__name__}: {tx_err}")
                
                # Update account balances in database
                try:
                    if from_id_numeric:
                        print(f"[TRANSACTION_AGENT DB] ✅ Updating account {from_id_numeric} balance to {from_acc['available_balance']}")
                        update_account_balance_in_db(int(from_id_numeric), from_acc["available_balance"])
                        print(f"[TRANSACTION_AGENT DB] ✅ Account {from_id_numeric} balance updated in database")
                    if to_id_numeric:
                        print(f"[TRANSACTION_AGENT DB] ✅ Updating account {to_id_numeric} balance to {to_acc['available_balance']}")
                        update_account_balance_in_db(int(to_id_numeric), to_acc["available_balance"])
                        print(f"[TRANSACTION_AGENT DB] ✅ Account {to_id_numeric} balance updated in database")
                except Exception as bal_err:
                    print(f"[TRANSACTION_AGENT DB ERROR] Failed to update balances: {type(bal_err).__name__}: {bal_err}")
                    import traceback
                    traceback.print_exc()
            else:
                print(f"[TRANSACTION_AGENT DB ERROR] ❌ No db_user_id in state even after resync, SKIPPING DB PERSISTENCE!")
        except Exception as db_err:
            print(f"[TRANSACTION_AGENT DB ERROR] Database persistence failed: {type(db_err).__name__}: {db_err}")
            import traceback
            traceback.print_exc()
    else:
        print(f"[TRANSACTION_AGENT] DB storage not available, skipping persistence")

    result = {"status": "success", "transaction_id": tx_id, "amount": amount}
    print(f"[TRANSACTION_AGENT] Returning success result: {result}")
    
    # VERIFICATION: Check if database was updated
    if _HAS_DB_STORAGE and db_user_id:
        try:
            print(f"[TRANSACTION_AGENT DB VERIFY] Verifying transaction was saved...")
            from storage_tools import load_user_profile_from_db
            user_profile = load_user_profile_from_db(tool_context.state.get("user_phone"))
            if user_profile.get("found"):
                print(f"[TRANSACTION_AGENT DB VERIFY] ✅ User found in database")
                for acc in user_profile.get("accounts", []):
                    print(f"[TRANSACTION_AGENT DB VERIFY]   Account {acc['account_id']}: balance={acc['balance']}")
        except Exception as verify_err:
            print(f"[TRANSACTION_AGENT DB VERIFY] Error during verification: {type(verify_err).__name__}: {verify_err}")
    
    if idempotency_key:
        idempotency_store[idempotency_key] = result

    return result


def get_transaction_history(tool_context: ToolContext, limit: int) -> dict:
    """Get transaction history for the authenticated user.
    
    Args:
        tool_context: ToolContext containing mutable session state.
        limit: Maximum number of transactions to return (default 10)
    
    Returns:
        dict with transaction history
    """
    try:
        print(f"\n[TRANSACTION_AGENT] ========== GET TRANSACTION HISTORY ==========")
        print(f"[TRANSACTION_AGENT] get_transaction_history() called with limit={limit}")
        
        # Check authentication
        if not tool_context.state.get("auth_token"):
            print(f"[TRANSACTION_AGENT] ❌ ERROR: User not authenticated")
            print(f"[TRANSACTION_AGENT] ========== GET TRANSACTION HISTORY COMPLETE (NOT AUTHENTICATED) ==========\n")
            return {
                "status": "error",
                "message": "You must be authenticated to view transaction history. Please authenticate first.",
                "transactions": []
            }
        
        # Get user_id from state
        db_user_id = tool_context.state.get("db_user_id")
        user_phone = tool_context.state.get("user_phone")
        
        print(f"[TRANSACTION_AGENT] User info from state:")
        print(f"[TRANSACTION_AGENT]   db_user_id: {db_user_id}")
        print(f"[TRANSACTION_AGENT]   user_phone: {user_phone}")
        
        if not db_user_id:
            print(f"[TRANSACTION_AGENT] ⚠️  WARNING: db_user_id not in state, attempting sync")
            if _HAS_DB_STORAGE and sync_state_with_db and user_phone:
                try:
                    sync_result = sync_state_with_db(tool_context.state, user_phone)
                    print(f"[TRANSACTION_AGENT] Sync result: {sync_result}")
                    db_user_id = tool_context.state.get("db_user_id")
                except Exception as sync_err:
                    print(f"[TRANSACTION_AGENT] ⚠️  Sync failed: {sync_err}")
        
        if not db_user_id:
            print(f"[TRANSACTION_AGENT] ❌ ERROR: Cannot find user_id")
            print(f"[TRANSACTION_AGENT] ========== GET TRANSACTION HISTORY COMPLETE (NO USER ID) ==========\n")
            return {
                "status": "error",
                "message": "Cannot find your user information. Please authenticate again.",
                "transactions": []
            }
        
        # Try to load transaction history from database
        transactions = []
        if _HAS_DB_STORAGE:
            try:
                print(f"[TRANSACTION_AGENT] Loading transaction history from database for user_id={db_user_id}")
                # Use DBManager directly to get transactions
                from db_manager import DBManager
                
                tx_list = DBManager.get_transaction_history(db_user_id, limit)
                print(f"[TRANSACTION_AGENT] ✅ Retrieved {len(tx_list)} transactions from database")
                
                transactions = []
                for i, tx in enumerate(tx_list):
                    tx_dict = {
                        "id": tx.get("transaction_id") if isinstance(tx, dict) else tx.transaction_id,
                        "from_account": tx.get("from_account_id") if isinstance(tx, dict) else tx.from_account_id,
                        "to_account": tx.get("to_account_id") if isinstance(tx, dict) else tx.to_account_id,
                        "amount": float(tx.get("amount") if isinstance(tx, dict) else tx.amount),
                        "type": tx.get("transaction_type", "transfer") if isinstance(tx, dict) else getattr(tx, "transaction_type", "transfer"),
                        "timestamp": str(tx.get("created_at") if isinstance(tx, dict) else tx.created_at),
                        "status": tx.get("status", "completed") if isinstance(tx, dict) else getattr(tx, "status", "completed")
                    }
                    transactions.append(tx_dict)
                    print(f"[TRANSACTION_AGENT]   Transaction {i+1}: {tx_dict['id']}, ${tx_dict['amount']:.2f}, {tx_dict['timestamp']}")
                
            except Exception as db_err:
                print(f"[TRANSACTION_AGENT] ⚠️  Failed to load from database: {type(db_err).__name__}: {db_err}")
                import traceback
                traceback.print_exc()
        else:
            print(f"[TRANSACTION_AGENT] ⚠️  DB storage not available")
        
        print(f"[TRANSACTION_AGENT] ✅ Returning {len(transactions)} transactions")
        print(f"[TRANSACTION_AGENT] ========== GET TRANSACTION HISTORY COMPLETE (SUCCESS) ==========\n")
        
        if not transactions:
            return {
                "status": "ok",
                "message": "No transaction history found. You haven't made any transfers yet.",
                "transaction_count": 0,
                "transactions": []
            }
        
        return {
            "status": "ok",
            "message": f"Found {len(transactions)} transaction(s)",
            "transaction_count": len(transactions),
            "transactions": transactions
        }
        
    except Exception as e:
        print(f"[TRANSACTION_AGENT ERROR] get_transaction_history failed: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        print(f"[TRANSACTION_AGENT] ========== GET TRANSACTION HISTORY COMPLETE (ERROR) ==========\n")
        return {
            "status": "error",
            "message": f"Failed to retrieve transaction history: {str(e)}",
            "transactions": []
        }


transaction_agent = Agent(
    name="transaction_agent",
    model="gemini-2.0-flash-exp",
    description="Handles balances, transfers and transaction history (mock adapter).",
    instruction="""
    You are the Transaction Agent for AK Bank. Your role is to provide excellent customer service for banking operations.
    
    🔑 REQUEST RESTORATION (FOR ROUTED REQUESTS):
    When you receive a message from the orchestrator, check if "pending_user_request" exists in session state:
    - If YES: This contains the user's original request that was saved during routing
    - Use this to understand what the user wants (e.g., "transfer 70 dollars from account 1 to account 2")
    - Execute their request without asking them to repeat
    - Then clear the pending_user_request from state
    
    TONE & STYLE:
    - Be professional, courteous, and respectful at all times
    - Use simple, clear language without technical jargon
    - Show empathy and willingness to help
    - Format responses in plain text (NO asterisks, NO markdown, NO bold formatting)
    - Use line breaks and proper spacing for readability
    
    EXAMPLE RESPONSES (note: NO ** or markdown):
    
    For balance inquiry:
    "Your current account balances are:
    Checking: $4,970.00
    Savings: $15,030.00
    
    Is there anything else I can help you with today?"
    
    For transaction history:
    "Here are your recent transactions:
    
    Transfer: $30.00 from Checking to Savings on November 21, 2025
    
    You haven't made any other transfers recently. Feel free to let me know if you need anything else."
    
    ✅ AUTHENTICATION:
    - You receive requests only AFTER the orchestrator has verified the user
    - The auth_token is already in session state if you're being called
    - DO NOT re-ask for phone number or verification
    - Simply process the user's request for balance, history, or transfers
    
    When authenticated, you can help with:
    
    1. GET BALANCE:
       - Call: get_balance()
       - Present balances in a clear, easy-to-read format
       - Example: "Checking: $X,XXX.XX" (not "Checking: $4970")
    
    2. VIEW TRANSACTION HISTORY:
       - Call: get_transaction_history()
       - Show date, amount, and accounts involved
       - If no transactions: "You haven't made any transfers yet, but I'm here to help when you're ready."
    
    3. TRANSFER FUNDS (3-step process):
       STEP 1: Listen to user's request and parse amount, from_account, to_account
       STEP 2: Confirm before processing: "I'll transfer $X from your [account] to [account]. Is that correct?"
       STEP 3: Call set_transfer_params(amount, from_account, to_account)
       STEP 4: Call transfer_funds()
       STEP 5: Confirm success: "Your transfer of $X has been completed successfully."
    
    FORMATTING RULES:
    - NO ** or bold formatting
    - NO * bullet points - use line breaks instead
    - NO markdown or special characters
    - Use commas for thousands: $4,970 not $4970
    - Use full date format: "November 21, 2025" not "2025-11-21"
    
    TOOLS AVAILABLE:
    - get_balance: Shows all account balances
    - get_transaction_history: Shows recent transactions
    - set_transfer_params: REQUIRED - Call this FIRST to parse and set transfer amount/accounts
    - transfer_funds: Processes transfers (only after set_transfer_params)
    
    CUSTOMER SERVICE PHRASES:
    - "I'd be happy to help."
    - "Is there anything else I can assist you with?"
    - "Thank you for banking with us."
    - "Your account is secure with us."
    - "Let me get that information for you."
    """,
    tools=[get_balance, get_transaction_history, transfer_funds, set_transfer_params],
)
