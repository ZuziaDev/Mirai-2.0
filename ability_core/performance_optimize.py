import ctypes
import json
import os
import platform
import re
import shutil
import subprocess
import tempfile
import threading
import time
import tkinter as tk
from ctypes import wintypes
from pathlib import Path

import psutil


BALANCED_PLAN_GUID = "381b4222-f694-41f0-9685-ff5bb260df2e"
HIGH_PERFORMANCE_GUID = "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"
ULTIMATE_PERFORMANCE_GUID = "e9a42b02-d5df-448d-aa00-03f14749eb61"

BASE_DIR = Path(__file__).resolve().parent.parent
VAULT_DIR = BASE_DIR / "security_vault"
PERFORMANCE_CONFIG_PATH = VAULT_DIR / "performance.json"
DISABLED_STARTUP_PATH = VAULT_DIR / "disabled_startup.json"
DISABLED_STARTUP_DIR = VAULT_DIR / "disabled_startup"
PERFORMANCE_HISTORY_PATH = VAULT_DIR / "performance_history.jsonl"
ACTION_HISTORY_PATH = VAULT_DIR / "performance_actions.jsonl"

_AUTO_GAME_LOCK = threading.Lock()
_AUTO_GAME_STATE = {
    "enabled": False,
    "thread": None,
    "stop_event": None,
    "boosted": False,
    "current_game": "",
    "current_keyword": "",
    "applied_profile": "",
    "player": None,
}

_MONITOR_LOCK = threading.Lock()
_MONITOR_STATE = {
    "enabled": False,
    "thread": None,
    "stop_event": None,
    "last_alert": "",
    "player": None,
}

_NETWORK_LOCK = threading.Lock()
_NETWORK_STATE = {
    "enabled": False,
    "thread": None,
    "stop_event": None,
    "last_alert": "",
    "player": None,
    "target": "",
}

_OVERLAY_LOCK = threading.Lock()
_OVERLAY_STATE = {
    "enabled": False,
    "window": None,
    "label": None,
    "player": None,
}


def _default_config() -> dict:
    return {
        "watch_interval_seconds": 10,
        "monitor_interval_seconds": 15,
        "cpu_alert_percent": 90,
        "ram_alert_percent": 88,
        "disk_alert_percent": 92,
        "temperature_alert_c": 85,
        "thermal_guard_enabled": True,
        "thermal_guard_restore_c": 88,
        "history_limit": 5000,
        "network_targets": [
            "1.1.1.1",
            "8.8.8.8",
            "google.com"
        ],
        "network_alert_ms": 120,
        "packet_loss_alert_percent": 35,
        "overlay_refresh_seconds": 2,
        "game_keywords": [
            "minecraft",
            "valorant",
            "cs2",
            "counter-strike",
            "fortnite",
            "rocket league",
            "rocketleague",
            "league of legends",
            "leagueoflegends",
            "apex",
            "r5apex",
            "elden ring",
            "eldenring",
            "warzone",
            "call of duty",
            "roblox",
            "dota 2",
            "dota2",
            "pubg",
            "overwatch",
            "gta v",
            "gta5",
            "ea fc",
            "fifa",
        ],
        "game_profiles": {
            "minecraft": "gaming",
            "valorant": "gaming",
            "cs2": "gaming",
            "fortnite": "gaming",
            "league of legends": "gaming",
            "roblox": "gaming"
        },
        "browser_process_names": [
            "chrome.exe",
            "msedge.exe",
            "firefox.exe",
            "opera.exe",
            "brave.exe",
        ],
        "non_essential_apps": [
            "discord",
            "chrome",
            "msedge",
            "firefox",
            "opera",
            "brave",
            "telegram",
            "whatsapp",
            "teams",
            "spotify",
            "epicgameslauncher",
            "riotclientservices",
            "riot client",
            "battle.net",
            "steamwebhelper",
            "onedrive",
        ],
        "startup_keywords": [
            "discord",
            "spotify",
            "epic",
            "riot",
            "teams",
            "onedrive",
            "telegram",
            "whatsapp",
            "steam",
        ],
        "profiles": {
            "gaming": {
                "power_mode": "boost",
                "cleanup_temp": True,
                "min_age_hours": 6,
                "start_monitor": True,
                "start_auto_game_mode": True,
                "thermal_check": True,
                "browser_audit": True,
                "app_audit": True,
                "startup_audit": False,
            },
            "work": {
                "power_mode": "restore",
                "cleanup_temp": False,
                "min_age_hours": 24,
                "start_monitor": False,
                "start_auto_game_mode": False,
                "thermal_check": False,
                "browser_audit": False,
                "app_audit": False,
                "startup_audit": False,
            },
            "silent": {
                "power_mode": "restore",
                "cleanup_temp": True,
                "min_age_hours": 24,
                "start_monitor": False,
                "start_auto_game_mode": False,
                "thermal_check": True,
                "browser_audit": False,
                "app_audit": False,
                "startup_audit": False,
            },
            "battery": {
                "power_mode": "restore",
                "cleanup_temp": False,
                "min_age_hours": 24,
                "start_monitor": False,
                "start_auto_game_mode": False,
                "thermal_check": False,
                "browser_audit": False,
                "app_audit": False,
                "startup_audit": False,
            },
        },
    }


def _load_json(path: Path) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def _deep_merge(base: dict, override: dict) -> dict:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _load_config() -> dict:
    default = _default_config()
    if not PERFORMANCE_CONFIG_PATH.exists():
        _save_json(PERFORMANCE_CONFIG_PATH, default)
        return default
    return _deep_merge(default, _load_json(PERFORMANCE_CONFIG_PATH))


def _default_startup_backup() -> dict:
    return {"registry": [], "shortcuts": []}


def _load_startup_backup() -> dict:
    data = _load_json(DISABLED_STARTUP_PATH)
    if not data:
        return _default_startup_backup()
    return {
        "registry": data.get("registry", []) if isinstance(data.get("registry"), list) else [],
        "shortcuts": data.get("shortcuts", []) if isinstance(data.get("shortcuts"), list) else [],
    }


def _save_startup_backup(data: dict) -> None:
    _save_json(DISABLED_STARTUP_PATH, data)


def _append_jsonl(path: Path, payload: dict, limit: int = 5000) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(payload, ensure_ascii=False)
        existing = []
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    existing = [row.rstrip("\n") for row in handle.readlines() if row.strip()]
            except Exception:
                existing = []
        existing.append(line)
        if len(existing) > max(100, int(limit or 5000)):
            existing = existing[-max(100, int(limit or 5000)) :]
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("\n".join(existing))
            if existing:
                handle.write("\n")
    except Exception:
        return


def _load_jsonl(path: Path, limit: int = 200) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    try:
        with open(path, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
    except Exception:
        return []
    if limit:
        return rows[-limit:]
    return rows


def _record_history(event_type: str, payload: dict | None = None) -> None:
    config = _load_config()
    item = {
        "ts": int(time.time()),
        "event_type": event_type,
        "data": payload or {},
    }
    _append_jsonl(PERFORMANCE_HISTORY_PATH, item, limit=config.get("history_limit", 5000))


def _record_action(action: str, payload: dict | None = None) -> None:
    config = _load_config()
    item = {
        "ts": int(time.time()),
        "action": action,
        "data": payload or {},
    }
    _append_jsonl(ACTION_HISTORY_PATH, item, limit=config.get("history_limit", 5000))


def _normalize_text(text: str) -> str:
    replacements = str.maketrans(
        {
            "ç": "c",
            "Ç": "c",
            "ğ": "g",
            "Ğ": "g",
            "ı": "i",
            "İ": "i",
            "ö": "o",
            "Ö": "o",
            "ş": "s",
            "Ş": "s",
            "ü": "u",
            "Ü": "u",
            "ý": "y",
            "Ý": "y",
        }
    )
    return str(text or "").translate(replacements).casefold()


def _format_bytes(value: float) -> str:
    size = float(max(0, value))
    units = ["B", "KB", "MB", "GB", "TB"]
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def _safe_filename(text: str) -> str:
    cleaned = re.sub(r'[^A-Za-z0-9._ -]+', "_", text or "").strip()
    return cleaned or f"item_{int(time.time())}"


def _parse_targets(value) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        chunks = re.split(r"[,;\n]+", value)
        return [chunk.strip() for chunk in chunks if chunk.strip()]
    return []


def _emit_log(player, text: str, alert: bool = False) -> None:
    if not player:
        return
    try:
        if hasattr(player, "write_log"):
            player.write_log(text)
        if alert and hasattr(player, "show_proactive_alert"):
            player.show_proactive_alert(text)
    except Exception:
        return


def _run_command(command: list[str]) -> tuple[bool, str]:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=30,
        )
        output = ((completed.stdout or "") + (completed.stderr or "")).strip()
        return completed.returncode == 0, output
    except Exception as exc:
        return False, str(exc)


