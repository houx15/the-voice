# =============================
# Volcano Engine TTS Config
# =============================

VOLC_APP_ID = "your_app_id_here"
VOLC_ACCESS_KEY = "your_access_key_here"
VOLC_SECRET_KEY = "your_secret_key_here"

VOLC_TTS_URL = "https://openspeech.bytedance.com/api/v1/tts"
VOLC_ASR_URL = "https://openspeech.bytedance.com/api/v1/asr"
VOLC_ASR_CLUSTER = "volcengine_input_common"  # or specific cluster id

# =============================
# Gemini Configuration
# =============================

GEMINI_API_KEY = "your_gemini_api_key_here"

# =============================
# Voice Configuration
# =============================

VOICE_NAME = "Sylus"
LANGUAGE = "en_us"

# =============================
# Audio Profile (Prayer Room)
# =============================

AUDIO_PROFILE = {
    # Silence (milliseconds)
    "prepend_silence_ms": 800,
    "append_silence_ms": 900,
    # TTS prosody
    "speed_ratio": 0.9,  # slower than default
    "pitch_ratio": 0.95,  # slightly lower
    "volume_ratio": 1.0,
    # Post-processing
    "use_reverb": True,
    "impulse_response": "ir/chapel_light.wav",
    # Loudness normalization
    "loudness_target": "-16",
    "true_peak": "-1.5",
}
