"""
Loan Specialist Agent for AK Bank
Handles loan applications, eligibility checks, EMI calculations, and loan management
"""

from datetime import datetime

from google.adk.agents import Agent
from google.adk.tools.tool_context import ToolContext

# Import storage tools for database operations
try:
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
    from storage_tools import sync_state_with_db, load_user_accounts_from_db
    _HAS_DB_STORAGE = True
    print("[LOAN_AGENT] Successfully imported storage_tools")
except Exception as e:
    _HAS_DB_STORAGE = False
    print(f"[LOAN_AGENT] Failed to import storage_tools: {e}")

# Import db_manager for loan operations
try:
    from db_manager import DBManager
    _HAS_DB_MANAGER = True
    print("[LOAN_AGENT] Successfully imported DBManager")
except Exception as e:
    _HAS_DB_MANAGER = False
    print(f"[LOAN_AGENT] Failed to import DBManager: {e}")


# ============================================================================
# LOAN TOOL #1: CHECK LOAN ELIGIBILITY
# ============================================================================

def check_loan_eligibility(tool_context: ToolContext, loan_type: str) -> dict:
    """
    Check if user is eligible for a specific loan type.
    Checks credit score, income, existing loans, and debt-to-income ratio.
    
    Args:
        tool_context: ToolContext containing mutable session state
        loan_type: Type of loan (e.g., "personal", "home", "auto", "education")
    
    Returns:
        dict with eligibility status and reasons
    """
    try:
        print(f"\n[LOAN_AGENT] ========== CHECK LOAN ELIGIBILITY ==========")
        print(f"[LOAN_AGENT] check_loan_eligibility() called for loan_type: {loan_type}")
        
        # Check if user is authenticated
        auth_token = tool_context.state.get("auth_token")
        if not auth_token:
            print(f"[LOAN_AGENT] ❌ User not authenticated (no auth_token)")
            return {
                "status": "error",
                "message": "User must be authenticated first",
                "eligible": False
            }
        
        # Get user identifiers - try multiple sources
        user_phone = tool_context.state.get("user_phone")
        db_user_id = tool_context.state.get("db_user_id")
        
        print(f"[LOAN_AGENT] user_phone: {user_phone}, db_user_id: {db_user_id}")
        
        # If we don't have db_user_id, try to sync from database using phone
        if not db_user_id and user_phone and _HAS_DB_STORAGE:
            print(f"[LOAN_AGENT] Attempting to sync user data from database...")
            try:
                from storage_tools import sync_state_with_db
                sync_state_with_db(tool_context.state, user_phone)
                db_user_id = tool_context.state.get("db_user_id")
                print(f"[LOAN_AGENT] After sync: db_user_id = {db_user_id}")
            except Exception as sync_err:
                print(f"[LOAN_AGENT] Sync failed: {sync_err}")
        
        if not db_user_id:
            print(f"[LOAN_AGENT] ⚠️  No db_user_id available, using mock eligibility")
            # Use mock eligibility check if db not available
            return {
                "status": "success",
                "loan_type": loan_type,
                "eligible": True,
                "credit_score": 700,
                "message": f"You are eligible for a {loan_type} loan. Our interest rate is 12.5% per annum.",
                "note": "Using default eligibility (database not available)"
            }
        
        if not _HAS_DB_MANAGER:
            print(f"[LOAN_AGENT] ❌ DB Manager not available")
            return {
                "status": "error",
                "message": "Database not available",
                "eligible": False
            }
        
        # Get user's credit score
        print(f"[LOAN_AGENT] Fetching credit score for user_id: {db_user_id}")
        credit_score = DBManager.get_credit_score(db_user_id)
        print(f"[LOAN_AGENT] Credit score: {credit_score}")
        
        # Get active loans count
        active_loans = DBManager.get_active_loans(db_user_id)
        print(f"[LOAN_AGENT] Active loans count: {len(active_loans) if active_loans else 0}")
        
        # Get total existing loan amount
        total_loan_amount = sum(float(loan.get("loan_amount", 0)) for loan in (active_loans or []))
        print(f"[LOAN_AGENT] Total existing loan amount: ${total_loan_amount}")
        
        # Eligibility criteria by loan type
        eligibility_rules = {
            "personal": {"min_credit": 550, "max_loans": 3, "max_existing_amount": 500000},
            "home": {"min_credit": 650, "max_loans": 1, "max_existing_amount": 0},
            "auto": {"min_credit": 600, "max_loans": 2, "max_existing_amount": 300000},
            "education": {"min_credit": 500, "max_loans": 5, "max_existing_amount": 1000000}
        }
        
        if loan_type not in eligibility_rules:
            print(f"[LOAN_AGENT] ❌ Unknown loan type: {loan_type}")
            return {
                "status": "error",
                "message": f"Unknown loan type: {loan_type}",
                "eligible": False
            }
        
        rules = eligibility_rules[loan_type]
        print(f"[LOAN_AGENT] Checking against rules: {rules}")
        
        # Check eligibility
        eligible = True
        reasons = []
        
        if credit_score is None or credit_score < rules["min_credit"]:
            eligible = False
            reasons.append(f"Credit score ({credit_score or 0}) below minimum ({rules['min_credit']})")
            print(f"[LOAN_AGENT] ❌ Credit score check failed")
        else:
            print(f"[LOAN_AGENT] ✅ Credit score check passed")
        
        if len(active_loans or []) >= rules["max_loans"]:
            eligible = False
            reasons.append(f"Maximum loans ({rules['max_loans']}) already reached")
            print(f"[LOAN_AGENT] ❌ Max loans check failed")
        else:
            print(f"[LOAN_AGENT] ✅ Max loans check passed")
        
        if total_loan_amount >= rules["max_existing_amount"]:
            eligible = False
            reasons.append(f"Existing loan amount (${total_loan_amount}) exceeds limit (${rules['max_existing_amount']})")
            print(f"[LOAN_AGENT] ❌ Existing amount check failed")
        else:
            print(f"[LOAN_AGENT] ✅ Existing amount check passed")
        
        print(f"[LOAN_AGENT] ========== CHECK LOAN ELIGIBILITY COMPLETE ==========\n")
        
        return {
            "status": "success",
            "eligible": eligible,
            "loan_type": loan_type,
            "credit_score": credit_score,
            "active_loans": len(active_loans or []),
            "total_existing_amount": total_loan_amount,
            "reasons": reasons if not eligible else ["You are eligible for this loan"],
            "message": f"Eligible for {loan_type} loan" if eligible else f"Not eligible: {', '.join(reasons)}"
        }
    
    except Exception as e:
        print(f"[LOAN_AGENT ERROR] check_loan_eligibility failed: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": f"Failed to check eligibility: {str(e)}", "eligible": False}