def _foreground_window_info() -> dict:
    if platform.system() != "Windows":
        return {}

    try:
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return {}

        length = user32.GetWindowTextLengthW(hwnd)
        buffer = ctypes.create_unicode_buffer(max(1, length + 1))
        user32.GetWindowTextW(hwnd, buffer, len(buffer))

        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

        info = {
            "pid": int(pid.value or 0),
            "title": (buffer.value or "").strip(),
            "name": "",
            "exe": "",
            "cmdline": "",
        }

        if info["pid"]:
            proc = psutil.Process(info["pid"])
            info["name"] = proc.name()
            try:
                info["exe"] = proc.exe()
            except Exception:
                info["exe"] = ""
            try:
                info["cmdline"] = " ".join(proc.cmdline())
            except Exception:
                info["cmdline"] = ""
        return info
    except Exception:
        return {}


def _keyword_match(text: str, keywords: list[str]) -> str:
    normalized = _normalize_text(text)
    for keyword in keywords:
        if _normalize_text(keyword) in normalized:
            return keyword
    return ""


def _sample_processes(include_details: bool = False) -> list[dict]:
    processes = []
    cpu_scale = max(psutil.cpu_count() or 1, 1)

    try:
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                proc.cpu_percent(None)
                processes.append(proc)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        time.sleep(0.35)
    except Exception:
        return []

    rows = []
    for proc in processes:
        try:
            name = proc.info.get("name") or "unknown"
            if proc.pid == 0 or "idle" in name.casefold():
                continue

            row = {
                "pid": proc.pid,
                "name": name,
                "cpu": proc.cpu_percent(None) / cpu_scale,
                "memory": proc.memory_percent(),
                "rss": proc.memory_info().rss,
            }

            if include_details:
                try:
                    row["exe"] = proc.exe()
                except Exception:
                    row["exe"] = ""
                try:
                    row["cmdline"] = " ".join(proc.cmdline())
                except Exception:
                    row["cmdline"] = ""

            rows.append(row)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    rows.sort(key=lambda item: (item["cpu"], item["rss"]), reverse=True)
    return rows


def _collect_top_processes(top_n: int) -> list[dict]:
    return _sample_processes(include_details=False)[: max(1, int(top_n or 5))]


def _read_power_plans() -> list[dict]:
    if platform.system() != "Windows":
        return []

    ok, output = _run_command(["powercfg", "/L"])
    if not ok and not output:
        return []

    plans = []
    pattern = re.compile(r"([A-Fa-f0-9-]{36})\s+\(([^)]+)\)(\s+\*)?")
    for match in pattern.finditer(output):
        plans.append(
            {
                "guid": match.group(1).lower(),
                "name": match.group(2).strip(),
                "active": bool(match.group(3)),
            }
        )
    return plans


def _current_power_plan(plans: list[dict]) -> dict | None:
    for plan in plans:
        if plan.get("active"):
            return plan
    return None


def _select_boost_plan(plans: list[dict]) -> dict | None:
    ranked = []
    for plan in plans:
        name = _normalize_text(plan["name"])
        guid = plan["guid"].lower()

        score = None
        if guid == ULTIMATE_PERFORMANCE_GUID or "ultimate" in name:
            score = 0
        elif guid == HIGH_PERFORMANCE_GUID:
            score = 1
        elif "high performance" in name or "yuksek performans" in name:
            score = 2
        elif "high" in name or "yuksek" in name:
            score = 3

        if score is not None:
            ranked.append((score, plan))

    if not ranked:
        return None

    ranked.sort(key=lambda item: item[0])
    return ranked[0][1]


def _select_balanced_plan(plans: list[dict]) -> dict | None:
    for plan in plans:
        name = _normalize_text(plan["name"])
        guid = plan["guid"].lower()
        if guid == BALANCED_PLAN_GUID or "balanced" in name or "dengeli" in name:
            return plan
    return None


def _switch_power_plan(plan: dict) -> tuple[bool, str]:
    ok, output = _run_command(["powercfg", "/S", plan["guid"]])
    if not ok:
        return False, output or f"Could not switch to {plan['name']}."
    return True, f"Power plan switched to {plan['name']}."


def _set_power_mode(mode: str) -> tuple[bool, str]:
    if platform.system() != "Windows":
        return False, "Power-plan optimization is currently implemented for Windows only."

    plans = _read_power_plans()
    current = _current_power_plan(plans)
    target = _select_boost_plan(plans) if mode == "boost" else _select_balanced_plan(plans)

    if not target:
        if mode == "boost":
            return False, "No high-performance power plan was found."
        return False, "Balanced power plan was not found."

    if current and current["guid"] == target["guid"]:
        return True, f"Power plan is already {target['name']}."

    return _switch_power_plan(target)


def _estimate_size(path: Path) -> int:
    try:
        if path.is_file():
            return path.stat().st_size
    except Exception:
        return 0

    total = 0
    try:
        for root, _, files in os.walk(path, onerror=lambda *_: None):
            for filename in files:
                file_path = Path(root) / filename
                try:
                    total += file_path.stat().st_size
                except Exception:
                    continue
    except Exception:
        return total
    return total


def _temp_paths() -> list[Path]:
    temp_value = os.environ.get("TEMP") or tempfile.gettempdir()
    tmp_value = os.environ.get("TMP") or tempfile.gettempdir()
    items = {
        Path(tempfile.gettempdir()),
        Path(temp_value),
        Path(tmp_value),
    }

    local_appdata = os.environ.get("LOCALAPPDATA") or ""
    if local_appdata:
        items.add(Path(local_appdata) / "Temp")

    return [path for path in items if str(path).strip()]


def _cleanup_temp(min_age_hours: int = 6) -> str:
    min_age_seconds = max(0, int(min_age_hours or 0)) * 3600
    now = time.time()
    freed_bytes = 0
    removed_files = 0
    removed_dirs = 0
    skipped = 0

    seen = set()
    for temp_dir in _temp_paths():
        key = str(temp_dir).lower()
        if key in seen or not temp_dir.exists():
            continue
        seen.add(key)

        try:
            children = list(temp_dir.iterdir())
        except Exception:
            continue

        for item in children:
            try:
                age = now - item.stat().st_mtime
                if age < min_age_seconds:
                    continue

                size = _estimate_size(item)
                if item.is_dir() and not item.is_symlink():
                    shutil.rmtree(item)
                    removed_dirs += 1
                else:
                    item.unlink()
                    removed_files += 1

                freed_bytes += size
            except Exception:
                skipped += 1

    if removed_files == 0 and removed_dirs == 0:
        return (
            "Temp cleanup finished. Nothing old enough to remove, or files were locked "
            "by active applications."
        )

    return (
        "Temp cleanup finished. "
        f"Removed {removed_files} files and {removed_dirs} folders, "
        f"freed about {_format_bytes(freed_bytes)}, skipped {skipped} locked items."
    )


def _read_temperatures() -> dict:
    readings = {"cpu_c": None, "gpu": []}

    if platform.system() == "Windows":
        ok, output = _run_command(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-WmiObject -Namespace root/wmi -Class MSAcpi_ThermalZoneTemperature | "
                "Select-Object -ExpandProperty CurrentTemperature",
            ]
        )
        if ok and output:
            values = []
            for line in output.splitlines():
                line = line.strip()
                if not line.isdigit():
                    continue
                raw = int(line)
                celsius = (raw / 10.0) - 273.15
                if 10 <= celsius <= 120:
                    values.append(celsius)
            if values:
                readings["cpu_c"] = round(max(values), 1)

    ok, output = _run_command(
        [
            "nvidia-smi",
            "--query-gpu=name,temperature.gpu,fan.speed,utilization.gpu,utilization.memory,memory.used,memory.total",
            "--format=csv,noheader,nounits",
        ]
    )
    if ok and output:
        for line in output.splitlines():
            parts = [part.strip() for part in line.split(",")]
            if len(parts) < 2:
                continue
            try:
                temp_c = float(parts[1])
            except Exception:
                continue

            fan_percent = None
            if len(parts) >= 3 and parts[2].replace(".", "", 1).isdigit():
                fan_percent = float(parts[2])
            gpu_util = None
            if len(parts) >= 4 and parts[3].replace(".", "", 1).isdigit():
                gpu_util = float(parts[3])
            memory_util = None
            if len(parts) >= 5 and parts[4].replace(".", "", 1).isdigit():
                memory_util = float(parts[4])
            memory_used_mb = None
            if len(parts) >= 6 and parts[5].replace(".", "", 1).isdigit():
                memory_used_mb = float(parts[5])
            memory_total_mb = None
            if len(parts) >= 7 and parts[6].replace(".", "", 1).isdigit():
                memory_total_mb = float(parts[6])

            readings["gpu"].append(
                {
                    "name": parts[0] or "GPU",
                    "temp_c": temp_c,
                    "fan_percent": fan_percent,
                    "gpu_util": gpu_util,
                    "memory_util": memory_util,
                    "memory_used_mb": memory_used_mb,
                    "memory_total_mb": memory_total_mb,
                }
            )

    return readings


