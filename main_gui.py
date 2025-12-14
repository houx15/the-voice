# ============================================================
# The Voice — ASR (Volc BigModel) + TTS (Volc HTTP) + Text Input
# ============================================================
import os
import tkinter as tk
from tkinter import font
import tkinter.ttk as ttk
import threading
import sounddevice as sd
import numpy as np
import scipy.io.wavfile as wav
import time
import json
import uuid
from pathlib import Path
import struct
import subprocess
import base64
import hashlib
import hmac
import requests

import websocket
import google.generativeai as genai

# ============================================================
# CONFIG MODULE (in-memory)
# ============================================================


class Config:
    pass


config = Config()

# ============================================================
# USER CONFIG (LOCAL)
# ============================================================

USER_CONFIG_DIR = Path.home() / ".the-voice"
USER_CONFIG_FILE = USER_CONFIG_DIR / "config.json"

DEFAULT_ASR_WS_URL = "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_nostream"
DEFAULT_TTS_URL = "https://openspeech.bytedance.com/api/v3/tts/unidirectional"


def load_user_config():
    if not USER_CONFIG_FILE.exists():
        return False
    with open(USER_CONFIG_FILE, "r") as f:
        data = json.load(f)
    for k, v in data.items():
        setattr(config, k, v)
    return True


def save_user_config(data: dict):
    USER_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(USER_CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=2)
    for k, v in data.items():
        setattr(config, k, v)


# ============================================================
# SETTINGS DIALOG
# ============================================================


class SettingsDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Settings")
        self.geometry("520x600")
        self.configure(bg="#1a1a1a")

        style = ttk.Style()
        style.configure("TLabel", background="#1a1a1a", foreground="#cccccc")

        def add(label, key, show=None):
            ttk.Label(self, text=label).pack(anchor="w", padx=20, pady=(10, 0))
            e = tk.Entry(self, width=55, show=show)
            e.pack(padx=20)
            e.insert(0, getattr(config, key, ""))
            return e

        ttk.Label(self, text="— Volcano ASR —", font=("Arial", 10, "bold")).pack(
            anchor="w", padx=20, pady=(15, 0)
        )
        self.asr_app = add("ASR App ID", "VOLC_ASR_APP_ID")
        self.asr_res = add("ASR Resource ID (BigModel)", "VOLC_ASR_RESOURCE_ID")

        ttk.Label(self, text="— Volcano TTS —", font=("Arial", 10, "bold")).pack(
            anchor="w", padx=20, pady=(15, 0)
        )
        self.tts_app = add("TTS App ID", "VOLC_TTS_APP_ID")

        ttk.Label(
            self, text="— Volcano Auth (Shared) —", font=("Arial", 10, "bold")
        ).pack(anchor="w", padx=20, pady=(15, 0))
        self.access = add("Access Key", "VOLC_ACCESS_KEY")
        self.secret = add("Secret Key (TTS only)", "VOLC_SECRET_KEY", show="*")

        ttk.Label(self, text="— LLM —", font=("Arial", 10, "bold")).pack(
            anchor="w", padx=20, pady=(15, 0)
        )
        self.gemini = add("Gemini API Key", "GEMINI_API_KEY", show="*")

        tk.Button(self, text="Save", command=self.save).pack(pady=25)

    def save(self):
        save_user_config(
            {
                "VOLC_ASR_APP_ID": self.asr_app.get().strip(),
                "VOLC_ASR_RESOURCE_ID": self.asr_res.get().strip(),
                "VOLC_TTS_APP_ID": self.tts_app.get().strip(),
                "VOLC_ACCESS_KEY": self.access.get().strip(),
                "VOLC_SECRET_KEY": self.secret.get().strip(),
                "GEMINI_API_KEY": self.gemini.get().strip(),
                "VOLC_ASR_WS_URL": DEFAULT_ASR_WS_URL,
                "VOLC_TTS_URL": DEFAULT_TTS_URL,
            }
        )
        self.destroy()


# ============================================================
# AUDIO CONFIG
# ============================================================

SAMPLE_RATE = 16000
CHANNELS = 1
TMP_DIR = Path("output/tmp")
TMP_DIR.mkdir(parents=True, exist_ok=True)

# ============================================================
# ASR — Volc BigModel Streaming (with partial results)
# ============================================================