# ============================================================================
# LOAN TOOL #2: GET USER CREDIT SCORE
# ============================================================================

def get_user_credit_score(tool_context: ToolContext) -> dict:
    """
    Retrieve user's current credit score from database.
    
    Args:
        tool_context: ToolContext containing mutable session state
    
    Returns:
        dict with credit score and additional info
    """
    try:
        print(f"\n[LOAN_AGENT] ========== GET CREDIT SCORE ==========")
        print(f"[LOAN_AGENT] get_user_credit_score() called")
        
        db_user_id = tool_context.state.get("db_user_id")
        
        print(f"[LOAN_AGENT] db_user_id: {db_user_id}")
        
        if not db_user_id:
            print(f"[LOAN_AGENT] ❌ User ID not found in state")
            return {
                "status": "error",
                "message": "User ID not found"
            }
        
        if not _HAS_DB_MANAGER:
            print(f"[LOAN_AGENT] ❌ DB Manager not available")
            return {"status": "error", "message": "Database not available"}
        
        credit_score = DBManager.get_credit_score(db_user_id)
        print(f"[LOAN_AGENT] Credit score retrieved: {credit_score}")
        
        # Determine credit quality
        if credit_score is None:
            quality = "Not available"
            print(f"[LOAN_AGENT] Credit score not available")
        elif credit_score >= 750:
            quality = "Excellent"
            print(f"[LOAN_AGENT] ✅ Excellent credit score")
        elif credit_score >= 700:
            quality = "Good"
            print(f"[LOAN_AGENT] ✅ Good credit score")
        elif credit_score >= 650:
            quality = "Fair"
            print(f"[LOAN_AGENT] Fair credit score")
        else:
            quality = "Poor"
            print(f"[LOAN_AGENT] ⚠️ Poor credit score")
        
        print(f"[LOAN_AGENT] ========== GET CREDIT SCORE COMPLETE ==========\n")
        
        return {
            "status": "success",
            "credit_score": credit_score,
            "quality": quality,
            "user_id": db_user_id,
            "message": f"Your credit score is {credit_score} ({quality})" if credit_score else "Credit score not available"
        }
    
    except Exception as e:
        print(f"[LOAN_AGENT ERROR] get_user_credit_score failed: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": f"Failed to get credit score: {str(e)}"}


# ============================================================================
# LOAN TOOL #3: GET AVAILABLE LOAN PRODUCTS
# ============================================================================