def _thermal_status() -> str:
    readings = _read_temperatures()
    lines = ["Thermal status:"]
    if readings.get("cpu_c") is not None:
        lines.append(f"- CPU temp: {readings['cpu_c']:.1f} C")
    for gpu in readings.get("gpu", []):
        fan_text = ""
        if gpu.get("fan_percent") is not None:
            fan_text = f" | fan {gpu['fan_percent']:.0f}%"
        util_text = ""
        if gpu.get("gpu_util") is not None:
            util_text += f" | gpu {gpu['gpu_util']:.0f}%"
        if gpu.get("memory_util") is not None:
            util_text += f" | vram {gpu['memory_util']:.0f}%"
        if gpu.get("memory_used_mb") is not None and gpu.get("memory_total_mb") is not None:
            util_text += (
                f" | {_format_bytes(gpu['memory_used_mb'] * 1024 * 1024)}"
                f"/{_format_bytes(gpu['memory_total_mb'] * 1024 * 1024)}"
            )
        lines.append(f"- {gpu['name']}: {gpu['temp_c']:.1f} C{fan_text}{util_text}")
    if len(lines) == 1:
        lines.append("- No temperature sensor data is available on this system.")
    return "\n".join(lines)


def _battery_status() -> str:
    battery = psutil.sensors_battery()
    if battery is None:
        return "Battery status: No battery detected on this system."

    if battery.secsleft in (psutil.POWER_TIME_UNLIMITED, psutil.POWER_TIME_UNKNOWN, None):
        eta = "Unknown"
    else:
        hours, remainder = divmod(int(battery.secsleft), 3600)
        minutes = remainder // 60
        eta = f"{hours}h {minutes}m"

    return (
        "Battery status:\n"
        f"- Percent: {battery.percent:.1f}%\n"
        f"- Plugged in: {'Yes' if battery.power_plugged else 'No'}\n"
        f"- Estimated time left: {eta}"
    )


def _disk_health() -> str:
    lines = ["Disk health:"]
    ok, output = _run_command(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-PhysicalDisk | Select-Object FriendlyName,MediaType,HealthStatus,OperationalStatus,Size | "
            "ConvertTo-Json -Compress",
        ]
    )
    if ok and output:
        try:
            items = json.loads(output)
            if isinstance(items, dict):
                items = [items]
            for item in items:
                size = float(item.get("Size") or 0)
                lines.append(
                    f"- {item.get('FriendlyName', 'Disk')} | {item.get('MediaType', 'Unknown')} | "
                    f"{item.get('HealthStatus', 'Unknown')} | {item.get('OperationalStatus', 'Unknown')} | "
                    f"{_format_bytes(size)}"
                )
        except Exception:
            pass

    if len(lines) == 1:
        root = Path.home().anchor or "C:\\"
        usage = psutil.disk_usage(root)
        lines.append(f"- {root} usage: {usage.percent:.1f}% of {_format_bytes(usage.total)}")
    return "\n".join(lines)


def _driver_inventory() -> str:
    lines = ["Driver inventory:"]

    video_ok, video_output = _run_command(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-CimInstance Win32_VideoController | Select-Object Name,DriverVersion,DriverDate | ConvertTo-Json -Compress",
        ]
    )
    if video_ok and video_output:
        try:
            items = json.loads(video_output)
            if isinstance(items, dict):
                items = [items]
            for item in items:
                lines.append(
                    f"- GPU: {item.get('Name', 'Unknown')} | Driver {item.get('DriverVersion', 'Unknown')} | Date {str(item.get('DriverDate', ''))[:10]}"
                )
        except Exception:
            pass

    sound_ok, sound_output = _run_command(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-CimInstance Win32_SoundDevice | Select-Object Name,Manufacturer,Status | ConvertTo-Json -Compress",
        ]
    )
    if sound_ok and sound_output:
        try:
            items = json.loads(sound_output)
            if isinstance(items, dict):
                items = [items]
            for item in items[:3]:
                lines.append(
                    f"- Audio: {item.get('Name', 'Unknown')} | {item.get('Manufacturer', 'Unknown')} | {item.get('Status', 'Unknown')}"
                )
        except Exception:
            pass

    if len(lines) == 1:
        lines.append("- Driver inventory could not be collected.")
    return "\n".join(lines)


def _ping_once(target: str) -> dict:
    target = (target or "").strip()
    if not target:
        return {"target": "", "ok": False, "latency_ms": None, "packet_loss_percent": 100, "error": "No target"}

    count_flag = "-n" if platform.system() == "Windows" else "-c"
    wait_flag = "-w" if platform.system() == "Windows" else "-W"
    ok, output = _run_command(["ping", count_flag, "1", wait_flag, "1500", target])
    text = output or ""

    latency_ms = None
    for pattern in [r"Average = (\d+)ms", r"time[=<]\s*(\d+(?:\.\d+)?)ms", r"Minimum = (\d+)ms"]:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            latency_ms = float(match.group(1))
            break

    packet_loss = None
    match = re.search(r"Lost = \d+ \((\d+)% loss\)", text, re.IGNORECASE)
    if match:
        packet_loss = float(match.group(1))
    else:
        match = re.search(r"(\d+(?:\.\d+)?)%\s*packet loss", text, re.IGNORECASE)
        if match:
            packet_loss = float(match.group(1))

    if latency_ms is None and ok:
        latency_ms = 1.0
    if packet_loss is None:
        packet_loss = 0.0 if ok else 100.0

    return {
        "target": target,
        "ok": bool(ok),
        "latency_ms": latency_ms,
        "packet_loss_percent": packet_loss,
        "raw": text[:500],
    }


def _network_status(config: dict, target: str = "") -> str:
    targets = [target] if target else config.get("network_targets", [])
    if not targets:
        return "Network status: No network target is configured."

    lines = ["Network status:"]
    best = None
    for host in targets[:3]:
        result = _ping_once(host)
        if result["ok"]:
            line = f"- {host}: {result['latency_ms']:.1f} ms | loss {result['packet_loss_percent']:.0f}%"
            if best is None or (result["latency_ms"] or 9999) < (best["latency_ms"] or 9999):
                best = result
        else:
            line = f"- {host}: ping failed"
        lines.append(line)

    if best:
        _record_history("network", best)
    return "\n".join(lines)


def _history_report(hours: int = 6, limit: int = 50) -> str:
    cutoff = int(time.time()) - max(1, int(hours or 1)) * 3600
    rows = [row for row in _load_jsonl(PERFORMANCE_HISTORY_PATH, limit=max(limit, 500)) if int(row.get("ts", 0)) >= cutoff]
    if not rows:
        return f"Performance history: No samples were recorded in the last {hours} hour(s)."

    snapshots = [row for row in rows if row.get("event_type") == "snapshot"]
    networks = [row for row in rows if row.get("event_type") == "network"]
    if not snapshots and not networks:
        return f"Performance history: No usable data was recorded in the last {hours} hour(s)."

    lines = [f"Performance history report ({hours}h):"]
    if snapshots:
        cpu_values = [float(row.get("data", {}).get("cpu_percent", 0)) for row in snapshots]
        ram_values = [float(row.get("data", {}).get("ram_percent", 0)) for row in snapshots]
        disk_values = [float(row.get("data", {}).get("disk_percent", 0)) for row in snapshots]
        lines.append(f"- Snapshots: {len(snapshots)}")
        lines.append(f"- CPU avg/max: {sum(cpu_values)/len(cpu_values):.1f}% / {max(cpu_values):.1f}%")
        lines.append(f"- RAM avg/max: {sum(ram_values)/len(ram_values):.1f}% / {max(ram_values):.1f}%")
        lines.append(f"- Disk avg/max: {sum(disk_values)/len(disk_values):.1f}% / {max(disk_values):.1f}%")

    if networks:
        latencies = [float(row.get("data", {}).get("latency_ms", 0) or 0) for row in networks if row.get("data", {}).get("latency_ms") is not None]
        losses = [float(row.get("data", {}).get("packet_loss_percent", 0) or 0) for row in networks]
        if latencies:
            lines.append(f"- Network latency avg/max: {sum(latencies)/len(latencies):.1f} ms / {max(latencies):.1f} ms")
        if losses:
            lines.append(f"- Network loss avg/max: {sum(losses)/len(losses):.1f}% / {max(losses):.1f}%")
    return "\n".join(lines)


