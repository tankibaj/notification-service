import pathlib
from typing import Any

from jinja2 import Environment, FileSystemLoader, TemplateNotFound

_TEMPLATES_DIR = pathlib.Path(__file__).parent.parent / "templates"


class TemplateEngine:
    def __init__(self, templates_dir: pathlib.Path | None = None) -> None:
        self._env = Environment(
            loader=FileSystemLoader(str(templates_dir or _TEMPLATES_DIR)),
            autoescape=True,
        )

    def render(self, template_id: str, variables: dict[str, Any]) -> str:
        template_name = f"{template_id}.html"
        try:
            template = self._env.get_template(template_name)
        except TemplateNotFound as exc:
            raise ValueError(f"Template '{template_id}' not found") from exc
        return template.render(**variables)
