import asyncio
import threading
import json
import sys
import traceback
import logging
import time
from pathlib import Path
from datetime import datetime

import pyaudio
import psutil
import pyautogui
from google import genai
from google.genai import types
from typing import Optional

# --- CONFIGURATION & LOGGING ---
logging.basicConfig(
    level=logging.WARNING, # Suppress noise
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[
        logging.FileHandler('mirai_neural.log', mode='w', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ],
    force=True
)
logger = logging.getLogger("MIRAI")
logger.setLevel(logging.INFO) # Only mirai logs at info level

# Core Constants
LIVE_MODEL          = "models/gemini-2.5-flash-native-audio-preview-12-2025"
SEND_SAMPLE_RATE    = 16000
RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE          = 1024
PA_FORMAT           = pyaudio.paInt16
CHANNELS            = 1

# Global Living Context
SENSORY_HUB = {
    "visual_context": "No visual data yet.",
    "system_health": "Optimal",
    "last_alert": None
}

# Project-specific imports
from monitor import MiraiUI
from neural_store.main import load_memory, update_memory, format_memory_for_prompt
from neural_store.semantic_memory import format_recent_knowledge_for_prompt

# Ability Core modules
from ability_core.open_app          import open_app
from ability_core.weather_report    import weather_action
from ability_core.send_message      import send_message
from ability_core.reminder          import reminder
from ability_core.computer_settings import computer_settings
from ability_core.screen_processor  import screen_process
from ability_core.youtube_video     import youtube_video
from ability_core.desktop           import desktop_control
from ability_core.browser_control   import browser_control
from ability_core.code_helper       import code_helper
from ability_core.dev_agent         import dev_agent
from ability_core.web_search        import web_search as web_search_action
from ability_core.computer_control  import computer_control
from ability_core.file_controller   import file_controller
from ability_core.game_control      import game_control
from ability_core.spotify_control   import spotify_control
from ability_core.cmd_control       import cmd_control
from ability_core.performance_optimize import performance_optimize
from ability_core.task_queue        import task_queue
from ability_core.knowledge_memory  import knowledge_memory

# --- SYSTEM PATHS ---
def get_base_dir():
    if getattr(sys, "frozen", False): return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

BASE_DIR        = get_base_dir()
API_CONFIG_PATH = BASE_DIR / "Mirai" / "security_vault" / "access.json"
if not API_CONFIG_PATH.exists():
    API_CONFIG_PATH = Path(__file__).resolve().parent / "security_vault" / "access.json"

PROMPT_PATH = Path(__file__).resolve().parent / "system_laws" / "rules.txt"

pya = pyaudio.PyAudio()

def _get_api_key() -> str:
    try:
        with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)["gemini_api_key"]
    except: return ""

def _load_system_prompt() -> str:
    try:
        return PROMPT_PATH.read_text(encoding="utf-8")
    except:
        return "You are Mirai. Zuzia RodzeN assistant. Turkish language."

def _get_full_prompt() -> str:
    memory = load_memory()
    mem_str = format_memory_for_prompt(memory)
    learned_knowledge = format_recent_knowledge_for_prompt()
    sys_p = _load_system_prompt()
    now      = datetime.now()
    time_str = now.strftime("%A, %B %d, %Y — %I:%M %p")
    operator_name = (
        memory.get("identity", {})
        .get("name", {})
        .get("value", "")
        .strip()
    )
    
    # Inject Living Context
    sensory_p = (
        f"\n[SENSORY CONTEXT — WHAT YOU SEE & FEEL]\n"
        f"Visual Input: {SENSORY_HUB['visual_context']}\n"
        f"System Status: {SENSORY_HUB['system_health']}\n"
    )

    operator_ctx = ""
    if operator_name:
        operator_ctx = (
            f"[CURRENT OPERATOR]\n"
            f"The person you are speaking to is: {operator_name}\n"
            f"Use their name naturally when helpful.\n\n"
        )

    time_ctx = (
        f"[CURRENT DATE & TIME]\n"
        f"Right now it is: {time_str}\n"
        f"Use this for accurate timing.\n\n"
    )
    prompt_body = sys_p
    if mem_str:
        prompt_body = mem_str + "\n\n" + prompt_body
    if learned_knowledge:
        prompt_body = learned_knowledge + "\n" + prompt_body
    if operator_ctx:
        prompt_body = operator_ctx + prompt_body
    return time_ctx + sensory_p + prompt_body