def get_available_loan_products(tool_context: ToolContext) -> dict:
    """
    Get list of all available loan products with rates, tenures, and limits.
    Returns default products if database is empty.
    
    Args:
        tool_context: ToolContext containing mutable session state
    
    Returns:
        dict with list of loan products
    """
    try:
        print(f"\n[LOAN_AGENT] ========== GET AVAILABLE LOAN PRODUCTS ==========")
        print(f"[LOAN_AGENT] get_available_loan_products() called")
        
        # Default loan products - always available
        default_products = [
            {
                "product_id": 1,
                "name": "Personal Loan",
                "loan_type": "personal",
                "min_amount": 10000,
                "max_amount": 500000,
                "interest_rate": 12.5,
                "min_tenure": 12,
                "max_tenure": 60,
                "processing_fee_percent": 1.0
            },
            {
                "product_id": 2,
                "name": "Home Loan",
                "loan_type": "home",
                "min_amount": 500000,
                "max_amount": 10000000,
                "interest_rate": 8.5,
                "min_tenure": 120,
                "max_tenure": 360,
                "processing_fee_percent": 0.5
            },
            {
                "product_id": 3,
                "name": "Auto Loan",
                "loan_type": "auto",
                "min_amount": 200000,
                "max_amount": 2000000,
                "interest_rate": 10.0,
                "min_tenure": 24,
                "max_tenure": 84,
                "processing_fee_percent": 0.75
            },
            {
                "product_id": 4,
                "name": "Education Loan",
                "loan_type": "education",
                "min_amount": 50000,
                "max_amount": 1000000,
                "interest_rate": 9.0,
                "min_tenure": 24,
                "max_tenure": 180,
                "processing_fee_percent": 0.5
            }
        ]
        
        # Try to get from database, but fall back to defaults
        if _HAS_DB_MANAGER:
            db_products = DBManager.get_loan_products()
            if db_products and len(db_products) > 0:
                print(f"[LOAN_AGENT] Retrieved {len(db_products)} loan products from database")
                products = db_products
            else:
                print(f"[LOAN_AGENT] Database returned no products, using defaults")
                products = default_products
        else:
            print(f"[LOAN_AGENT] DB Manager not available, using default products")
            products = default_products
        
        print(f"[LOAN_AGENT] Total {len(products)} products available")
        
        print(f"[LOAN_AGENT] ========== GET AVAILABLE LOAN PRODUCTS COMPLETE ==========\n")
        
        return {
            "status": "success",
            "product_count": len(products),
            "products": products,
            "message": f"We offer 4 loan products: Personal (12.5%), Home (8.5%), Auto (10%), Education (9%)"
        }
    
    except Exception as e:
        print(f"[LOAN_AGENT ERROR] get_available_loan_products failed: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": f"Failed to get loan products: {str(e)}"}


# ============================================================================
# LOAN TOOL #4: START LOAN APPLICATION
# ============================================================================

def start_loan_application(tool_context: ToolContext, loan_type: str, loan_amount: float, tenure_months: int) -> dict:
    """
    Start a new loan application.
    
    Args:
        tool_context: ToolContext containing mutable session state
        loan_type: Type of loan (personal, home, auto, education)
        loan_amount: Requested loan amount
        tenure_months: Requested tenure in months
    
    Returns:
        dict with application ID and status
    """
    try:
        print(f"\n[LOAN_AGENT] ========== START LOAN APPLICATION ==========")
        print(f"[LOAN_AGENT] start_loan_application() called")
        print(f"[LOAN_AGENT] Loan Type: {loan_type}, Amount: ${loan_amount}, Tenure: {tenure_months} months")
        
        db_user_id = tool_context.state.get("db_user_id")
        user_phone = tool_context.state.get("user_phone")
        
        print(f"[LOAN_AGENT] db_user_id: {db_user_id}, user_phone: {user_phone}")
        
        # CRITICAL FIX: If db_user_id missing but phone available, reload from database
        if not db_user_id and user_phone and _HAS_DB_STORAGE:
            print(f"[LOAN_AGENT] ⚠️  db_user_id missing, attempting to reload from database...")
            try:
                from storage_tools import sync_state_with_db, check_auth_token_exists
                sync_state_with_db(tool_context.state, user_phone)
                db_user_id = tool_context.state.get("db_user_id")
                
                # Also verify authentication status
                if db_user_id:
                    auth_check = check_auth_token_exists(db_user_id)
                    if not auth_check.get("exists"):
                        print(f"[LOAN_AGENT] ❌ No auth token found in database")
                        return {
                            "status": "error",
                            "message": "You must be authenticated first. Please complete verification with the verification agent."
                        }
                
                print(f"[LOAN_AGENT] ✅ Reloaded: db_user_id = {db_user_id}")
            except Exception as reload_err:
                print(f"[LOAN_AGENT] Reload failed: {reload_err}")
        
        if not db_user_id or not user_phone:
            print(f"[LOAN_AGENT] ❌ User authentication data missing")
            return {
                "status": "error",
                "message": "You must be logged in first. Please provide your phone number to continue."
            }
        
        if not _HAS_DB_MANAGER:
            print(f"[LOAN_AGENT] ❌ DB Manager not available")
            return {"status": "error", "message": "Database not available"}
        
        # Create application in database
        print(f"[LOAN_AGENT] Creating loan application in database")
        application = DBManager.create_loan_application(
            user_id=db_user_id,
            loan_type=loan_type,
            requested_amount=loan_amount,
            tenure_months=tenure_months,
            status="pending"
        )
        
        if application:
            print(f"[LOAN_AGENT] ✅ Application created with ID: {application.get('application_id', 'N/A')}")
            
            # Store in state for reference
            tool_context.state["current_application"] = {
                "application_id": application.get("application_id"),
                "loan_type": loan_type,
                "amount": loan_amount,
                "tenure": tenure_months
            }
            print(f"[LOAN_AGENT] Application stored in state")
            
            print(f"[LOAN_AGENT] ========== START LOAN APPLICATION COMPLETE ==========\n")
            
            return {
                "status": "success",
                "application_id": application.get("application_id"),
                "loan_type": loan_type,
                "requested_amount": loan_amount,
                "tenure_months": tenure_months,
                "application_status": "pending",
                "message": f"Loan application created successfully (ID: {application.get('application_id')})"
            }
        else:
            print(f"[LOAN_AGENT] ❌ Failed to create application")
            return {
                "status": "error",
                "message": "Failed to create loan application"
            }
    
    except Exception as e:
        print(f"[LOAN_AGENT ERROR] start_loan_application failed: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": f"Failed to start application: {str(e)}"}


