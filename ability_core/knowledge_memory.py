import json
import re
import sys
from pathlib import Path
from urllib.parse import quote

import requests

from neural_store.semantic_memory import knowledge_stats, search_knowledge, upsert_knowledge

try:
    from google import genai
except Exception:
    genai = None


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = get_base_dir()
API_CONFIG_PATH = BASE_DIR / "security_vault" / "access.json"
USER_AGENT = "MiraiKnowledge/1.0"


def _get_api_key() -> str:
    try:
        with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f).get("gemini_api_key", "")
    except Exception:
        return ""


def _wiki_search_title(query: str, lang: str = "tr") -> str:
    try:
        response = requests.get(
            f"https://{lang}.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "list": "search",
                "srsearch": query,
                "srlimit": 1,
                "format": "json",
            },
            headers={"User-Agent": USER_AGENT},
            timeout=15,
        )
        data = response.json()
        items = data.get("query", {}).get("search", [])
        if items:
            return items[0].get("title", "")
    except Exception:
        return ""
    return ""


def _wiki_summary(query: str, lang: str = "tr") -> dict:
    title = _wiki_search_title(query, lang=lang)
    if not title:
        return {}

    try:
        response = requests.get(
            f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{quote(title)}",
            headers={"User-Agent": USER_AGENT},
            timeout=15,
        )
        data = response.json()
        extract = (data.get("extract") or "").strip()
        url = data.get("content_urls", {}).get("desktop", {}).get("page", "")
        if extract:
            return {
                "source_name": f"Wikipedia ({lang})",
                "title": data.get("title", title),
                "summary": extract,
                "url": url,
            }
    except Exception:
        return {}
    return {}


def _ddg_snippets(query: str, max_results: int = 4) -> list[dict]:
    try:
        from duckduckgo_search import DDGS

        results = []
        with DDGS() as ddgs:
            for row in ddgs.text(query, max_results=max_results):
                results.append(
                    {
                        "source_name": "DuckDuckGo",
                        "title": row.get("title", ""),
                        "summary": row.get("body", row.get("snippet", "")),
                        "url": row.get("href", row.get("link", "")),
                    }
                )
        return results
    except Exception:
        return []


def _research_sources(query: str) -> list[dict]:
    sources = []
    for lang in ("tr", "en"):
        item = _wiki_summary(query, lang=lang)
        if item:
            sources.append(item)
    if not sources:
        sources.extend(_ddg_snippets(query))
    return sources


def _fallback_summary(query: str, sources: list[dict]) -> str:
    if not sources:
        return ""
    pieces = []
    for source in sources[:3]:
        title = source.get("title", source.get("source_name", "Source"))
        summary = source.get("summary", "").strip()
        if summary:
            pieces.append(f"{title}: {summary}")
    text = " ".join(pieces)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:1500]


def _summarize_sources(query: str, sources: list[dict]) -> str:
    fallback = _fallback_summary(query, sources)
    api_key = _get_api_key()
    if not api_key or genai is None or not sources:
        return fallback

    context = "\n".join(
        f"- {item.get('source_name', 'Source')} | {item.get('title', '')}: {item.get('summary', '')}"
        for item in sources[:5]
    )
    prompt = (
        f"Konu: {query}\n\n"
        f"Kaynaklar:\n{context}\n\n"
        "Bu konuyu Turkce, kisa ama bilgi dolu sekilde acikla. "
        "Fazla uzun olma. 5-7 cumle yeterli. Uydurma bilgi verme."
    )

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=prompt,
        )
        text = (response.text or "").strip()
        return text if text else fallback
    except Exception:
        return fallback


def _format_source_lines(sources: list[dict]) -> str:
    lines = []
    for item in sources[:4]:
        title = item.get("title") or item.get("source_name") or "Source"
        url = item.get("url", "")
        if url:
            lines.append(f"- {title}: {url}")
    return "\n".join(lines)


def knowledge_memory(
    parameters: dict,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    """
    Long-term semantic knowledge tool.

    actions:
      lookup
      research
      remember_text
      stats
    """
    params = parameters or {}
    action = (params.get("action") or "lookup").strip().lower()
    query = (params.get("query") or params.get("topic") or "").strip()
    text = (params.get("text") or "").strip()
    top_k = max(1, min(5, int(params.get("top_k", 3) or 3)))
    refresh = bool(params.get("refresh", False))

    if action == "stats":
        stats = knowledge_stats()
        return (
            "Knowledge memory stats:\n"
            f"- Items: {stats.get('count', 0)}\n"
            f"- Recent topics: {', '.join(stats.get('recent_topics', [])) or 'None'}"
        )

    if action == "remember_text":
        if not query or not text:
            return "remember_text needs both topic/query and text."
        entry = upsert_knowledge(
            topic=query,
            summary=text,
            source_name="Manual Note",
            source_url="",
            tags=["manual"],
            raw_text=text,
        )
        return f"Stored manual knowledge for '{entry.get('topic', query)}'."

    if not query:
        return "Please provide a topic or query."

    matches = search_knowledge(query, top_k=top_k)
    if action == "lookup":
        if not matches:
            return f"No long-term knowledge found for '{query}'."
        lines = ["Long-term knowledge recall:"]
        for item in matches:
            lines.append(
                f"- {item.get('topic', 'Unknown')} | score {item.get('score', 0):.2f} | "
                f"{str(item.get('summary', '')).replace(chr(10), ' ')[:220]}"
            )
        return "\n".join(lines)

    if matches and not refresh and matches[0].get("score", 0) >= 0.42:
        best = matches[0]
        return (
            f"Known topic from long-term memory: {best.get('topic', query)}\n"
            f"{best.get('summary', '')}\n"
            + (
                f"Source: {best.get('source_name', '')} {best.get('source_url', '')}".strip()
                if best.get("source_name") or best.get("source_url")
                else ""
            )
        ).strip()

    if player:
        try:
            player.write_log(f"[knowledge] researching: {query}")
        except Exception:
            pass

    sources = _research_sources(query)
    if not sources:
        return f"I could not research '{query}' from Wikipedia or search sources."

    summary = _summarize_sources(query, sources)
    entry = upsert_knowledge(
        topic=query,
        summary=summary,
        source_name=sources[0].get("source_name", ""),
        source_url=sources[0].get("url", ""),
        tags=["researched", "web"],
        raw_text="\n".join(item.get("summary", "") for item in sources[:5]),
    )
    source_lines = _format_source_lines(sources)
    return (
        f"Learned and stored '{entry.get('topic', query)}' in long-term memory.\n"
        f"{entry.get('summary', summary)}\n"
        + (f"Sources:\n{source_lines}" if source_lines else "")
    ).strip()