def _pack_asr(msg_type, flags, payload, seq=None):
    version = 1
    header_words = 2 if seq is not None else 1
    header = bytes(
        [
            (version << 4) | header_words,
            (msg_type << 4) | flags,
            0x10,
            0,
        ]
    )
    ext = struct.pack(">i", seq) if seq is not None else b""
    return header + ext + struct.pack(">I", len(payload)) + payload


def recognize_speech_volc_ws(wav_path, partial_cb=None):
    ws = websocket.create_connection(
        config.VOLC_ASR_WS_URL,
        header=[
            f"X-Api-App-Key: {config.VOLC_ASR_APP_ID}",
            f"X-Api-Access-Key: {config.VOLC_ACCESS_KEY}",
            f"X-Api-Resource-Id: {config.VOLC_ASR_RESOURCE_ID}",
            f"X-Api-Connect-Id: {uuid.uuid4()}",
        ],
        timeout=10,
    )

    rate, data = wav.read(wav_path)
    if data.ndim == 2:
        data = data[:, 0]
    pcm = data.astype(np.int16).tobytes()

    ws.send_binary(
        _pack_asr(
            1,
            0,
            json.dumps(
                {
                    "audio": {
                        "format": "pcm",
                        "rate": SAMPLE_RATE,
                        "language": "en-US",
                    },
                    "request": {"enable_punc": True},
                }
            ).encode(),
        )
    )

    chunk = int(SAMPLE_RATE * 2 * 0.2)
    seq = 1
    final_text = ""

    for i in range(0, len(pcm), chunk):
        ws.send_binary(_pack_asr(2, 1, pcm[i : i + chunk], seq=seq))
        seq += 1

        ws.settimeout(0.2)
        try:
            msg = ws.recv()
            if isinstance(msg, bytes):
                j = json.loads(msg[8:].decode(errors="ignore"))
                text = j.get("text") or j.get("result", {}).get("text")
                if text:
                    final_text = text
                    if partial_cb:
                        partial_cb(text)
        except:
            pass

        time.sleep(0.2)

    ws.send_binary(_pack_asr(2, 3, b"", seq=-seq))
    time.sleep(0.8)
    ws.close()
    return final_text.strip() if final_text else None


# ============================================================
# TTS — Volc HTTP (HMAC-SHA256)
# ============================================================


def volc_tts_sign(method, path, body, access_key, secret_key, service="tts"):
    from datetime import datetime
    import hashlib
    import hmac

    now = datetime.utcnow()
    x_date = now.strftime("%Y%m%dT%H%M%SZ")
    date = now.strftime("%Y%m%d")

    body_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()

    canonical_request = "\n".join(
        [
            method,
            path,
            "",
            "host:openspeech.bytedance.com\nx-date:" + x_date,
            "",
            "host;x-date",
            body_hash,
        ]
    )

    algorithm = "HMAC-SHA256"
    credential_scope = f"{date}/{service}/request"
    string_to_sign = "\n".join(
        [
            algorithm,
            x_date,
            credential_scope,
            hashlib.sha256(canonical_request.encode()).hexdigest(),
        ]
    )

    def hmac_sha256(key, msg):
        return hmac.new(key, msg.encode(), hashlib.sha256).digest()

    k_date = hmac_sha256(("HMAC-SHA256" + secret_key).encode(), date)
    k_service = hmac_sha256(k_date, service)
    k_signing = hmac_sha256(k_service, "request")

    signature = hmac.new(k_signing, string_to_sign.encode(), hashlib.sha256).hexdigest()

    authorization = (
        f"{algorithm} "
        f"Credential={access_key}/{credential_scope}, "
        f"SignedHeaders=host;x-date, "
        f"Signature={signature}"
    )

    return authorization, x_date