# ============================================================================
# LOAN TOOL #5: GET MY LOAN APPLICATIONS (AUTO-FETCH FOR LOGGED-IN USER)
# ============================================================================

def get_my_loan_applications(tool_context: ToolContext) -> dict:
    """
    Get all loan applications for the currently logged-in user.
    Automatically uses db_user_id from session state.
    No parameters needed - this is auto-populated from user's authenticated session.
    
    Args:
        tool_context: ToolContext containing mutable session state with db_user_id
    
    Returns:
        dict with list of user's loan applications
    """
    try:
        print(f"\n[LOAN_AGENT] ========== GET MY LOAN APPLICATIONS ==========")
        print(f"[LOAN_AGENT] get_my_loan_applications() called")
        
        db_user_id = tool_context.state.get("db_user_id")
        user_phone = tool_context.state.get("user_phone")
        
        print(f"[LOAN_AGENT] db_user_id: {db_user_id}, user_phone: {user_phone}")
        
        # CRITICAL FIX: If db_user_id missing but phone available, reload from database
        if not db_user_id and user_phone and _HAS_DB_STORAGE:
            print(f"[LOAN_AGENT] ⚠️  db_user_id missing, attempting to reload from database...")
            try:
                from storage_tools import sync_state_with_db, check_auth_token_exists
                sync_state_with_db(tool_context.state, user_phone)
                db_user_id = tool_context.state.get("db_user_id")
                
                # Also verify authentication status
                if db_user_id:
                    auth_check = check_auth_token_exists(db_user_id)
                    if not auth_check.get("exists"):
                        print(f"[LOAN_AGENT] ❌ No auth token found in database")
                        return {
                            "status": "error",
                            "message": "You must be authenticated first. Please complete verification with the verification agent."
                        }
                
                print(f"[LOAN_AGENT] ✅ Reloaded: db_user_id = {db_user_id}")
            except Exception as reload_err:
                print(f"[LOAN_AGENT] Reload failed: {reload_err}")
        
        if not db_user_id:
            print(f"[LOAN_AGENT] ❌ User ID not found in session")
            return {
                "status": "error",
                "message": "You must be logged in first. Please provide your phone number to continue."
            }
        
        if not _HAS_DB_MANAGER:
            print(f"[LOAN_AGENT] ❌ DB Manager not available")
            return {"status": "error", "message": "Database not available"}
        
        # Get all applications for this user from database
        print(f"[LOAN_AGENT] Fetching all loan applications for user_id: {db_user_id}")
        session = _HAS_DB_MANAGER and __import__('sys').modules.get('db_manager')
        
        # Query database for this user's applications
        from db_manager import SessionLocal, LoanApplication
        db_session = SessionLocal()
        try:
            applications = db_session.query(LoanApplication).filter(
                LoanApplication.user_id == db_user_id
            ).all()
            
            apps_data = []
            if applications:
                print(f"[LOAN_AGENT] Found {len(applications)} application(s)")
                for app in applications:
                    app_dict = {
                        "application_id": app.application_id,
                        "loan_type": app.loan_type,
                        "requested_amount": float(app.requested_amount),
                        "tenure_months": app.tenure_months,
                        "status": app.status,
                        "created_at": app.created_at.strftime("%Y-%m-%d") if app.created_at else None
                    }
                    apps_data.append(app_dict)
                    print(f"[LOAN_AGENT]   Application {app.application_id}: {app.loan_type} - {app.status}")
            else:
                print(f"[LOAN_AGENT] No applications found for this user")
            
            db_session.close()
            
            print(f"[LOAN_AGENT] ========== GET MY LOAN APPLICATIONS COMPLETE ==========\n")
            
            return {
                "status": "success",
                "application_count": len(apps_data),
                "applications": apps_data,
                "message": f"You have {len(apps_data)} loan application(s)" if apps_data else "You don't have any loan applications yet. Would you like to start one?"
            }
        
        except Exception as e:
            db_session.close()
            print(f"[LOAN_AGENT ERROR] Database query failed: {type(e).__name__}: {e}")
            return {"status": "error", "message": f"Failed to fetch applications: {str(e)}"}
    
    except Exception as e:
        print(f"[LOAN_AGENT ERROR] get_my_loan_applications failed: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": f"Failed to get your loan applications: {str(e)}"}


# ============================================================================
# LOAN TOOL #6: GET APPLICATION STATUS
# ============================================================================

