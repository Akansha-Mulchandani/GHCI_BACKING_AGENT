import asyncio

import os
from dotenv import load_dotenv
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService

from .agent import banking_orchestrator
from .utils import add_user_query_to_history, add_agent_response_to_history, call_agent_async, simple_nlu, perform_action

load_dotenv()


# ===== PART 1: Initialize In-Memory Session Service =====
session_service = InMemorySessionService()


# ===== PART 2: Define Initial State =====
initial_state = {
    "user_name": "Test User",
    "accounts": [
        {"id": "acc-001", "type": "savings", "currency": "INR", "available_balance": 5000.0},
        {"id": "acc-002", "type": "checking", "currency": "INR", "available_balance": 15000.0},
    ],
    "interaction_history": [],
}
# Optionally seed a default phone number from environment for demo runs
env_phone = os.getenv("USER_PHONE")
if env_phone:
    initial_state["user_phone"] = env_phone


async def main_async():
    APP_NAME = "FinAgent"
    USER_ID = "user_test"

    # Create session
    new_session = session_service.create_session(
        app_name=APP_NAME, user_id=USER_ID, state=initial_state
    )
    SESSION_ID = new_session.id
    print(f"Created new session: {SESSION_ID}")

    # Create a runner with the orchestrator
    runner = Runner(agent=banking_orchestrator, app_name=APP_NAME, session_service=session_service)

    print("\nWelcome to FinAgent (text-only). Type 'exit' to quit.\n")

    while True:
        user_input = input("You: ")
        if user_input.lower() in ["exit", "quit"]:
            print("Goodbye")
            break

        # Persist user query
        add_user_query_to_history(session_service, APP_NAME, USER_ID, SESSION_ID, user_input)

        # Simple deterministic NLU routing first
        intent, entities = simple_nlu(user_input)
        if intent != "unknown":
            msg, result = perform_action(session_service, APP_NAME, USER_ID, SESSION_ID, intent, entities)
            # Print and persist the orchestration result as agent response
            print(f"Agent: {msg}")
            add_agent_response_to_history(session_service, APP_NAME, USER_ID, SESSION_ID, "orchestrator", msg)
            continue

        # Fallback to model-driven behavior
        await call_agent_async(runner, USER_ID, SESSION_ID, user_input)


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