def tts_http_stream(url, headers, params, audio_save_path):
    session = requests.Session()
    try:
        print("请求的url:", url)
        print("请求的headers:", headers)
        print("请求的params:\n", params)
        response = session.post(url, headers=headers, json=params, stream=True)
        print(response)
        # 打印response headers
        print(f"code: {response.status_code} header: {response.headers}")
        logid = response.headers.get("X-Tt-Logid")
        print(f"X-Tt-Logid: {logid}")

        # 用于存储音频数据
        audio_data = bytearray()
        total_audio_size = 0
        for chunk in response.iter_lines(decode_unicode=True):
            if not chunk:
                continue
            data = json.loads(chunk)

            if data.get("code", 0) == 0 and "data" in data and data["data"]:
                chunk_audio = base64.b64decode(data["data"])
                audio_size = len(chunk_audio)
                total_audio_size += audio_size
                audio_data.extend(chunk_audio)
                continue
            if data.get("code", 0) == 0 and "sentence" in data and data["sentence"]:
                print("sentence_data:", data)
                continue
            if data.get("code", 0) == 20000000:
                if "usage" in data:
                    print("usage:", data["usage"])
                break
            if data.get("code", 0) > 0:
                print(f"error response:{data}")
                break

        # 保存音频文件
        if audio_data:
            with open(audio_save_path, "wb") as f:
                f.write(audio_data)
            print(
                f"文件保存在{audio_save_path},文件大小: {len(audio_data) / 1024:.2f} KB"
            )
            # 确保生成的音频有正确的访问权限
            os.chmod(audio_save_path, 0o644)

    except Exception as e:
        print(f"请求失败: {e}")
    finally:
        response.close()
        session.close()


def tts_volc(text: str) -> Path:
    """
    Volcano TTS (Unidirectional)
    Doc: https://www.volcengine.com/docs/6561/1598757
    """

    headers = {
        # === 必须的鉴权 Header（无签名）===
        "X-Api-App-Id": config.VOLC_TTS_APP_ID,
        "X-Api-Access-Key": config.VOLC_ACCESS_KEY,
        "X-Api-Resource-Id": "seed-tts-1.0",  # 例如: seed-tts-2.0
        "X-Api-Request-Id": str(uuid.uuid4()),
        "Content-Type": "application/json",
    }

    body = {
        "req_params": {
            # ===== 文本 =====
            "text": text,
            # ===== 发音人（必须）=====
            # ⚠️ 这个一定要是文档中支持的 speaker
            "speaker": "en_male_sylus_emo_v2_mars_bigtts",
            # "speaker": "en_male_bruce_moon_bigtts",
            # ===== 音频参数（必须）=====
            "audio_params": {"format": "pcm", "sample_rate": 24000, "speech_rate": -20},
            # "additions": {"enable_language_detector": True},
            # ===== 可选：模型版本 =====
            # "model": "seed-tts-1.1",
        },
    }

    audio_save_path = TMP_DIR / f"tts_{int(time.time())}.pcm"
    tts_http_stream(config.VOLC_TTS_URL, headers, body, audio_save_path)

    return audio_save_path


# ============================================================
# AUDIO RECORDING
# ============================================================


class AudioHandler:
    def __init__(self):
        self.data = []
        self.recording = False

    def start(self):
        self.data.clear()
        self.recording = True

        def cb(indata, *_):
            if self.recording:
                self.data.append(indata.copy())

        self.stream = sd.InputStream(
            samplerate=SAMPLE_RATE, channels=CHANNELS, callback=cb
        )
        self.stream.start()

    def stop(self):
        self.recording = False
        self.stream.stop()
        self.stream.close()
        if not self.data:
            return None
        arr = np.concatenate(self.data, axis=0)
        path = TMP_DIR / f"input_{int(time.time())}.wav"
        wav.write(path, SAMPLE_RATE, (arr * 32767).astype(np.int16))
        return path


def postprocess_audio(
    input_pcm: Path,
    ir_path: Path,
    prepend_ms: int = 1000,
    append_ms: int = 1200,
    sample_rate: int = 24000,
):
    """
    Post-process raw PCM TTS audio into a calm, prayer-room style voice.

    Design principles:
    - No loudnorm (preserve natural dynamics)
    - Slower perceived pace
    - Gentle volume lift
    - Space for silence
    - No harshness
    """

    output_audio = input_pcm.parent / f"{uuid.uuid4().hex}_processed.wav"

    filter_graph = (
        # Pause before speaking
        f"adelay={prepend_ms}|{prepend_ms},"
        # Slow down slightly (fine-tuning; main speed should be set at TTS)
        "atempo=0.95,"
        # Reduce sibilance before space
        "deesser=i=0.4,"
        # Convolution reverb (IR as second input)
        "afir,"
        # Silence tail
        f"apad=pad_dur={append_ms / 1000:.2f},"
        # Gentle gain (no normalization)
        "volume=2.0"
    )

    cmd = [
        "ffmpeg",
        "-y",
        # Input 0: raw PCM from TTS
        "-f",
        "s16le",
        "-ar",
        str(sample_rate),
        "-ac",
        "1",
        "-i",
        str(input_pcm),
        # Input 1: mono impulse response
        "-i",
        str(ir_path),
        # Audio processing graph
        "-filter_complex",
        filter_graph,
        # Output WAV (stable for demo)
        str(output_audio),
    ]

    subprocess.run(cmd, check=True)
    return output_audio


