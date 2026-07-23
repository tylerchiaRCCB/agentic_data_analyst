import re

import mistune
import nh3

_renderer = mistune.create_markdown(
    plugins=["table", "strikethrough", "task_lists", "url"],
    escape=False,  # preserve raw HTML (nh3 sanitizes it afterward)
)

_ALLOWED_TAGS = {
    "a", "abbr", "b", "blockquote", "br", "code", "del", "details", "div", "em",
    "h1", "h2", "h3", "h4", "h5", "h6", "hr", "i", "img", "input", "li", "ol",
    "p", "pre", "s", "span", "strong", "summary", "sub", "sup", "table", "tbody",
    "td", "th", "thead", "tr", "ul",
}

# Match ```mermaid ... ``` blocks BEFORE mistune processes them
_MERMAID_FENCE = re.compile(r"```mermaid\s*\n(.*?)```", re.DOTALL)
_MERMAID_PLACEHOLDER = "MERMAID_BLOCK_{i}_PLACEHOLDER"


def render_report(markdown_text: str) -> str:
    """Render LLM-generated markdown to sanitized HTML (reports are untrusted input)."""
    # Extract mermaid blocks before markdown rendering (they'd be mangled by nh3)
    mermaid_blocks: list[str] = []
    def _stash_mermaid(m: re.Match) -> str:
        idx = len(mermaid_blocks)
        mermaid_blocks.append(m.group(1).strip())
        return _MERMAID_PLACEHOLDER.format(i=idx)

    text = _MERMAID_FENCE.sub(_stash_mermaid, markdown_text)
    html = _renderer(text)
    html = nh3.clean(html, tags=_ALLOWED_TAGS, url_schemes={"http", "https", "mailto"})

    # Re-inject mermaid blocks as <pre class="mermaid"> (mermaid.js picks these up)
    for i, block in enumerate(mermaid_blocks):
        # Minimal sanitization: strip HTML tags but preserve mermaid syntax characters
        safe_block = nh3.clean(block, tags=set())
        # nh3 escapes > to &gt; which breaks mermaid arrow syntax — restore it
        safe_block = safe_block.replace("&gt;", ">").replace("&lt;", "<").replace("&amp;", "&")
        html = html.replace(
            _MERMAID_PLACEHOLDER.format(i=i),
            f'<pre class="mermaid">{safe_block}</pre>',
        )
    return html