def get_application_status(tool_context: ToolContext, application_id: int) -> dict:
    """
    Get status of a loan application.
    
    Args:
        tool_context: ToolContext containing mutable session state
        application_id: Application ID
    
    Returns:
        dict with application status and details
    """
    try:
        print(f"\n[LOAN_AGENT] ========== GET APPLICATION STATUS ==========")
        print(f"[LOAN_AGENT] get_application_status() called with application_id: {application_id}")
        
        db_user_id = tool_context.state.get("db_user_id")
        
        if not application_id:
            print(f"[LOAN_AGENT] ❌ No application ID provided")
            return {"status": "error", "message": "Application ID is required"}
        
        if not _HAS_DB_MANAGER:
            print(f"[LOAN_AGENT] ❌ DB Manager not available")
            return {"status": "error", "message": "Database not available"}
        
        # Get application from database
        print(f"[LOAN_AGENT] Fetching application {application_id} from database")
        application = DBManager.get_loan_application(application_id)
        
        if application:
            print(f"[LOAN_AGENT] ✅ Application found")
            print(f"[LOAN_AGENT]   Status: {application.get('status')}")
            print(f"[LOAN_AGENT]   Amount: ${application.get('requested_amount')}")
            print(f"[LOAN_AGENT]   Loan Type: {application.get('loan_type')}")
            
            print(f"[LOAN_AGENT] ========== GET APPLICATION STATUS COMPLETE ==========\n")
            
            return {
                "status": "success",
                "application_id": application.get("application_id"),
                "loan_type": application.get("loan_type"),
                "requested_amount": application.get("requested_amount"),
                "tenure_months": application.get("tenure_months"),
                "application_status": application.get("status"),
                "created_at": application.get("created_at"),
                "message": f"Application status: {application.get('status')}"
            }
        else:
            print(f"[LOAN_AGENT] ❌ Application not found")
            return {
                "status": "error",
                "message": f"Application {application_id} not found"
            }
    
    except Exception as e:
        print(f"[LOAN_AGENT ERROR] get_application_status failed: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": f"Failed to get application status: {str(e)}"}


# ============================================================================
# LOAN TOOL #7: GET ACTIVE LOANS
# ============================================================================

def get_active_loans(tool_context: ToolContext) -> dict:
    """
    Get list of user's active loans.
    
    Args:
        tool_context: ToolContext containing mutable session state
    
    Returns:
        dict with list of active loans
    """
    try:
        print(f"\n[LOAN_AGENT] ========== GET ACTIVE LOANS ==========")
        print(f"[LOAN_AGENT] get_active_loans() called")
        
        db_user_id = tool_context.state.get("db_user_id")
        
        print(f"[LOAN_AGENT] db_user_id: {db_user_id}")
        
        if not db_user_id:
            print(f"[LOAN_AGENT] ❌ User ID not found")
            return {"status": "error", "message": "User ID not found"}
        
        if not _HAS_DB_MANAGER:
            print(f"[LOAN_AGENT] ❌ DB Manager not available")
            return {"status": "error", "message": "Database not available"}
        
        # Get active loans
        print(f"[LOAN_AGENT] Fetching active loans for user_id: {db_user_id}")
        loans = DBManager.get_active_loans(db_user_id)
        
        print(f"[LOAN_AGENT] Found {len(loans) if loans else 0} active loans")
        if loans:
            for i, loan in enumerate(loans):
                print(f"[LOAN_AGENT]   Loan {i+1}: ID={loan.get('loan_id')}, Type={loan.get('loan_type')}, Amount=${loan.get('loan_amount')}, Balance=${loan.get('outstanding_balance')}")
        
        print(f"[LOAN_AGENT] ========== GET ACTIVE LOANS COMPLETE ==========\n")
        
        return {
            "status": "success",
            "loan_count": len(loans or []),
            "loans": loans or [],
            "total_outstanding": sum(float(loan.get("outstanding_balance", 0)) for loan in (loans or [])),
            "message": f"You have {len(loans or [])} active loan(s)"
        }
    
    except Exception as e:
        print(f"[LOAN_AGENT ERROR] get_active_loans failed: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": f"Failed to get active loans: {str(e)}"}


# ============================================================================
# LOAN TOOL #8: GET LOAN DETAILS
# ============================================================================

