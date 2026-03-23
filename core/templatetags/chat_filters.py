from django import template
from django.utils.safestring import mark_safe
from core.utils.markdown_renderer import render_markdown

register = template.Library()

@register.filter(name='markdown')
def markdown_filter(text):
    """Convert markdown text to HTML"""
    if not text:
        return ""
    return mark_safe(render_markdown(text))
