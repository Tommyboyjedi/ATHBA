"""
Simple markdown renderer for chat messages.

This module provides basic markdown support without additional dependencies,
following the same patterns as the existing codebase for text processing.
All HTML is properly escaped before processing to prevent XSS attacks.
"""
import re
import html
from typing import List, Dict, Match


def render_markdown(text: str) -> str:
    """
    Convert markdown text to HTML with basic formatting support.
    
    Security: All input is HTML-escaped before processing to prevent XSS.
    
    Supported markdown features:
    - Code blocks with optional language (```python...```)
    - Inline code (`code`)
    - Bold text (**text** or __text__)
    - Italic text (*text* or _text_)
    - Links ([text](url))
    - Line breaks (preserved as <br>)
    
    Args:
        text: Raw markdown text to convert
        
    Returns:
        HTML string with markdown formatting applied
        
    Example:
        >>> render_markdown("**bold** and `code`")
        '<strong>bold</strong> and <code>code</code>'
    """
    if not text:
        return ""
    
    # Escape HTML to prevent injection - security first
    text = html.escape(text)
    
    # Code blocks with language syntax highlighting
    def replace_code_block(match: Match) -> str:
        """Replace code block match with HTML pre/code tags."""
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
    
    # Links with security attributes
    text = re.sub(
        r'\[([^\]]+)\]\(([^\)]+)\)',
        r'<a href="\2" target="_blank" rel="noopener">\1</a>',
        text
    )
    
    # Line breaks (preserve newlines as <br>)
    text = text.replace('\n', '<br>')
    
    return text


def extract_code_blocks(text: str) -> List[Dict[str, str]]:
    """
    Extract code blocks from markdown text.
    
    Args:
        text: Markdown text containing code blocks
        
    Returns:
        List of dictionaries with 'language' and 'code' keys
        
    Example:
        >>> extract_code_blocks("```python\\nprint('hi')\\n```")
        [{'language': 'python', 'code': "print('hi')"}]
    """
    pattern = r'```(\w*)\n(.*?)```'
    matches = re.findall(pattern, text, flags=re.DOTALL)
    
    code_blocks: List[Dict[str, str]] = []
    for language, code in matches:
        code_blocks.append({
            'language': language or 'text',
            'code': code.strip()
        })
    
    return code_blocks
