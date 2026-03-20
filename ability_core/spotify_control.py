# actions/spotify_control.py
# Controls Spotify with either desktop shortcuts or the Spotify Web API.

import base64
import json
import re
import subprocess
import sys
import time
from pathlib import Path

import pyautogui
import requests

try:
    import pygetwindow as gw
except Exception:
    gw = None

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.05


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = get_base_dir()
API_CONFIG_PATH = BASE_DIR / "security_vault" / "access.json"
SPOTIFY_CONFIG_PATH = BASE_DIR / "security_vault" / "spotify.json"
SPOTIFY_ACCOUNTS_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_API_BASE = "https://api.spotify.com/v1"


def _load_json(path: Path) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _load_config() -> dict:
    config = {}
    config.update(_load_json(API_CONFIG_PATH))
    config.update(_load_json(SPOTIFY_CONFIG_PATH))
    return config


def _focus_spotify_window() -> bool:
    if gw is None:
        return False

    try:
        for win in gw.getAllWindows():
            title = (getattr(win, "title", "") or "").lower()
            if "spotify" not in title:
                continue

            try:
                if getattr(win, "isMinimized", False):
                    win.restore()
                    time.sleep(0.3)
                win.activate()
                time.sleep(0.8)
                return True
            except Exception:
                continue
    except Exception:
        return False

    return False


def _open_spotify() -> bool:
    try:
        pyautogui.press("win")
        time.sleep(0.5)
        pyautogui.write("Spotify", interval=0.04)
        time.sleep(0.6)
        pyautogui.press("enter")
        time.sleep(3.0)
        return True
    except Exception:
        return False


def _activate_or_open_spotify() -> bool:
    if _focus_spotify_window():
        return True
    if not _open_spotify():
        return False
    time.sleep(1.0)
    _focus_spotify_window()
    return True


