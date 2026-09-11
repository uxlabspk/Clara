"""Web search via DuckDuckGo (no key required)."""
from html.parser import HTMLParser
import requests

SEARCH_URL = "https://api.duckduckgo.com/"
HTML_SEARCH_URL = "https://html.duckduckgo.com/html/"


class _SearchResultParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.results = []
        self._in_result = False
        self._in_snippet = False
        self._current = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = attrs.get("class", "").split()
        if tag == "a" and "result__a" in classes:
            self._in_result = True
            self._current = []
        elif tag in {"a", "div"} and "result__snippet" in classes:
            self._in_snippet = True
            self._current = []

    def handle_data(self, data):
        if self._in_result or self._in_snippet:
            self._current.append(data)

    def handle_endtag(self, tag):
        if self._in_result and tag == "a":
            title = " ".join("".join(self._current).split())
            if title:
                self.results.append(title)
            self._in_result = False
        elif self._in_snippet and tag in {"a", "div"}:
            snippet = " ".join("".join(self._current).split())
            if snippet and self.results:
                self.results[-1] += ": " + snippet
            self._in_snippet = False


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
    if results:
        return "\n".join(results)

    try:
        r = requests.get(
            HTML_SEARCH_URL,
            params={"q": query},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=timeout,
        )
        r.raise_for_status()
        parser = _SearchResultParser()
        parser.feed(r.text)
        return "\n".join(parser.results[:5])
    except Exception:
        return ""
