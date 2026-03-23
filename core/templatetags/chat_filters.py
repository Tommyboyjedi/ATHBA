"""Django template filters for chat message rendering."""
from django import template
from django.utils.safestring import mark_safe, SafeString
from core.utils.markdown_renderer import render_markdown

register = template.Library()


@register.filter(name='markdown')
def markdown_filter(text: str) -> SafeString:
    """
    Convert markdown text to HTML for safe display in templates.
    
    This filter applies markdown formatting to text while ensuring
    all HTML is properly escaped to prevent XSS attacks.
    
    Args:
        text: Raw markdown text
        
    Returns:
        SafeString containing rendered HTML
        
    Example:
        {{ message.content|markdown }}
    """
    if not text:
        return ""
    return mark_safe(render_markdown(text))
