# actions/send_message.py
# Universal messaging for desktop apps like WhatsApp, Telegram, Instagram, and Discord.

import json
import re
import sys
import time
import webbrowser
from pathlib import Path

import pyautogui
import requests

try:
    import pygetwindow as gw
except Exception:
    gw = None

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.08


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = get_base_dir()
API_CONFIG_PATH = BASE_DIR / "security_vault" / "access.json"
CONTACTS_PATH = BASE_DIR / "security_vault" / "contacts.json"


def _open_app(app_name: str) -> bool:
    """Opens an app via Windows search."""
    try:
        pyautogui.press("win")
        time.sleep(0.4)
        pyautogui.write(app_name, interval=0.04)
        time.sleep(0.5)
        pyautogui.press("enter")
        time.sleep(2.0)
        return True
    except Exception as e:
        print(f"[SendMessage] Could not open {app_name}: {e}")
        return False


def _focus_existing_window(*keywords: str) -> bool:
    """Brings an already open app window to the foreground."""
    if gw is None:
        return False

    wanted = [key.lower() for key in keywords if key]
    if not wanted:
        return False

    try:
        for win in gw.getAllWindows():
            title = (getattr(win, "title", "") or "").lower()
            if not title or not any(key in title for key in wanted):
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


def _activate_or_open_app(app_name: str, *window_keywords: str) -> bool:
    """Uses the existing desktop app when available, otherwise launches it."""
    if _focus_existing_window(*window_keywords):
        return True

    if not _open_app(app_name):
        return False

    time.sleep(2.0)
    if window_keywords:
        _focus_existing_window(*window_keywords)
    return True


def _load_config() -> dict:
    try:
        with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _load_contacts() -> dict:
    try:
        with open(CONTACTS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {str(k).strip().lower(): str(v).strip() for k, v in data.items()}
    except Exception:
        return {}


def _normalize_phone(phone: str) -> str:
    return re.sub(r"\D", "", phone or "")


def _resolve_receiver_phone(receiver: str, explicit_phone: str = "") -> str:
    if explicit_phone:
        return _normalize_phone(explicit_phone)

    config = _load_config()
    contacts = {}

    for source in (config.get("contact_phones", {}), _load_contacts()):
        if isinstance(source, dict):
            contacts.update({str(k).strip().lower(): str(v).strip() for k, v in source.items()})

    return _normalize_phone(contacts.get(receiver.strip().lower(), ""))


def _clear_current_input():
    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.1)
    pyautogui.press("backspace")


def _search_contact(contact: str):
    """Searches for a contact inside the currently focused desktop app."""
    time.sleep(0.5)
    pyautogui.hotkey("ctrl", "f")
    time.sleep(0.4)
    _clear_current_input()
    pyautogui.write(contact, interval=0.04)
    time.sleep(0.8)
    pyautogui.press("enter")
    time.sleep(0.8)


def _type_and_send(message: str, focus_message_box: bool = False):
    """Types a message and sends it in the currently focused conversation."""
    if focus_message_box:
        pyautogui.press("tab")
        time.sleep(0.2)
    pyautogui.write(message, interval=0.03)
    time.sleep(0.2)
    pyautogui.press("enter")
    time.sleep(0.3)


def _send_whatsapp(receiver: str, message: str) -> str:
    """Sends a WhatsApp message via the desktop app."""
    try:
        if not _activate_or_open_app("WhatsApp", "whatsapp"):
            return "Could not open WhatsApp."

        _search_contact(receiver)
        _type_and_send(message)
        return f"Message sent to {receiver} via WhatsApp."

    except Exception as e:
        return f"WhatsApp error: {e}"


def _send_whatsapp_background(receiver: str, message: str, receiver_phone: str = "") -> str:
    cfg = _load_config()
    access_token = cfg.get("whatsapp_access_token", "").strip()
    phone_number_id = cfg.get("whatsapp_phone_number_id", "").strip()
    api_version = cfg.get("whatsapp_api_version", "v23.0").strip()
    phone = _resolve_receiver_phone(receiver, receiver_phone)

    if not access_token or not phone_number_id:
        return (
            "Background WhatsApp send needs whatsapp_access_token and "
            "whatsapp_phone_number_id in security_vault/access.json."
        )

    if not phone:
        return (
            "Background WhatsApp send also needs receiver_phone or a "
            "phone mapping in security_vault/contacts.json."
        )

    url = f"https://graph.facebook.com/{api_version}/{phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "text",
        "text": {"body": message},
    }
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=20)
        if response.ok:
            return f"Background WhatsApp message sent to {receiver}."

        try:
            detail = response.json()
        except Exception:
            detail = response.text[:300]
        return f"WhatsApp Cloud API error: {detail}"
    except Exception as e:
        return f"WhatsApp background send failed: {e}"