def get_loan_details(tool_context: ToolContext, loan_id: int) -> dict:
    """
    Get detailed information about a specific loan including EMI, rates, schedule.
    
    Args:
        tool_context: ToolContext containing mutable session state
        loan_id: ID of the loan
    
    Returns:
        dict with detailed loan information
    """
    try:
        print(f"\n[LOAN_AGENT] ========== GET LOAN DETAILS ==========")
        print(f"[LOAN_AGENT] get_loan_details() called for loan_id: {loan_id}")
        
        db_user_id = tool_context.state.get("db_user_id")
        
        if not _HAS_DB_MANAGER:
            print(f"[LOAN_AGENT] ❌ DB Manager not available")
            return {"status": "error", "message": "Database not available"}
        
        # Get loan details
        print(f"[LOAN_AGENT] Fetching loan {loan_id} from database")
        loan = DBManager.get_loan_details(loan_id)
        
        if loan:
            print(f"[LOAN_AGENT] ✅ Loan found")
            print(f"[LOAN_AGENT]   Loan Type: {loan.get('loan_type')}")
            print(f"[LOAN_AGENT]   Amount: ${loan.get('loan_amount')}")
            print(f"[LOAN_AGENT]   Balance: ${loan.get('outstanding_balance')}")
            print(f"[LOAN_AGENT]   Interest Rate: {loan.get('interest_rate')}%")
            print(f"[LOAN_AGENT]   EMI: ${loan.get('emi_amount')}")
            
            print(f"[LOAN_AGENT] ========== GET LOAN DETAILS COMPLETE ==========\n")
            
            return {
                "status": "success",
                "loan_id": loan.get("loan_id"),
                "loan_type": loan.get("loan_type"),
                "loan_amount": loan.get("loan_amount"),
                "outstanding_balance": loan.get("outstanding_balance"),
                "interest_rate": loan.get("interest_rate"),
                "emi_amount": loan.get("emi_amount"),
                "tenure_months": loan.get("tenure_months"),
                "disbursed_date": loan.get("disbursed_date"),
                "maturity_date": loan.get("maturity_date"),
                "message": f"Loan details for {loan.get('loan_type')} - EMI: ${loan.get('emi_amount')}"
            }
        else:
            print(f"[LOAN_AGENT] ❌ Loan not found")
            return {
                "status": "error",
                "message": f"Loan {loan_id} not found"
            }
    
    except Exception as e:
        print(f"[LOAN_AGENT ERROR] get_loan_details failed: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": f"Failed to get loan details: {str(e)}"}


# ============================================================================
# LOAN TOOL #9: CALCULATE EMI
# ============================================================================

def calculate_emi(tool_context: ToolContext, principal: float, annual_rate: float, tenure_months: int) -> dict:
    """
    Calculate EMI (Equated Monthly Installment) for a loan.
    Formula: EMI = P * r * (1+r)^n / ((1+r)^n - 1)
    where r = annual_rate / (12 * 100), n = tenure_months
    
    Args:
        tool_context: ToolContext containing mutable session state
        principal: Loan principal amount
        annual_rate: Annual interest rate (%)
        tenure_months: Loan tenure in months
    
    Returns:
        dict with EMI calculation and breakdown
    """
    try:
        print(f"\n[LOAN_AGENT] ========== CALCULATE EMI ==========")
        print(f"[LOAN_AGENT] calculate_emi() called")
        print(f"[LOAN_AGENT] Principal: ${principal}, Rate: {annual_rate}%, Tenure: {tenure_months} months")
        
        if principal <= 0 or annual_rate < 0 or tenure_months <= 0:
            print(f"[LOAN_AGENT] ❌ Invalid input parameters")
            return {
                "status": "error",
                "message": "Invalid parameters: principal and tenure must be > 0, rate must be >= 0"
            }
        
        # Calculate EMI using standard formula
        monthly_rate = annual_rate / (12 * 100)
        print(f"[LOAN_AGENT] Monthly rate: {monthly_rate}")
        
        if monthly_rate == 0:
            # If no interest, simple division
            emi = principal / tenure_months
            print(f"[LOAN_AGENT] Zero interest: EMI = {emi}")
        else:
            # Standard EMI formula
            numerator = monthly_rate * ((1 + monthly_rate) ** tenure_months)
            denominator = ((1 + monthly_rate) ** tenure_months) - 1
            emi = principal * (numerator / denominator)
            print(f"[LOAN_AGENT] Calculated EMI: ${emi:.2f}")
        
        # Calculate totals
        total_amount = emi * tenure_months
        total_interest = total_amount - principal
        
        print(f"[LOAN_AGENT] Total amount: ${total_amount:.2f}")
        print(f"[LOAN_AGENT] Total interest: ${total_interest:.2f}")
        
        print(f"[LOAN_AGENT] ========== CALCULATE EMI COMPLETE ==========\n")
        
        return {
            "status": "success",
            "principal": principal,
            "annual_rate": annual_rate,
            "tenure_months": tenure_months,
            "monthly_emi": round(emi, 2),
            "total_amount_payable": round(total_amount, 2),
            "total_interest_payable": round(total_interest, 2),
            "message": f"Monthly EMI: ${round(emi, 2)}, Total Interest: ${round(total_interest, 2)}"
        }
    
    except Exception as e:
        print(f"[LOAN_AGENT ERROR] calculate_emi failed: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": f"Failed to calculate EMI: {str(e)}"}


# ============================================================================
# LOAN TOOL #10: GET NEXT PAYMENT DUE
# ============================================================================

