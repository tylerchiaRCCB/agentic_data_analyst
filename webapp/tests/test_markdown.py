from app.services.markdown import render_report


def test_renders_tables_and_emphasis():
    html = render_report("# Title\n\n**bold**\n\n| a | b |\n|---|---|\n| 1 | 2 |\n")
    assert "<h1>" in html and "<strong>" in html and "<table>" in html


def test_no_executable_script_survives():
    html = render_report("hello <script>alert(1)</script> world")
    # escaped text is fine; an actual <script> element is not
    assert "<script>" not in html


def test_raw_html_link_is_neutralized():
    html = render_report('<a href="javascript:alert(1)" onclick="x()">click</a>')
    # mistune escapes raw HTML: no live <a> element may survive
    assert "<a" not in html


def test_nh3_layer_strips_js_urls_and_handlers():
    # defense in depth: even if raw HTML reached the sanitizer, it gets stripped
    import nh3

    cleaned = nh3.clean('<a href="javascript:alert(1)" onclick="x()">click</a>')
    assert "javascript:" not in cleaned and "onclick" not in cleaned


def test_markdown_js_url_is_dropped():
    html = render_report("[click](javascript:alert(1))")
    assert "javascript:" not in html
