import argparse
import base64
import json
import threading
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import requests


ROOT = Path(__file__).resolve().parent.parent
SPOTIFY_CONFIG_PATH = ROOT / "security_vault" / "spotify.json"
DEFAULT_REDIRECT_URI = "http://127.0.0.1:4381/callback"
DEFAULT_SCOPES = (
    "user-read-playback-state "
    "user-modify-playback-state "
    "user-library-modify "
    "user-read-currently-playing"
)
AUTH_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"
API_BASE = "https://api.spotify.com/v1"


def load_spotify_config() -> dict:
    if not SPOTIFY_CONFIG_PATH.exists():
        raise FileNotFoundError(f"Missing config: {SPOTIFY_CONFIG_PATH}")
    with open(SPOTIFY_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_spotify_config(data: dict) -> None:
    SPOTIFY_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SPOTIFY_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def basic_auth_header(client_id: str, client_secret: str) -> str:
    raw = f"{client_id}:{client_secret}".encode("utf-8")
    token = base64.b64encode(raw).decode("utf-8")
    return f"Basic {token}"


class CallbackState:
    def __init__(self):
        self.event = threading.Event()
        self.code = ""
        self.error = ""
        self.error_description = ""


def make_handler(state: CallbackState):
    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)

            state.code = query.get("code", [""])[0]
            state.error = query.get("error", [""])[0]
            state.error_description = query.get("error_description", [""])[0]

            if state.code:
                body = (
                    "<html><body><h2>Spotify authorization complete.</h2>"
                    "<p>You can return to the terminal.</p></body></html>"
                )
                self.send_response(200)
            else:
                body = (
                    "<html><body><h2>Spotify authorization failed.</h2>"
                    "<p>You can return to the terminal and review the error.</p></body></html>"
                )
                self.send_response(400)

            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body.encode("utf-8"))
            state.event.set()

        def log_message(self, fmt, *args):
            return

    return CallbackHandler


def run_callback_server(redirect_uri: str, state: CallbackState) -> tuple[HTTPServer, threading.Thread]:
    parsed = urlparse(redirect_uri)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise ValueError("spotify_redirect_uri must be local, e.g. http://127.0.0.1:4381/callback")

    host = parsed.hostname
    port = parsed.port or 80
    server = HTTPServer((host, port), make_handler(state))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def build_authorize_url(client_id: str, redirect_uri: str, scopes: str) -> str:
    return (
        f"{AUTH_URL}?"
        + urlencode(
            {
                "client_id": client_id,
                "response_type": "code",
                "redirect_uri": redirect_uri,
                "scope": scopes,
                "show_dialog": "true",
            }
        )
    )


def exchange_code_for_tokens(client_id: str, client_secret: str, code: str, redirect_uri: str) -> dict:
    response = requests.post(
        TOKEN_URL,
        headers={
            "Authorization": basic_auth_header(client_id, client_secret),
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
        },
        timeout=30,
    )
    if not response.ok:
        raise RuntimeError(f"Token exchange failed: {response.text[:500]}")
    return response.json()


def api_get(path: str, access_token: str) -> dict:
    response = requests.get(
        f"{API_BASE}{path}",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=20,
    )
    if response.status_code == 204:
        return {}
    if not response.ok:
        raise RuntimeError(f"Spotify API request failed for {path}: {response.text[:500]}")
    return response.json()


def choose_device(devices: list[dict]) -> tuple[str, str]:
    if not devices:
        return "", ""

    for device in devices:
        if device.get("is_active"):
            return device.get("name", ""), device.get("id", "")

    for device in devices:
        if not device.get("is_restricted"):
            return device.get("name", ""), device.get("id", "")

    return devices[0].get("name", ""), devices[0].get("id", "")


def main():
    parser = argparse.ArgumentParser(description="Authorize Spotify and save refresh token/device info.")
    parser.add_argument("--timeout", type=int, default=180, help="Seconds to wait for Spotify callback.")
    parser.add_argument("--no-browser", action="store_true", help="Print the URL without opening a browser.")
    args = parser.parse_args()

    config = load_spotify_config()
    client_id = str(config.get("spotify_client_id", "")).strip()
    client_secret = str(config.get("spotify_client_secret", "")).strip()
    redirect_uri = str(config.get("spotify_redirect_uri", DEFAULT_REDIRECT_URI)).strip() or DEFAULT_REDIRECT_URI
    scopes = str(config.get("spotify_scopes", DEFAULT_SCOPES)).strip() or DEFAULT_SCOPES

    if not client_id or not client_secret:
        raise SystemExit(
            "spotify_client_id and spotify_client_secret are required in security_vault/spotify.json.\n"
            "Also add the same redirect URI in your Spotify developer app settings."
        )

    state = CallbackState()
    server, _thread = run_callback_server(redirect_uri, state)

    try:
        authorize_url = build_authorize_url(client_id, redirect_uri, scopes)
        print("Open this URL and complete Spotify login:")
        print(authorize_url)
        print("")
        print(f"Waiting for callback on {redirect_uri} ...")

        if not args.no_browser:
            webbrowser.open(authorize_url)

        if not state.event.wait(timeout=args.timeout):
            raise SystemExit("Timed out waiting for Spotify callback.")

        if state.error:
            raise SystemExit(f"Spotify authorization error: {state.error} {state.error_description}".strip())
        if not state.code:
            raise SystemExit("No authorization code was returned by Spotify.")

        token_data = exchange_code_for_tokens(client_id, client_secret, state.code, redirect_uri)
        access_token = token_data.get("access_token", "")
        refresh_token = token_data.get("refresh_token", "")
        if not access_token or not refresh_token:
            raise SystemExit("Spotify did not return both access_token and refresh_token.")

        profile = api_get("/me", access_token)
        device_payload = api_get("/me/player/devices", access_token)
        devices = device_payload.get("devices", [])
        device_name, device_id = choose_device(devices)

        config["spotify_refresh_token"] = refresh_token
        config["spotify_device_name"] = device_name or config.get("spotify_device_name", "")
        config["spotify_device_id"] = device_id or config.get("spotify_device_id", "")
        config["spotify_auth_updated_at"] = datetime.now(timezone.utc).isoformat()
        config["spotify_user_display_name"] = profile.get("display_name", "")
        config["spotify_user_id"] = profile.get("id", "")
        save_spotify_config(config)

        print("")
        print("Spotify authorization complete.")
        print(f"User           : {profile.get('display_name', '') or profile.get('id', 'Unknown')}")
        print(f"Refresh token  : saved to {SPOTIFY_CONFIG_PATH}")
        print(f"Device name    : {config.get('spotify_device_name', '') or '(none found)'}")
        print(f"Device id      : {config.get('spotify_device_id', '') or '(none found)'}")

        if devices:
            print("")
            print("Available devices:")
            for device in devices:
                active = "active" if device.get("is_active") else "idle"
                restricted = "restricted" if device.get("is_restricted") else "ok"
                print(f"- {device.get('name', 'Unknown')} | {device.get('id', '')} | {active} | {restricted}")
        else:
            print("")
            print("No Spotify devices were reported. Open Spotify on your PC and rerun if needed.")

    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
