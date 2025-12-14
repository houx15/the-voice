import uuid
import json
import base64
import hashlib
import hmac
import requests
import subprocess
import os
import sys
from pathlib import Path

from pydub import AudioSegment
import google.generativeai as genai
import config


# =============================
# DIRECTORIES
# =============================

OUTPUT_DIR = Path("output")
TMP_DIR = OUTPUT_DIR / "tmp"
OUTPUT_DIR.mkdir(exist_ok=True)
TMP_DIR.mkdir(exist_ok=True)

# =============================
# FFMPEG SETUP
# =============================

def get_ffmpeg_path():
    """Locate ffmpeg executable, handling PyInstaller temporary paths."""
    if getattr(sys, 'frozen', False):
        # Running in a PyInstaller bundle
        base_path = sys._MEIPASS
        ffmpeg_path = os.path.join(base_path, "ffmpeg")
        if os.path.exists(ffmpeg_path):
            return ffmpeg_path
        
        # Check inside a bin folder if packaged that way
        ffmpeg_path = os.path.join(base_path, "bin", "ffmpeg")
        if os.path.exists(ffmpeg_path):
            return ffmpeg_path
            
    # Check current directory or system path
    return "ffmpeg"

FFMPEG_BIN = get_ffmpeg_path()
AudioSegment.converter = FFMPEG_BIN

# =============================
# VOLC SIGNATURE
# =============================


def volc_sign(body: str, secret: str) -> str:
    return hmac.new(
        secret.encode("utf-8"), body.encode("utf-8"), hashlib.sha256
    ).hexdigest()


# =============================
# STEP 0: GEMINI GENERATION
# =============================


def generate_gospel_text(user_input: str) -> str:
    print("▶ Generating Gospel response with Gemini...")
    if not hasattr(config, 'GEMINI_API_KEY') or not config.GEMINI_API_KEY:
        print("⚠ GEMINI_API_KEY missing in config. Using input as-is.")
        return user_input

    try:
        genai.configure(api_key=config.GEMINI_API_KEY)
        # Using gemini-1.5-flash as a balanced option
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        prompt = (
            "You are a wise, comforting, and solemn religious figure. "
            f"The user says: \"{user_input}\"\n"
            "Please rewrite or respond to this text in a gospel-like, prayerful, and resonant style. "
            "Keep it relatively short (2-4 sentences) and suitable for reading aloud slowly. "
            "Do not add markdown formatting like **bold** or *italics*. "
            "Return only the text to be spoken."
        )

        response = model.generate_content(prompt)
        if response.text:
            return response.text.strip()
    except Exception as e:
        print(f"⚠ Gemini API Error: {e}")
    
    return user_input


# =============================
# STEP 1: VOLCANO TTS
# =============================


def generate_volc_tts(text: str, out_path: Path):
    req_id = str(uuid.uuid4())

    payload = {
        "app": {
            "appid": config.VOLC_APP_ID,
            "token": config.VOLC_ACCESS_KEY,
            "cluster": "volcano_tts",
        },
        "user": {"uid": "prayer-room-demo"},
        "audio": {
            "voice_type": config.VOICE_NAME,
            "encoding": "mp3",
            "speed_ratio": config.AUDIO_PROFILE["speed_ratio"],
            "pitch_ratio": config.AUDIO_PROFILE["pitch_ratio"],
            "volume_ratio": config.AUDIO_PROFILE["volume_ratio"],
        },
        "request": {
            "reqid": req_id,
            "text": text,
            "text_type": "ssml" if text.strip().startswith("<speak>") else "plain",
            "operation": "query",
        },
    }

    body = json.dumps(payload, ensure_ascii=False)
    signature = volc_sign(body, config.VOLC_SECRET_KEY)

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"HMAC-SHA256 {signature}",
    }

    resp = requests.post(
        config.VOLC_TTS_URL, headers=headers, data=body.encode("utf-8"), timeout=30
    )
    resp.raise_for_status()

    data = resp.json()
    if "data" not in data:
        raise RuntimeError(f"TTS failed: {data}")

    audio_bytes = base64.b64decode(data["data"])
    with open(out_path, "wb") as f:
        f.write(audio_bytes)


# =============================
# STEP 2: SILENCE PADDING
# =============================


def add_silence(input_audio: Path, output_audio: Path):
    audio = AudioSegment.from_file(input_audio)
    silence_pre = AudioSegment.silent(
        duration=config.AUDIO_PROFILE["prepend_silence_ms"]
    )
    silence_post = AudioSegment.silent(
        duration=config.AUDIO_PROFILE["append_silence_ms"]
    )
    final = silence_pre + audio + silence_post
    final.export(output_audio, format="mp3")


# =============================
# STEP 3: POST-PROCESSING
# =============================


def post_process(input_audio: Path, output_audio: Path):
    filters = [
        "highshelf=f=6000:g=-2",
        "lowpass=f=12000",
    ]

    if (
        config.AUDIO_PROFILE["use_reverb"]
        and Path(config.AUDIO_PROFILE["impulse_response"]).exists()
    ):
        filters.append(f"afir={config.AUDIO_PROFILE['impulse_response']}")

    filters.append(
        f"loudnorm=I={config.AUDIO_PROFILE['loudness_target']}:"
        f"LRA=7:TP={config.AUDIO_PROFILE['true_peak']}"
    )

    cmd = [
        FFMPEG_BIN,
        "-y",
        "-i",
        str(input_audio),
        "-af",
        ",".join(filters),
        "-codec:a",
        "libmp3lame",
        "-b:a",
        "128k",
        str(output_audio),
    ]

    subprocess.run(cmd, check=True)


# =============================
# MAIN PIPELINE
# =============================


def generate_prayer_audio(text: str) -> Path:
    uid = uuid.uuid4().hex

    raw_audio = TMP_DIR / f"{uid}_raw.mp3"
    padded_audio = TMP_DIR / f"{uid}_padded.mp3"
    final_audio = OUTPUT_DIR / f"{uid}_prayer.mp3"

    print("▶ Volcano TTS...")
    generate_volc_tts(text, raw_audio)

    print("▶ Adding silence...")
    add_silence(raw_audio, padded_audio)

    print("▶ Post-processing...")
    post_process(padded_audio, final_audio)

    print(f"✔ Done: {final_audio}")
    return final_audio


def run_interactive_mode():
    print("Welcome to the Gospel Prayer Generator.")
    print("Enter your text below (or 'q' to quit):")
    
    while True:
        try:
            user_input = input("\n> ")
            if user_input.lower() in ('q', 'quit', 'exit'):
                break
            if not user_input.strip():
                continue
            
            # Step 1: Gemini
            gospel_text = generate_gospel_text(user_input)
            print(f"\nGenerated Gospel Text:\n---\n{gospel_text}\n---")
            
            # Step 2: Audio Generation
            generate_prayer_audio(gospel_text)
            
        except KeyboardInterrupt:
            print("\nGoodbye.")
            break
        except Exception as e:
            print(f"Error: {e}")


# =============================
# ENTRY POINT
# =============================

if __name__ == "__main__":
    if len(sys.argv) > 1:
        # If arguments provided, treat as direct text input for testing
        input_text = " ".join(sys.argv[1:])
        generate_prayer_audio(input_text)
    else:
        # Interactive mode
        run_interactive_mode()