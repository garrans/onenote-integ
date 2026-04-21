"""
F-T03 + F-T04: Page-create and block-level PATCH logic.

Rules:
- Page create: template renders full HTML → Graph POST to section.
- Block PATCH: only replace `data-id` blocks owned by the pipeline.
  The `user-notes` block is NEVER patched — it belongs to the user.
- Mapping of NoteArtifact → owned blocks is explicit in OWNED_BLOCKS.
"""

from __future__ import annotations

import logging
from typing import Any

from src.renderer.graph_adapter import IGraphAdapter
from src.renderer.retry import with_retry
from src.renderer.templates import TemplateRegistry
from src.schema.note_artifact import NoteArtifact

log = logging.getLogger(__name__)

# data-id values owned by the pipeline. "user-notes" is intentionally absent.
OWNED_BLOCKS: tuple[str, ...] = (
    "artifact-title",
    "source-system",
    "tags-section",
    "people-section",
    "body-section",
)


class PageManager:
    """
    Orchestrates page creation and block-level patching against OneNote via Graph.

    F-T03: create_page — renders full template HTML and POSTs to a section.
    F-T04: patch_page — builds targeted PATCH commands for owned blocks only.
    """

    def __init__(
        self,
        adapter: IGraphAdapter,
        templates: TemplateRegistry,
        *,
        max_retry_attempts: int = 5,
    ) -> None:
        self._adapter = adapter
        self._templates = templates
        self._max_retry_attempts = max_retry_attempts

    # ------------------------------------------------------------------
    # F-T03: Page create
    # ------------------------------------------------------------------

    def create_page(self, artifact: NoteArtifact) -> str:
        """
        Create a new OneNote page for *artifact*.

        Returns:
            The Graph page ID of the newly created page.

        Raises:
            GraphError on non-retryable failure.
        """
        if artifact.routing is None:
            raise ValueError(
                f"NoteArtifact '{artifact.artifact_id}' has no routing; cannot create page."
            )

        section_id = with_retry(
            lambda: self._adapter.get_section_id(
                artifact.routing.notebook_name,  # type: ignore[union-attr]
                artifact.routing.section_name,   # type: ignore[union-attr]
            ),
            max_attempts=self._max_retry_attempts,
            sleep_fn=lambda _: None,
        )

        html_body = self._templates.render(artifact)

        response = with_retry(
            lambda: self._adapter.create_page(
                section_id,
                html_body,
                artifact.title,
            ),
            max_attempts=self._max_retry_attempts,
            sleep_fn=lambda _: None,
        )

        page_id: str = response.body.get("id", "")
        log.info(
            "Created OneNote page id=%s for artifact=%s",
            page_id,
            artifact.artifact_id,
        )
        return page_id

    # ------------------------------------------------------------------
    # F-T04: Block-level PATCH
    # ------------------------------------------------------------------

    def patch_page(self, page_id: str, artifact: NoteArtifact) -> None:
        """
        Patch *page_id* with updated content from *artifact*.

        Only blocks listed in OWNED_BLOCKS are targeted.
        The `user-notes` block is never touched.

        Raises:
            GraphError on non-retryable failure.
        """
        commands = self._build_patch_commands(artifact)
        if not commands:
            log.debug("No patch commands generated for artifact=%s", artifact.artifact_id)
            return

        with_retry(
            lambda: self._adapter.patch_page(page_id, commands),
            max_attempts=self._max_retry_attempts,
            sleep_fn=lambda _: None,
        )
        log.info(
            "Patched page id=%s with %d commands for artifact=%s",
            page_id,
            len(commands),
            artifact.artifact_id,
        )

    def _build_patch_commands(self, artifact: NoteArtifact) -> list[dict[str, Any]]:
        """
        Build PATCH commands for each owned block.

        The content for each block mirrors the default template layout.
        """
        import html as _html

        cmds: list[dict[str, Any]] = []

        def _cmd(target: str, content: str) -> dict[str, Any]:
            return {"target": target, "action": "replace", "content": content}

        cmds.append(_cmd("artifact-title", f"<h1>{_html.escape(artifact.title)}</h1>"))
        cmds.append(
            _cmd(
                "source-system",
                f"<p><strong>Source:</strong> {_html.escape(artifact.source_system)}</p>",
            )
        )

        tags_content = (
            "<p><em>No tags.</em></p>"
            if not artifact.tags
            else "<p>" + ", ".join(_html.escape(t) for t in artifact.tags) + "</p>"
        )
        cmds.append(_cmd("tags-section", f"<h2>Tags</h2>{tags_content}"))

        if artifact.people:
            rows = "".join(
                f"<tr><td>{_html.escape(p.name)}</td><td>{_html.escape(p.role or '')}</td></tr>"
                for p in artifact.people
            )
            people_content = (
                f'<table data-id="people-table"><tr><th>Name</th><th>Role</th></tr>{rows}</table>'
            )
        else:
            people_content = "<p><em>No people listed.</em></p>"
        cmds.append(_cmd("people-section", f"<h2>People</h2>{people_content}"))

        cmds.append(_cmd("body-section", f"<h2>Details</h2>{artifact.body}"))

        return cmds
