import mistune
import nh3

_renderer = mistune.create_markdown(plugins=["table", "strikethrough", "task_lists", "url"])

_ALLOWED_TAGS = {
    "a", "abbr", "b", "blockquote", "br", "code", "del", "details", "div", "em",
    "h1", "h2", "h3", "h4", "h5", "h6", "hr", "i", "img", "input", "li", "ol",
    "p", "pre", "s", "span", "strong", "summary", "sub", "sup", "table", "tbody",
    "td", "th", "thead", "tr", "ul",
}


def render_report(markdown_text: str) -> str:
    """Render LLM-generated markdown to sanitized HTML (reports are untrusted input)."""
    html = _renderer(markdown_text)
    return nh3.clean(html, tags=_ALLOWED_TAGS, url_schemes={"http", "https", "mailto"})
