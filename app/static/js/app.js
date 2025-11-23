/**
 * app.js: JS code for the adk-streaming sample app.
 */

/**
 * WebSocket handling
 */

// Global variables
// Use a compact base36 session id (non-empty) so session ids are stable and valid
const sessionId = Math.random().toString(36).substring(2, 10);
let websocket = null;
let currentWsUrl = null; // track the URL used for the current websocket
let is_audio = false;
let currentMessageId = null; // Track the current message ID during a conversation turn
let reconnectAttempts = 0;
const MAX_RECONNECT_ATTEMPTS = 6;
const RECONNECT_BASE_MS = 1000; // base backoff
let isAgentSpeaking = false; // Track if agent is currently responding
let isMuted = true; // Start muted by default when voice is enabled
let pendingMessages = []; // Buffer for messages while muted

// Get DOM elements
const messageForm = document.getElementById("messageForm");
const messageInput = document.getElementById("message");
const messagesDiv = document.getElementById("messages");
const statusDot = document.getElementById("status-dot");
const connectionStatus = document.getElementById("connection-status");
const typingIndicator = document.getElementById("typing-indicator");
const listeningIndicator = document.getElementById("listening-indicator");
const startAudioButton = document.getElementById("startAudioButton");
const stopAudioButton = document.getElementById("stopAudioButton");
const recordingContainer = document.getElementById("recording-container");
const unmuteButton = document.getElementById("unmuteButton");
const muteButton = document.getElementById("muteButton");
const voiceControls = document.querySelector(".voice-controls");

// Function to process a message (extracted so it can be called for buffered messages too)
function processMessage(message_from_server) {
  // Show typing indicator for first message in a response sequence
  if (
    !message_from_server.turn_complete &&
    (message_from_server.mime_type === "text/plain" ||
      message_from_server.mime_type === "audio/pcm")
  ) {
    typingIndicator.style.display = "block";
  }

  // Check if the turn is complete
  if (
    message_from_server.turn_complete &&
    message_from_server.turn_complete === true
  ) {
    // Reset currentMessageId to ensure the next message gets a new element
    currentMessageId = null;
    typingIndicator.style.display = "none";
    isAgentSpeaking = false; // Agent finished speaking, user can now speak
    
    // If in audio mode, re-enable listening after agent response
    if (is_audio && listeningIndicator) {
      listeningIndicator.style.display = "block";
    }
    return;
  }

  // If it's audio, play it
  if (message_from_server.mime_type === "audio/pcm" && audioPlayerNode) {
    audioPlayerNode.port.postMessage(base64ToArray(message_from_server.data));

    // If we have an existing message element for this turn, add audio icon if needed
    if (currentMessageId) {
      const messageElem = document.getElementById(currentMessageId);
      if (
        messageElem &&
        !messageElem.querySelector(".audio-icon") &&
        is_audio
      ) {
        const audioIcon = document.createElement("span");
        audioIcon.className = "audio-icon";
        messageElem.prepend(audioIcon);
      }
    }
  }

  // Handle text messages
  if (message_from_server.mime_type === "text/plain") {
    // Hide typing indicator
    typingIndicator.style.display = "none";

    const role = message_from_server.role || "model";
    const isUserMessage = role === "user";
    const newText = message_from_server.data;
    
    // If agent is responding, mark it
    if (role === "model") {
      isAgentSpeaking = true;
    }

    // For agent messages: try to append to existing message if in same turn
    if (!isUserMessage && currentMessageId) {
      const existingMessage = document.getElementById(currentMessageId);
      if (existingMessage) {
        const currentContent = existingMessage.textContent;
        
        // If new text is much longer (complete message), replace instead of append
        if (newText.length > currentContent.length * 1.5 && !currentContent.includes(newText)) {
          // Clear the existing text nodes (but keep audio icon if present)
          const audioIcon = existingMessage.querySelector(".audio-icon");
          while (existingMessage.firstChild) {
            existingMessage.removeChild(existingMessage.firstChild);
          }
          // Re-add audio icon if it existed
          if (audioIcon) {
            existingMessage.appendChild(audioIcon);
          }
          existingMessage.appendChild(document.createTextNode(newText));
        } else {
          // Append the text
          const textNode = document.createTextNode(newText);
          existingMessage.appendChild(textNode);
        }

        // Scroll to the bottom
        messagesDiv.scrollTop = messagesDiv.scrollHeight;
        return;
      }
    }

    // Create a new message element
    const messageId = Math.random().toString(36).substring(7);
    const messageElem = document.createElement("p");
    messageElem.id = messageId;

    // Set class based on role
    messageElem.className = isUserMessage ? "user-message" : "agent-message";

    // Add audio icon for model messages if audio is enabled
    if (is_audio && !isUserMessage) {
      const audioIcon = document.createElement("span");
      audioIcon.className = "audio-icon";
      messageElem.appendChild(audioIcon);
    }

    // Add the text content
    messageElem.appendChild(
      document.createTextNode(newText)
    );

    // Add the message to the DOM
    messagesDiv.appendChild(messageElem);

    // Only track agent message IDs for appending in same turn
    if (!isUserMessage) {
      currentMessageId = messageId;
    }

    // Scroll to the bottom
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
  }
}

