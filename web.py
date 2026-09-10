"""Web search via DuckDuckGo instant answer API (no key required)."""
import requests

SEARCH_URL = "https://api.duckduckgo.com/"


def search(query: str, timeout: int = 5) -> str:
    """Returns a short text summary for `query`, or empty string on failure."""
    try:
        r = requests.get(
            SEARCH_URL,
            params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
            timeout=timeout,
        )
        r.raise_for_status()
        data = r.json()
    except Exception:
        return ""

    abstract = data.get("AbstractText", "")
    if abstract:
        return abstract

    topics = data.get("RelatedTopics", [])
    results = []
    for t in topics[:3]:
        if isinstance(t, dict) and "Text" in t:
            results.append(t["Text"])
    return "\n".join(results)