def get_next_payment_due(tool_context: ToolContext, loan_id: int) -> dict:
    """
    Get next EMI due date and amount for a loan.
    
    Args:
        tool_context: ToolContext containing mutable session state
        loan_id: ID of the loan
    
    Returns:
        dict with next payment details
    """
    try:
        print(f"\n[LOAN_AGENT] ========== GET NEXT PAYMENT DUE ==========")
        print(f"[LOAN_AGENT] get_next_payment_due() called for loan_id: {loan_id}")
        
        if not _HAS_DB_MANAGER:
            print(f"[LOAN_AGENT] ❌ DB Manager not available")
            return {"status": "error", "message": "Database not available"}
        
        # Get next payment details
        print(f"[LOAN_AGENT] Fetching next payment for loan {loan_id}")
        payment = DBManager.get_next_payment_due(loan_id)
        
        if payment:
            print(f"[LOAN_AGENT] ✅ Payment found")
            print(f"[LOAN_AGENT]   Amount: ${payment.get('amount')}")
            print(f"[LOAN_AGENT]   Due Date: {payment.get('due_date')}")
            
            print(f"[LOAN_AGENT] ========== GET NEXT PAYMENT DUE COMPLETE ==========\n")
            
            return {
                "status": "success",
                "loan_id": loan_id,
                "payment_amount": payment.get("amount"),
                "due_date": payment.get("due_date"),
                "days_remaining": payment.get("days_remaining"),
                "message": f"Next EMI of ${payment.get('amount')} due on {payment.get('due_date')}"
            }
        else:
            print(f"[LOAN_AGENT] ❌ No upcoming payment found")
            return {
                "status": "error",
                "message": f"No upcoming payment found for loan {loan_id}"
            }
    
    except Exception as e:
        print(f"[LOAN_AGENT ERROR] get_next_payment_due failed: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": f"Failed to get next payment: {str(e)}"}


# ============================================================================
# LOAN TOOL #11: REQUEST LOAN CLOSURE
# ============================================================================

def request_loan_closure(tool_context: ToolContext, loan_id: int, closure_type: str) -> dict:
    """
    Request loan closure (prepayment or foreclosure).
    
    Args:
        tool_context: ToolContext containing mutable session state
        loan_id: ID of the loan to close
        closure_type: Type of closure ("prepayment" or "foreclosure")
    
    Returns:
        dict with closure request details and payoff amount
    """
    try:
        print(f"\n[LOAN_AGENT] ========== REQUEST LOAN CLOSURE ==========")
        print(f"[LOAN_AGENT] request_loan_closure() called")
        print(f"[LOAN_AGENT] Loan ID: {loan_id}, Closure Type: {closure_type}")
        
        db_user_id = tool_context.state.get("db_user_id")
        
        if not db_user_id:
            print(f"[LOAN_AGENT] ❌ User ID not found")
            return {"status": "error", "message": "User ID not found"}
        
        if closure_type not in ["prepayment", "foreclosure"]:
            print(f"[LOAN_AGENT] ❌ Invalid closure type: {closure_type}")
            return {"status": "error", "message": f"Invalid closure type: {closure_type}"}
        
        if not _HAS_DB_MANAGER:
            print(f"[LOAN_AGENT] ❌ DB Manager not available")
            return {"status": "error", "message": "Database not available"}
        
        # Get loan details for payoff calculation
        print(f"[LOAN_AGENT] Fetching loan {loan_id} for closure calculation")
        loan = DBManager.get_loan_details(loan_id)
        
        if not loan:
            print(f"[LOAN_AGENT] ❌ Loan not found")
            return {"status": "error", "message": f"Loan {loan_id} not found"}
        
        # Calculate payoff amount (outstanding balance + any pending charges)
        outstanding = float(loan.get("outstanding_balance", 0))
        processing_charge = outstanding * 0.001  # 0.1% processing charge
        payoff_amount = outstanding + processing_charge
        
        print(f"[LOAN_AGENT] Outstanding balance: ${outstanding}")
        print(f"[LOAN_AGENT] Processing charge: ${processing_charge:.2f}")
        print(f"[LOAN_AGENT] Total payoff amount: ${payoff_amount:.2f}")
        
        # Create closure request in database
        closure_request = DBManager.create_loan_closure_request(
            loan_id=loan_id,
            user_id=db_user_id,
            closure_type=closure_type,
            payoff_amount=payoff_amount,
            status="pending"
        )
        
        if closure_request:
            print(f"[LOAN_AGENT] ✅ Closure request created with ID: {closure_request.get('closure_request_id')}")
            
            print(f"[LOAN_AGENT] ========== REQUEST LOAN CLOSURE COMPLETE ==========\n")
            
            return {
                "status": "success",
                "closure_request_id": closure_request.get("closure_request_id"),
                "loan_id": loan_id,
                "closure_type": closure_type,
                "outstanding_balance": outstanding,
                "processing_charge": round(processing_charge, 2),
                "total_payoff_amount": round(payoff_amount, 2),
                "message": f"Closure request created. Total payoff amount: ${round(payoff_amount, 2)}"
            }
        else:
            print(f"[LOAN_AGENT] ❌ Failed to create closure request")
            return {
                "status": "error",
                "message": "Failed to create closure request"
            }
    
    except Exception as e:
        print(f"[LOAN_AGENT ERROR] request_loan_closure failed: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": f"Failed to request closure: {str(e)}"}


# ============================================================================
# LOAN AGENT DEFINITION
# ============================================================================

