import asyncio
import base64
import json
import os
from pathlib import Path
from typing import AsyncIterable

from dotenv import load_dotenv
from fastapi import FastAPI, Query, WebSocket
from starlette.websockets import WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from google.adk.agents import LiveRequestQueue
from google.adk.agents.run_config import RunConfig
from google.adk.events.event import Event
from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.adk.sessions import DatabaseSessionService
from google.genai import types
import sys
from pathlib import Path

# Database imports
try:
    from db_manager import DBManager, seed_demo_data
    DB_AVAILABLE = True
except Exception as e:
    print(f"[INIT] Database module not available: {e}")
    DB_AVAILABLE = False

# Try to make the banking agent importable when this voice app is run from its folder.
# Strategy: Try local first (adk-voice-agent/app/banking_agent), then try sibling folder.
def _load_root_agent() -> tuple:
    """Attempt to import the project's banking agent, falling back to the bundled sample.

    Returns (agent, app_name)
    """
    # First try: Local banking_agent in adk-voice-agent/app/banking_agent
    try:
        from banking_agent.agent import banking_orchestrator as root_agent
        return root_agent, "Banking Agent (voice) - Local"
    except Exception as e:
        local_error = e
        pass
    
    # Second try: Sibling folder agent-development-kit-crash-course
    try:
        ROOT = Path(__file__).resolve().parents[2]
        candidate = ROOT / "agent-development-kit-crash-course"
        if candidate.exists():
            sys.path.insert(0, str(candidate))
        from banking_agent.agent import banking_orchestrator as root_agent
        return root_agent, "Banking Agent (voice) - Sibling"
    except Exception as e:
        sibling_error = e
        pass
    
    # Third try: Sample jarvis agent that ships with the voice demo
    try:
        from jarvis.agent import root_agent
        return root_agent, "ADK Streaming example"
    except Exception:
        pass
    
    # If all fail, propagate the local error
    raise local_error

#
# ADK Streaming
#

# Load Gemini API Key - explicitly load from app directory .env
print(f"[INIT] Loading environment from .env file")
env_file = Path(__file__).parent / ".env"
print(f"[INIT] .env file path: {env_file}")
load_dotenv(dotenv_path=env_file)
print(f"[INIT] Environment loaded successfully")

# CRITICAL: Set up credentials for Google Cloud services
# Keep GOOGLE_APPLICATION_CREDENTIALS if it was set in .env
# But ensure GOOGLE_API_KEY is available for Gemini
credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
if credentials_path and os.path.exists(credentials_path):
    print(f"[INIT] Google Cloud credentials found at: {credentials_path}")
    # Keep it set for speech client
else:
    print(f"[INIT] Google Cloud credentials not found, audio transcription may not work")
    os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)

# Disable Vertex AI flag to use public API key instead
os.environ.pop("GOOGLE_GENAI_USE_VERTEXAI", None)
print(f"[INIT] Cleared GOOGLE_GENAI_USE_VERTEXAI flag, using public API key mode")


# Quick credentials sanity check / normalization
def _check_genai_credentials():
    """Detect common credential patterns and print actionable guidance.

    The google-genai library accepts either an API key (GOOGLE_API_KEY) or
    Vertex credentials (service account via GOOGLE_APPLICATION_CREDENTIALS
    plus GOOGLE_CLOUD_PROJECT and GOOGLE_CLOUD_LOCATION). This helper
    attempts to detect a usable configuration and prints clear errors
    so the user can fix the environment instead of hitting a vague
    ValueError deep inside the SDK.
    """

    has_api_key = bool(os.getenv("GOOGLE_API_KEY"))
    has_service_account = bool(os.getenv("GOOGLE_APPLICATION_CREDENTIALS"))
    genai_vertex_flag = os.getenv("GOOGLE_GENAI_USE_VERTEXAI")

    if has_api_key:
        print("Using GOOGLE_API_KEY for GenAI API (non-Vertex mode).")
        return

    # If service account is present, prefer vertex mode but require project+location
    if has_service_account:
        project = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GOOGLE_PROJECT")
        location = os.getenv("GOOGLE_CLOUD_LOCATION") or os.getenv("GOOGLE_LOCATION")
        if not project or not location:
            print("Found GOOGLE_APPLICATION_CREDENTIALS but missing project/location.")
            print("Set GOOGLE_CLOUD_PROJECT and GOOGLE_CLOUD_LOCATION (e.g. us-central1).")
            return

        # normalize the flag so downstream libraries detect Vertex usage
        if not genai_vertex_flag:
            os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "TRUE"
            print("Set GOOGLE_GENAI_USE_VERTEXAI=TRUE (auto-detected service account).")
        print("Using Vertex (service account) for GenAI: project=%s location=%s" % (project, location))
        return

    # Nothing obvious found - give instructions
    print("WARNING: No GenAI credentials detected.")
    print("Either set GOOGLE_API_KEY for the public GenAI API, or set GOOGLE_APPLICATION_CREDENTIALS + GOOGLE_CLOUD_PROJECT + GOOGLE_CLOUD_LOCATION to use Vertex.")
    print("Example (PowerShell):")
    print("  $env:GOOGLE_API_KEY='your_api_key_here'")
    print("  # -- or --")
    print("  $env:GOOGLE_APPLICATION_CREDENTIALS='C:/path/to/key.json'; $env:GOOGLE_CLOUD_PROJECT='my-project'; $env:GOOGLE_CLOUD_LOCATION='us-central1'")


