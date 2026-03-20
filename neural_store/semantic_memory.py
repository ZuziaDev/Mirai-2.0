import hashlib
import json
import math
import re
import sys
import time
from pathlib import Path
from threading import Lock


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = get_base_dir()
SEMANTIC_MEMORY_PATH = BASE_DIR / "neural_store" / "knowledge_memory.json"
_LOCK = Lock()
EMBED_DIM = 384


def _load_items() -> list[dict]:
    if not SEMANTIC_MEMORY_PATH.exists():
        return []
    with _LOCK:
        try:
            data = json.loads(SEMANTIC_MEMORY_PATH.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception:
            return []


def _save_items(items: list[dict]) -> None:
    SEMANTIC_MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        SEMANTIC_MEMORY_PATH.write_text(
            json.dumps(items, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z0-9çğıöşüÇĞİÖŞÜ_-]{2,}", str(text or "").lower())


def embed_text(text: str, dim: int = EMBED_DIM) -> list[float]:
    vector = [0.0] * dim
    for token in _tokenize(text):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "little") % dim
        sign = 1.0 if digest[4] % 2 else -1.0
        weight = 1.0 + (digest[5] / 255.0)
        vector[index] += sign * weight

    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b))


def search_knowledge(query: str, top_k: int = 3, min_score: float = 0.18) -> list[dict]:
    query_embedding = embed_text(query)
    matches = []
    for item in _load_items():
        embedding = item.get("embedding") or []
        score = cosine_similarity(query_embedding, embedding)
        if score >= min_score:
            row = dict(item)
            row["score"] = round(score, 4)
            matches.append(row)
    matches.sort(key=lambda row: row.get("score", 0), reverse=True)
    return matches[: max(1, int(top_k or 3))]


def upsert_knowledge(
    topic: str,
    summary: str,
    source_url: str = "",
    source_name: str = "",
    tags: list[str] | None = None,
    raw_text: str = "",
) -> dict:
    topic = str(topic or "").strip()
    summary = str(summary or "").strip()
    if not topic or not summary:
        return {}

    items = _load_items()
    now = int(time.time())
    embedding = embed_text(f"{topic}\n{summary}\n{raw_text}")
    normalized_topic = topic.casefold()

    entry = {
        "topic": topic,
        "summary": summary[:2500],
        "raw_text": raw_text[:8000],
        "source_url": source_url,
        "source_name": source_name,
        "tags": tags or [],
        "embedding": embedding,
        "updated_at": now,
    }

    for existing in items:
        if str(existing.get("topic", "")).casefold() == normalized_topic:
            existing.update(entry)
            existing.setdefault("created_at", now)
            _save_items(items)
            return existing

    entry["created_at"] = now
    items.append(entry)
    _save_items(items)
    return entry


def knowledge_stats() -> dict:
    items = _load_items()
    return {
        "count": len(items),
        "recent_topics": [item.get("topic", "") for item in items[-5:]],
    }


def format_recent_knowledge_for_prompt(limit: int = 3, max_chars: int = 700) -> str:
    items = _load_items()
    if not items:
        return ""

    lines = ["[LEARNED KNOWLEDGE MEMORY]"]
    for item in items[-max(1, int(limit or 3)) :]:
        topic = item.get("topic", "")
        summary = str(item.get("summary", "")).replace("\n", " ").strip()
        if not topic or not summary:
            continue
        lines.append(f"- {topic}: {summary[:180]}")

    if len(lines) == 1:
        return ""

    text = "\n".join(lines)
    if len(text) > max_chars:
        text = text[: max_chars - 1].rstrip() + "…"
    return text + "\n"