# FULL MODULE DECLARATIONS
MODULE_DECLARATIONS = [
    {"name": "open_app", "description": "Opens system applications.", "parameters": {"type": "OBJECT", "properties": {"app_name": {"type": "STRING"}}, "required": ["app_name"]}},
    {"name": "web_search", "description": "Global information retrieval.", "parameters": {"type": "OBJECT", "properties": {"query": {"type": "STRING"}}, "required": ["query"]}},
    {"name": "weather_report", "description": "Environmental synchronization.", "parameters": {"type": "OBJECT", "properties": {"city": {"type": "STRING"}}, "required": ["city"]}},
    {"name": "send_message", "description": "Sends messages via WhatsApp, Telegram, Instagram, or Discord. When background is true, use API-based sending if available instead of foreground UI automation.", "parameters": {"type": "OBJECT", "properties": {"receiver": {"type": "STRING"}, "receiver_phone": {"type": "STRING"}, "message_text": {"type": "STRING"}, "platform": {"type": "STRING", "enum": ["whatsapp", "telegram", "instagram", "discord"]}, "background": {"type": "BOOLEAN"}}, "required": ["receiver", "message_text"]}},
    {"name": "reminder", "description": "Sets a reminder for a specific date and time.", "parameters": {"type": "OBJECT", "properties": {"date": {"type": "STRING", "description": "YYYY-MM-DD"}, "time": {"type": "STRING", "description": "HH:MM"}, "message": {"type": "STRING"}}, "required": ["date", "time", "message"]}},
    {"name": "computer_settings", "description": "Controls system settings like volume, brightness, and window management.", "parameters": {"type": "OBJECT", "properties": {"action": {"type": "STRING"}, "description": {"type": "STRING"}, "value": {"type": "STRING"}}, "required": []}},
    {"name": "screen_process", "description": "Analyzes screen content or takes a screenshot.", "parameters": {"type": "OBJECT", "properties": {"text": {"type": "STRING"}}, "required": ["text"]}},
    {"name": "youtube_video", "description": "Plays or summarizes YouTube videos.", "parameters": {"type": "OBJECT", "properties": {"action": {"type": "STRING", "enum": ["play", "summarize", "get_info", "trending"]}, "query": {"type": "STRING"}, "url": {"type": "STRING"}}, "required": []}},
    {"name": "desktop_control", "description": "Manages desktop wallpaper, files, and organization.", "parameters": {"type": "OBJECT", "properties": {"action": {"type": "STRING"}, "task": {"type": "STRING"}, "path": {"type": "STRING"}}, "required": []}},
    {"name": "browser_control", "description": "Controls the web browser (navigation, clicking, typing).", "parameters": {"type": "OBJECT", "properties": {"action": {"type": "STRING"}, "url": {"type": "STRING"}, "query": {"type": "STRING"}, "text": {"type": "STRING"}}, "required": []}},
    {"name": "code_helper", "description": "Assists with coding tasks (write, edit, explain, run, optimize).", "parameters": {"type": "OBJECT", "properties": {"action": {"type": "STRING"}, "description": {"type": "STRING"}, "language": {"type": "STRING"}}, "required": ["description"]}},
    {"name": "dev_agent", "description": "Builds full projects from a description.", "parameters": {"type": "OBJECT", "properties": {"description": {"type": "STRING"}, "language": {"type": "STRING"}, "project_name": {"type": "STRING"}}, "required": ["description"]}},
    {"name": "computer_control", "description": "Atomic mouse and keyboard control.", "parameters": {"type": "OBJECT", "properties": {"action": {"type": "STRING"}, "text": {"type": "STRING"}, "x": {"type": "INTEGER"}, "y": {"type": "INTEGER"}}, "required": []}},
    {"name": "file_controller", "description": "Manages local files and folders (list, create, delete, move, rename).", "parameters": {"type": "OBJECT", "properties": {"action": {"type": "STRING"}, "path": {"type": "STRING"}, "name": {"type": "STRING"}}, "required": []}},
    {"name": "game_control", "description": "Controls an open game window such as Minecraft using keyboard and mouse input, and can run macros or saved routines.", "parameters": {"type": "OBJECT", "properties": {"game": {"type": "STRING"}, "action": {"type": "STRING", "enum": ["focus", "move_forward", "move_backward", "strafe_left", "strafe_right", "sprint_forward", "jump", "crouch", "attack", "use", "inventory", "drop", "slot", "look", "press_key", "hold_key", "mouse_button", "chat", "command", "wait", "macro", "routine"]}, "description": {"type": "STRING"}, "seconds": {"type": "NUMBER"}, "key": {"type": "STRING"}, "button": {"type": "STRING", "enum": ["left", "right", "middle"]}, "text": {"type": "STRING"}, "steps_text": {"type": "STRING"}, "routine_name": {"type": "STRING"}, "slot": {"type": "INTEGER"}, "dx": {"type": "INTEGER"}, "dy": {"type": "INTEGER"}, "repeat": {"type": "INTEGER"}}, "required": []}},
    {"name": "spotify_control", "description": "Controls the Spotify desktop app for playback, track switching, and search. When background is true, prefer API/background control over window focus.", "parameters": {"type": "OBJECT", "properties": {"action": {"type": "STRING", "enum": ["focus", "play_pause", "next_track", "previous_track", "search", "search_and_play", "shuffle", "repeat", "like", "mute"]}, "query": {"type": "STRING"}, "description": {"type": "STRING"}, "focus_window": {"type": "BOOLEAN"}, "background": {"type": "BOOLEAN"}}, "required": []}},
    {"name": "performance_optimize", "description": "Analyzes system performance and manages safe optimization features like auto game mode, live monitoring, network checks, overlay, thermal guard, heavy app audits, browser audits, startup audits, profiles, history, and one-command game prep.", "parameters": {"type": "OBJECT", "properties": {"action": {"type": "STRING", "enum": ["analyze", "smart_optimize", "boost", "cleanup", "restore", "network_status", "network_monitor", "overlay", "battery_status", "disk_health", "driver_inventory", "history_report", "benchmark", "undo_last", "auto_game_mode", "monitor", "thermal_status", "app_audit", "trim_apps", "browser_audit", "browser_optimize", "startup_audit", "startup_disable", "startup_restore", "profile", "prep_game", "status"]}, "description": {"type": "STRING"}, "top_n": {"type": "INTEGER"}, "min_age_hours": {"type": "INTEGER"}, "min_memory_mb": {"type": "INTEGER"}, "history_hours": {"type": "INTEGER"}, "benchmark_seconds": {"type": "INTEGER"}, "sample_interval": {"type": "NUMBER"}, "profile_name": {"type": "STRING"}, "enabled": {"type": "BOOLEAN"}, "mode": {"type": "STRING"}, "target": {"type": "STRING"}, "targets": {"type": "STRING"}, "confirm_close": {"type": "BOOLEAN"}, "confirm_disable": {"type": "BOOLEAN"}}, "required": []}},
    {"name": "knowledge_memory", "description": "Looks up long-term learned knowledge, researches unknown topics from Wikipedia and web sources, and stores them in semantic memory with embeddings for future recall.", "parameters": {"type": "OBJECT", "properties": {"action": {"type": "STRING", "enum": ["lookup", "research", "remember_text", "stats"]}, "query": {"type": "STRING"}, "topic": {"type": "STRING"}, "text": {"type": "STRING"}, "top_k": {"type": "INTEGER"}, "refresh": {"type": "BOOLEAN"}}, "required": []}},
    {"name": "task_queue", "description": "Queues background tool tasks like Spotify control, message sending, performance actions, knowledge research, reminders, and game macros for delayed or sequential execution.", "parameters": {"type": "OBJECT", "properties": {"action": {"type": "STRING", "enum": ["enqueue", "list", "clear", "remove", "run_next", "start_worker", "stop_worker", "status", "history"]}, "tool": {"type": "STRING", "enum": ["open_app", "send_message", "spotify_control", "performance_optimize", "knowledge_memory", "game_control", "reminder"]}, "label": {"type": "STRING"}, "task_id": {"type": "STRING"}, "parameters_json": {"type": "STRING"}, "delay_seconds": {"type": "INTEGER"}, "only_if_not_gaming": {"type": "BOOLEAN"}, "auto_start": {"type": "BOOLEAN"}}, "required": []}},
    {"name": "cmd_control", "description": "Executes shell commands directly.", "parameters": {"type": "OBJECT", "properties": {"command": {"type": "STRING"}}, "required": ["command"]}},
    {"name": "vision_control", "description": "Toggles visual analysis mode.", "parameters": {"type": "OBJECT", "properties": {"mode": {"type": "STRING", "enum": ["on", "off"]}}, "required": ["mode"]}}
]

