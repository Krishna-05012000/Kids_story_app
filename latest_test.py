import websocket
import json
import base64
import threading
import pyaudio
import time
import streamlit as st
from collections import deque

# Constants
API_KEY = "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"
URL = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01"

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "OpenAI-Beta": "realtime=v1",
}

# List of sentences for the user to read
sentences = [
    "Once upon a time there was a little dragon.",
    "The sun was shining brightly over the mountains.",
    "A young boy was playing with his toy car in the garden.",
    "The little dragon flew down to the garden and saw the boy.",
    "The boy looked up and smiled at the friendly dragon.",
    "The dragon asked if the boy wanted to go on a magical adventure.",
    "The boy nodded excitedly and climbed onto the dragon's back.",
    "They flew high into the sky, above the mountains and clouds.",
    "The dragon showed the boy a secret valley filled with colorful flowers.",
    "In the valley, they met talking animals and danced under a rainbow."
]


# Initialize session state for current sentence index and sentence queue
if 'current_sentence_index' not in st.session_state:
    st.session_state.current_sentence_index = 0

if 'sentence_queue' not in st.session_state:
    st.session_state.sentence_queue = deque(sentences[st.session_state.current_sentence_index].rstrip('.').lower().split())

# Function to reset the sentence queue based on the current sentence index
def reset_sentence_queue():
    current_sentence = sentences[st.session_state.current_sentence_index]
    st.session_state.sentence_queue = deque(current_sentence.rstrip('.').lower().split())

# Reset the queue if the index has changed
reset_sentence_queue()

p = pyaudio.PyAudio()
if p.get_device_count() == 0:
    print("No input devices available")
else:
    stream = p.open(format=pyaudio.paInt16, channels=1, rate=24000, input=True, frames_per_buffer=1024)

session_updated = False  # Track session state
ws = None  # Global WebSocket reference to avoid scope issues

# Streamlit session state
if 'highlighted_text' not in st.session_state:
    st.session_state.highlighted_text = sentences[st.session_state.current_sentence_index]

# Placeholder for real-time updating
highlight_placeholder = st.empty()

# --- Update Session ---
def update_session(ws, instructions, enable_transcription=True):
    """Update session with new instructions and optionally enable/disable transcription."""
    session_event = {
        "event_id": "session_001",
        "type": "session.update",
        "session": {
            "instructions": instructions,
            "input_audio_transcription": {"model": "whisper-1"} if enable_transcription else None,
            "turn_detection": {
                "type": "server_vad",
                "threshold": 0.5,
                "prefix_padding_ms": 300,
                "silence_duration_ms": 200
            },
            "input_audio_format": "pcm16",
            "output_audio_format": "pcm16",
        }
    }
    print(f"Updating session: {instructions}")
    ws.send(json.dumps(session_event))

# --- Send Audio ---
def send_audio(ws):
    """Continuously send audio data for transcription."""
    if not session_updated:
        st.write("Waiting for session update...")
        return

    st.write("Starting audio stream...")
    while True:
        try:
            audio_data = stream.read(1024)
            encoded_audio = base64.b64encode(audio_data).decode('utf-8')
            ws.send(json.dumps({"type": "input_audio_buffer.append", "audio": encoded_audio}))
        except websocket.WebSocketConnectionClosedException:
            st.write("WebSocket closed. Stopping audio stream.")
            break
        except Exception as e:
            st.write(f"Error while sending audio: {e}")
            break

# --- Handle WebSocket Messages ---
def on_message(ws, message):
    """Handle incoming WebSocket messages."""
    global session_updated

    data = json.loads(message)
    message_type = data.get('type')

    if message_type == 'session.updated':
        session_updated = True
        st.write("Session updated successfully.")
        threading.Thread(target=send_audio, args=(ws,)).start()

    elif message_type == 'conversation.item.input_audio_transcription.completed':
        transcript = data.get('transcript', '').strip()
        process_transcript(transcript)

    elif message_type == 'conversation.item.input_audio_transcription.failed':
        st.write(f"Error received: {json.dumps(data, indent=2)}")

    elif message_type == 'error':
        st.write(f"Error received: {json.dumps(data, indent=2)}")

def process_transcript(transcript):
    """Process the transcript to match words."""
    global ws

    # Split transcript into individual words
    spoken_words = transcript.lower().replace(",", "").replace(".", "").split()

    # Match spoken words with the queue in order
    for word in spoken_words:
        if st.session_state.sentence_queue and word == st.session_state.sentence_queue[0]:
            st.session_state.sentence_queue.popleft()  # Remove matched word from the queue

    # Update the highlighted text after processing
    update_highlighted_text()

    # Check if the sentence is fully spoken
    if not st.session_state.sentence_queue:
        st.write("\nAll words matched! Closing WebSocket connection.")
        ws.close()  # Close WebSocket after sentence is fully read

def update_highlighted_text():
    """Update the highlighted sentence on the UI."""
    highlighted_text = ""
    remaining_words = list(st.session_state.sentence_queue)
    spoken_count = len(sentences[st.session_state.current_sentence_index].split()) - len(remaining_words)

    # Build the highlighted sentence dynamically
    words = sentences[st.session_state.current_sentence_index].split()
    for i, word in enumerate(words):
        if i < spoken_count:
            highlighted_text += f"<span style='color:green'><strong>{word.upper()}</strong></span> "
        else:
            highlighted_text += f"{word} "

    # Display the highlighted text
    highlight_placeholder.markdown(highlighted_text, unsafe_allow_html=True)

def load_next_sentence():
    """Load the next sentence into the queue."""
    # Increment the current sentence index
    st.session_state.current_sentence_index += 1
    
    # Reset the sentence queue for the new sentence
    reset_sentence_queue()
    
    # Update the highlighted text to the new sentence
    st.session_state.highlighted_text = sentences[st.session_state.current_sentence_index]
    update_highlighted_text()

# --- WebSocket Events ---
def on_open(ws):
    """Handle WebSocket opening."""
    st.write("WebSocket connection opened.")
    # Start the transcription session with the initial instruction
    update_session(ws, "You are a storytelling assistant for Indian kids. You only know English.")

def on_error(ws, error):
    """Handle WebSocket errors."""
    st.write(f"WebSocket Error: {error}")

def on_close(ws, close_status_code, close_msg):
    """Handle WebSocket closure and clean up."""
    st.write(f"WebSocket closed with code {close_status_code}. Reason: {close_msg}")

# --- Start WebSocket Client ---
def start_websocket():
    """Initialize and start the WebSocket connection."""
    global ws
    ws = websocket.WebSocketApp(
        URL,
        header=[f"{key}: {value}" for key, value in HEADERS.items()],
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close
    )
    ws.run_forever()

# --- Streamlit UI Setup ---
st.title("Kids' Storytelling App")
st.subheader("Read the sentence below and watch it highlight word by word:")

# Display the target sentence
st.write(f"Target Sentence: {sentences[st.session_state.current_sentence_index]}")
highlight_placeholder.markdown(st.session_state.highlighted_text, unsafe_allow_html=True)

# Button to start WebSocket
if st.button("Start Listening", key="start_listening"):
    start_websocket()

# Button to load the next sentence after finishing
if st.session_state.current_sentence_index < len(sentences) - 1:
    if st.button("Next Sentence", key=f"next_sentence_{st.session_state.current_sentence_index}"):
        load_next_sentence()