// WebSocket handlers
function connectWebsocket() {
  // Build the websocket URL for the current mode
  const wsUrl = "ws://" + window.location.host + "/ws/" + sessionId + "?is_audio=" + is_audio;
  
  console.log(`🔄 Connecting WebSocket: ${wsUrl}`);

  // If there's already a websocket open/connecting for the same URL, do nothing
  if (
    websocket &&
    (websocket.readyState === WebSocket.OPEN || websocket.readyState === WebSocket.CONNECTING) &&
    currentWsUrl === wsUrl
  ) {
    console.log(`ℹ️ WebSocket already connected to same URL, skipping reconnect`);
    return;
  }

  // If an existing websocket is open/connecting for a different URL (mode change), close it first
  if (websocket && (websocket.readyState === WebSocket.OPEN || websocket.readyState === WebSocket.CONNECTING)) {
    console.log(`⚠️ Closing existing WebSocket connection to switch modes`);
    websocket.close();
  }

  // Connect websocket
  console.log(`🔌 Creating new WebSocket connection`);
  websocket = new WebSocket(wsUrl);
  currentWsUrl = wsUrl;

  // Handle connection open
  websocket.onopen = function () {
    console.log("✅ Connected to server");
    connectionStatus.textContent = "Connected";
    statusDot.classList.add("connected");

    // Enable the Send button
    document.getElementById("sendButton").disabled = false;
    addSubmitHandler();
  };

  // Handle incoming messages
  websocket.onmessage = function (event) {
    // Parse the incoming message
    const message_from_server = JSON.parse(event.data);
    
    // NEVER buffer turn_complete or complete messages - always process immediately
    // Only buffer partial USER input while muted
    const isUserMessage = message_from_server.role === "user" && message_from_server.mime_type === "text/plain";
    const isTurnComplete = message_from_server.turn_complete;
    const isComplete = message_from_server.complete; // Check if message is marked complete
    
    if (is_audio && isMuted && isUserMessage && !isTurnComplete && !isComplete) {
      // Buffer ONLY partial user input while still speaking and not complete
      pendingMessages.push(message_from_server);
      return; // Don't display user input until unmuted or turn ends
    }
    
    // Log only actions, not every message
    if (message_from_server.mime_type === "text/plain" && message_from_server.role === "user") {
      console.log(`✅ USER INPUT: "${message_from_server.data}"`);
    } else if (message_from_server.turn_complete) {
      console.log(`✅ TURN COMPLETE`);
    }

    // Process the message
    processMessage(message_from_server);
    
    // If turn_complete, also flush any pending buffered messages
    if (isTurnComplete && is_audio && isMuted && pendingMessages.length > 0) {
      console.log(`🔄 Turn complete - processing ${pendingMessages.length} buffered messages while still muted`);
      const bufferedMessages = [...pendingMessages];
      pendingMessages = []; // Clear buffer
      bufferedMessages.forEach(msg => processMessage(msg));
    }
  };

  // Handle connection close
  websocket.onclose = function (event) {
    console.log(`⚠️ Disconnected from server (code: ${event.code}, reason: ${event.reason})`);
    document.getElementById("sendButton").disabled = true;
    connectionStatus.textContent = "Disconnected.";
    statusDot.classList.remove("connected");
    typingIndicator.style.display = "none";
    listeningIndicator.style.display = "none";

    // Exponential backoff for reconnects
    reconnectAttempts += 1;
    if (reconnectAttempts > MAX_RECONNECT_ATTEMPTS) {
      connectionStatus.textContent = "Connection failed. Check server logs.";
      console.warn("Max reconnect attempts reached.");
      return;
    }

    const backoff = RECONNECT_BASE_MS * Math.pow(2, reconnectAttempts - 1);
    setTimeout(function () {
      connectWebsocket();
    }, backoff);
  };

  websocket.onerror = function (e) {
    console.log("❌ Connection error");
    connectionStatus.textContent = "Connection error - retrying...";
    statusDot.classList.remove("connected");
    typingIndicator.style.display = "none";
    listeningIndicator.style.display = "none";
    
    // Add error message to chat
    const errorMsg = document.createElement("p");
    errorMsg.textContent = "Connection error. Attempting to reconnect...";
    errorMsg.className = "system-message";
    errorMsg.style.color = "#EA4335";
    errorMsg.style.fontSize = "12px";
    messagesDiv.appendChild(errorMsg);
  };
}
connectWebsocket();

