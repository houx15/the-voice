import tkinter as tk
from tkinter import font
import tkinter.ttk as ttk
import threading
import queue
import sounddevice as sd
import numpy as np
import scipy.io.wavfile as wav
import tempfile
import os
import glob
import time
import json
import base64
import requests
import uuid
from pathlib import Path
import google.generativeai as genai
import config

# Import TTS pipeline components
import generate_prayer_audio
from generate_prayer_audio import volc_sign

# =============================
# SETTINGS MANAGEMENT
# =============================

USER_CONFIG_DIR = Path.home() / ".the-voice"
USER_CONFIG_FILE = USER_CONFIG_DIR / "config.json"

def load_user_config():
    """Load user config from JSON and update the config module."""
    if not USER_CONFIG_FILE.exists():
        return False
    
    try:
        with open(USER_CONFIG_FILE, 'r') as f:
            data = json.load(f)
            
        config.VOLC_APP_ID = data.get("VOLC_APP_ID", "")
        config.VOLC_ACCESS_KEY = data.get("VOLC_ACCESS_KEY", "")
        config.VOLC_SECRET_KEY = data.get("VOLC_SECRET_KEY", "")
        config.GEMINI_API_KEY = data.get("GEMINI_API_KEY", "")
        return True
    except Exception as e:
        print(f"Error loading config: {e}")
        return False

def save_user_config(app_id, access_key, secret_key, gemini_key):
    """Save user config to JSON and update the config module."""
    USER_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    
    data = {
        "VOLC_APP_ID": app_id,
        "VOLC_ACCESS_KEY": access_key,
        "VOLC_SECRET_KEY": secret_key,
        "GEMINI_API_KEY": gemini_key
    }
    
    with open(USER_CONFIG_FILE, 'w') as f:
        json.dump(data, f, indent=2)
        
    config.VOLC_APP_ID = app_id
    config.VOLC_ACCESS_KEY = access_key
    config.VOLC_SECRET_KEY = secret_key
    config.GEMINI_API_KEY = gemini_key

class SettingsDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Settings")
        self.geometry("400x350")
        self.configure(bg="#1a1a1a")
        
        self.parent = parent
        self.result = None
        
        style = ttk.Style()
        style.configure("TLabel", background="#1a1a1a", foreground="#cccccc")
        style.configure("TButton", background="#333333", foreground="#333333")
        
        # Volc Engine
        ttk.Label(self, text="Volcano App ID:").pack(pady=(10, 0))
        self.volc_app_id = tk.Entry(self, width=40)
        self.volc_app_id.pack()
        self.volc_app_id.insert(0, getattr(config, 'VOLC_APP_ID', ''))

        ttk.Label(self, text="Volcano Access Key:").pack(pady=(10, 0))
        self.volc_access_key = tk.Entry(self, width=40)
        self.volc_access_key.pack()
        self.volc_access_key.insert(0, getattr(config, 'VOLC_ACCESS_KEY', ''))

        ttk.Label(self, text="Volcano Secret Key:").pack(pady=(10, 0))
        self.volc_secret_key = tk.Entry(self, width=40, show="*")
        self.volc_secret_key.pack()
        self.volc_secret_key.insert(0, getattr(config, 'VOLC_SECRET_KEY', ''))
        
        # Gemini
        ttk.Label(self, text="Gemini API Key:").pack(pady=(20, 0))
        self.gemini_key = tk.Entry(self, width=40, show="*")
        self.gemini_key.pack()
        self.gemini_key.insert(0, getattr(config, 'GEMINI_API_KEY', ''))
        
        # Save Button
        save_btn = tk.Button(self, text="Save", command=self.on_save, bg="#333333", fg="#000000")
        save_btn.pack(pady=20)
        
    def on_save(self):
        save_user_config(
            self.volc_app_id.get().strip(),
            self.volc_access_key.get().strip(),
            self.volc_secret_key.get().strip(),
            self.gemini_key.get().strip()
        )
        self.destroy()

# =============================
# CONFIGURATION
# =============================

SAMPLE_RATE = 16000 # Volcano ASR often prefers 16k
CHANNELS = 1
TMP_DIR = Path("output/tmp")
TMP_DIR.mkdir(parents=True, exist_ok=True)

# =============================
# BACKEND: ASR
# =============================