def _benchmark(seconds: int = 15, sample_interval: float = 1.0) -> str:
    duration = max(5, min(300, int(seconds or 15)))
    interval = max(0.5, min(5.0, float(sample_interval or 1.0)))
    samples = []
    started = time.time()
    while time.time() - started < duration:
        gpu = _read_temperatures()
        sample = {
            "cpu": psutil.cpu_percent(interval=0.2),
            "ram": psutil.virtual_memory().percent,
            "gpu_temp": gpu.get("gpu", [{}])[0].get("temp_c") if gpu.get("gpu") else None,
            "gpu_util": gpu.get("gpu", [{}])[0].get("gpu_util") if gpu.get("gpu") else None,
        }
        samples.append(sample)
        time.sleep(max(0.0, interval - 0.2))

    cpu_values = [sample["cpu"] for sample in samples]
    ram_values = [sample["ram"] for sample in samples]
    gpu_temps = [sample["gpu_temp"] for sample in samples if sample["gpu_temp"] is not None]
    gpu_utils = [sample["gpu_util"] for sample in samples if sample["gpu_util"] is not None]

    result = {
        "seconds": duration,
        "samples": len(samples),
        "cpu_avg": sum(cpu_values) / len(cpu_values),
        "cpu_max": max(cpu_values),
        "ram_avg": sum(ram_values) / len(ram_values),
        "ram_max": max(ram_values),
        "gpu_temp_max": max(gpu_temps) if gpu_temps else None,
        "gpu_util_avg": (sum(gpu_utils) / len(gpu_utils)) if gpu_utils else None,
    }
    _record_history("benchmark", result)

    lines = [f"Benchmark finished ({duration}s):"]
    lines.append(f"- Samples: {result['samples']}")
    lines.append(f"- CPU avg/max: {result['cpu_avg']:.1f}% / {result['cpu_max']:.1f}%")
    lines.append(f"- RAM avg/max: {result['ram_avg']:.1f}% / {result['ram_max']:.1f}%")
    if result["gpu_temp_max"] is not None:
        lines.append(f"- GPU max temp: {result['gpu_temp_max']:.1f} C")
    if result["gpu_util_avg"] is not None:
        lines.append(f"- GPU avg load: {result['gpu_util_avg']:.1f}%")
    return "\n".join(lines)


def _overlay_text() -> str:
    plans = _read_power_plans()
    active_plan = _current_power_plan(plans)
    temps = _read_temperatures()
    parts = [f"Mode: {active_plan['name'] if active_plan else 'Unknown'}"]
    parts.append(f"CPU {psutil.cpu_percent(interval=0.0):.0f}%")
    parts.append(f"RAM {psutil.virtual_memory().percent:.0f}%")
    if temps.get("gpu"):
        gpu = temps["gpu"][0]
        parts.append(f"GPU {gpu.get('temp_c', 0):.0f}C")
        if gpu.get("gpu_util") is not None:
            parts.append(f"GPU Load {gpu['gpu_util']:.0f}%")
    return "\n".join(parts)


def _overlay_render() -> None:
    with _OVERLAY_LOCK:
        enabled = _OVERLAY_STATE["enabled"]
        player = _OVERLAY_STATE["player"]
        window = _OVERLAY_STATE["window"]
        label = _OVERLAY_STATE["label"]

    if not enabled or not player or not getattr(player, "root", None):
        return

    root = player.root
    if window is None or label is None or not bool(window.winfo_exists()):
        window = tk.Toplevel(root)
        window.overrideredirect(True)
        window.attributes("-topmost", True)
        window.configure(bg="#061014")
        window.geometry("+25+25")
        label = tk.Label(
            window,
            text="",
            justify="left",
            bg="#061014",
            fg="#7fffd4",
            font=("Consolas", 10, "bold"),
            padx=10,
            pady=8,
        )
        label.pack()
        with _OVERLAY_LOCK:
            _OVERLAY_STATE["window"] = window
            _OVERLAY_STATE["label"] = label

    try:
        label.config(text=_overlay_text())
    except Exception:
        return

    interval_ms = max(1000, int(_load_config().get("overlay_refresh_seconds", 2) * 1000))
    try:
        root.after(interval_ms, _overlay_render)
    except Exception:
        return


def _overlay_control(enabled: bool, player=None) -> str:
    with _OVERLAY_LOCK:
        if player is not None:
            _OVERLAY_STATE["player"] = player
        current_player = _OVERLAY_STATE["player"]
        if enabled and _OVERLAY_STATE["enabled"]:
            return "Performance overlay is already running."
        if not enabled and not _OVERLAY_STATE["enabled"]:
            return "Performance overlay is already stopped."
        _OVERLAY_STATE["enabled"] = enabled
        window = _OVERLAY_STATE["window"]

    if enabled:
        if not current_player or not getattr(current_player, "root", None):
            with _OVERLAY_LOCK:
                _OVERLAY_STATE["enabled"] = False
            return "Performance overlay needs the main UI to be open."
        try:
            current_player.root.after(0, _overlay_render)
            _record_action("overlay_on", {})
            return "Performance overlay started."
        except Exception as exc:
            with _OVERLAY_LOCK:
                _OVERLAY_STATE["enabled"] = False
            return f"Performance overlay failed to start: {exc}"

    if window is not None:
        try:
            current_player = current_player or _OVERLAY_STATE["player"]
            if current_player and getattr(current_player, "root", None):
                current_player.root.after(0, window.destroy)
            else:
                window.destroy()
        except Exception:
            pass

    with _OVERLAY_LOCK:
        _OVERLAY_STATE["window"] = None
        _OVERLAY_STATE["label"] = None
    _record_action("overlay_off", {})
    return "Performance overlay stopped."


def _network_monitor_loop(stop_event: threading.Event) -> None:
    while not stop_event.wait(max(5, int(_load_config().get("monitor_interval_seconds", 15)))):
        config = _load_config()
        with _NETWORK_LOCK:
            player = _NETWORK_STATE["player"]
            target = _NETWORK_STATE["target"]
            last_alert = _NETWORK_STATE["last_alert"]

        targets = [target] if target else config.get("network_targets", [])
        best = None
        for host in targets[:3]:
            result = _ping_once(host)
            if result["ok"] and (best is None or (result["latency_ms"] or 9999) < (best["latency_ms"] or 9999)):
                best = result

        if best:
            _record_history("network", best)

        message = ""
        alert_ms = float(config.get("network_alert_ms", 120))
        alert_loss = float(config.get("packet_loss_alert_percent", 35))
        if best is None:
            message = "Network alert: no ping target responded."
        elif (best.get("latency_ms") or 0) >= alert_ms or (best.get("packet_loss_percent") or 0) >= alert_loss:
            message = (
                "Network alert: "
                f"{best['target']} latency {best.get('latency_ms') or 0:.1f} ms, "
                f"loss {best.get('packet_loss_percent') or 0:.0f}%"
            )

        with _NETWORK_LOCK:
            _NETWORK_STATE["last_alert"] = message

        if message and message != last_alert:
            _emit_log(player, message, alert=True)
        elif not message and last_alert:
            _emit_log(player, "Network monitor: connection is back to normal.")


def _network_monitor(enabled: bool, player=None, target: str = "") -> str:
    with _NETWORK_LOCK:
        _NETWORK_STATE["player"] = player or _NETWORK_STATE["player"]
        if target:
            _NETWORK_STATE["target"] = target
        if enabled and _NETWORK_STATE["enabled"]:
            return "Network monitor is already running."
        if not enabled and not _NETWORK_STATE["enabled"]:
            return "Network monitor is already stopped."

        if enabled:
            stop_event = threading.Event()
            thread = threading.Thread(target=_network_monitor_loop, args=(stop_event,), daemon=True)
            _NETWORK_STATE.update(
                {
                    "enabled": True,
                    "thread": thread,
                    "stop_event": stop_event,
                    "last_alert": "",
                }
            )
            thread.start()
            _record_action("network_monitor_on", {"target": _NETWORK_STATE.get("target", "")})
            return "Network monitor started."

        stop_event = _NETWORK_STATE.get("stop_event")
        _NETWORK_STATE.update(
            {
                "enabled": False,
                "thread": None,
                "stop_event": None,
                "last_alert": "",
            }
        )

    if stop_event:
        stop_event.set()
    _record_action("network_monitor_off", {})
    return "Network monitor stopped."


def _undo_last_action() -> str:
    rows = _load_jsonl(ACTION_HISTORY_PATH, limit=30)
    if not rows:
        return "Undo history is empty."

    last = rows[-1]
    action = last.get("action", "")
    data = last.get("data", {})

    if action in {"boost", "profile_boost", "prep_game"}:
        ok, message = _set_power_mode("restore")
        return f"Undo result: {message if ok else 'Restore failed: ' + message}"
    if action == "restore":
        ok, message = _set_power_mode("boost")
        return f"Undo result: {message if ok else 'Boost failed: ' + message}"
    if action == "monitor_on":
        return "Undo result: " + _performance_monitor(False)
    if action == "monitor_off":
        return "Undo result: " + _performance_monitor(True)
    if action == "network_monitor_on":
        return "Undo result: " + _network_monitor(False)
    if action == "network_monitor_off":
        return "Undo result: " + _network_monitor(True)
    if action == "auto_game_on":
        return "Undo result: " + _auto_game_mode(False)
    if action == "auto_game_off":
        return "Undo result: " + _auto_game_mode(True)
    if action == "overlay_on":
        return "Undo result: " + _overlay_control(False)
    if action == "overlay_off":
        return "Undo result: " + _overlay_control(True)
    if action == "startup_disable":
        return "Undo result: " + _startup_restore(targets=_parse_targets(data.get("targets")))
    return f"Undo is not available for the last action: {action}"