class VisionWatcher:
    """The 'Eyes' of mirai — Periodically scans screen/camera."""
    def __init__(self, ui):
        self.ui = ui
        self.active = True

    def _get_frame(self):
        try:
            scr = pyautogui.screenshot()
            scr = scr.resize((600, 360))
            return "Visible: Windows Desktop. User active."
        except: return "Visual feed interrupted."

    def start(self):
        def loop():
            while self.active:
                SENSORY_HUB["visual_context"] = self._get_frame()
                time.sleep(120) # Update context every 2 min
        threading.Thread(target=loop, daemon=True).start()

class ProactiveHeartbeat:
    """The 'Nervous System' — Detects system anomalies."""
    def __init__(self, ui):
        self.ui = ui

    def start(self):
        def loop():
            while True:
                cpu = psutil.cpu_percent()
                if cpu > 85:
                    SENSORY_HUB["system_health"] = "High Load (CPU Alert)"
                    self.ui.write_log(f"ALERT: CPU spike detected ({cpu}%)")
                else:
                    SENSORY_HUB["system_health"] = "Stable"
                time.sleep(15)
        threading.Thread(target=loop, daemon=True).start()

class MiraiLive:
    def __init__(self, ui: MiraiUI):
        self.ui             = ui
        self.session        = None
        self.audio_in_queue = asyncio.Queue() # Dummy for linter
        self.out_queue      = asyncio.Queue() # Dummy for linter
        self._loop          = None
        self.vision_watcher = VisionWatcher(self.ui)
        self._assistant_log_buffer = ""

    def _merge_stream_text(self, existing: str, chunk: str) -> str:
        left = str(existing or "").strip()
        right = str(chunk or "").strip()
        if not right:
            return left
        if not left:
            return right
        if right == left or left.endswith(right):
            return left
        if right.startswith(left):
            return right

        overlap_max = min(len(left), len(right))
        for size in range(overlap_max, 0, -1):
            if left[-size:].lower() == right[:size].lower():
                return left + right[size:]

        if left[-1].isspace() or right[0] in ".,!?;:)]}%":
            joiner = ""
        elif left[-1] in "([{\"'":
            joiner = ""
        else:
            joiner = " "
        return left + joiner + right

    def _build_config(self) -> types.LiveConnectConfig:
        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            output_audio_transcription={},
            input_audio_transcription={},
            system_instruction=_get_full_prompt(),
            tools=[{"function_declarations": MODULE_DECLARATIONS}],
            session_resumption=types.SessionResumptionConfig(),
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Charon")
                )
            ),
        )

    def speak_text(self, text: str):
        pass

    async def _execute_tool(self, fc) -> types.FunctionResponse:
        name = fc.name; args = dict(fc.args or {})
        loop = asyncio.get_event_loop(); result = "Acknowledged."
        
        # Tool Mapping System
        TOOL_MAP = {
            "open_app":          lambda: open_app(parameters=args, player=self.ui),
            "web_search":        lambda: web_search_action(parameters=args, player=self.ui),
            "weather_report":    lambda: weather_action(parameters=args, player=self.ui),
            "send_message":      lambda: send_message(parameters=args, player=self.ui),
            "reminder":          lambda: reminder(parameters=args, player=self.ui),
            "computer_settings": lambda: computer_settings(parameters=args, player=self.ui),
            "youtube_video":     lambda: youtube_video(parameters=args, player=self.ui),
            "desktop_control":   lambda: desktop_control(parameters=args, player=self.ui),
            "browser_control":   lambda: browser_control(parameters=args, player=self.ui),
            "code_helper":       lambda: code_helper(parameters=args, player=self.ui),
            "dev_agent":         lambda: dev_agent(parameters=args, player=self.ui),
            "computer_control":  lambda: computer_control(parameters=args, player=self.ui),
            "file_controller":   lambda: file_controller(parameters=args, player=self.ui),
            "game_control":      lambda: game_control(parameters=args, player=self.ui),
            "spotify_control":   lambda: spotify_control(parameters=args, player=self.ui),
            "performance_optimize": lambda: performance_optimize(parameters=args, player=self.ui),
            "knowledge_memory":  lambda: knowledge_memory(parameters=args, player=self.ui),
            "task_queue":        lambda: task_queue(parameters=args, player=self.ui),
            "cmd_control":       lambda: cmd_control(parameters=args, player=self.ui)
        }

        try:
            if name in TOOL_MAP:
                r = await loop.run_in_executor(None, TOOL_MAP[name])
                result = r or f"Processed {name}."
            elif name == "screen_process":
                threading.Thread(target=screen_process, kwargs={"parameters": args, "player": self.ui}, daemon=True).start()
                result = "Analyzing screen context..."
            elif name == "vision_control":
                mode = args.get("mode", "off")
                self.vision_watcher.active = (mode == "on")
                result = f"Visual tele-sync {mode}, efendim."
            else:
                result = f"Command {name} executed."
        except Exception as e:
            result = f"Neural Error: {e}"
        
        return types.FunctionResponse(id=fc.id, name=name, response={"result": result})

    async def _send_realtime(self):
        while True:
            msg = await self.out_queue.get()
            if self.session and self.out_queue:
                try: await self.session.send_realtime_input(media=msg)
                except: pass

    async def _listen_audio(self):
        logger.info("🎤 Mic sensing active")
        stream = await asyncio.to_thread(
            pya.open, format=PA_FORMAT, channels=CHANNELS, rate=SEND_SAMPLE_RATE, input=True, frames_per_buffer=CHUNK_SIZE
        )
        try:
            while True:
                data = await asyncio.to_thread(stream.read, CHUNK_SIZE, exception_on_overflow=False)
                # Only send audio if mirai is NOT speaking to avoid echo loop
                if not self.ui.speaking:
                    await self.out_queue.put({"data": data, "mime_type": "audio/pcm"})
        except Exception as e:
            logger.error(f"[mirai] 🎤 Mic fatal: {e}")
            raise
        finally: stream.close()

    async def _receive_audio(self):
        logger.info("[mirai] 👂 Downlink active")
        try:
            while True:
                if not self.session: break
                turn = self.session.receive()
                async for response in turn:
                    if not self.session: break
                    if response.data:
                        self.audio_in_queue.put_nowait(response.data)

                    if response.server_content:
                        sc = response.server_content
                        # Multi-attribute mapping
                        it = getattr(sc, 'input_transcription', None) or getattr(sc, 'input_audio_transcription', None)
                        if it and it.text:
                            logger.info(f"USER: {it.text}")
                            self.ui.write_log(f"You: {it.text}")
                        
                        ot = getattr(sc, 'output_transcription', None) or getattr(sc, 'output_audio_transcription', None)
                        if ot and ot.text:
                            self._assistant_log_buffer = self._merge_stream_text(self._assistant_log_buffer, ot.text)
                            self.ui.write_log(f"mirai: {ot.text}")

                        if sc.interrupted:
                            while not self.audio_in_queue.empty(): self.audio_in_queue.get_nowait()
                            if self._assistant_log_buffer:
                                logger.info(f"AI: {self._assistant_log_buffer}")
                                self._assistant_log_buffer = ""
                            self.ui.finish_stream()
                            self.ui.stop_speaking(); self.ui.write_log("SYS: Interrupted.")
                        
                        if sc.turn_complete:
                            if self._assistant_log_buffer:
                                logger.info(f"AI: {self._assistant_log_buffer}")
                                self._assistant_log_buffer = ""
                            self.ui.finish_stream()
                            # We don't stop speaking here because audio might still be in playback queue

                    if response.tool_call:
                        fn_responses = []
                        for fc in response.tool_call.function_calls:
                            logger.info(f"[mirai] 📞 Tool: {fc.name}")
                            fr = await self._execute_tool(fc)
                            fn_responses.append(fr)
                        await self.session.send_tool_response(function_responses=fn_responses)
        except Exception as e:
            logger.error(f"[mirai] 👂 Downlink fatal: {e}")
            traceback.print_exc()

    async def _play_audio(self):
        logger.info("🔊 Neural speaker active")
        stream = await asyncio.to_thread(
            pya.open, format=PA_FORMAT, channels=CHANNELS, rate=RECEIVE_SAMPLE_RATE, output=True, frames_per_buffer=1024
        )
        try:
            while True:
                if self.audio_in_queue is None:
                    await asyncio.sleep(0.1)
                    continue
                chunk = await self.audio_in_queue.get()
                self.ui.start_speaking() # Signal UI and mute Mic
                await asyncio.to_thread(stream.write, chunk)
                if self.audio_in_queue.empty():
                    self.ui.stop_speaking() # Unmute Mic and signal UI
        except Exception as e:
            logger.error(f"[mirai] 🔊 Speaker fatal: {e}")
            raise
        finally: stream.close()

    async def run_session(self):
        logger.info("[mirai] 🚀 Neural Hub Booting...")
        
        # Wait for API Authorization if needed
        while not self.ui._api_key_ready:
            logger.info("[mirai] ⚠ Waiting for API Master Key authorization...")
            await asyncio.sleep(2)

        self.vision_watcher.start()
        ProactiveHeartbeat(self.ui).start()

        while True:
            try:
                # Initialize queues within the session loop to ensure they attach to the correct event loop
                self.audio_in_queue = asyncio.Queue()
                self.out_queue      = asyncio.Queue(maxsize=100)
                client = genai.Client(api_key=_get_api_key(), http_options={"api_version": "v1alpha"})
                
                async with (
                    client.aio.live.connect(model=LIVE_MODEL, config=self._build_config()) as session,
                    asyncio.TaskGroup() as tg
                ):
                    self.session = session; self._loop = asyncio.get_event_loop()
                    self.ui.write_log("SYS: Neural Engine ONLINE.")
                    logger.info("[mirai] ✨ Link Established.")
                    
                    # Proactive Activation Greeting
                    try:
                        await session.send_realtime_input(text="Çevrim içi ve emrinizdeyim efendim.")
                    except: pass
                    
                    tg.create_task(self._send_realtime())
                    tg.create_task(self._listen_audio())
                    tg.create_task(self._receive_audio())
                    tg.create_task(self._play_audio())
            except Exception as e:
                logger.error(f"[mirai] ❌ Hub Crash: {e}"); await asyncio.sleep(2)

    def start(self):
        threading.Thread(target=lambda: asyncio.run(self.run_session()), daemon=True).start()
        self.ui.root.mainloop()

if __name__ == "__main__":
    app_ui = MiraiUI(); core = MiraiLive(app_ui); core.start()