def recognize_speech_volc(audio_path):
    """
    Sends audio to Volcano Engine ASR (HTTP One-Sentence Recognition).
    """
    if not hasattr(config, 'VOLC_ASR_URL'):
        print("⚠ VOLC_ASR_URL not found in config.")
        return None

    # Read audio and encode to base64
    with open(audio_path, "rb") as f:
        audio_data = f.read()
    b64_audio = base64.b64encode(audio_data).decode("utf-8")
    
    req_id = str(uuid.uuid4())
    cluster = getattr(config, 'VOLC_ASR_CLUSTER', 'volcengine_input_common')
    
    payload = {
        "app": {
            "appid": config.VOLC_APP_ID,
            "token": config.VOLC_ACCESS_KEY,
            "cluster": cluster
        },
        "user": {
            "uid": "prayer-room-user"
        },
        "audio": {
            "format": "wav",
            "rate": 16000,
            "bits": 16,
            "channel": 1,
            "language": "en-US",
        },
        "request": {
            "reqid": req_id,
            "workflow": "audio_in,resample,partition,vad,fe,decode,itn,nlu_punctuate",
            "sequence": 1,
            "nbest": 1,
            "format": "wav",
            "command": "query"
        }
    }
    
    # Volcano ASR HTTP body is often just the audio for raw, 
    # OR a JSON wrapper. The docs vary. 
    # Using the standardized JSON submission if supported, or header-based.
    # Let's try the JSON method similar to TTS which is often supported for unified gateways.
    # HOWEVER, standard Volc ASR often puts audio in the body and metadata in headers.
    # Let's try the common JSON-body approach for "Full-link" API if available.
    
    # Actually, simpler approach for Volcano ASR:
    # Use the `volcengine` python SDK structure manually.
    # The payload above is for the websocket/json gateway.
    # Let's stick to the JSON payload with "data" field if we want to mimic TTS style:
    
    payload_full = payload.copy()
    payload_full["data"] = b64_audio
    
    body = json.dumps(payload_full, ensure_ascii=False)
    signature = volc_sign(body, config.VOLC_SECRET_KEY)
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"HMAC-SHA256 {signature}"
    }
    
    try:
        resp = requests.post(
            config.VOLC_ASR_URL, 
            headers=headers, 
            data=body.encode("utf-8"), 
            timeout=10
        )
        resp.raise_for_status()
        
        # Parse response
        # Expected: { "result": [{ "text": "..." }], ... }
        data = resp.json()
        if "result" in data and len(data["result"]) > 0:
            return data["result"][0]["text"]
        
        # Fallback check
        if "message" in data and data["message"] == "Success":
             # Sometimes structure differs
             pass
             
        print(f"ASR Raw Response: {data}")
        return None

    except Exception as e:
        print(f"ASR Error: {e}")
        return None


# =============================
# BACKEND: WORKER
# =============================

class AudioHandler:
    def __init__(self):
        self.recording = False
        self.audio_data = []
        self.stream = None
        self.start_time = 0

    def start_recording(self):
        if self.recording:
            return
        self.recording = True
        self.audio_data = []
        self.start_time = time.time()
        
        def callback(indata, frames, time, status):
            if self.recording:
                self.audio_data.append(indata.copy())

        self.stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS, callback=callback)
        self.stream.start()

    def stop_recording(self):
        if not self.recording:
            return None
        self.recording = False
        self.stream.stop()
        self.stream.close()
        
        if not self.audio_data:
            return None
            
        audio_concatenated = np.concatenate(self.audio_data, axis=0)
        
        duration = time.time() - self.start_time
        if duration < 0.5:
            return None
            
        filename = TMP_DIR / f"input_{int(time.time())}.wav"
        # Save as 16-bit PCM WAV
        wav.write(str(filename), SAMPLE_RATE, (audio_concatenated * 32767).astype(np.int16))
        return filename

def process_interaction(audio_path, update_status_callback, on_complete_callback):
    try:
        if not audio_path:
            update_status_callback("I didn't hear anything.")
            time.sleep(1.5)
            on_complete_callback()
            return

        # 1. ASR (Volcano)
        update_status_callback("Listening...")
        
        # Check config
        if not hasattr(config, 'VOLC_APP_ID'):
            update_status_callback("Config Error: Missing VOLC keys.")
            time.sleep(2)
            on_complete_callback()
            return

        user_text = recognize_speech_volc(audio_path)
        
        if not user_text:
            update_status_callback("Could not hear clearly.")
            time.sleep(1.5)
            on_complete_callback()
            return

        print(f"USER SAID: {user_text}")

        # 2. LLM (Gemini 3.0 Pro)
        update_status_callback("Reflecting...")
        
        if not hasattr(config, 'GEMINI_API_KEY') or not config.GEMINI_API_KEY:
            update_status_callback("Config Error: Missing GEMINI_API_KEY.")
            time.sleep(2)
            on_complete_callback()
            return

        genai.configure(api_key=config.GEMINI_API_KEY)
        # Using Gemini 3.0 Pro as requested
        model = genai.GenerativeModel('gemini-3.0-pro')

        prompt = (
            "You are a theological narrator inspired by the moral tone of the Christian Gospels. "
            "You are not God or Jesus. You speak calmly and slowly. "
            "You do not give commands, predictions, or absolution. "
            "You invite reflection and moral attention. "
            "You respect silence and do not try to conclude everything. "
            "\n\n"
            "The user said:\n"
            f'"{user_text}"\n\n'
            "Respond with a pastoral, reflective message. "
            "Use short sentences, simple vocabulary, and metaphor over explanation. "
            "Keep the response roughly 60-100 words (20-40 seconds spoken). "
            "Return ONLY the spoken text."
        )

        response = model.generate_content(prompt)
        gospel_response = response.text.strip()
        print(f"RESPONSE: {gospel_response}")

        # 3. TTS & Audio Gen (Volcano + Post-proc)
        update_status_callback("Preparing voice...")
        output_path = generate_prayer_audio.generate_prayer_audio(gospel_response)
        
        # 4. Playback
        update_status_callback("...")
        import subprocess
        subprocess.run(["afplay", str(output_path)])

    except Exception as e:
        print(f"Process Error: {e}")
        update_status_callback("Something went wrong.")
        time.sleep(2)
    finally:
        on_complete_callback()