def _performance_snapshot(top_n: int = 5, include_temps: bool = True) -> str:
    cpu = psutil.cpu_percent(interval=0.4)
    memory = psutil.virtual_memory()
    readings = {"gpu": []}

    disk_root = Path.home().anchor or "C:\\"
    try:
        disk = psutil.disk_usage(disk_root)
    except Exception:
        disk = psutil.disk_usage(str(Path.home()))

    plans = _read_power_plans()
    active_plan = _current_power_plan(plans)

    lines = [
        "Performance snapshot:",
        f"- CPU usage: {cpu:.1f}%",
        (
            f"- RAM usage: {_format_bytes(memory.used)} / {_format_bytes(memory.total)} "
            f"({memory.percent:.1f}%)"
        ),
        (
            f"- Disk usage ({disk_root}): {_format_bytes(disk.used)} / {_format_bytes(disk.total)} "
            f"({disk.percent:.1f}%)"
        ),
    ]

    if active_plan:
        lines.append(f"- Power plan: {active_plan['name']}")

    if include_temps:
        readings = _read_temperatures()
        if readings.get("cpu_c") is not None:
            lines.append(f"- CPU temp: {readings['cpu_c']:.1f} C")
        if readings.get("gpu"):
            hottest = max(readings["gpu"], key=lambda item: item.get("temp_c", 0))
            fan_text = ""
            if hottest.get("fan_percent") is not None:
                fan_text = f" | fan {hottest['fan_percent']:.0f}%"
            gpu_text = f"- GPU temp: {hottest['temp_c']:.1f} C ({hottest['name']}){fan_text}"
            if hottest.get("gpu_util") is not None:
                gpu_text += f" | load {hottest['gpu_util']:.0f}%"
            if hottest.get("memory_used_mb") is not None and hottest.get("memory_total_mb") is not None:
                gpu_text += (
                    " | VRAM "
                    f"{_format_bytes(hottest['memory_used_mb'] * 1024 * 1024)}"
                    f"/{_format_bytes(hottest['memory_total_mb'] * 1024 * 1024)}"
                )
            lines.append(gpu_text)

    top_processes = _collect_top_processes(top_n=top_n)
    if top_processes:
        lines.append("- Top active processes:")
        for index, proc in enumerate(top_processes, start=1):
            lines.append(
                f"  {index}. {proc['name']} (PID {proc['pid']}) | "
                f"CPU {proc['cpu']:.1f}% | RAM {proc['memory']:.1f}%"
            )

    snapshot = "\n".join(lines)
    _record_history(
        "snapshot",
        {
            "cpu_percent": cpu,
            "ram_percent": memory.percent,
            "disk_percent": disk.percent,
            "power_plan": active_plan["name"] if active_plan else "",
            "gpu": readings.get("gpu", [])[:1] if include_temps else [],
        },
    )
    return snapshot


def _detect_active_game(config: dict) -> dict:
    info = _foreground_window_info()
    if not info:
        return {}

    combined = " ".join(
        [
            info.get("title", ""),
            info.get("name", ""),
            info.get("exe", ""),
            info.get("cmdline", ""),
        ]
    )
    matched = _keyword_match(combined, config.get("game_keywords", []))
    if not matched:
        return {}

    title = info.get("title", "").strip()
    label = title if title else (info.get("name") or matched)
    return {
        "name": label,
        "keyword": matched,
        "pid": info.get("pid", 0),
        "process_name": info.get("name", ""),
    }


def _browser_rows(config: dict) -> list[dict]:
    wanted = {_normalize_text(name) for name in config.get("browser_process_names", [])}
    rows = []
    for row in _sample_processes(include_details=True):
        if _normalize_text(row["name"]) in wanted:
            rows.append(row)
    rows.sort(key=lambda item: (item["rss"], item["cpu"]), reverse=True)
    return rows


def _app_candidate_rows(config: dict, min_memory_mb: int = 150) -> list[dict]:
    active_pid = _foreground_window_info().get("pid", 0)
    keywords = config.get("non_essential_apps", [])
    rows = []

    for row in _sample_processes(include_details=True):
        if row["pid"] == active_pid:
            continue

        combined = " ".join([row["name"], row.get("exe", ""), row.get("cmdline", "")])
        matched = _keyword_match(combined, keywords)
        if not matched:
            continue
        if row["rss"] < max(50, int(min_memory_mb or 0)) * 1024 * 1024 and row["cpu"] < 2:
            continue

        item = dict(row)
        item["keyword"] = matched
        rows.append(item)

    rows.sort(key=lambda item: (item["rss"], item["cpu"]), reverse=True)
    return rows


def _browser_audit(config: dict, min_memory_mb: int = 150) -> str:
    rows = _browser_rows(config)
    if not rows:
        return "Browser audit: No supported browser process is active."

    total_rss = sum(row["rss"] for row in rows)
    counts = {}
    for row in rows:
        counts[row["name"]] = counts.get(row["name"], {"count": 0, "rss": 0})
        counts[row["name"]]["count"] += 1
        counts[row["name"]]["rss"] += row["rss"]

    lines = [
        "Browser memory audit:",
        f"- Total browser memory: {_format_bytes(total_rss)} across {len(rows)} processes",
    ]
    for name, stats in sorted(counts.items(), key=lambda item: item[1]["rss"], reverse=True):
        lines.append(f"- {name}: {stats['count']} process | total {_format_bytes(stats['rss'])}")

    heavy = [row for row in rows if row["rss"] >= max(50, int(min_memory_mb or 0)) * 1024 * 1024]
    if heavy:
        lines.append("- Heavy browser processes:")
        for row in heavy[:5]:
            lines.append(
                f"  - {row['name']} (PID {row['pid']}) | "
                f"{_format_bytes(row['rss'])} | CPU {row['cpu']:.1f}%"
            )

    lines.append("No browser was closed automatically.")
    return "\n".join(lines)


def _app_audit(config: dict, min_memory_mb: int = 150) -> str:
    rows = _app_candidate_rows(config, min_memory_mb=min_memory_mb)
    if not rows:
        return "Heavy app audit: No non-essential heavy background app was found."

    lines = [
        "Heavy app audit:",
        "- Suggested background apps to close if you want more FPS or RAM:",
    ]
    for row in rows[:8]:
        lines.append(
            f"  - {row['name']} (PID {row['pid']}) | "
            f"{_format_bytes(row['rss'])} | CPU {row['cpu']:.1f}%"
        )
    lines.append("Nothing was closed automatically.")
    return "\n".join(lines)


def _terminate_processes(rows: list[dict]) -> tuple[int, list[str], list[str]]:
    closed = 0
    names = []
    failures = []
    for row in rows:
        try:
            proc = psutil.Process(row["pid"])
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except psutil.TimeoutExpired:
                proc.kill()
            closed += 1
            names.append(f"{row['name']} (PID {row['pid']})")
        except Exception as exc:
            failures.append(f"{row['name']} (PID {row['pid']}): {exc}")
    return closed, names, failures


def _matches_targets(row: dict, targets: list[str]) -> bool:
    if not targets:
        return False
    combined = _normalize_text(" ".join([row["name"], row.get("exe", ""), row.get("cmdline", "")]))
    return any(_normalize_text(target) in combined for target in targets)


def _trim_apps(config: dict, targets: list[str], confirm_close: bool, min_memory_mb: int = 150) -> str:
    audit = _app_audit(config, min_memory_mb=min_memory_mb)
    if not confirm_close:
        return audit + "\n\nTo close apps, call trim_apps with confirm_close=true and targets like Discord,Chrome."

    rows = [row for row in _app_candidate_rows(config, min_memory_mb=min_memory_mb) if _matches_targets(row, targets)]
    if not rows:
        return audit + "\n\nNo matching app was closed."

    closed, names, failures = _terminate_processes(rows)
    lines = [audit, "", f"Closed {closed} app process(es)."]
    if names:
        lines.extend(f"- {name}" for name in names)
    if failures:
        lines.append("Failed to close:")
        lines.extend(f"- {item}" for item in failures[:5])
    return "\n".join(lines)


def _browser_optimize(config: dict, targets: list[str], confirm_close: bool, min_memory_mb: int = 150) -> str:
    audit = _browser_audit(config, min_memory_mb=min_memory_mb)
    if not confirm_close:
        return audit + "\n\nTo close a browser in background, call browser_optimize with confirm_close=true and targets like chrome.exe."

    rows = [row for row in _browser_rows(config) if _matches_targets(row, targets)]
    if not rows:
        return audit + "\n\nNo matching browser process was closed."

    closed, names, failures = _terminate_processes(rows)
    lines = [audit, "", f"Closed {closed} browser process(es)."]
    if names:
        lines.extend(f"- {name}" for name in names)
    if failures:
        lines.append("Failed to close:")
        lines.extend(f"- {item}" for item in failures[:5])
    return "\n".join(lines)