loan_agent = Agent(
    name="loan_agent",
    model="gemini-2.0-flash-exp",
    description="Loan Specialist Agent - Handles loan applications, eligibility, and management",
    instruction="""
    You are the Loan Specialist Agent for AK Bank. Your role is to assist customers with all loan-related needs.
    
    � AUTHENTICATION CHECK:
    - Check if "auth_token" exists in session state
    - If YES → User is authenticated, proceed with loan operations
    - If NO → User must authenticate first. Ask them to authenticate with the verification agent
    
    �📋 REQUEST RESTORATION (FOR ROUTED REQUESTS):
    When you receive a message from the orchestrator, check if "pending_user_request" exists in session state:
    - If YES: This contains the user's original request that was saved during routing
    - Use this to understand what the user wants (e.g., "I want a personal loan for $100,000")
    - Execute their request without asking them to repeat
    - Then clear the pending_user_request from state
    
    TONE & STYLE:
    - Professional, knowledgeable, and helpful
    - Use plain text, no markdown formatting
    - Explain loan concepts clearly to non-technical users
    - Always emphasize responsible borrowing
    - Provide specific numbers and dates when available
    
    YOUR CAPABILITIES:
    1. Check loan eligibility (credit score, income, existing loans)
    2. Show available loan products (personal, home, auto, education)
    3. Calculate EMI for different loan amounts and tenures
    4. Help start new loan applications
    5. Track application status
    6. Show active loans and details
    7. Display upcoming EMI payments
    8. Process loan prepayment/closure requests
    
    IMPORTANT FLOWS:
    
    FOR NEW LOAN INQUIRY (Customer says "I want to borrow $X" or "I want a personal loan"):
    Step 1: Ask what type of loan (if not specified): personal, home, auto, education?
    Step 2: Call check_loan_eligibility with the loan type
    Step 3: If eligible, say: "Great! You are eligible for a personal loan. Our interest rate is 12.5% per annum."
    Step 4: Immediately ask: "How much would you like to borrow?"
    Step 5: After they give amount, ask: "How many months would you like to repay? (12, 24, 36, 48, or 60 months suggested)"
    Step 6: Once you have amount and tenure, calculate EMI using STANDARD RATE for that loan type
    Step 7: Call calculate_emi(amount, standard_rate, tenure)
    Step 8: Show result with full breakdown
    Step 9: Ask: "Would you like to proceed with the application?"
    Step 10: If yes, call start_loan_application
    
    FOR EXISTING CUSTOMER WITH ACTIVE LOANS:
    Step 1: Call get_active_loans to show their current loans
    Step 2: For any loan, can show details with get_loan_details
    Step 3: Can show next payment with get_next_payment_due
    Step 4: Can process closure with request_loan_closure
    
    FOR CHECKING LOAN APPLICATION STATUS:
    - If customer asks "What's the status of my loan?" or "Check my application"
    - ALWAYS use get_my_loan_applications FIRST - no need to ask for ID
    - This automatically fetches ALL applications for the logged-in user
    - Shows: Application ID, Loan Type, Amount, Tenure, Status, and Creation Date
    - If they have multiple applications, list all of them
    - If they want details on one specific application, you can refer to the ID shown
    - Example response: "I found 2 applications for you:
      Application 1: Personal Loan - $12,000 for 12 months - Status: Pending
      Application 2: Home Loan - $500,000 for 120 months - Status: Approved"
    
    FOR EMI CALCULATION:
    - Always use STANDARD interest rates (do NOT ask customer):
      * Personal Loan: 12.5% per annum
      * Home Loan: 8.5% per annum
      * Auto Loan: 10.0% per annum
      * Education Loan: 9.0% per annum
    - Ask for: loan amount and tenure (in months)
    - Suggested tenures: 12, 24, 36, 48, 60 months
    - Call calculate_emi with: principal, standard_rate, tenure_months
    - Show clear breakdown: Monthly EMI, Total Interest, Total Payable Amount
    - Example: "For a personal loan of 10,000 at 12.5% for 36 months, your monthly EMI would be 313, total interest 2,683, total payment 12,683"
    
    SECURITY RULES:
    - All operations require user authentication (db_user_id in state)
    - Never process large amounts without confirmation
    - Always show clear breakdown of charges
    - Confirm identity before sensitive operations
    
    EXAMPLE RESPONSES (Plain Text Format):
    
    "Your credit score is 720 (Good). You are eligible for personal loans up to 500,000 with interest rates starting at 12.5% per annum."
    
    "I found 3 active loans on your account:
    1. Personal Loan - 200,000 outstanding balance
    2. Auto Loan - 150,000 outstanding balance
    3. Education Loan - 75,000 outstanding balance
    Total outstanding: 425,000"
    
    "For a personal loan of 100,000 at 12% interest for 36 months:
    Monthly EMI: 3,214
    Total interest payable: 15,704
    Total amount payable: 115,704"
    
    ALWAYS:
    - Use get_user_credit_score to show eligibility
    - Do NOT ask for interest rate - use standard rates per loan type
    - Use calculate_emi for any EMI discussions with standard rates
    - Confirm all numbers with the customer before final submission
    - Provide clear next steps after each action
    - Give examples with numbers: "Your EMI would be 313 per month"
    """,
    tools=[
        check_loan_eligibility,
        get_user_credit_score,
        get_available_loan_products,
        start_loan_application,
        get_my_loan_applications,
        get_application_status,
        get_active_loans,
        get_loan_details,
        calculate_emi,
        get_next_payment_due,
        request_loan_closure,
    ]
)
