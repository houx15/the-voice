#!/bin/bash
set -e

APP_NAME="TheVoice"
MAIN_SCRIPT="main_gui.py"

echo "=== Building $APP_NAME for macOS ==="

# 1. Locate ffmpeg
FFMPEG_PATH=$(which ffmpeg)
if [ -z "$FFMPEG_PATH" ]; then
    echo "Error: ffmpeg not found. Please install it (e.g., brew install ffmpeg)."
    exit 1
fi
echo "Found ffmpeg at: $FFMPEG_PATH"

# 2. Install dependencies
echo "Installing requirements..."
pip install -r requirements.txt

# 3. Clean previous builds
rm -rf build dist *.spec

# 4. Run PyInstaller
# We bundle ffmpeg into the root of the app bundle (inside Contents/MacOS usually or sys._MEIPASS)
echo "Running PyInstaller..."
pyinstaller --noconfirm --windowed --clean \
    --name "$APP_NAME" \
    --add-data "ir:ir" \
    --add-binary "$FFMPEG_PATH:." \
    --hidden-import "PIL" \
    --hidden-import "PIL.Image" \
    --hidden-import "tkinter" \
    --collect-all "config" \
    "$MAIN_SCRIPT"

echo "=== Build Complete ==="
echo "The app is located at: dist/$APP_NAME.app"

# 5. Create DMG (Optional)
if command -v create-dmg &> /dev/null; then
    echo "Creating DMG..."
    create-dmg \
      --volname "$APP_NAME Installer" \
      --window-pos 200 120 \
      --window-size 800 400 \
      --icon-size 100 \
      --icon "$APP_NAME.app" 200 190 \
      --hide-extension "$APP_NAME.app" \
      --app-drop-link 600 185 \
      "dist/$APP_NAME.dmg" \
      "dist/$APP_NAME.app"
    echo "DMG created at: dist/$APP_NAME.dmg"
else
    echo "Tip: Install 'create-dmg' (brew install create-dmg) to generate a nice .dmg file."
    echo "Manual zip: cd dist && zip -r $APP_NAME.zip $APP_NAME.app"
fi
