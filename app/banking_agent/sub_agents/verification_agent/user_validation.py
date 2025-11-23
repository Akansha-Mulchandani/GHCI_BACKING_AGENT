"""
User validation tools for checking user existence in database
"""

from db_manager import DBManager
from google.adk.tools.tool_context import ToolContext

print(f"[USER_VALIDATION] Module imported")


def check_user_exists(tool_context: ToolContext, phone_number: str) -> dict:
    """
    Check if a user already exists in the database WITHOUT creating them.
    
    Args:
        tool_context: ToolContext containing session state
        phone_number: Phone number to check (e.g., "+919999999999")
        
    Returns:
        dict with user existence status
    """
    try:
        print(f"\n[USER_VALIDATION] ========== CHECK USER EXISTS ==========")
        print(f"[USER_VALIDATION] check_user_exists() called for: {phone_number}")
        
        user = DBManager.get_user_by_phone(phone_number)
        print(f"[USER_VALIDATION] Database lookup returned: {user}")
        
        if user:
            print(f"[USER_VALIDATION] ✅ USER FOUND in database")
            print(f"[USER_VALIDATION]    user_id: {user.get('user_id')}")
            print(f"[USER_VALIDATION]    phone: {user.get('phone_number')}")
            print(f"[USER_VALIDATION]    name: {user.get('name')}")
            print(f"[USER_VALIDATION] ========== CHECK USER EXISTS COMPLETE ==========\n")
            return {
                "status": "found",
                "exists": True,
                "user_id": user["user_id"],
                "message": f"User account found for {phone_number}. Welcome back!"
            }
        else:
            print(f"[USER_VALIDATION] ❌ USER NOT FOUND in database")
            print(f"[USER_VALIDATION] ========== CHECK USER EXISTS COMPLETE ==========\n")
            return {
                "status": "not_found",
                "exists": False,
                "message": f"No account found for {phone_number}. You can create a new account."
            }
    except Exception as e:
        print(f"[USER_VALIDATION ERROR] check_user_exists failed: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        print(f"[USER_VALIDATION] ========== CHECK USER EXISTS COMPLETE (ERROR) ==========\n")
        return {
            "status": "error",
            "exists": None,
            "message": f"Error checking user: {str(e)}"
        }


if __name__ == "__main__":
    print("[TEST] Testing user validation...")
    
    # Test existing user
    print("\nTest 1: Existing user")
    class MockContext:
        state = {}
    
    result = check_user_exists(MockContext(), "+919999999999")
    print(f"Result: {result}")
    
    # Test non-existent user
    print("\nTest 2: Non-existent user")
    result = check_user_exists(MockContext(), "+919999999999")
    print(f"Result: {result}")