# Run check at import time so we fail fast with guidance
_check_genai_credentials()

# Cache API key globally at startup
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY") or "AIzaSyDcUVboxdIi_9lC2_YMC_XTqgo7lg-SK_M"
if not GOOGLE_API_KEY:
    print("[CRITICAL] GOOGLE_API_KEY not found in environment or .env file!")
    print("[CRITICAL] Agent will fail when trying to process requests.")
else:
    print(f"[STARTUP] API Key loaded: {GOOGLE_API_KEY[:10]}...")

APP_NAME = "ADK Streaming example"

# Initialize session service with DATABASE persistence
# This means session state (conversations, state) is saved to database per user
# Sessions are keyed by phone number, so data persists across logins
print(f"[STARTUP] Initializing persistent DatabaseSessionService")
try:
    # Get database URL from environment
    DATABASE_URL = os.getenv("DATABASE_URL")
    if not DATABASE_URL:
        print(f"[STARTUP WARNING] DATABASE_URL not set, falling back to InMemorySessionService")
        session_service = InMemorySessionService()
    else:
        print(f"[STARTUP] Using DatabaseSessionService with URL: {DATABASE_URL[:50]}...")
        # DatabaseSessionService persists all session state to database
        # This is critical for user data persistence across sessions
        session_service = DatabaseSessionService(db_url=DATABASE_URL)
        print(f"[STARTUP] DatabaseSessionService initialized successfully")
except Exception as e:
    print(f"[STARTUP ERROR] Failed to initialize DatabaseSessionService: {e}")
    print(f"[STARTUP] Falling back to InMemorySessionService")
    session_service = InMemorySessionService()