# ============================================================
# CORE INTERACTION
# ============================================================


def process_interaction(audio_path, update, done, text_input=None):
    try:
        if text_input:
            user_text = text_input
        else:
            update("Listening…", interim=True)

            def on_partial(t):
                update(t, interim=True)

            user_text = recognize_speech_volc_ws(audio_path, on_partial)

        if not user_text:
            update("Could not hear clearly.")
            time.sleep(1)
            return

        update(user_text)

        genai.configure(api_key=config.GEMINI_API_KEY)
        # Using Gemini 3.0 Pro as requested
        model = genai.GenerativeModel("gemini-3-pro-preview")

        prompt = (
            "You are a theological narrator inspired by the moral tone of the Christian Gospels. "
            "You speak calmly and slowly. Like a priest. If possible, use sentences from the Bible."
            "You do not give commands, predictions, or absolution. "
            "You invite reflection and moral attention. "
            "\n\n"
            "The user said:\n"
            f'"{user_text}"\n\n'
            "Respond with a pastoral, reflective message. "
            "Use short sentences, simple vocabulary, and metaphor over explanation. "
            "Keep the response roughly 60-100 words (20-40 seconds spoken). "
            "Return ONLY the spoken text."
        )

        resp = model.generate_content(prompt)
        spoken = resp.text.strip()
        print("LLM Response:", spoken)
        update("Preparing voice…")
        out = tts_volc(spoken)
        update("Preparing voice…")

        processed = postprocess_audio(
            out,
            ir_path="ir/chapel_mono.wav",
            prepend_ms=900,
            append_ms=900,
        )

        subprocess.run(["afplay", str(processed)])

    finally:
        done()


# ============================================================
# GUI
# ============================================================


class App:
    def __init__(self, root):
        self.root = root
        root.title("The Voice")
        root.geometry("620x440")
        root.configure(bg="#1a1a1a")

        self.font = font.Font(family="Georgia", size=18)
        self.label = tk.Label(
            root,
            text="Press SPACE to speak or type below.",
            font=self.font,
            bg="#1a1a1a",
            fg="#cccccc",
            wraplength=520,
        )
        self.label.pack(expand=True)

        frame = tk.Frame(root, bg="#1a1a1a")
        frame.pack(pady=10)

        self.entry = tk.Entry(frame, width=42, font=("Arial", 14))
        self.entry.pack(side=tk.LEFT, padx=5)
        self.entry.bind("<Return>", lambda e: self.send_text())

        tk.Button(frame, text="Send", command=self.send_text).pack(side=tk.LEFT)

        tk.Button(root, text="⚙ Settings", command=self.open_settings).pack()

        self.audio = AudioHandler()
        self.processing = False
        self.space = False

        root.bind("<KeyPress-space>", self.down)
        root.bind("<KeyRelease-space>", self.up)

        load_user_config()

    def open_settings(self):
        SettingsDialog(self.root)

    def update(self, text, interim=False):
        self.label.config(text=text, fg="#888888" if interim else "#cccccc")
        self.root.update_idletasks()

    def done(self):
        self.processing = False
        self.update("Press SPACE to speak or type below.")

    def send_text(self):
        if self.processing:
            return
        text = self.entry.get().strip()
        if not text:
            return
        self.entry.delete(0, tk.END)
        self.processing = True
        self.update("Thinking…")
        threading.Thread(
            target=process_interaction,
            args=(None, self.update, self.done, text),
            daemon=True,
        ).start()

    def down(self, _):
        if self.processing or self.space:
            return
        if self.root.focus_get() == self.entry:
            return
        self.space = True
        self.audio.start()
        self.update("Listening…", interim=True)

    def up(self, _):
        if not self.space:
            return
        self.space = False
        self.processing = True
        wav_path = self.audio.stop()
        threading.Thread(
            target=process_interaction,
            args=(wav_path, self.update, self.done),
            daemon=True,
        ).start()


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
