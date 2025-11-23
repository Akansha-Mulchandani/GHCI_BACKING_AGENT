from google.adk.agents import Agent
from google.adk.tools.tool_context import ToolContext

from .sub_agents.transaction_agent.agent import transaction_agent, get_balance, get_transaction_history, transfer_funds, set_transfer_params
from .sub_agents.verification_agent.agent import verification_agent, set_user_phone, request_otp, validate_otp, create_new_user_account
from .sub_agents.loan_agent.agent import loan_agent, check_loan_eligibility, get_user_credit_score, get_available_loan_products, start_loan_application, get_application_status, get_active_loans, get_loan_details, calculate_emi, get_next_payment_due, request_loan_closure

# Try to import check_user_exists for existing customer validation
try:
    from .sub_agents.verification_agent.user_validation import check_user_exists
except Exception as e:
    print(f"[ORCHESTRATOR] Warning: Could not import check_user_exists: {e}")
    check_user_exists = None


def save_user_request(tool_context: ToolContext, request: str) -> dict:
    """Save the user's original request in session state for routing to sub-agents.
    
    This prevents the request from being lost when routing to transaction_agent or loan_agent.
    The sub-agent will read pending_user_request and execute the user's original request.
    """
    print(f"[ORCHESTRATOR] Saving user request for sub-agent routing: {request}")
    tool_context.state["pending_user_request"] = request
    return {
        "status": "ok",
        "message": f"User request saved: {request}",
        "pending_request": request
    }


# Root orchestrator agent for the banking MVP
banking_orchestrator = Agent(
    name="banking_orchestrator",
    model="gemini-2.0-flash-exp",
    description="Orchestrator for FinAgent MVP (text-only). Routes to verification and transaction subagents.",
    instruction="""
You are the Banking Orchestrator. Your job is simple: delegate all user requests to the right sub-agent.

YOU HAVE THREE SUB-AGENTS:
1. verification_agent → Authentication, phone, OTP, account checks
2. transaction_agent → Balance, transfers, transaction history
3. loan_agent → Loans, credit score, EMI, applications

ROUTING (SUPER SIMPLE):
- First message or anything you're unsure about → verification_agent
- "balance" or "transfer" or "send" → transaction_agent
- "loan" or "borrow" or "credit" or "emi" → loan_agent

THAT'S IT. Just pick the right agent and delegate. Do NOT:
- Answer questions yourself
- Check auth_token
- Process payments
- Create accounts

Just delegate to the right sub-agent. They handle everything.

EXAMPLES:
- User: "What is my balance?" → Delegate to transaction_agent
- User: "Transfer $100" → Delegate to transaction_agent
- User: "Get me a loan" → Delegate to loan_agent
- User: "Hello" or anything else → Delegate to verification_agent
""",
    sub_agents=[verification_agent, transaction_agent, loan_agent],
    tools=[save_user_request] if check_user_exists else [save_user_request],
)
