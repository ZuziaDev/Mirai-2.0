# actions/game_control.py
# Controls an active game window such as Minecraft with keyboard and mouse.

import json
import re
import sys
import time
from pathlib import Path

try:
    import pyautogui
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.04
    _PYAUTOGUI = True
except ImportError:
    _PYAUTOGUI = False

try:
    import pygetwindow as gw
except Exception:
    gw = None


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = get_base_dir()
API_CONFIG_PATH = BASE_DIR / "security_vault" / "access.json"
MACRO_CONFIG_PATH = BASE_DIR / "security_vault" / "game_macros.json"

DEFAULT_SECONDS = 0.8


def _ensure_pyautogui():
    if not _PYAUTOGUI:
        raise RuntimeError("PyAutoGUI not installed. Run: pip install pyautogui")


def _get_api_key() -> str:
    try:
        with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f).get("gemini_api_key", "")
    except Exception:
        return ""


def _focus_game_window(game: str) -> bool:
    if gw is None or not game:
        return False

    wanted = [game.lower().strip()]
    if game.lower().strip() == "minecraft":
        wanted.extend(["minecraft", "java(tm) platform se binary", "lunar client", "badlion"])

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


def _tap(key: str, repeat: int = 1, interval: float = 0.08):
    for _ in range(max(1, repeat)):
        pyautogui.press(key)
        time.sleep(interval)


def _hold_keys(keys: list[str], seconds: float):
    for key in keys:
        pyautogui.keyDown(key)
    try:
        time.sleep(max(0.05, seconds))
    finally:
        for key in reversed(keys):
            pyautogui.keyUp(key)


def _mouse_action(button: str = "left", seconds: float = 0.0, repeat: int = 1):
    repeat = max(1, int(repeat or 1))
    if seconds and seconds > 0:
        for _ in range(repeat):
            pyautogui.mouseDown(button=button)
            time.sleep(seconds)
            pyautogui.mouseUp(button=button)
            time.sleep(0.08)
    else:
        pyautogui.click(button=button, clicks=repeat, interval=0.08)


def _look(dx: int = 0, dy: int = 0, duration: float = 0.12):
    pyautogui.moveRel(int(dx), int(dy), duration=max(0.0, duration))


def _send_chat(text: str):
    pyautogui.press("t")
    time.sleep(0.2)
    pyautogui.write(text, interval=0.02)
    time.sleep(0.1)
    pyautogui.press("enter")


def _send_command(text: str):
    command_text = (text or "").strip()
    if command_text.startswith("/"):
        command_text = command_text[1:]
    pyautogui.press("/")
    time.sleep(0.2)
    pyautogui.write(command_text, interval=0.02)
    time.sleep(0.1)
    pyautogui.press("enter")


