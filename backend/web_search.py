import urllib.request
import urllib.parse
import json
import re

def duckduckgo_search(query: str, max_results: int = 3) -> list[dict]:
    """
    Instant Answer API — no key needed.
    Falls back to scraping abstract from DDG HTML if instant answer is empty.
    """
    results = []

    # 1. Try DDG Instant Answer API
    try:
        encoded = urllib.parse.quote(query)
        url = f"https://api.duckduckgo.com/?q={encoded}&format=json&no_html=1&skip_disambig=1"
        req = urllib.request.Request(url, headers={"User-Agent": "JARVIS/1.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read().decode())

        abstract = data.get("AbstractText", "").strip()
        if abstract:
            results.append({
                "title": data.get("Heading", query),
                "snippet": abstract,
                "url": data.get("AbstractURL", ""),
            })

        # Related topics
        for topic in data.get("RelatedTopics", [])[:max_results]:
            if isinstance(topic, dict) and topic.get("Text"):
                results.append({
                    "title": topic.get("Text", "")[:60],
                    "snippet": topic.get("Text", ""),
                    "url": topic.get("FirstURL", ""),
                })
            if len(results) >= max_results:
                break

    except Exception:
        pass

    if not results:
        results.append({
            "title": f"Search: {query}",
            "snippet": f"Could not retrieve results for '{query}'. Try searching manually.",
            "url": f"https://duckduckgo.com/?q={urllib.parse.quote(query)}",
        })

    return results[:max_results]
