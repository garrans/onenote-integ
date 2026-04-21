"""
F-T05: Template registry — maps routing.template to page HTML builder.

Templates are pure functions: NoteArtifact → HTML string.
The registry follows the same plug-in pattern as the connector registry.
"""

from __future__ import annotations

import html
import logging
from typing import Callable

from src.schema.note_artifact import NoteArtifact

log = logging.getLogger(__name__)

# Template function type alias.
TemplateFunc = Callable[[NoteArtifact], str]

_DEFAULT_TEMPLATE_NAME = "default"


def _default_template(artifact: NoteArtifact) -> str:
    """
    Standard page template.

    Produces:
      <title>   — page title (OneNote uses this for the tab label)
      <body>
        h1 title
        metadata table (sourceSystem, status tags, people)
        body content
        data-id blocks for all updatable sections
    """
    title_esc = html.escape(artifact.title)
    source_esc = html.escape(artifact.source_system)

    tags_html = (
        "<p><em>No tags.</em></p>"
        if not artifact.tags
        else "<p>" + ", ".join(html.escape(t) for t in artifact.tags) + "</p>"
    )

    people_rows = "".join(
        f"<tr><td>{html.escape(p.name)}</td><td>{html.escape(p.role or '')}</td></tr>"
        for p in artifact.people
    )
    people_html = (
        f'<table data-id="people-table"><tr><th>Name</th><th>Role</th></tr>{people_rows}</table>'
        if artifact.people
        else "<p><em>No people listed.</em></p>"
    )

    return f"""<!DOCTYPE html>
<html>
<head><title>{title_esc}</title></head>
<body>
<h1 data-id="artifact-title">{title_esc}</h1>
<p data-id="source-system"><strong>Source:</strong> {source_esc}</p>
<div data-id="tags-section">
<h2>Tags</h2>
{tags_html}
</div>
<div data-id="people-section">
<h2>People</h2>
{people_html}
</div>
<div data-id="body-section">
<h2>Details</h2>
{artifact.body}
</div>
<div data-id="user-notes">
<h2>Notes</h2>
<p><em>Add your notes here.</em></p>
</div>
</body>
</html>"""


class TemplateRegistry:
    """Registry mapping template names to HTML builder functions."""

    def __init__(self) -> None:
        self._templates: dict[str, TemplateFunc] = {}
        # Seed with the default template.
        self.register(_DEFAULT_TEMPLATE_NAME, _default_template)

    def register(self, name: str, func: TemplateFunc) -> None:
        """Register *func* under *name*. Overwrites silently (update-safe)."""
        self._templates[name] = func
        log.debug("Registered template: %s", name)

    def render(self, artifact: NoteArtifact) -> str:
        """
        Render *artifact* using the template named by ``artifact.routing.template``.

        Falls back to the default template when:
        - ``artifact.routing`` is None.
        - ``artifact.routing.template`` is None.
        - The named template is not registered.
        """
        template_name = (
            artifact.routing.template
            if artifact.routing and artifact.routing.template
            else _DEFAULT_TEMPLATE_NAME
        )

        func = self._templates.get(template_name)
        if func is None:
            log.warning(
                "Template '%s' not found; falling back to '%s'.",
                template_name,
                _DEFAULT_TEMPLATE_NAME,
            )
            func = self._templates[_DEFAULT_TEMPLATE_NAME]

        return func(artifact)

    def registered_names(self) -> list[str]:
        return list(self._templates.keys())