def _open_spotify_background() -> bool:
    try:
        if sys.platform == "win32":
            subprocess.Popen(
                ["cmd", "/c", "start", "/min", "", "spotify"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
            )
            time.sleep(2.5)
            return True
    except Exception:
        return False
    return False


def _shortcut(*keys):
    pyautogui.hotkey(*keys)
    time.sleep(0.2)


def _press(key: str, repeats: int = 1):
    for _ in range(max(1, int(repeats or 1))):
        pyautogui.press(key)
        time.sleep(0.12)


def _clear_active_input():
    _shortcut("ctrl", "a")
    pyautogui.press("backspace")
    time.sleep(0.1)


def _extract_query(description: str) -> str:
    text = (description or "").strip()
    if not text:
        return ""

    cleaned = re.sub(r"(?i)\bspotify('?da|'de)?\b", "", text)
    cleaned = re.sub(r"(?i)\b(muzik|sarki|song|music|playlist|artist)\b", "", cleaned)
    cleaned = re.sub(r"(?i)\b(ara|search|cal|ac|baslat|dinlet|oynat|play)\b", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -:,.")
    return cleaned.strip()


def _resolve_action(params: dict) -> tuple[str, str]:
    action = (params.get("action") or "").strip().lower()
    description = (params.get("description") or "").strip()
    query = (params.get("query") or "").strip()

    aliases = {
        "play": "play_pause",
        "pause": "play_pause",
        "resume": "play_pause",
        "next": "next_track",
        "previous": "previous_track",
        "prev": "previous_track",
        "search_play": "search_and_play",
        "open": "focus",
    }
    if action:
        action = aliases.get(action, action)
    else:
        lower = description.lower()
        if any(token in lower for token in ["sonraki", "next", "degistir", "ileri sar", "gec"]):
            action = "next_track"
        elif any(token in lower for token in ["onceki", "previous", "geri al", "geri don"]):
            action = "previous_track"
        elif any(token in lower for token in ["duraklat", "pause", "resume", "devam", "oynatmayi durdur"]):
            action = "play_pause"
        elif any(token in lower for token in ["ara", "search"]):
            action = "search"
        elif any(token in lower for token in ["cal", "baslat", "dinlet", "oynat", "play"]):
            action = "search_and_play"
        elif any(token in lower for token in ["shuffle", "karisik"]):
            action = "shuffle"
        elif any(token in lower for token in ["repeat", "tekrar"]):
            action = "repeat"
        elif any(token in lower for token in ["begen", "like", "kalbe al"]):
            action = "like"
        elif any(token in lower for token in ["mute", "sessiz"]):
            action = "mute"
        else:
            action = "focus"

    if not query:
        query = _extract_query(description)

    return action, query


def _spotify_credentials() -> tuple[dict, str]:
    cfg = _load_config()
    needed = ["spotify_client_id", "spotify_client_secret", "spotify_refresh_token"]
    missing = [key for key in needed if not cfg.get(key)]
    if missing:
        return {}, (
            "Background Spotify control needs spotify_client_id, "
            "spotify_client_secret, and spotify_refresh_token in security_vault/access.json."
        )
    return cfg, ""


def _spotify_access_token(cfg: dict) -> tuple[str, str]:
    raw = f"{cfg['spotify_client_id']}:{cfg['spotify_client_secret']}".encode("utf-8")
    auth = base64.b64encode(raw).decode("utf-8")
    response = requests.post(
        SPOTIFY_ACCOUNTS_URL,
        headers={
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type": "refresh_token",
            "refresh_token": cfg["spotify_refresh_token"],
        },
        timeout=20,
    )
    if not response.ok:
        return "", f"Spotify token refresh failed: {response.text[:300]}"
    data = response.json()
    return data.get("access_token", ""), ""


def _spotify_request(method: str, path: str, token: str, **kwargs):
    headers = kwargs.pop("headers", {})
    headers["Authorization"] = f"Bearer {token}"
    return requests.request(
        method,
        f"{SPOTIFY_API_BASE}{path}",
        headers=headers,
        timeout=20,
        **kwargs,
    )


def _spotify_choose_device(cfg: dict, token: str) -> tuple[str, str]:
    response = _spotify_request("GET", "/me/player/devices", token)
    if not response.ok:
        return "", f"Could not read Spotify devices: {response.text[:300]}"

    items = response.json().get("devices", [])
    if not items:
        return "", (
            "No active Spotify device was found. Leave Spotify running in the background "
            "on your PC or set spotify_device_id / spotify_device_name in access.json."
        )

    wanted_id = (cfg.get("spotify_device_id") or "").strip()
    wanted_name = (cfg.get("spotify_device_name") or "").strip().lower()

    for device in items:
        if wanted_id and device.get("id") == wanted_id:
            return device["id"], ""

    for device in items:
        if wanted_name and wanted_name in (device.get("name") or "").lower():
            return device["id"], ""

    for device in items:
        if device.get("is_active"):
            return device["id"], ""

    for device in items:
        if not device.get("is_restricted"):
            return device["id"], ""

    return items[0].get("id", ""), ""


def _spotify_transfer_device(token: str, device_id: str) -> tuple[bool, str]:
    response = _spotify_request(
        "PUT",
        "/me/player",
        token,
        json={"device_ids": [device_id], "play": False},
    )
    if response.status_code not in (200, 202, 204):
        return False, f"Could not switch Spotify device: {response.text[:300]}"
    return True, ""


def _spotify_player_state(token: str) -> tuple[dict, str]:
    response = _spotify_request("GET", "/me/player", token)
    if response.status_code == 204:
        return {}, ""
    if not response.ok:
        return {}, f"Could not read Spotify player state: {response.text[:300]}"
    return response.json(), ""


def _spotify_current_track(token: str) -> tuple[dict, str]:
    response = _spotify_request("GET", "/me/player/currently-playing", token)
    if response.status_code == 204:
        return {}, ""
    if not response.ok:
        return {}, f"Could not read current Spotify track: {response.text[:300]}"
    return response.json(), ""


def _spotify_search_top_track(token: str, query: str) -> tuple[dict, str]:
    response = _spotify_request(
        "GET",
        "/search",
        token,
        params={"q": query, "type": "track", "limit": 1},
    )
    if not response.ok:
        return {}, f"Spotify search failed: {response.text[:300]}"
    items = response.json().get("tracks", {}).get("items", [])
    if not items:
        return {}, f"No Spotify result found for '{query}'."
    return items[0], ""


def _spotify_background_action(action: str, query: str) -> str:
    if action == "focus":
        if _open_spotify_background() or _focus_spotify_window():
            return "Spotify background launch requested."

    cfg, err = _spotify_credentials()
    if err:
        return err

    token, err = _spotify_access_token(cfg)
    if err:
        return err

    device_id, err = _spotify_choose_device(cfg, token)
    if err and action not in ("search",):
        return err

    if device_id:
        ok, err = _spotify_transfer_device(token, device_id)
        if not ok and action not in ("search",):
            return err

    if action == "focus":
        return "Spotify background mode is ready."

    if action == "search":
        track, err = _spotify_search_top_track(token, query)
        if err:
            return err
        artist = ", ".join(a.get("name", "") for a in track.get("artists", []))
        return f"Top Spotify result: {track.get('name', 'Unknown')} - {artist}"

    if action == "search_and_play":
        track, err = _spotify_search_top_track(token, query)
        if err:
            return err
        response = _spotify_request(
            "PUT",
            "/me/player/play",
            token,
            params={"device_id": device_id} if device_id else None,
            json={"uris": [track["uri"]]},
        )
        if response.status_code not in (200, 202, 204):
            return f"Spotify play request failed: {response.text[:300]}"
        artist = ", ".join(a.get("name", "") for a in track.get("artists", []))
        return f"Playing in background on Spotify: {track.get('name', 'Unknown')} - {artist}"

    if action == "play_pause":
        state, err = _spotify_player_state(token)
        if err:
            return err
        endpoint = "/me/player/pause" if state.get("is_playing") else "/me/player/play"
        response = _spotify_request(
            "PUT",
            endpoint,
            token,
            params={"device_id": device_id} if device_id and endpoint.endswith("/play") else None,
        )
        if response.status_code not in (200, 202, 204):
            return f"Spotify playback request failed: {response.text[:300]}"
        return "Spotify background playback toggled."

    if action == "next_track":
        response = _spotify_request("POST", "/me/player/next", token)
        if response.status_code not in (200, 202, 204):
            return f"Spotify next-track request failed: {response.text[:300]}"
        return "Skipped to the next Spotify track in background."

    if action == "previous_track":
        response = _spotify_request("POST", "/me/player/previous", token)
        if response.status_code not in (200, 202, 204):
            return f"Spotify previous-track request failed: {response.text[:300]}"
        return "Went to the previous Spotify track in background."

    if action == "like":
        current, err = _spotify_current_track(token)
        if err:
            return err
        track = current.get("item") or {}
        track_id = track.get("id")
        if not track_id:
            return "No active Spotify track to like in background."
        response = _spotify_request("PUT", "/me/tracks", token, params={"ids": track_id})
        if response.status_code not in (200, 202, 204):
            return f"Spotify like request failed: {response.text[:300]}"
        return "Liked the current Spotify track in background."

    return (
        "Background Spotify currently supports focus, play_pause, next_track, "
        "previous_track, search, search_and_play, and like."
    )


def spotify_control(
    parameters: dict,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    """
    Controls the Spotify desktop app.

    actions:
      focus
      play_pause
      next_track
      previous_track
      search
      search_and_play
      shuffle
      repeat
      like
      mute
    """
    params = parameters or {}
    action, query = _resolve_action(params)
    background = bool(params.get("background", False))
    focus_window = params.get("focus_window", True)

    if player:
        mode = "background" if background else "foreground"
        player.write_log(f"[spotify] {mode}: {action}" + (f" -> {query}" if query else ""))

    if background:
        return _spotify_background_action(action, query)

    if focus_window:
        if not _activate_or_open_spotify():
            return "Could not open or focus Spotify."

    try:
        if action == "focus":
            return "Spotify is ready."

        if action == "play_pause":
            _press("space")
            return "Toggled Spotify playback."

        if action == "next_track":
            _press("down")
            return "Skipped to the next Spotify track."

        if action == "previous_track":
            _press("up")
            return "Went to the previous Spotify track."

        if action == "search":
            if not query:
                return "Please provide a song, artist, or playlist to search on Spotify."
            _shortcut("ctrl", "k")
            _clear_active_input()
            pyautogui.write(query, interval=0.03)
            return f"Searched Spotify for: {query}"

        if action == "search_and_play":
            if not query:
                return "Please provide what to play on Spotify."
            _shortcut("ctrl", "k")
            _clear_active_input()
            pyautogui.write(query, interval=0.03)
            time.sleep(1.0)
            _press("tab")
            _press("enter")
            time.sleep(0.7)
            _press("space")
            return f"Attempted to play on Spotify: {query}"

        if action == "shuffle":
            _shortcut("ctrl", "s")
            return "Toggled Spotify shuffle."

        if action == "repeat":
            _shortcut("ctrl", "r")
            return "Toggled Spotify repeat."

        if action == "like":
            _shortcut("alt", "shift", "b")
            return "Toggled like on the current Spotify track."

        if action == "mute":
            _press("m")
            return "Toggled Spotify mute."

        return f"Unknown Spotify action: {action}"

    except Exception as e:
        return f"spotify_control failed: {e}"