async def start_agent_session(session_id, is_audio=False):
    """Starts an agent session"""
    
    # CRITICAL: Ensure API key is in environment for this request
    if GOOGLE_API_KEY:
        os.environ["GOOGLE_API_KEY"] = GOOGLE_API_KEY
        print(f"[SESSION {session_id}] API Key set: {GOOGLE_API_KEY[:20]}...")
    else:
        print(f"[ERROR] No API key available for session {session_id}")
    
    # Import genai and explicitly configure with hardcoded API key
    try:
        import google.genai as genai
        # Try to configure if the method exists in this version
        if hasattr(genai, 'configure'):
            genai.configure(api_key=GOOGLE_API_KEY)
            print(f"[SESSION {session_id}] genai.configure() called")
    except Exception as e:
        print(f"[SESSION {session_id}] genai.configure() not available: {e}")

    # Create a Session
    # Provide a minimal default state so agents that expect context variables
    # (like `{user_name}`, `accounts`, `interaction_history`) can render
    # their instruction templates without KeyError.
    default_state = {
        "user_name": "Guest",
        "accounts": [
            {"id": "acc-001", "type": "checking", "currency": "USD", "available_balance": 5000.0},
            {"id": "acc-002", "type": "savings", "currency": "USD", "available_balance": 15000.0},
        ],
        "interaction_history": [],
    }

    # create_session may be sync or async depending on ADK version.
    # If session already exists, get it instead of creating duplicate
    try:
        maybe_coro = session_service.create_session(
            app_name=APP_NAME,
            user_id=session_id,
            session_id=session_id,
            state=default_state,
        )
        if asyncio.iscoroutine(maybe_coro):
            session = await maybe_coro
        else:
            session = maybe_coro
        print(f"[SESSION {session_id}] New session created")
    except Exception as e:
        # Session already exists - just load it with existing state (preserve data)
        print(f"[SESSION {session_id}] Session already exists, reusing it: {e}")
        maybe_coro = session_service.get_session(
            app_name=APP_NAME,
            user_id=session_id,
            session_id=session_id,
        )
        if asyncio.iscoroutine(maybe_coro):
            session = await maybe_coro
        else:
            session = maybe_coro
        print(f"[SESSION {session_id}] Loaded existing session (data preserved)")

    # Lazy-load the agent (so we can check credentials first at module import)
    root_agent, app_name = _load_root_agent()

    # Create a Runner
    runner = Runner(
        app_name=app_name,
        agent=root_agent,
        session_service=session_service,
    )

    # Set response modality
    from google.genai import types as genai_types
    modality = genai_types.Modality.AUDIO if is_audio else genai_types.Modality.TEXT

    # Create speech config with voice settings
    speech_config = types.SpeechConfig(
        voice_config=types.VoiceConfig(
            # Puck, Charon, Kore, Fenrir, Aoede, Leda, Orus, and Zephyr
            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Puck")
        )
    )

    # Create run config with basic settings
    config = {"response_modalities": [modality], "speech_config": speech_config}

    # Add audio transcription settings when audio is enabled
    if is_audio:
        # output_audio_transcription: Returns text transcription of the agent's audio response
        config["output_audio_transcription"] = {}
        # input_audio_transcription: Returns text transcription of the user's audio input (KEY FOR VOICE DISPLAY!)
        config["input_audio_transcription"] = {}

    run_config = RunConfig(**config)

    # Create a LiveRequestQueue for this session
    live_request_queue = LiveRequestQueue()

    # CRITICAL: Set credentials in environment right before calling run_live
    # This ensures they're available for all Google Cloud services
    if GOOGLE_API_KEY:
        os.environ["GOOGLE_API_KEY"] = GOOGLE_API_KEY
        print(f"[RUN_LIVE] Set GOOGLE_API_KEY in os.environ: {GOOGLE_API_KEY[:20]}...")
    
    # Ensure Google Cloud credentials are set for Speech API
    credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if credentials_path and os.path.exists(credentials_path):
        print(f"[RUN_LIVE] Google Cloud credentials set to: {credentials_path}")
    else:
        print(f"[RUN_LIVE] WARNING: Google Cloud credentials not configured")
    
    # Disable Vertex AI flag to use public API key
    os.environ.pop("GOOGLE_GENAI_USE_VERTEXAI", None)
    print(f"[RUN_LIVE] Cleared GOOGLE_GENAI_USE_VERTEXAI flag")

    print(f"[RUN_LIVE] Calling runner.run_live()...")
    # Start agent session
    live_events_gen = runner.run_live(
        session=session,
        live_request_queue=live_request_queue,
        run_config=run_config,
    )
    print(f"[RUN_LIVE] runner.run_live() returned generator, type: {type(live_events_gen)}")
    
    # Wrap the generator to ensure API key is set for each event
    # runner.run_live() returns an async generator, so we need to use async for
    async def live_events_with_env():
        print(f"[EVENTS] Starting event processing for session {session_id}")
        event_count = 0
        try:
            # Iterate over the async generator with async for
            async for event in live_events_gen:
                event_count += 1
                # Re-set credentials before processing each event
                if GOOGLE_API_KEY:
                    os.environ["GOOGLE_API_KEY"] = GOOGLE_API_KEY
                    print(f"[EVENTS] Event #{event_count}: Re-set API key")
                
                # Re-set Google Cloud credentials for speech client
                credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
                if credentials_path and os.path.exists(credentials_path):
                    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path
                    print(f"[EVENTS] Event #{event_count}: Re-set Cloud credentials")
                
                print(f"[EVENTS] Event #{event_count}: About to yield event")
                yield event
                print(f"[EVENTS] Event #{event_count}: Successfully yielded")
        except GeneratorExit:
            print(f"[EVENTS] Generator closed after {event_count} events")
            raise
        except Exception as e:
            print(f"[EVENTS ERROR] Event processing failed after {event_count} events: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            raise
    
    print(f"[RUN_LIVE] Returning wrapped async generator and queue")
    return live_events_with_env(), live_request_queue


async def agent_to_client_messaging(
    websocket: WebSocket, live_events: AsyncIterable[Event | None]
):
    """Agent to client communication"""
    turn_started = False
    accumulated_user_input = ""  # Accumulate user input transcriptions
    accumulated_agent_output = ""  # Accumulate agent response text
    accumulated_audio_chunks = []  # Buffer audio until text message is sent
    user_message_sent = False  # Track if user message was already sent
    agent_text_sent = False  # Track if agent text message was sent
    
    while True:
        async for event in live_events:
            if event is None:
                continue

            # IMPORTANT: Process content BEFORE checking turn_complete
            # because final event may contain both content and turn_complete flag
            
            # Read the Content and its first Part
            part = event.content and event.content.parts and event.content.parts[0]
            
            if part and isinstance(part, types.Part):
                # Handle user speech transcriptions (from audio input)
                if part.text and event.content.role == "user":
                    # Accumulate user input
                    accumulated_user_input = part.text
                    print(f"[VOICE INPUT TRANSCRIBING] (partial/accumulating) {part.text}")
                
                # Handle agent text responses (streaming or partial)
                elif part.text and event.content.role == "model":
                    # SEND USER MESSAGE NOW - agent started responding means user transcription is complete
                    if accumulated_user_input and not user_message_sent:
                        message = {
                            "mime_type": "text/plain",
                            "data": accumulated_user_input,
                            "role": "user",
                            "complete": True,
                        }
                        await websocket.send_text(json.dumps(message))
                        print(f"[VOICE INPUT COMPLETE - SENT IMMEDIATELY] {accumulated_user_input}")
                        user_message_sent = True
                    
                    # Now accumulate agent response text (don't send fragments)
                    accumulated_agent_output = part.text
                    print(f"[AGENT RESPONSE ACCUMULATING] {part.text}")
                    turn_started = True
                
                # If it's audio, buffer it (don't send immediately - wait for text)
                is_audio = (
                    part.inline_data
                    and part.inline_data.mime_type
                    and part.inline_data.mime_type.startswith("audio/pcm")
                )
                if is_audio:
                    audio_data = part.inline_data and part.inline_data.data
                    if audio_data:
                        # Buffer the audio chunk - we'll send after text displays
                        audio_chunk = {
                            "mime_type": "audio/pcm",
                            "data": base64.b64encode(audio_data).decode("ascii"),
                            "role": "model",
                        }
                        accumulated_audio_chunks.append(audio_chunk)
                        print(f"[AGENT AUDIO BUFFERED] Chunk {len(accumulated_audio_chunks)}")

            # NOW check if the turn is complete or interrupted
            # and send those signals AFTER content
            if event.turn_complete or event.interrupted:
                # Send the complete accumulated user input FIRST (at turn end)
                if accumulated_user_input and not user_message_sent:
                    message = {
                        "mime_type": "text/plain",
                        "data": accumulated_user_input,
                        "role": "user",
                        "complete": True,
                    }
                    await websocket.send_text(json.dumps(message))
                    print(f"[VOICE INPUT COMPLETE] User said: {accumulated_user_input}")
                    user_message_sent = True
                
                # Send the complete accumulated agent response SECOND (at turn end)
                if accumulated_agent_output and not agent_text_sent:
                    message = {
                        "mime_type": "text/plain",
                        "data": accumulated_agent_output,
                        "role": "model",
                    }
                    await websocket.send_text(json.dumps(message))
                    print(f"[AGENT RESPONSE COMPLETE - TEXT SENT FIRST] {accumulated_agent_output}")
                    agent_text_sent = True
                
                # THEN send all buffered audio chunks (NOW that text is displayed)
                for audio_chunk in accumulated_audio_chunks:
                    await websocket.send_text(json.dumps(audio_chunk))
                if accumulated_audio_chunks:
                    print(f"[AGENT AUDIO SENT AFTER TEXT] {len(accumulated_audio_chunks)} chunks")
                    accumulated_audio_chunks = []
                
                message = {
                    "turn_complete": event.turn_complete,
                    "interrupted": event.interrupted,
                }
                await websocket.send_text(json.dumps(message))
                if event.turn_complete:
                    print(f"[TURN COMPLETE] Agent finished processing")
                    # Reset for next turn
                    turn_started = False
                    accumulated_user_input = ""
                    accumulated_agent_output = ""
                    accumulated_audio_chunks = []
                    user_message_sent = False
                    agent_text_sent = False
                if event.interrupted:
                    print(f"[TURN INTERRUPTED] Agent response was interrupted")



async def client_to_agent_messaging(
    websocket: WebSocket, live_request_queue: LiveRequestQueue
):
    """Client to agent communication"""
    while True:
        # Decode JSON message
        message_json = await websocket.receive_text()
        message = json.loads(message_json)
        mime_type = message["mime_type"]
        data = message["data"]
        role = message.get("role", "user")  # Default to 'user' if role is not provided

        # Send the message to the agent
        if mime_type == "text/plain":
            # Send a text message
            content = types.Content(role=role, parts=[types.Part.from_text(text=data)])
            live_request_queue.send_content(content=content)
            print(f"[TEXT INPUT] User typed: {data}")
        elif mime_type == "audio/pcm":
            # Send audio data
            decoded_data = base64.b64decode(data)

            # Send the audio data - note that ActivityStart/End and transcription
            # handling is done automatically by the ADK when input_audio_transcription
            # is enabled in the config
            live_request_queue.send_realtime(
                types.Blob(data=decoded_data, mime_type=mime_type)
            )
            # Audio chunks logged silently - only transcription will be logged

        else:
            raise ValueError(f"Mime type not supported: {mime_type}")


#
# FastAPI web app
#

app = FastAPI()

# ========================================================================
# DATABASE INITIALIZATION
# ========================================================================

@app.on_event("startup")
async def startup_event():
    """Initialize database on app startup"""
    if DB_AVAILABLE:
        try:
            print("[INIT] Initializing database...")
            DBManager.init_db()
            seed_demo_data()
            print("[INIT] Database initialized successfully")
        except Exception as e:
            print(f"[INIT] WARNING: Database initialization failed: {e}")
            print("[INIT] Continuing without persistent storage...")
    else:
        print("[INIT] Database module not available, using in-memory storage only")


STATIC_DIR = Path(__file__).parent / "static"

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def root():
    """Serves the index.html"""
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok", "message": "AK Bank Voice Agent is running"}


@app.websocket("/ws/{session_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    session_id: str,
    is_audio: str = Query(...),
):
    """Client websocket endpoint
    
    IMPORTANT: session_id should be the user's phone number!
    With DatabaseSessionService, all state is persisted to the database.
    By using phone number as session_id, user data persists across sessions:
    - When user "9998889999" connects, their previous conversations/state are restored
    - Transactions, accounts, and auth tokens remain persistent
    - This ensures seamless user experience across multiple sessions
    """

    # Wait for client connection
    await websocket.accept()
    audio_mode_status = "ENABLED ✓" if is_audio == "true" else "TEXT MODE"
    print(f"\n{'='*60}")
    print(f"[WEBSOCKET CONNECTION] Client #{session_id} connected")
    print(f"[MODE] Audio/Voice: {audio_mode_status}")
    print(f"[SESSION] Session ID: {session_id}")
    print(f"{'='*60}\n")

    # Start agent session
    # start_agent_session is async (await the coroutine)
    live_events, live_request_queue = await start_agent_session(
        session_id, is_audio == "true"
    )

    # Send initial trigger to start conversation (agent will greet based on instructions)
    # This is ONLY for text mode - in audio mode, let user speak first
    if is_audio != "true":
        print(f"[WEBSOCKET] Triggering initial agent greeting for session {session_id}")
        trigger_content = types.Content(
            role="user",
            parts=[types.Part.from_text(text="")]  # Empty message to trigger agent's greeting
        )
        live_request_queue.send_content(content=trigger_content)
        print(f"[WEBSOCKET] Greeting trigger sent for session {session_id}")
    else:
        print(f"[WEBSOCKET] Audio mode: Waiting for user voice input (no automatic greeting)")


    # Start tasks
    agent_to_client_task = asyncio.create_task(
        agent_to_client_messaging(websocket, live_events)
    )
    client_to_agent_task = asyncio.create_task(
        client_to_agent_messaging(websocket, live_request_queue)
    )

    try:
        await asyncio.gather(agent_to_client_task, client_to_agent_task)
    except WebSocketDisconnect as e:
        # Client closed the connection (expected when disabling voice)
        print(f"WebSocketDisconnect for client #{session_id}: code={e.code} reason={e.args}")
        # Cancel any remaining tasks
        for t in (agent_to_client_task, client_to_agent_task):
            if not t.done():
                t.cancel()
        # Wait briefly for cancellation to propagate
        await asyncio.sleep(0)
    except asyncio.CancelledError:
        # Normal shutdown cancellation
        pass
    except Exception as e:
        # Log unexpected exceptions but ensure cleanup
        print(f"Unexpected error in websocket endpoint for client #{session_id}: {e}")
        for t in (agent_to_client_task, client_to_agent_task):
            if not t.done():
                t.cancel()
    finally:
        # Ensure tasks are finished or cancelled before returning
        for t in (agent_to_client_task, client_to_agent_task):
            try:
                if not t.done():
                    t.cancel()
                await t
            except asyncio.CancelledError:
                pass
            except Exception:
                pass

    # Disconnected
    print(f"Client #{session_id} disconnected")