# =============================
# GUI
# =============================

class PrayerRoomApp:
    def __init__(self, root):
        self.root = root
        self.root.title("The Voice")
        self.root.geometry("600x400")
        self.root.configure(bg="#1a1a1a")

        # Center window
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()
        x_c = int((screen_width/2) - (600/2))
        y_c = int((screen_height/2) - (400/2))
        self.root.geometry(f"600x400+{x_c}+{y_c}")

        self.status_font = font.Font(family="Georgia", size=18)
        self.label = tk.Label(
            root, 
            text="Press SPACE to speak.", 
            font=self.status_font, 
            bg="#1a1a1a", 
            fg="#cccccc",
            wraplength=500
        )
        self.label.pack(expand=True)

        self.audio_handler = AudioHandler()
        self.processing = False
        self.space_pressed = False

        self.root.bind('<KeyPress-space>', self.on_space_down)
        self.root.bind('<KeyRelease-space>', self.on_space_up)

        # IR Selector
        self.setup_ir_selector()

        # Load user config
        load_user_config()
        self.check_config()

    def check_config(self):
        # Check if keys are present
        missing_keys = not (config.VOLC_APP_ID and config.VOLC_ACCESS_KEY and config.VOLC_SECRET_KEY and config.GEMINI_API_KEY)
        if missing_keys:
            self.update_status("Please configure API keys.")
            self.root.after(500, self.open_settings)

    def open_settings(self):
        dlg = SettingsDialog(self.root)
        self.root.wait_window(dlg)
        self.update_status("Press SPACE to speak.")

    def setup_ir_selector(self):
        self.ir_frame = tk.Frame(self.root, bg="#1a1a1a")
        self.ir_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=20, pady=20)
        
        # Settings Button
        tk.Button(self.ir_frame, text="⚙", command=self.open_settings, bg="#333333", fg="#000000", width=3).pack(side=tk.RIGHT, padx=5)

        tk.Label(self.ir_frame, text="Reverb:", bg="#1a1a1a", fg="#888888").pack(side=tk.LEFT)
        
        # Find IR files
        self.ir_files = sorted(glob.glob("ir/**/*.wav", recursive=True))
        # Filter out likely non-IR files (e.g. examples)
        self.ir_files = [f for f in self.ir_files if "examples" not in f.lower()]
        
        # Make paths relative for display
        self.ir_options = [os.path.relpath(f) for f in self.ir_files]
        
        self.selected_ir = tk.StringVar()
        
        if self.ir_options:
            # Default to one if available
            default_ir = self.ir_options[0]
            # Try to find a nice default (e.g. 1st baptist or chapel)
            for opt in self.ir_options:
                if "1st_baptist" in opt and "balcony" in opt:
                    default_ir = opt
                    break
            
            self.selected_ir.set(default_ir)
            config.AUDIO_PROFILE["impulse_response"] = default_ir
        
        style = ttk.Style()
        style.theme_use('default')
        style.configure("TCombobox", fieldbackground="#333333", background="#333333", foreground="#cccccc", arrowcolor="#cccccc")
        
        self.ir_combo = ttk.Combobox(self.ir_frame, textvariable=self.selected_ir, values=self.ir_options, state="readonly", width=50)
        self.ir_combo.pack(side=tk.LEFT, padx=10)
        self.ir_combo.bind("<<ComboboxSelected>>", self.on_ir_change)

    def on_ir_change(self, event):
        path = self.selected_ir.get()
        print(f"Selected IR: {path}")
        config.AUDIO_PROFILE["impulse_response"] = path

    def update_status(self, text):
        self.label.config(text=text)
        self.root.update_idletasks()

    def on_complete(self):
        self.processing = False
        self.update_status("Press SPACE to speak.")

    def on_space_down(self, event):
        if self.processing or self.space_pressed:
            return
        self.space_pressed = True
        self.update_status("Listening...")
        self.audio_handler.start_recording()

    def on_space_up(self, event):
        if not self.space_pressed:
            return
        self.space_pressed = False
        
        if self.processing:
            return

        self.update_status("...")
        wav_path = self.audio_handler.stop_recording()
        
        self.processing = True
        t = threading.Thread(
            target=process_interaction, 
            args=(wav_path, self.update_status, self.on_complete)
        )
        t.start()

if __name__ == "__main__":
    root = tk.Tk()
    app = PrayerRoomApp(root)
    root.mainloop()