def _send_instagram(receiver: str, message: str) -> str:
    """Sends an Instagram DM via instagram.com/direct."""
    try:
        webbrowser.open("https://www.instagram.com/direct/new/")
        time.sleep(3.5)

        pyautogui.write(receiver, interval=0.05)
        time.sleep(1.5)

        pyautogui.press("down")
        time.sleep(0.3)
        pyautogui.press("enter")
        time.sleep(0.5)

        for _ in range(3):
            pyautogui.press("tab")
            time.sleep(0.1)
        pyautogui.press("enter")
        time.sleep(1.5)

        _type_and_send(message)
        return f"Message sent to {receiver} via Instagram."

    except Exception as e:
        return f"Instagram error: {e}"


def _send_telegram(receiver: str, message: str) -> str:
    """Sends a Telegram message via the desktop app."""
    try:
        if not _activate_or_open_app("Telegram", "telegram"):
            return "Could not open Telegram."

        _search_contact(receiver)
        _type_and_send(message)
        return f"Message sent to {receiver} via Telegram."

    except Exception as e:
        return f"Telegram error: {e}"


def _send_discord(receiver: str, message: str) -> str:
    """
    Sends a Discord DM or channel message via the desktop app.
    Uses Discord quick switcher so it works with the already-open app.
    """
    try:
        if not _activate_or_open_app("Discord", "discord"):
            return "Could not activate Discord."

        time.sleep(0.8)
        pyautogui.hotkey("ctrl", "k")
        time.sleep(0.5)
        _clear_current_input()
        pyautogui.write(receiver, interval=0.04)
        time.sleep(1.2)
        pyautogui.press("enter")
        time.sleep(1.0)

        _type_and_send(message)
        return f"Message sent to {receiver} via Discord."

    except Exception as e:
        return f"Discord error: {e}"


def _send_generic(platform: str, receiver: str, message: str) -> str:
    """
    Fallback for platforms that support desktop search and direct text entry.
    """
    try:
        if not _activate_or_open_app(platform, platform):
            return f"Could not open {platform}."

        _search_contact(receiver)
        _type_and_send(message)
        return f"Message sent to {receiver} via {platform}."

    except Exception as e:
        return f"{platform} error: {e}"


def send_message(
    parameters: dict,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    """
    parameters:
        receiver     : Contact, DM, or channel name
        message_text : The message content
        platform     : whatsapp | instagram | telegram | discord | <any app name>
    """
    params = parameters or {}
    receiver = params.get("receiver", "").strip()
    message_text = params.get("message_text", "").strip()
    platform = params.get("platform", "whatsapp").strip().lower()
    background = bool(params.get("background", False))
    receiver_phone = params.get("receiver_phone", "").strip()

    if not receiver:
        return "Please specify who to send the message to, sir."
    if not message_text:
        return "Please specify what message to send, sir."

    print(f"[SendMessage] Sending via {platform} -> {receiver}: {message_text[:40]}")
    if player:
        player.write_log(f"[msg] Sending to {receiver} via {platform}...")

    if background and ("whatsapp" in platform or "wp" in platform or "wapp" in platform):
        result = _send_whatsapp_background(receiver, message_text, receiver_phone)
    elif background:
        result = (
            f"True background sending is not available for {platform} with desktop UI automation. "
            "For WhatsApp, configure the Cloud API instead."
        )
    elif "whatsapp" in platform or "wp" in platform or "wapp" in platform:
        result = _send_whatsapp(receiver, message_text)
    elif "instagram" in platform or "ig" in platform or "insta" in platform:
        result = _send_instagram(receiver, message_text)
    elif "telegram" in platform or "tg" in platform:
        result = _send_telegram(receiver, message_text)
    elif "discord" in platform or platform == "dc":
        result = _send_discord(receiver, message_text)
    else:
        result = _send_generic(platform, receiver, message_text)

    print(f"[SendMessage] {result}")
    if player:
        player.write_log(f"[msg] {result}")

    return result