// Add submit handler to the form
function addSubmitHandler() {
  messageForm.onsubmit = function (e) {
    e.preventDefault();
    const message = messageInput.value;
    if (message) {
      const p = document.createElement("p");
      p.textContent = message;
      p.className = "user-message";
      messagesDiv.appendChild(p);
      messageInput.value = "";

      // Show typing indicator after sending message
      typingIndicator.classList.add("visible");

      sendMessage({
        mime_type: "text/plain",
        data: message,
        role: "user",
      });
      // Scroll down to the bottom of the messagesDiv
      messagesDiv.scrollTop = messagesDiv.scrollHeight;
    }
    return false;
  };
}

// Send a message to the server as a JSON string
function sendMessage(message) {
  if (websocket && websocket.readyState == WebSocket.OPEN) {
    const messageJson = JSON.stringify(message);
    websocket.send(messageJson);
  }
}

// Decode Base64 data to Array
function base64ToArray(base64) {
  const binaryString = window.atob(base64);
  const len = binaryString.length;
  const bytes = new Uint8Array(len);
  for (let i = 0; i < len; i++) {
    bytes[i] = binaryString.charCodeAt(i);
  }
  return bytes.buffer;
}

/**
 * Audio handling
 */

let audioPlayerNode;
let audioPlayerContext;
let audioRecorderNode;
let audioRecorderContext;
let micStream;
let isRecording = false;

// Import the audio worklets
import { startAudioPlayerWorklet } from "./audio-player.js";
import { startAudioRecorderWorklet } from "./audio-recorder.js";

// Start audio
function startAudio() {
  // Show listening indicator
  if (listeningIndicator) {
    listeningIndicator.style.display = "block";
  }
  
  // Start audio output
  startAudioPlayerWorklet().then(([node, ctx]) => {
    audioPlayerNode = node;
    audioPlayerContext = ctx;
  });
  // Start audio input
  startAudioRecorderWorklet(audioRecorderHandler).then(
    ([node, ctx, stream]) => {
      audioRecorderNode = node;
      audioRecorderContext = ctx;
      micStream = stream;
      isRecording = true;
    }
  );
}

