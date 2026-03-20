# MIRAI 2.0

MIRAI is a Windows-based desktop assistant that combines voice commands, screen automation, file operations, browser control, messaging, Spotify control, game macros, and performance tools in a single system.

This README is a full setup guide for installing the project from scratch, filling in the required settings, and running it for the first time.

## 1. System Requirements

- Windows 10 or Windows 11
- Python 3.x
- Internet connection
- Microphone
- Speakers or headphones

Notes:
- The main target platform is Windows because the project uses `.bat` files and desktop automation.
- Playwright is required for browser automation.

## 2. Project Structure

Main folders:

- `ability_core/` : core capability modules
- `central_nerve/` : planning and execution layer
- `neural_store/` : memory and knowledge storage
- `security_vault/` : API keys and settings files
- `system_laws/` : system rules
- `visual_link/` : web-based UI experiments

Main runtime files:

- `installer.bat`
- `run.bat`
- `igniter.py`

## 3. Quick Setup

Open PowerShell or CMD:

```powershell
cd Mirai_2.0
.\installer.bat
.\run.bat
```

These two steps are usually enough.

## 4. Step-by-Step Installation

### 4.1 Enter the project folder

```powershell
cd Mirai_2.0
```

### 4.2 Install dependencies

Standard method:

```powershell
.\installer.bat
```

This script will:
- install the Python packages listed in `deps.txt`
- run `playwright install`

Alternative:

```powershell
python setup.py
```

or:

```powershell
py setup.py
```

### 4.3 Start the application

```powershell
.\run.bat
```

or directly:

```powershell
python igniter.py
```

## 5. Required Configuration

The project requires a `Gemini API key` for the main functionality.

File:

```text
security_vault/access.json
```

Minimum format:

```json
{
  "gemini_api_key": "PUT_YOUR_GEMINI_API_KEY_HERE"
}
```

Notes:
- If this file does not exist, the app may show a key entry window on first launch.
- The key is stored locally in `security_vault/access.json`.

## 6. Optional Settings

### 6.1 WhatsApp background sending

To send WhatsApp messages in the background, you need WhatsApp Cloud API credentials.

You can add these fields to `security_vault/access.json`:

```json
{
  "gemini_api_key": "PUT_YOUR_GEMINI_API_KEY_HERE",
  "whatsapp_access_token": "PUT_YOUR_WHATSAPP_TOKEN_HERE",
  "whatsapp_phone_number_id": "PUT_YOUR_PHONE_NUMBER_ID_HERE",
  "whatsapp_api_version": "v23.0",
  "contact_phones": {
    "ridvan": "905551112233"
  }
}
```

You can also store contact-to-phone mappings in a separate file:

```text
security_vault/contacts.json
```

Example:

```json
{
  "ridvan": "905551112233",

}
```

### 6.2 Spotify background control

For Spotify API-based background control, use this config file:

```text
security_vault/spotify.json
```

Example format:

```json
{
  "spotify_client_id": "",
  "spotify_client_secret": "",
  "spotify_refresh_token": "",
  "spotify_redirect_uri": "http://127.0.0.1:4381/callback",
  "spotify_scopes": "user-read-playback-state user-modify-playback-state user-library-modify user-read-currently-playing",
  "spotify_device_name": "",
  "spotify_device_id": ""
}
```

#### Getting a Spotify token

1. Create an app in the Spotify Developer Dashboard
2. Add this redirect URI:

```text
http://127.0.0.1:4381/callback
```

3. Fill in `spotify_client_id` and `spotify_client_secret`
4. Then run:

```powershell
.\spotify_auth.bat
```

This process will:
- open the Spotify login page in your browser
- catch the callback locally
- save the `spotify_refresh_token`
- save the device name and device ID if available

### 6.3 Performance settings

File:

```text
security_vault/performance.json
```

You can customize:
- CPU, RAM, disk, and temperature alert thresholds
- auto game mode intervals
- game profiles
- overlay refresh interval
- network monitoring targets

### 6.4 Game macros

File:

```text
security_vault/game_macros.json
```

This file stores named game routines. Example:

```json
{
  "minecraft_escape": [
    {
      "action": "look",
      "dx": 220,
      "dy": 0
    },
    {
      "action": "sprint_forward",
      "seconds": 2.0
    },
    {
      "action": "jump",
      "repeat": 1
    }
  ]
}
```

## 7. First Run Flow

1. Run `installer.bat`
2. Add `gemini_api_key` to `access.json`, or enter it in the first-launch window
3. Run `run.bat`
4. Check your microphone permissions and audio devices
5. Start giving commands once MIRAI is open

## 8. Basic Usage Ideas

Examples:

- open applications
- search the web
- open Spotify or switch songs
- send Discord or WhatsApp messages
- run a macro in a game like Minecraft
- enable performance mode

Purpose:
- Figma design specification
- single-file premium Next.js + Tailwind UI
- fullscreen WebGL/Canvas demo

These files are currently independent from the Python runtime and can be connected later if needed.

## 19. Troubleshooting

### Python not found

Problem:

```text
ERROR: Python not detected.
```

Solution:
- install Python
- make sure `py` or `python` works in the terminal

Check with:

```powershell
py --version
```

or:

```powershell
python --version
```

### Playwright issue

If browser packages are missing after setup:

```powershell
py -m playwright install
```

or:

```powershell
python -m playwright install
```

### `ModuleNotFoundError`

If a dependency is missing, run:

```powershell
.\installer.bat
```

### API key not found

Check `security_vault/access.json`.

Minimum valid format:

```json
{
  "gemini_api_key": "PUT_YOUR_GEMINI_API_KEY_HERE"
}
```

### Spotify background control is not working

Check:
- is `security_vault/spotify.json` filled in
- was `spotify_refresh_token` saved
- is the Spotify desktop app open
- is the device name or device ID correct

### WhatsApp background sending is not working

Check:
- `whatsapp_access_token`
- `whatsapp_phone_number_id`
- `receiver_phone` or `contacts.json`

## 10. Security Note

- do not put real API keys inside the README
- do not share the secret files inside `security_vault/`
- if a key was accidentally exposed, generate a new one

## 11. Running Again

After the setup is complete, daily usage is usually just:

```powershell
.\run.bat
```

If dependencies changed, run this first:

```powershell
.\installer.bat
```

## 12. Recommended File Order

The most important files for setup and configuration are:

1. `deps.txt`
2. `installer.bat`
3. `run.bat`
4. `security_vault/access.json`
5. `security_vault/spotify.json`
6. `security_vault/performance.json`
7. `security_vault/game_macros.json`

## 13. Short Summary

For a minimum working setup, these steps are enough:

1. Install Python
2. Run `.\installer.bat`
3. Add `gemini_api_key` to `security_vault/access.json`
4. Run `.\run.bat`

All other settings are optional features such as Spotify, WhatsApp, performance tools, and game macros.
