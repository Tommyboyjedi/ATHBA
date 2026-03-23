"""
Tests for markdown renderer utility.

These tests verify the markdown rendering functionality including:
- Code block rendering with language support
- Inline code formatting
- Bold and italic text
- Link rendering with security attributes
- HTML escaping for XSS prevention
"""
from core.utils.markdown_renderer import render_markdown, extract_code_blocks


def test_render_markdown_code_blocks():
    """Test code block rendering with language specification."""
    text = "```python\nprint('hello')\n```"
    result = render_markdown(text)
    assert '<pre>' in result
    assert '<code' in result
    assert 'language-python' in result
    assert 'print(&#x27;hello&#x27;)' in result


def test_render_markdown_inline_code():
    """Test inline code rendering."""
    text = "This is `inline code` in text"
    result = render_markdown(text)
    assert '<code>inline code</code>' in result


def test_render_markdown_bold():
    """Test bold text rendering with both ** and __ syntax."""
    text = "This is **bold text** and __also bold__"
    result = render_markdown(text)
    assert '<strong>bold text</strong>' in result
    assert '<strong>also bold</strong>' in result


def test_render_markdown_italic():
    """Test italic text rendering with both * and _ syntax."""
    text = "This is *italic* and _also italic_"
    result = render_markdown(text)
    assert '<em>italic</em>' in result
    assert '<em>also italic</em>' in result


def test_render_markdown_links():
    """Test link rendering with security attributes."""
    text = "Check out [this link](https://example.com)"
    result = render_markdown(text)
    assert '<a href="https://example.com"' in result
    assert 'target="_blank"' in result
    assert 'rel="noopener"' in result
    assert '>this link</a>' in result


def test_extract_code_blocks():
    """Test extraction of code blocks from markdown text."""
    text = """
Some text
```python
def hello():
    print("world")
```
More text
```javascript
console.log("test");
```
"""
    blocks = extract_code_blocks(text)
    assert len(blocks) == 2
    assert blocks[0]['language'] == 'python'
    assert 'def hello' in blocks[0]['code']
    assert blocks[1]['language'] == 'javascript'
    assert 'console.log' in blocks[1]['code']


def test_html_escaping():
    """Test that HTML is properly escaped to prevent XSS attacks."""
    text = "<script>alert('xss')</script>"
    result = render_markdown(text)
    assert '<script>' not in result
    assert '&lt;script&gt;' in result


def test_empty_text():
    """Test that empty text returns empty string."""
    assert render_markdown("") == ""
    assert render_markdown(None) == ""


def test_combined_formatting():
    """Test multiple markdown features together."""
    text = "**Bold** with `code` and [link](http://test.com)"
    result = render_markdown(text)
    assert '<strong>Bold</strong>' in result
    assert '<code>code</code>' in result
    assert '<a href="http://test.com"' in result
