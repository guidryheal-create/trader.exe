"""
HTML formatting utilities for agentic logs display.

Converts Python string outputs (with newlines, code blocks, etc.) to safe HTML
for display in the frontend.
"""
from __future__ import annotations

import html
import re
from typing import Any, Dict, List, Optional


def format_text_for_html(text: str, max_length: Optional[int] = None) -> str:
    """
    Format plain text for HTML display.
    
    - Escapes HTML special characters
    - Converts newlines to <br> tags
    - Preserves code blocks (```...```)
    - Preserves inline code (`...`)
    - Converts markdown-style formatting
    
    Args:
        text: Plain text string
        max_length: Optional maximum length (truncates with ellipsis)
        
    Returns:
        HTML-safe string
    """
    if not text:
        return ""
    
    # Truncate if needed
    if max_length and len(text) > max_length:
        text = text[:max_length] + "..."
    
    # Escape HTML first
    text = html.escape(text)
    
    # Convert code blocks (```language\ncode\n```)
    def replace_code_block(match):
        lang = match.group(1) or ""
        code = match.group(2)
        # Escape code content (already escaped above, but code blocks need special handling)
        code = html.escape(code)
        return f'<pre class="bg-gray-100 dark:bg-gray-800 p-3 rounded mt-2 mb-2 overflow-x-auto"><code class="language-{lang}">{code}</code></pre>'
    
    text = re.sub(r'```(\w+)?\n(.*?)```', replace_code_block, text, flags=re.DOTALL)
    
    # Convert inline code (`code`)
    def replace_inline_code(match):
        code = match.group(1)
        return f'<code class="bg-gray-100 dark:bg-gray-800 px-1.5 py-0.5 rounded text-sm font-mono">{code}</code>'
    
    text = re.sub(r'`([^`]+)`', replace_inline_code, text)
    
    # Convert markdown headers
    text = re.sub(r'^### (.*?)$', r'<h3 class="text-lg font-bold mt-4 mb-2">\1</h3>', text, flags=re.MULTILINE)
    text = re.sub(r'^## (.*?)$', r'<h2 class="text-xl font-bold mt-4 mb-2">\1</h2>', text, flags=re.MULTILINE)
    text = re.sub(r'^# (.*?)$', r'<h1 class="text-2xl font-bold mt-4 mb-2">\1</h1>', text, flags=re.MULTILINE)
    
    # Convert bold (**text** or __text__)
    text = re.sub(r'\*\*(.*?)\*\*', r'<strong class="font-semibold">\1</strong>', text)
    text = re.sub(r'__(.*?)__', r'<strong class="font-semibold">\1</strong>', text)
    
    # Convert italic (*text* or _text_)
    text = re.sub(r'(?<!\*)\*(?!\*)([^*]+?)(?<!\*)\*(?!\*)', r'<em class="italic">\1</em>', text)
    text = re.sub(r'(?<!_)_(?!_)([^_]+?)(?<!_)_(?!_)', r'<em class="italic">\1</em>', text)
    
    # Convert links [text](url)
    text = re.sub(
        r'\[([^\]]+)\]\(([^)]+)\)',
        r'<a href="\2" target="_blank" rel="noopener noreferrer" class="text-blue-500 hover:underline">\1</a>',
        text
    )
    
    # Convert unordered lists (- item or * item)
    lines = text.split('\n')
    in_list = False
    result_lines = []
    
    for line in lines:
        # Check if line is a list item
        if re.match(r'^[\-\*] (.+)$', line):
            if not in_list:
                result_lines.append('<ul class="list-disc list-inside my-2 space-y-1">')
                in_list = True
            item_text = re.sub(r'^[\-\*] (.+)$', r'\1', line)
            result_lines.append(f'<li class="ml-4">{item_text}</li>')
        else:
            if in_list:
                result_lines.append('</ul>')
                in_list = False
            result_lines.append(line)
    
    if in_list:
        result_lines.append('</ul>')
    
    text = '\n'.join(result_lines)
    
    # Convert newlines to <br> (but preserve existing HTML)
    # Only convert newlines that aren't already inside HTML tags
    text = re.sub(r'\n(?!<)', '<br />', text)
    
    # Wrap in paragraph if not already wrapped
    if not text.strip().startswith('<'):
        text = f'<p class="my-2">{text}</p>'
    
    return text


def format_workflow_trace_for_html(workflow_trace: List[Dict[str, Any]]) -> str:
    """
    Format workflow trace for HTML display.
    
    Args:
        workflow_trace: List of workflow step dictionaries
        
    Returns:
        HTML-formatted string
    """
    if not workflow_trace:
        return ""
    
    html_parts = ['<div class="workflow-trace space-y-2">']
    
    for idx, step in enumerate(workflow_trace, 1):
        role = step.get("role", "unknown")
        content = step.get("content") or step.get("message") or step.get("output", "")
        step_num = step.get("step", idx)
        
        # Format content
        formatted_content = format_text_for_html(str(content), max_length=500)
        
        html_parts.append(f'''
        <div class="workflow-step p-3 bg-gray-50 dark:bg-gray-900 rounded border-l-4 border-blue-500">
            <div class="flex items-center space-x-2 mb-1">
                <span class="text-xs font-mono text-gray-500">Step {step_num}</span>
                <span class="text-sm font-semibold text-blue-700 dark:text-blue-400">{role}</span>
            </div>
            <div class="text-sm text-gray-700 dark:text-gray-300">{formatted_content}</div>
        </div>
        ''')
    
    html_parts.append('</div>')
    return '\n'.join(html_parts)


def format_agent_message_for_html(message: str, max_length: Optional[int] = None) -> str:
    """
    Format a single agent message for HTML display.
    
    Args:
        message: Message text
        max_length: Optional maximum length
        
    Returns:
        HTML-formatted string
    """
    return format_text_for_html(message, max_length=max_length)


def format_explanation_for_html(explanation: str) -> str:
    """
    Format explanation text for HTML display.
    
    Args:
        explanation: Explanation text
        
    Returns:
        HTML-formatted string
    """
    return format_text_for_html(explanation, max_length=1000)