def _load_macro_config() -> dict:
    defaults = {
        "minecraft_strip_mine": [
            {"action": "slot", "slot": 1},
            {"action": "move_forward", "seconds": 1.4},
            {"action": "attack", "seconds": 1.5},
            {"action": "wait", "seconds": 0.3},
        ],
        "minecraft_bridge_short": [
            {"action": "crouch", "seconds": 0.6},
            {"action": "use", "repeat": 3},
            {"action": "move_backward", "seconds": 0.7},
        ],
        "minecraft_escape": [
            {"action": "look", "dx": 220, "dy": 0},
            {"action": "sprint_forward", "seconds": 2.0},
            {"action": "jump", "repeat": 1},
        ],
    }
    try:
        with open(MACRO_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            defaults.update(data)
    except Exception:
        pass
    return defaults


def _extract_number(text: str, pattern: str, default=None):
    match = re.search(pattern, text, re.IGNORECASE)
    if not match:
        return default
    value = match.group(1)
    if "." in value:
        return float(value)
    return int(value)


def _heuristic_parse(description: str) -> dict:
    text = (description or "").strip().lower()
    seconds = _extract_number(text, r"(\d+(?:\.\d+)?)\s*(?:s|sec|secs|second|seconds|saniye)") or DEFAULT_SECONDS
    slot = _extract_number(text, r"\b([1-9])\b")

    if any(token in text for token in ["jump", "zipla", "ziplasin"]):
        return {"action": "jump"}
    if any(token in text for token in ["inventory", "envanter"]):
        return {"action": "inventory"}
    if any(token in text for token in ["drop", "birak", "drop item", "item birak"]):
        return {"action": "drop"}
    if any(token in text for token in ["mine", "attack", "vur", "kir", "kaz"]):
        return {"action": "attack", "seconds": seconds}
    if any(token in text for token in ["place", "use", "interact", "koy", "kullan"]):
        return {"action": "use", "seconds": seconds}
    if any(token in text for token in ["sprint", "kos", "kos", "run forward"]):
        return {"action": "sprint_forward", "seconds": seconds}
    if any(token in text for token in ["look left", "sola don"]):
        return {"action": "look", "dx": -180, "dy": 0}
    if any(token in text for token in ["look right", "saga don"]):
        return {"action": "look", "dx": 180, "dy": 0}
    if any(token in text for token in ["look up", "yukari bak"]):
        return {"action": "look", "dx": 0, "dy": -140}
    if any(token in text for token in ["look down", "asagi bak"]):
        return {"action": "look", "dx": 0, "dy": 140}
    if any(token in text for token in ["forward", "ileri", "ilerle"]):
        return {"action": "move_forward", "seconds": seconds}
    if any(token in text for token in ["back", "geri"]):
        return {"action": "move_backward", "seconds": seconds}
    if any(token in text for token in ["strafe left", "move left", "sola git", "left"]):
        return {"action": "strafe_left", "seconds": seconds}
    if any(token in text for token in ["strafe right", "move right", "saga git", "saga", "right"]):
        return {"action": "strafe_right", "seconds": seconds}
    if any(token in text for token in ["command", "komut", "/"]):
        return {"action": "command", "text": description}
    if any(token in text for token in ["chat", "mesaj", "yaz "]):
        return {"action": "chat", "text": description}
    if any(token in text for token in ["macro", "makro"]):
        return {"action": "macro", "text": description}
    if any(token in text for token in ["routine", "rutin"]):
        return {"action": "routine", "text": description}
    if slot:
        return {"action": "slot", "slot": slot}
    return {"action": "focus"}


def _ai_parse(description: str, game: str) -> dict | None:
    api_key = _get_api_key()
    if not api_key or not description:
        return None

    try:
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.5-flash-lite")
        prompt = f"""Convert the user's request into one game action for an open {game or 'game'} window.

Allowed actions:
- focus
- move_forward
- move_backward
- strafe_left
- strafe_right
- sprint_forward
- jump
- crouch
- attack
- use
- inventory
- drop
- slot
- look
- press_key
- hold_key
- mouse_button
- chat
- command
- wait
- macro
- routine

Return ONLY valid JSON with this shape:
{{
  "action": "allowed_action",
  "seconds": null_or_number,
  "key": null_or_string,
  "button": null_or_string,
  "text": null_or_string,
  "slot": null_or_integer,
  "dx": null_or_integer,
  "dy": null_or_integer,
  "repeat": null_or_integer
}}

Examples:
- "minecraftta ileri git" -> {{"action":"move_forward","seconds":1.0,"key":null,"button":null,"text":null,"slot":null,"dx":null,"dy":null,"repeat":null}}
- "ziplasin" -> {{"action":"jump","seconds":null,"key":null,"button":null,"text":null,"slot":null,"dx":null,"dy":null,"repeat":1}}
- "saga bak" -> {{"action":"look","seconds":null,"key":null,"button":null,"text":null,"slot":null,"dx":180,"dy":0,"repeat":null}}
- "slash command olarak time set day yaz" -> {{"action":"command","seconds":null,"key":null,"button":null,"text":"time set day","slot":null,"dx":null,"dy":null,"repeat":null}}

User request: {description}
JSON:"""

        response = model.generate_content(prompt)
        text = response.text.strip()
        text = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()
        data = json.loads(text)
        if isinstance(data, dict) and data.get("action"):
            return data
    except Exception:
        return None

    return None


def _resolve_action(parameters: dict) -> dict:
    params = dict(parameters or {})
    action = (params.get("action") or "").strip().lower()
    description = (params.get("description") or "").strip()
    game = (params.get("game") or "minecraft").strip()

    aliases = {
        "forward": "move_forward",
        "back": "move_backward",
        "left": "strafe_left",
        "right": "strafe_right",
        "run": "sprint_forward",
        "mine": "attack",
        "place_block": "use",
        "interact": "use",
        "open_inventory": "inventory",
        "hotbar": "slot",
        "look_around": "look",
        "mouse_move": "look",
        "key": "press_key",
        "hold": "hold_key",
        "click": "mouse_button",
        "sleep": "wait",
        "macro_run": "macro",
        "run_macro": "macro",
        "routine_run": "routine",
    }

    if action:
        params["action"] = aliases.get(action, action)
        return params

    parsed = _ai_parse(description, game) or _heuristic_parse(description)
    parsed["game"] = game
    for key, value in params.items():
        if key not in parsed or parsed[key] in (None, ""):
            parsed[key] = value
    return parsed


def _macro_step_from_text(step_text: str) -> dict:
    text = (step_text or "").strip()
    if not text:
        return {}

    lowered = text.lower()
    seconds = _extract_number(lowered, r"(\d+(?:\.\d+)?)") or DEFAULT_SECONDS
    if lowered.startswith("wait"):
        return {"action": "wait", "seconds": seconds}
    if lowered.startswith("slot"):
        slot = _extract_number(lowered, r"slot\s+([1-9])", default=1)
        return {"action": "slot", "slot": slot}
    if lowered.startswith("look"):
        numbers = re.findall(r"-?\d+", lowered)
        if len(numbers) >= 2:
            return {"action": "look", "dx": int(numbers[0]), "dy": int(numbers[1])}
    if lowered.startswith("press "):
        return {"action": "press_key", "key": text.split(" ", 1)[1].strip()}
    if lowered.startswith("hold "):
        return {"action": "hold_key", "key": text.split(" ", 1)[1].strip(), "seconds": seconds}
    if lowered.startswith("chat "):
        return {"action": "chat", "text": text.split(" ", 1)[1].strip()}
    if lowered.startswith("command "):
        return {"action": "command", "text": text.split(" ", 1)[1].strip()}
    if lowered.startswith("forward"):
        return {"action": "move_forward", "seconds": seconds}
    if lowered.startswith("back"):
        return {"action": "move_backward", "seconds": seconds}
    if lowered.startswith("left"):
        return {"action": "strafe_left", "seconds": seconds}
    if lowered.startswith("right"):
        return {"action": "strafe_right", "seconds": seconds}
    if lowered.startswith("sprint"):
        return {"action": "sprint_forward", "seconds": seconds}
    if lowered.startswith("jump"):
        return {"action": "jump", "repeat": max(1, int(_extract_number(lowered, r"(\d+)", default=1)))}
    if lowered.startswith("crouch"):
        return {"action": "crouch", "seconds": seconds}
    if lowered.startswith("attack") or lowered.startswith("mine"):
        return {"action": "attack", "seconds": seconds}
    if lowered.startswith("use") or lowered.startswith("place"):
        repeat = _extract_number(lowered, r"(\d+)", default=1)
        return {"action": "use", "repeat": max(1, int(repeat or 1))}
    return _heuristic_parse(text)


def _expand_macro_steps(resolved: dict) -> tuple[str, list[dict]]:
    action = (resolved.get("action") or "").strip().lower()
    if action not in {"macro", "routine"}:
        return "", []

    if action == "routine":
        name = (
            resolved.get("routine_name")
            or resolved.get("name")
            or resolved.get("text")
            or resolved.get("description")
            or ""
        ).strip()
        routines = _load_macro_config()
        steps = routines.get(name, [])
        return name, [dict(step) for step in steps if isinstance(step, dict)]

    raw_steps = resolved.get("steps")
    if isinstance(raw_steps, list):
        steps = [step for step in raw_steps if isinstance(step, dict)]
        return resolved.get("name", "macro"), steps

    source = (
        resolved.get("steps_text")
        or resolved.get("text")
        or resolved.get("description")
        or ""
    )
    parts = [part.strip() for part in re.split(r"[;\n]+", source) if part.strip()]
    steps = [_macro_step_from_text(part) for part in parts]
    steps = [step for step in steps if step]
    return resolved.get("name", "macro"), steps


def game_control(
    parameters: dict,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    """
    Controls an open game such as Minecraft with keyboard and mouse.

    parameters:
        game         : Game/window name. Default: minecraft
        action       : Structured action name
        description  : Natural language instruction
        steps / steps_text : Macro step list or semicolon-separated macro text
        routine_name : Saved routine name from security_vault/game_macros.json
        seconds      : Hold/wait duration
        key          : Key for press_key / hold_key
        button       : Mouse button for mouse_button
        text         : Chat or command text
        slot         : Hotbar slot 1-9
        dx / dy      : Relative mouse movement for look
        repeat       : Repetition count
        focus_window : Focus the game window before acting. Default: true
    """
    _ensure_pyautogui()

    resolved = _resolve_action(parameters)
    action = (resolved.get("action") or "").strip().lower()
    game = (resolved.get("game") or "minecraft").strip()
    seconds = float(resolved.get("seconds") or DEFAULT_SECONDS)
    repeat = int(resolved.get("repeat") or 1)
    focus_window = resolved.get("focus_window", True)

    if focus_window and game:
        focused = _focus_game_window(game)
        if gw is not None and not focused:
            return f"Could not focus the {game} window. Open or click the game and try again."

    if player:
        player.write_log(f"[game] {game}: {action}")

    try:
        if action == "focus":
            return f"{game} window ready."

        if action in {"macro", "routine"}:
            name, steps = _expand_macro_steps(resolved)
            if not steps:
                return f"No steps found for {action}."
            results = []
            for step in steps:
                payload = dict(step)
                payload["game"] = game
                payload["focus_window"] = False
                result = game_control(parameters=payload, player=player)
                results.append(result)
            return f"Executed {action} '{name}' with {len(steps)} step(s)."

        if action == "move_forward":
            _hold_keys(["w"], seconds)
            return f"Moved forward for {seconds:.2f}s in {game}."

        if action == "move_backward":
            _hold_keys(["s"], seconds)
            return f"Moved backward for {seconds:.2f}s in {game}."

        if action == "strafe_left":
            _hold_keys(["a"], seconds)
            return f"Moved left for {seconds:.2f}s in {game}."

        if action == "strafe_right":
            _hold_keys(["d"], seconds)
            return f"Moved right for {seconds:.2f}s in {game}."

        if action == "sprint_forward":
            _hold_keys(["ctrl", "w"], seconds)
            return f"Sprinted forward for {seconds:.2f}s in {game}."

        if action == "jump":
            _tap("space", repeat=repeat)
            return f"Jumped {repeat} time(s) in {game}."

        if action == "crouch":
            _hold_keys(["shift"], seconds)
            return f"Crouched for {seconds:.2f}s in {game}."

        if action == "attack":
            _mouse_action(button="left", seconds=seconds, repeat=repeat)
            return f"Attack action executed in {game}."

        if action == "use":
            _mouse_action(button="right", seconds=seconds, repeat=repeat)
            return f"Use/place action executed in {game}."

        if action == "inventory":
            _tap("e", repeat=1)
            return f"Opened inventory in {game}."

        if action == "drop":
            _tap("q", repeat=repeat)
            return f"Dropped item {repeat} time(s) in {game}."

        if action == "slot":
            slot = int(resolved.get("slot") or 1)
            slot = max(1, min(9, slot))
            _tap(str(slot), repeat=1)
            return f"Selected hotbar slot {slot} in {game}."

        if action == "look":
            dx = int(resolved.get("dx") or 0)
            dy = int(resolved.get("dy") or 0)
            _look(dx=dx, dy=dy, duration=float(resolved.get("duration") or 0.12))
            return f"Looked in {game} by dx={dx}, dy={dy}."

        if action == "press_key":
            key = (resolved.get("key") or "").strip()
            if not key:
                return "Please provide a key for press_key."
            _tap(key, repeat=repeat)
            return f"Pressed {key} in {game}."

        if action == "hold_key":
            key = (resolved.get("key") or "").strip()
            if not key:
                return "Please provide a key for hold_key."
            _hold_keys([key], seconds)
            return f"Held {key} for {seconds:.2f}s in {game}."

        if action == "mouse_button":
            button = (resolved.get("button") or "left").strip().lower()
            _mouse_action(button=button, seconds=seconds if seconds > 0 else 0.0, repeat=repeat)
            return f"Mouse {button} action executed in {game}."

        if action == "chat":
            text = (resolved.get("text") or "").strip()
            if not text:
                return "Please provide text for chat."
            _send_chat(text)
            return f"Sent chat message in {game}."

        if action == "command":
            text = (resolved.get("text") or "").strip()
            if not text:
                return "Please provide a slash command."
            _send_command(text)
            return f"Executed command in {game}: {text}"

        if action == "wait":
            time.sleep(seconds)
            return f"Waited {seconds:.2f}s."

        return f"Unknown game action: {action}"

    except Exception as e:
        return f"game_control failed: {e}"