// Stop audio recording
function stopAudio() {
  // Hide listening indicator
  if (listeningIndicator) {
    listeningIndicator.style.display = "none";
  }
  
  if (audioRecorderNode) {
    audioRecorderNode.disconnect();
    audioRecorderNode = null;
  }

  if (audioRecorderContext) {
    audioRecorderContext
      .close()
      .catch((err) => console.error("Error closing audio context:", err));
    audioRecorderContext = null;
  }

  if (micStream) {
    micStream.getTracks().forEach((track) => track.stop());
    micStream = null;
  }

  isRecording = false;
}

// Start the audio only when the user clicked the button
// (due to the gesture requirement for the Web Audio API)
startAudioButton.addEventListener("click", () => {
  startAudioButton.disabled = true;
  startAudioButton.textContent = "🎤 Voice Enabled";
  startAudioButton.style.display = "none";
  stopAudioButton.style.display = "inline-block";
  stopAudioButton.textContent = "🛑 Stop Voice";
  voiceControls.style.display = "flex";
  recordingContainer.style.display = "flex";
  
  // Add visual feedback
  messagesDiv.style.borderTop = "3px solid var(--secondary-color)";
  
  startAudio();
  is_audio = true;
  isMuted = true; // Start muted - user must click unmute to speak
  updateMuteState();

  // Add class to messages container to enable audio styling
  messagesDiv.classList.add("audio-enabled");

  connectWebsocket(); // reconnect with the audio mode
});

// Unmute (start recording)
unmuteButton.addEventListener("click", () => {
  isMuted = false;
  unmuteButton.style.display = "none";
  muteButton.style.display = "inline-block";
  listeningIndicator.style.display = "block"; // Show listening indicator
  
  // Process all buffered messages that arrived while muted
  if (pendingMessages.length > 0) {
    console.log(`🔄 Processing ${pendingMessages.length} buffered messages on unmute`);
    const bufferedMessages = [...pendingMessages];
    pendingMessages = []; // Clear buffer
    
    // Process each buffered message immediately
    bufferedMessages.forEach(msg => {
      processMessage(msg);
    });
  }
});

// Mute (stop recording)
muteButton.addEventListener("click", () => {
  isMuted = true;
  muteButton.style.display = "none";
  unmuteButton.style.display = "inline-block";
});

// Update mute state
function updateMuteState() {
  if (is_audio) {
    if (isMuted) {
      unmuteButton.style.display = "inline-block";
      muteButton.style.display = "none";
    } else {
      unmuteButton.style.display = "none";
      muteButton.style.display = "inline-block";
    }
  }
}

// Stop audio recording when stop button is clicked
stopAudioButton.addEventListener("click", () => {
  stopAudio();
  stopAudioButton.style.display = "none";
  startAudioButton.style.display = "inline-block";
  startAudioButton.disabled = false;
  startAudioButton.textContent = "🎤 Enable Voice";
  voiceControls.style.display = "none";
  recordingContainer.style.display = "none";

  // Remove visual feedback
  messagesDiv.style.borderTop = "none";

  // Remove audio styling class
  messagesDiv.classList.remove("audio-enabled");

  // Reconnect without audio mode
  is_audio = false;

  // Only reconnect if the connection is still open
  if (websocket && websocket.readyState === WebSocket.OPEN) {
    websocket.close();
    // The onclose handler will trigger reconnection
  }
});

// Audio recorder handler
function audioRecorderHandler(pcmData) {
  // Only send data if we're still recording AND not muted
  if (!isRecording) {
    return;
  }
  
  if (isMuted) {
    return;
  }

  // Send the pcm data as base64
  sendMessage({
    mime_type: "audio/pcm",
    data: arrayBufferToBase64(pcmData),
  });

  // Log every few samples to avoid flooding the console
  if (Math.random() < 0.01) {
    // Only log ~1% of audio chunks
  }
}

// Encode an array buffer with Base64
function arrayBufferToBase64(buffer) {
  let binary = "";
  const bytes = new Uint8Array(buffer);
  const len = bytes.byteLength;
  for (let i = 0; i < len; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return window.btoa(binary);
}
