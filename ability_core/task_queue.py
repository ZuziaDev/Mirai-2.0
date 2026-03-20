import json
import threading
import time
import uuid
from pathlib import Path

from ability_core.game_control import game_control
from ability_core.open_app import open_app
from ability_core.performance_optimize import _detect_active_game, _load_config, performance_optimize
from ability_core.knowledge_memory import knowledge_memory
from ability_core.reminder import reminder
from ability_core.send_message import send_message
from ability_core.spotify_control import spotify_control


BASE_DIR = Path(__file__).resolve().parent.parent
VAULT_DIR = BASE_DIR / "security_vault"
TASK_QUEUE_PATH = VAULT_DIR / "task_queue.json"
TASK_HISTORY_PATH = VAULT_DIR / "task_queue_history.jsonl"

_QUEUE_LOCK = threading.Lock()
_QUEUE_STATE = {
    "enabled": False,
    "thread": None,
    "stop_event": None,
    "player": None,
}


def _load_queue() -> list[dict]:
    try:
        with open(TASK_QUEUE_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_queue(items: list[dict]) -> None:
    TASK_QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(TASK_QUEUE_PATH, "w", encoding="utf-8") as handle:
        json.dump(items, handle, ensure_ascii=False, indent=2)


def _append_history(payload: dict) -> None:
    try:
        TASK_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(TASK_HISTORY_PATH, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        return


def _parse_params(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    return {}


def _tool_map(player) -> dict:
    return {
        "open_app": lambda params: open_app(parameters=params, player=player),
        "send_message": lambda params: send_message(parameters=params, player=player),
        "spotify_control": lambda params: spotify_control(parameters=params, player=player),
        "performance_optimize": lambda params: performance_optimize(parameters=params, player=player),
        "knowledge_memory": lambda params: knowledge_memory(parameters=params, player=player),
        "game_control": lambda params: game_control(parameters=params, player=player),
        "reminder": lambda params: reminder(parameters=params, player=player),
    }


def _execute_item(item: dict, player=None) -> tuple[bool, str]:
    tool = (item.get("tool") or "").strip()
    params = item.get("parameters") or {}
    runner = _tool_map(player).get(tool)
    if runner is None:
        return False, f"Unsupported queued tool: {tool}"

    try:
        result = runner(params)
        return True, str(result or f"Queued task finished: {tool}")
    except Exception as exc:
        return False, str(exc)


def _is_game_active() -> bool:
    try:
        config = _load_config()
        return bool(_detect_active_game(config))
    except Exception:
        return False


def _queue_worker(stop_event: threading.Event) -> None:
    while not stop_event.wait(1.0):
        with _QUEUE_LOCK:
            player = _QUEUE_STATE["player"]

        items = _load_queue()
        now = int(time.time())
        due = sorted(
            [
                item
                for item in items
                if item.get("status") == "queued" and int(item.get("run_at", 0)) <= now
            ],
            key=lambda item: (int(item.get("run_at", 0)), item.get("created_at", 0)),
        )
        if not due:
            continue

        item = due[0]
        if item.get("only_if_not_gaming") and _is_game_active():
            continue

        for row in items:
            if row.get("id") == item.get("id"):
                row["status"] = "running"
                break
        _save_queue(items)

        ok, result = _execute_item(item, player=player)

        items = _load_queue()
        for row in items:
            if row.get("id") != item.get("id"):
                continue
            row["status"] = "done" if ok else "error"
            row["finished_at"] = int(time.time())
            row["result"] = result
            break
        _save_queue(items)

        _append_history(
            {
                "ts": int(time.time()),
                "id": item.get("id"),
                "tool": item.get("tool"),
                "label": item.get("label"),
                "ok": ok,
                "result": result,
            }
        )
        if player and hasattr(player, "write_log"):
            try:
                player.write_log(f"[queue] {item.get('label') or item.get('tool')}: {result}")
            except Exception:
                pass


def _start_worker(player=None) -> str:
    with _QUEUE_LOCK:
        _QUEUE_STATE["player"] = player or _QUEUE_STATE["player"]
        if _QUEUE_STATE["enabled"]:
            return "Task queue worker is already running."
        stop_event = threading.Event()
        thread = threading.Thread(target=_queue_worker, args=(stop_event,), daemon=True)
        _QUEUE_STATE.update(
            {
                "enabled": True,
                "thread": thread,
                "stop_event": stop_event,
            }
        )
        thread.start()
    return "Task queue worker started."


def _stop_worker() -> str:
    with _QUEUE_LOCK:
        if not _QUEUE_STATE["enabled"]:
            return "Task queue worker is already stopped."
        stop_event = _QUEUE_STATE.get("stop_event")
        _QUEUE_STATE.update(
            {
                "enabled": False,
                "thread": None,
                "stop_event": None,
            }
        )
    if stop_event:
        stop_event.set()
    return "Task queue worker stopped."


def _queue_status() -> str:
    items = _load_queue()
    queued = sum(1 for item in items if item.get("status") == "queued")
    running = sum(1 for item in items if item.get("status") == "running")
    done = sum(1 for item in items if item.get("status") == "done")
    errors = sum(1 for item in items if item.get("status") == "error")
    with _QUEUE_LOCK:
        enabled = _QUEUE_STATE["enabled"]
    return (
        "Task queue status:\n"
        f"- Worker: {'ON' if enabled else 'OFF'}\n"
        f"- Queued: {queued}\n"
        f"- Running: {running}\n"
        f"- Done: {done}\n"
        f"- Error: {errors}"
    )


def task_queue(
    parameters: dict,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    """
    Persistent queue for background tool execution.

    actions:
      enqueue
      list
      clear
      remove
      run_next
      start_worker
      stop_worker
      status
      history
    """
    params = parameters or {}
    action = (params.get("action") or "status").strip().lower()
    tool = (params.get("tool") or "").strip()
    label = (params.get("label") or tool or "task").strip()
    task_id = (params.get("task_id") or "").strip()
    delay_seconds = max(0, int(params.get("delay_seconds", 0) or 0))
    only_if_not_gaming = bool(params.get("only_if_not_gaming", False))
    auto_start = params.get("auto_start", True)
    item_params = _parse_params(params.get("parameters")) or _parse_params(params.get("parameters_json"))

    if action == "enqueue":
        if not tool:
            return "Task queue enqueue needs a tool name."
        item = {
            "id": uuid.uuid4().hex[:10],
            "tool": tool,
            "label": label,
            "parameters": item_params,
            "created_at": int(time.time()),
            "run_at": int(time.time()) + delay_seconds,
            "only_if_not_gaming": only_if_not_gaming,
            "status": "queued",
        }
        items = _load_queue()
        items.append(item)
        _save_queue(items)
        if auto_start:
            _start_worker(player=player)
        return f"Queued task {item['id']} for {tool}."

    if action == "list":
        items = _load_queue()
        if not items:
            return "Task queue is empty."
        lines = ["Task queue:"]
        for item in sorted(items, key=lambda row: (int(row.get("run_at", 0)), row.get("created_at", 0)))[:20]:
            lines.append(
                f"- {item.get('id')} | {item.get('status')} | {item.get('tool')} | "
                f"{item.get('label')} | run_at {item.get('run_at')}"
            )
        return "\n".join(lines)

    if action == "clear":
        _save_queue([])
        return "Task queue cleared."

    if action == "remove":
        if not task_id:
            return "Task queue remove needs task_id."
        items = [item for item in _load_queue() if item.get("id") != task_id]
        _save_queue(items)
        return f"Removed task {task_id} from the queue."

    if action == "run_next":
        items = _load_queue()
        queued = sorted(
            [item for item in items if item.get("status") == "queued"],
            key=lambda item: (int(item.get("run_at", 0)), item.get("created_at", 0)),
        )
        if not queued:
            return "No queued task is waiting."
        item = queued[0]
        ok, result = _execute_item(item, player=player)
        for row in items:
            if row.get("id") == item.get("id"):
                row["status"] = "done" if ok else "error"
                row["finished_at"] = int(time.time())
                row["result"] = result
                break
        _save_queue(items)
        _append_history(
            {
                "ts": int(time.time()),
                "id": item.get("id"),
                "tool": item.get("tool"),
                "label": item.get("label"),
                "ok": ok,
                "result": result,
            }
        )
        return result

    if action == "start_worker":
        return _start_worker(player=player)

    if action == "stop_worker":
        return _stop_worker()

    if action == "history":
        if not TASK_HISTORY_PATH.exists():
            return "Task queue history is empty."
        rows = []
        try:
            with open(TASK_HISTORY_PATH, "r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rows.append(json.loads(line))
                    except Exception:
                        continue
        except Exception:
            return "Task queue history could not be read."
        if not rows:
            return "Task queue history is empty."
        lines = ["Task queue history:"]
        for row in rows[-20:]:
            lines.append(
                f"- {row.get('id')} | {row.get('tool')} | "
                f"{'ok' if row.get('ok') else 'error'} | {str(row.get('result', ''))[:90]}"
            )
        return "\n".join(lines)

    return _queue_status()
