"""
Simple markdown renderer for chat messages.
This provides basic markdown support without additional dependencies.
"""
import re
import html


def render_markdown(text: str) -> str:
    """
    Convert markdown text to HTML with basic formatting support.
    
    Supports:
    - Code blocks (```language)
    - Inline code (`code`)
    - Bold (**text** or __text__)
    - Italic (*text* or _text_)
    - Links ([text](url))
    - Line breaks
    """
    if not text:
        return ""
    
    # Escape HTML to prevent injection
    text = html.escape(text)
    
    # Code blocks with language syntax highlighting
    def replace_code_block(match):
        language = match.group(1) or ''
        code = match.group(2).strip()
        lang_class = f' class="language-{language}"' if language else ''
        return f'<pre><code{lang_class}>{code}</code></pre>'
    
    text = re.sub(r'```(\w*)\n(.*?)```', replace_code_block, text, flags=re.DOTALL)
    
    # Inline code
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
    
    # Bold (strong)
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'__(.+?)__', r'<strong>\1</strong>', text)
    
    # Italic (em)
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
    text = re.sub(r'_(.+?)_', r'<em>\1</em>', text)
    
    # Links
    text = re.sub(r'\[([^\]]+)\]\(([^\)]+)\)', r'<a href="\2" target="_blank" rel="noopener">\1</a>', text)
    
    # Line breaks (preserve newlines as <br>)
    text = text.replace('\n', '<br>')
    
    return text


def extract_code_blocks(text: str) -> list:
    """
    Extract code blocks from markdown text.
    Returns a list of dicts with 'language' and 'code' keys.
    """
    pattern = r'```(\w*)\n(.*?)```'
    matches = re.findall(pattern, text, flags=re.DOTALL)
    
    code_blocks = []
    for language, code in matches:
        code_blocks.append({
            'language': language or 'text',
            'code': code.strip()
        })
    
    return code_blocks
