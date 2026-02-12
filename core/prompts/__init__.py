"""
Prompt template loader for CAMEL workforce.

Loads Jinja2 templates and renders them with context variables.
"""
from pathlib import Path
from typing import Dict, Any, Optional
from jinja2 import Environment, FileSystemLoader, TemplateNotFound

# Get templates directory
TEMPLATES_DIR = Path(__file__).parent / "templates"

# Initialize Jinja2 environment
_jinja_env: Optional[Environment] = None


def get_jinja_env() -> Environment:
    """Get or create Jinja2 environment."""
    global _jinja_env
    if _jinja_env is None:
        _jinja_env = Environment(
            loader=FileSystemLoader(str(TEMPLATES_DIR)),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
        )
    return _jinja_env


def render_template(template_name: str, **context: Any) -> str:
    """
    Render a Jinja2 template with context variables.
    
    Args:
        template_name: Name of template file (e.g., "workforce_task.j2")
        **context: Variables to pass to template
        
    Returns:
        Rendered template string
        
    Raises:
        TemplateNotFound: If template doesn't exist
    """
    env = get_jinja_env()
    try:
        template = env.get_template(template_name)
        return template.render(**context)
    except TemplateNotFound:
        raise FileNotFoundError(f"Template not found: {template_name} in {TEMPLATES_DIR}")


def render_workforce_task_prompt(signal: Dict[str, Any]) -> str:
    """
    Render workforce task prompt with signal data.
    
    Args:
        signal: Signal dictionary with ticker, action, interval, etc.
        
    Returns:
        Rendered prompt string
    """
    import json
    signal_payload = json.dumps(signal, indent=2, default=str)
    return render_template("workforce_task.j2", signal_payload=signal_payload)


def render_coordinator_system_prompt() -> str:
    """Render coordinator agent system prompt."""
    return render_template("coordinator_system.j2")


def render_task_agent_system_prompt() -> str:
    """Render task agent system prompt."""
    return render_template("task_agent_system.j2")

