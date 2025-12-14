# The Voice - Reflective AI Narrator

"The Voice" is a macOS application that allows users to interact with an AI narrator designed to provide pastoral, reflective messages inspired by Christian Gospels. It leverages Volcano Engine for Speech-to-Text (ASR) and Text-to-Speech (TTS), and Google Gemini Pro for theological reflection. The application features real-time audio input, AI processing, and a customizable audio output with impulse responses (reverb) to create an immersive experience.

## Features

*   **Real-time Interaction:** Speak into your microphone and receive a reflective response.
*   **AI-powered Reflection:** Uses Google Gemini Pro to generate gospel-like, prayerful messages.
*   **High-Quality Audio:** Employs Volcano Engine for accurate Speech-to-Text and natural-sounding Text-to-Speech.
*   **Customizable Acoustics:** Apply various impulse responses (IRs) from the `ir/` directory to simulate different acoustic environments (e.g., church, chapel).
*   **Easy API Key Management:** A built-in settings dialog allows you to enter and save your API keys securely.
*   **macOS Standalone Application:** Easily package and distribute as a `.app` bundle and `.dmg` installer.

## Prerequisites

Before you begin, ensure you have the following installed:

*   **Python 3.8+**: Download from [python.org](https://www.python.org/downloads/).
*   **`pip`**: Python package installer (usually comes with Python).
*   **`ffmpeg`**: Required for audio processing by `pydub`.
    *   On macOS, install via Homebrew: `brew install ffmpeg`
*   **API Keys**:
    *   **Google Gemini API Key**: Obtain from the [Google AI Studio](https://aistudio.google.com/).
    *   **Volcano Engine API Keys (App ID, Access Key, Secret Key)**: Obtain from the [Volcano Engine Console](https://console.volcengine.com/).

## Installation and Setup

1.  **Clone the Repository:**
    ```bash
    git clone [your-repo-url]
    cd the-voice
    ```

2.  **Create a Virtual Environment (Recommended):**
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    ```

3.  **Install Python Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Initial Configuration (API Keys):**
    When you run the application for the first time, it will prompt you to enter your API keys. These keys will be securely saved in `~/.the-voice/config.json` for future use.

    *   **Google Gemini API Key**
    *   **Volcano Engine App ID**
    *   **Volcano Engine Access Key**
    *   **Volcano Engine Secret Key**

    You can also access the settings dialog at any time via the "⚙" button in the application.

## Running the Application

To start "The Voice" application:

1.  **Activate your virtual environment** (if you created one):
    ```bash
    source .venv/bin/activate
    ```
2.  **Run the main GUI script:**
    ```bash
    python main_gui.py
    ```

    The application window will appear. Press and hold the SPACE bar to speak, and release to hear the AI's response.

## Building a Standalone macOS Application (.app) and DMG Installer

For easy distribution to other macOS users, you can build a standalone `.app` bundle and a `.dmg` installer.

1.  **Ensure `create-dmg` is installed (for DMG creation):**
    ```bash
    brew install create-dmg
    ```
    (If you don't install `create-dmg`, the script will still build the `.app` but will skip DMG creation and provide instructions for manual zipping).

2.  **Run the build script:**
    ```bash
    ./build_mac.sh
    ```

    This script will:
    *   Install Python dependencies.
    *   Locate your `ffmpeg` installation.
    *   Use `PyInstaller` to create a `TheVoice.app` bundle in the `dist/` directory. This bundle will include all necessary Python libraries, the `ir/` files, and a bundled `ffmpeg` executable.
    *   If `create-dmg` is installed, it will then create `TheVoice.dmg` in the `dist/` directory.

## Project Structure

*   `main_gui.py`: The main GUI application script.
*   `generate_prayer_audio.py`: Handles Gemini text generation, Volcano TTS, silence padding, and audio post-processing (including impulse responses).
*   `config.py`: Contains default/placeholder configuration values. **Do not put your actual API keys here, use the in-app settings.**
*   `config.example.py`: An example of the configuration structure.
*   `requirements.txt`: Lists all Python dependencies.
*   `ir/`: Directory containing impulse response (reverb) audio files.
*   `build_mac.sh`: Script to build the macOS `.app` and `.dmg`.
*   `.gitignore`: Specifies files and directories to be ignored by Git.

## Troubleshooting

*   **"ffmpeg not found" error during build:** Make sure `ffmpeg` is installed and accessible in your system's PATH. (`brew install ffmpeg`)
*   **Application not starting after packaging:** Check the console for logs. Ensure all `requirements.txt` dependencies are correctly installed.
*   **API Key issues:** Double-check your API keys in the settings dialog. Ensure they are correct and have the necessary permissions.

## License

[Specify your license here, e.g., MIT, Apache 2.0, etc.]