def _registry_run_entries() -> list[dict]:
    entries = []
    registry_keys = [
        ("HKCU", r"HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run", True),
        ("HKLM", r"HKEY_LOCAL_MACHINE\Software\Microsoft\Windows\CurrentVersion\Run", False),
    ]

    for scope, key_path, can_disable in registry_keys:
        ok, output = _run_command(["reg", "query", key_path])
        if not ok and not output:
            continue

        for raw_line in output.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("HKEY_"):
                continue
            parts = re.split(r"\s{2,}", line, maxsplit=2)
            if len(parts) != 3:
                continue
            name, reg_type, command = parts
            entries.append(
                {
                    "name": name,
                    "type": reg_type,
                    "command": command,
                    "source": "registry",
                    "scope": scope,
                    "key_path": key_path,
                    "can_disable": can_disable,
                }
            )

    return entries


def _startup_folder_entries() -> list[dict]:
    entries = []
    appdata = os.environ.get("APPDATA") or ""
    programdata = os.environ.get("PROGRAMDATA") or ""
    folders = [
        ("User Startup", Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"),
        ("Common Startup", Path(programdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"),
    ]

    for scope, folder in folders:
        if not str(folder).strip() or not folder.exists():
            continue
        try:
            for item in folder.iterdir():
                if not item.is_file():
                    continue
                entries.append(
                    {
                        "name": item.stem,
                        "type": item.suffix.lower(),
                        "command": str(item),
                        "source": "shortcut",
                        "scope": scope,
                        "path": str(item),
                        "can_disable": True,
                    }
                )
        except Exception:
            continue

    return entries


def _startup_entries(config: dict) -> list[dict]:
    entries = _registry_run_entries() + _startup_folder_entries()
    keywords = config.get("startup_keywords", [])
    for entry in entries:
        combined = " ".join([entry.get("name", ""), entry.get("command", "")])
        entry["keyword"] = _keyword_match(combined, keywords)
        entry["suggested"] = bool(entry["keyword"])
    return entries


def _startup_audit(config: dict) -> str:
    entries = _startup_entries(config)
    if not entries:
        return "Startup audit: No startup entry was found."

    suggested = [entry for entry in entries if entry.get("suggested")]
    lines = [
        "Startup audit:",
        f"- Total startup entries: {len(entries)}",
        f"- Suggested optional entries: {len(suggested)}",
    ]

    if suggested:
        lines.append("- Suggested startup items to disable:")
        for entry in suggested[:8]:
            lines.append(
                f"  - {entry['name']} [{entry['scope']}]"
                + ("" if entry.get("can_disable") else " (read-only)")
            )
    else:
        lines.append("- No obvious optional startup app matched the configured keywords.")

    return "\n".join(lines)


def _entry_matches_targets(entry: dict, targets: list[str]) -> bool:
    if not targets:
        return bool(entry.get("suggested"))
    combined = _normalize_text(" ".join([entry.get("name", ""), entry.get("command", "")]))
    return any(_normalize_text(target) in combined for target in targets)


def _startup_disable(config: dict, targets: list[str], confirm_disable: bool) -> str:
    audit = _startup_audit(config)
    if not confirm_disable:
        return audit + "\n\nNo startup item was disabled. Use confirm_disable=true and optional targets like Discord,Spotify."

    entries = [
        entry
        for entry in _startup_entries(config)
        if entry.get("can_disable") and _entry_matches_targets(entry, targets)
    ]
    if not entries:
        return audit + "\n\nNo matching startup entry could be disabled."

    backup = _load_startup_backup()
    disabled = []
    failures = []

    for entry in entries:
        try:
            if entry["source"] == "registry":
                backup["registry"] = [
                    item
                    for item in backup["registry"]
                    if not (
                        item.get("key_path") == entry["key_path"]
                        and item.get("name") == entry["name"]
                    )
                ]
                backup["registry"].append(
                    {
                        "key_path": entry["key_path"],
                        "name": entry["name"],
                        "type": entry["type"],
                        "value": entry["command"],
                    }
                )
                ok, output = _run_command(
                    ["reg", "delete", entry["key_path"], "/v", entry["name"], "/f"]
                )
                if not ok:
                    failures.append(f"{entry['name']}: {output}")
                    continue
                disabled.append(f"{entry['name']} [{entry['scope']}]")
                continue

            source_path = Path(entry["path"])
            if not source_path.exists():
                failures.append(f"{entry['name']}: shortcut not found")
                continue

            DISABLED_STARTUP_DIR.mkdir(parents=True, exist_ok=True)
            backup_name = f"{int(time.time())}_{_safe_filename(source_path.name)}"
            backup_path = DISABLED_STARTUP_DIR / backup_name
            shutil.move(str(source_path), str(backup_path))
            backup["shortcuts"].append(
                {
                    "name": entry["name"],
                    "original_path": str(source_path),
                    "backup_path": str(backup_path),
                }
            )
            disabled.append(f"{entry['name']} [{entry['scope']}]")
        except Exception as exc:
            failures.append(f"{entry['name']}: {exc}")

    _save_startup_backup(backup)
    if disabled:
        _record_action("startup_disable", {"targets": targets or [entry.split(" [", 1)[0] for entry in disabled]})

    lines = [audit, "", f"Disabled {len(disabled)} startup item(s)."]
    if disabled:
        lines.extend(f"- {item}" for item in disabled)
    if failures:
        lines.append("Failed to disable:")
        lines.extend(f"- {item}" for item in failures[:5])
    lines.append("Use startup_restore to bring disabled startup items back.")
    return "\n".join(lines)


def _startup_restore(targets: list[str]) -> str:
    backup = _load_startup_backup()
    if not backup["registry"] and not backup["shortcuts"]:
        return "Startup restore: There is nothing to restore."

    restored = []
    failures = []
    remaining_registry = []
    remaining_shortcuts = []

    for entry in backup["registry"]:
        if targets and not _entry_matches_targets(entry, targets):
            remaining_registry.append(entry)
            continue
        ok, output = _run_command(
            [
                "reg",
                "add",
                entry["key_path"],
                "/v",
                entry["name"],
                "/t",
                entry.get("type", "REG_SZ"),
                "/d",
                entry.get("value", ""),
                "/f",
            ]
        )
        if ok:
            restored.append(entry["name"])
        else:
            failures.append(f"{entry['name']}: {output}")
            remaining_registry.append(entry)

    for entry in backup["shortcuts"]:
        if targets and not _entry_matches_targets(entry, targets):
            remaining_shortcuts.append(entry)
            continue
        try:
            backup_path = Path(entry["backup_path"])
            original_path = Path(entry["original_path"])
            if not backup_path.exists():
                failures.append(f"{entry['name']}: backup shortcut is missing")
                continue
            original_path.parent.mkdir(parents=True, exist_ok=True)
            if original_path.exists():
                original_path = original_path.with_name(
                    f"{original_path.stem}_restored{original_path.suffix}"
                )
            shutil.move(str(backup_path), str(original_path))
            restored.append(entry["name"])
        except Exception as exc:
            failures.append(f"{entry['name']}: {exc}")
            remaining_shortcuts.append(entry)

    _save_startup_backup(
        {
            "registry": remaining_registry,
            "shortcuts": remaining_shortcuts,
        }
    )

    lines = [f"Startup restore completed. Restored {len(restored)} item(s)."]
    if restored:
        lines.extend(f"- {item}" for item in restored)
    if failures:
        lines.append("Failed to restore:")
        lines.extend(f"- {item}" for item in failures[:5])
    return "\n".join(lines)


def _auto_game_loop(stop_event: threading.Event) -> None:
    while not stop_event.wait(max(3, int(_load_config().get("watch_interval_seconds", 10)))):
        config = _load_config()
        game = _detect_active_game(config)

        with _AUTO_GAME_LOCK:
            player = _AUTO_GAME_STATE["player"]
            boosted = _AUTO_GAME_STATE["boosted"]
            current_game = _AUTO_GAME_STATE["current_game"]
            applied_profile = _AUTO_GAME_STATE["applied_profile"]

        if game and not boosted:
            mapped_profile = config.get("game_profiles", {}).get(game["keyword"], "")
            if mapped_profile:
                message = _apply_profile(mapped_profile, config, player=player)
                ok = True
            else:
                ok, message = _set_power_mode("boost")
            with _AUTO_GAME_LOCK:
                _AUTO_GAME_STATE["boosted"] = ok
                _AUTO_GAME_STATE["current_game"] = game["name"]
                _AUTO_GAME_STATE["current_keyword"] = game["keyword"]
                _AUTO_GAME_STATE["applied_profile"] = mapped_profile if mapped_profile else ""
            _record_action("auto_game_on", {"game": game["name"], "profile": mapped_profile})
            _emit_log(player, f"Auto game mode: {game['name']} detected. {message}", alert=ok)
            continue

        if game and boosted and game["name"] != current_game:
            with _AUTO_GAME_LOCK:
                _AUTO_GAME_STATE["current_game"] = game["name"]
                _AUTO_GAME_STATE["current_keyword"] = game["keyword"]
            _emit_log(player, f"Auto game mode now tracking: {game['name']}")
            continue

        if game and boosted and config.get("game_profiles", {}).get(game["keyword"], "") != applied_profile:
            mapped_profile = config.get("game_profiles", {}).get(game["keyword"], "")
            if mapped_profile:
                message = _apply_profile(mapped_profile, config, player=player)
                with _AUTO_GAME_LOCK:
                    _AUTO_GAME_STATE["applied_profile"] = mapped_profile
                _emit_log(player, f"Auto game mode applied game profile '{mapped_profile}' for {game['name']}.")
                _record_action("profile_boost", {"profile": mapped_profile, "game": game["name"]})
            continue

        if not game and boosted:
            ok, message = _set_power_mode("restore")
            with _AUTO_GAME_LOCK:
                _AUTO_GAME_STATE["boosted"] = False
                _AUTO_GAME_STATE["current_game"] = ""
                _AUTO_GAME_STATE["current_keyword"] = ""
                _AUTO_GAME_STATE["applied_profile"] = ""
            _emit_log(player, f"Auto game mode: game session ended. {message}", alert=ok)


def _monitor_loop(stop_event: threading.Event) -> None:
    while not stop_event.wait(max(5, int(_load_config().get("monitor_interval_seconds", 15)))):
        config = _load_config()
        with _MONITOR_LOCK:
            player = _MONITOR_STATE["player"]

        memory = psutil.virtual_memory()
        disk_root = Path.home().anchor or "C:\\"
        try:
            disk = psutil.disk_usage(disk_root)
        except Exception:
            disk = psutil.disk_usage(str(Path.home()))

        cpu = psutil.cpu_percent(interval=0.3)
        alerts = []
        if cpu >= float(config.get("cpu_alert_percent", 90)):
            alerts.append(f"CPU {cpu:.1f}%")
        if memory.percent >= float(config.get("ram_alert_percent", 88)):
            alerts.append(f"RAM {memory.percent:.1f}%")
        if disk.percent >= float(config.get("disk_alert_percent", 92)):
            alerts.append(f"Disk {disk.percent:.1f}%")

        temperature_limit = float(config.get("temperature_alert_c", 85))
        temps = _read_temperatures()
        if temps.get("cpu_c") is not None and temps["cpu_c"] >= temperature_limit:
            alerts.append(f"CPU temp {temps['cpu_c']:.1f}C")
        for gpu in temps.get("gpu", []):
            if gpu.get("temp_c", 0) >= temperature_limit:
                alerts.append(f"{gpu['name']} {gpu['temp_c']:.1f}C")

        if config.get("thermal_guard_enabled", True):
            hottest_gpu = max(temps.get("gpu", []) or [{"temp_c": 0}], key=lambda item: item.get("temp_c", 0))
            if (temps.get("cpu_c") or 0) >= float(config.get("thermal_guard_restore_c", 88)) or hottest_gpu.get("temp_c", 0) >= float(config.get("thermal_guard_restore_c", 88)):
                ok, restore_message = _set_power_mode("restore")
                if ok:
                    alerts.append("Thermal guard restored balanced mode")
                    _record_action("restore", {"source": "thermal_guard"})
                    with _AUTO_GAME_LOCK:
                        _AUTO_GAME_STATE["boosted"] = False
                else:
                    alerts.append(f"Thermal guard failed: {restore_message}")

        message = ""
        if alerts:
            message = "Performance alert: " + ", ".join(alerts)

        with _MONITOR_LOCK:
            last_alert = _MONITOR_STATE["last_alert"]
            _MONITOR_STATE["last_alert"] = message

        if message and message != last_alert:
            _emit_log(player, message, alert=True)
            if player and hasattr(player, "update_sensory"):
                try:
                    player.update_sensory(health="HIGH LOAD")
                except Exception:
                    pass
        elif not message and last_alert:
            _emit_log(player, "Performance monitor: system load is back to normal.")
            if player and hasattr(player, "update_sensory"):
                try:
                    player.update_sensory(health="STABLE")
                except Exception:
                    pass


def _auto_game_mode(enabled: bool, player=None) -> str:
    with _AUTO_GAME_LOCK:
        _AUTO_GAME_STATE["player"] = player or _AUTO_GAME_STATE["player"]

        if enabled and _AUTO_GAME_STATE["enabled"]:
            return "Auto game mode is already running."
        if not enabled and not _AUTO_GAME_STATE["enabled"]:
            return "Auto game mode is already stopped."

        if enabled:
            stop_event = threading.Event()
            thread = threading.Thread(target=_auto_game_loop, args=(stop_event,), daemon=True)
            _AUTO_GAME_STATE.update(
                {
                    "enabled": True,
                    "stop_event": stop_event,
                    "thread": thread,
                    "boosted": False,
                    "current_game": "",
                }
            )
            thread.start()
            _record_action("auto_game_on", {})
            return "Auto game mode started. Mirai will boost when a tracked game is in the foreground."

        stop_event = _AUTO_GAME_STATE.get("stop_event")
        boosted = _AUTO_GAME_STATE.get("boosted", False)
        _AUTO_GAME_STATE.update(
            {
                "enabled": False,
                "stop_event": None,
                "thread": None,
                "boosted": False,
                "current_game": "",
            }
        )

    if stop_event:
        stop_event.set()
    _record_action("auto_game_off", {})
    if boosted:
        ok, message = _set_power_mode("restore")
        return f"Auto game mode stopped. {message if ok else 'Restore failed: ' + message}"
    return "Auto game mode stopped."


def _performance_monitor(enabled: bool, player=None) -> str:
    with _MONITOR_LOCK:
        _MONITOR_STATE["player"] = player or _MONITOR_STATE["player"]

        if enabled and _MONITOR_STATE["enabled"]:
            return "Live performance monitor is already running."
        if not enabled and not _MONITOR_STATE["enabled"]:
            return "Live performance monitor is already stopped."

        if enabled:
            stop_event = threading.Event()
            thread = threading.Thread(target=_monitor_loop, args=(stop_event,), daemon=True)
            _MONITOR_STATE.update(
                {
                    "enabled": True,
                    "stop_event": stop_event,
                    "thread": thread,
                    "last_alert": "",
                }
            )
            thread.start()
            _record_action("monitor_on", {})
            return "Live performance monitor started."

        stop_event = _MONITOR_STATE.get("stop_event")
        _MONITOR_STATE.update(
            {
                "enabled": False,
                "stop_event": None,
                "thread": None,
                "last_alert": "",
            }
        )

    if stop_event:
        stop_event.set()
    _record_action("monitor_off", {})
    return "Live performance monitor stopped."


def _status_report() -> str:
    plans = _read_power_plans()
    active_plan = _current_power_plan(plans)
    with _AUTO_GAME_LOCK:
        auto_state = dict(_AUTO_GAME_STATE)
    with _MONITOR_LOCK:
        monitor_state = dict(_MONITOR_STATE)
    with _NETWORK_LOCK:
        network_state = dict(_NETWORK_STATE)
    with _OVERLAY_LOCK:
        overlay_state = dict(_OVERLAY_STATE)

    lines = ["Performance control status:"]
    lines.append(f"- Power plan: {active_plan['name'] if active_plan else 'Unknown'}")
    lines.append(
        "- Auto game mode: "
        + ("ON" if auto_state.get("enabled") else "OFF")
        + (f" | tracking {auto_state['current_game']}" if auto_state.get("current_game") else "")
        + (f" | profile {auto_state['applied_profile']}" if auto_state.get("applied_profile") else "")
    )
    lines.append("- Live performance monitor: " + ("ON" if monitor_state.get("enabled") else "OFF"))
    lines.append("- Network monitor: " + ("ON" if network_state.get("enabled") else "OFF"))
    lines.append("- Overlay: " + ("ON" if overlay_state.get("enabled") else "OFF"))
    if monitor_state.get("last_alert"):
        lines.append(f"- Last alert: {monitor_state['last_alert']}")
    if network_state.get("last_alert"):
        lines.append(f"- Last network alert: {network_state['last_alert']}")
    lines.append(_thermal_status())
    return "\n".join(lines)


def _apply_profile(profile_name: str, config: dict, player=None) -> str:
    profiles = config.get("profiles", {})
    if not profile_name:
        return "Available profiles: " + ", ".join(sorted(profiles.keys()))

    profile_key = _normalize_text(profile_name)
    selected = None
    selected_name = ""
    for name, profile in profiles.items():
        if _normalize_text(name) == profile_key:
            selected = profile
            selected_name = name
            break

    if not selected:
        return f"Unknown profile: {profile_name}. Available profiles: " + ", ".join(sorted(profiles.keys()))

    steps = [f"Profile '{selected_name}' applied:"]
    power_mode = selected.get("power_mode", "")
    if power_mode in {"boost", "restore"}:
        ok, message = _set_power_mode(power_mode)
        if ok and power_mode == "boost":
            _record_action("profile_boost", {"profile": selected_name})
        steps.append(f"- {message if ok else 'Power change failed: ' + message}")

    if selected.get("cleanup_temp"):
        steps.append(f"- {_cleanup_temp(min_age_hours=int(selected.get('min_age_hours', 6)))}")

    if selected.get("start_monitor"):
        steps.append(f"- {_performance_monitor(True, player=player)}")
    else:
        steps.append(f"- {_performance_monitor(False, player=player)}")

    if selected.get("start_auto_game_mode"):
        steps.append(f"- {_auto_game_mode(True, player=player)}")
    else:
        steps.append(f"- {_auto_game_mode(False, player=player)}")

    if selected.get("thermal_check"):
        thermal = _read_temperatures()
        if thermal.get("cpu_c") is not None or thermal.get("gpu"):
            steps.append("- Thermal sensors checked.")

    if selected.get("app_audit"):
        steps.append("")
        steps.append(_app_audit(config))

    if selected.get("browser_audit"):
        steps.append("")
        steps.append(_browser_audit(config))

    if selected.get("startup_audit"):
        steps.append("")
        steps.append(_startup_audit(config))

    return "\n".join(steps)


def _prep_game(config: dict, player=None, min_age_hours: int = 6) -> str:
    steps = ["Game prep started:"]
    ok, message = _set_power_mode("boost")
    if ok:
        _record_action("prep_game", {})
    steps.append(f"- {message if ok else 'Power change failed: ' + message}")
    steps.append(f"- {_cleanup_temp(min_age_hours=min_age_hours)}")
    steps.append(f"- {_performance_monitor(True, player=player)}")
    steps.append(f"- {_auto_game_mode(True, player=player)}")
    steps.append("")
    steps.append(_app_audit(config))
    steps.append("")
    steps.append(_browser_audit(config))
    steps.append("")
    steps.append(_thermal_status())
    return "\n".join(steps)


def _resolve_action(params: dict) -> str:
    action = (params.get("action") or "").strip().lower()
    if action:
        return action

    description = _normalize_text(params.get("description") or "")
    if any(token in description for token in ["oyuna hazirla", "game prep", "fps hazirla", "prepare game"]):
        return "prep_game"
    if "profil" in description or "profile" in description:
        return "profile"
    if "otomatik oyun" in description or "auto game" in description:
        return "auto_game_mode"
    if "monitor" in description or "izleme" in description or "canli takip" in description:
        return "monitor"
    if "overlay" in description or "hud" in description:
        return "overlay"
    if "ag" in description or "network" in description or "ping" in description:
        return "network_status"
    if "benchmark" in description or "stres testi" in description:
        return "benchmark"
    if "history" in description or "gecmis" in description or "log raporu" in description:
        return "history_report"
    if "driver" in description or "surucu" in description:
        return "driver_inventory"
    if "disk" in description and ("health" in description or "saglik" in description):
        return "disk_health"
    if "batarya" in description or "battery" in description:
        return "battery_status"
    if "geri al" in description or "undo" in description:
        return "undo_last"
    if "sicaklik" in description or "termal" in description or "temperature" in description:
        return "thermal_status"
    if "startup" in description and ("geri" in description or "restore" in description):
        return "startup_restore"
    if "startup" in description and ("disable" in description or "kapat" in description):
        return "startup_disable"
    if "startup" in description or "baslangic" in description:
        return "startup_audit"
    if "browser" in description and ("optimize" in description or "kapat" in description):
        return "browser_optimize"
    if "browser" in description or "tarayici" in description:
        return "browser_audit"
    if ("uygulama" in description or "app" in description or "program" in description) and (
        "kapat" in description or "trim" in description or "close" in description
    ):
        return "trim_apps"
    if "uygulama" in description or "app" in description or "program" in description:
        return "app_audit"
    if any(token in description for token in ["analiz", "analyze", "durum", "status", "rapor"]):
        return "analyze"
    if any(token in description for token in ["cleanup", "temizle", "cache", "temp"]):
        return "cleanup"
    if any(token in description for token in ["restore", "normal", "balanced", "dengeli"]):
        return "restore"
    if any(token in description for token in ["boost", "oyun", "gaming", "fps", "hizlandir"]):
        return "boost"
    return "smart_optimize"


def performance_optimize(
    parameters: dict,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    """
    Safe performance helper.

    actions:
      analyze
      smart_optimize
      boost
      cleanup
      restore
      network_status
      network_monitor
      overlay
      battery_status
      disk_health
      driver_inventory
      history_report
      benchmark
      undo_last
      auto_game_mode
      monitor
      thermal_status
      app_audit
      trim_apps
      browser_audit
      browser_optimize
      startup_audit
      startup_disable
      startup_restore
      profile
      prep_game
      status
    """
    params = parameters or {}
    config = _load_config()
    action = _resolve_action(params)
    top_n = max(1, min(10, int(params.get("top_n", 5) or 5)))
    min_age_hours = max(0, min(72, int(params.get("min_age_hours", 6) or 6)))
    min_memory_mb = max(50, min(4096, int(params.get("min_memory_mb", 150) or 150)))
    profile_name = params.get("profile_name") or params.get("profile") or params.get("name") or ""
    targets = _parse_targets(params.get("targets"))
    confirm_close = bool(params.get("confirm_close", False))
    confirm_disable = bool(params.get("confirm_disable", False))
    history_hours = max(1, min(168, int(params.get("history_hours", 6) or 6)))
    benchmark_seconds = max(5, min(300, int(params.get("benchmark_seconds", 15) or 15)))
    target = (params.get("target") or "").strip()
    enabled = params.get("enabled")
    if enabled is None:
        mode = _normalize_text(params.get("mode", ""))
        if mode in {"on", "start", "enable", "enabled"}:
            enabled = True
        elif mode in {"off", "stop", "disable", "disabled"}:
            enabled = False

    if player:
        _emit_log(player, f"[performance] {action}")

    if action == "analyze":
        return _performance_snapshot(top_n=top_n)
    if action == "status":
        return _status_report()
    if action == "network_status":
        return _network_status(config, target=target)
    if action == "network_monitor":
        if enabled is None:
            with _NETWORK_LOCK:
                state = _NETWORK_STATE["enabled"]
            return "Network monitor is ON." if state else "Network monitor is OFF."
        return _network_monitor(bool(enabled), player=player, target=target)
    if action == "overlay":
        if enabled is None:
            with _OVERLAY_LOCK:
                state = _OVERLAY_STATE["enabled"]
            return "Performance overlay is ON." if state else "Performance overlay is OFF."
        return _overlay_control(bool(enabled), player=player)
    if action == "battery_status":
        return _battery_status()
    if action == "disk_health":
        return _disk_health()
    if action == "driver_inventory":
        return _driver_inventory()
    if action == "history_report":
        return _history_report(hours=history_hours)
    if action == "benchmark":
        return _benchmark(seconds=benchmark_seconds, sample_interval=float(params.get("sample_interval", 1.0) or 1.0))
    if action == "undo_last":
        return _undo_last_action()
    if action == "cleanup":
        return _cleanup_temp(min_age_hours=min_age_hours)
    if action == "boost":
        ok, message = _set_power_mode("boost")
        if ok:
            _record_action("boost", {})
        return message if ok else f"Boost mode failed: {message}"
    if action == "restore":
        ok, message = _set_power_mode("restore")
        if ok:
            _record_action("restore", {})
        return message if ok else f"Restore mode failed: {message}"
    if action == "smart_optimize":
        steps = []
        ok, message = _set_power_mode("boost")
        steps.append(message if ok else f"Boost mode failed: {message}")
        steps.append(_cleanup_temp(min_age_hours=min_age_hours))
        steps.append("")
        steps.append(_performance_snapshot(top_n=top_n))
        return "\n".join(steps)
    if action == "auto_game_mode":
        if enabled is None:
            with _AUTO_GAME_LOCK:
                state = _AUTO_GAME_STATE["enabled"]
                current_game = _AUTO_GAME_STATE["current_game"]
            text = "Auto game mode is ON." if state else "Auto game mode is OFF."
            if current_game:
                text += f" Tracking: {current_game}."
            return text
        return _auto_game_mode(bool(enabled), player=player)
    if action == "monitor":
        if enabled is None:
            with _MONITOR_LOCK:
                state = _MONITOR_STATE["enabled"]
            return "Live performance monitor is ON." if state else "Live performance monitor is OFF."
        return _performance_monitor(bool(enabled), player=player)
    if action == "thermal_status":
        return _thermal_status()
    if action == "app_audit":
        return _app_audit(config, min_memory_mb=min_memory_mb)
    if action == "trim_apps":
        return _trim_apps(config, targets=targets, confirm_close=confirm_close, min_memory_mb=min_memory_mb)
    if action == "browser_audit":
        return _browser_audit(config, min_memory_mb=min_memory_mb)
    if action == "browser_optimize":
        return _browser_optimize(config, targets=targets, confirm_close=confirm_close, min_memory_mb=min_memory_mb)
    if action == "startup_audit":
        return _startup_audit(config)
    if action == "startup_disable":
        return _startup_disable(config, targets=targets, confirm_disable=confirm_disable)
    if action == "startup_restore":
        return _startup_restore(targets=targets)
    if action == "profile":
        return _apply_profile(profile_name, config, player=player)
    if action == "prep_game":
        return _prep_game(config, player=player, min_age_hours=min_age_hours)
    return f"Unknown performance action: {action}"
