"""
I-T03: Conflict detection.
I-T04: Reconciliation task skeleton.

Conflict detection:
  When the ChangeDetector fires an ONENOTE_PAGE_EDITED_V1 event, the
  ConflictDetector fetches the current page HTML and checks whether any
  *owned* block (those managed by the renderer) was edited externally.

  Strategy:
    1. Retrieve the latest renderer-authored HTML from the artifact (via
       the NoteArtifact registry or re-rendering).
    2. Compare that against the live OneNote HTML block-by-block.
    3. If a discrepancy is found in an owned block → raise ConflictError.
    4. If the discrepancy is only in user-notes → no conflict (expected).

Reconciliation:
  ReconciliationTask is a skeleton that receives ConflictError objects and
  decides a resolution strategy (currently: log and flag for human review).
  Future extensions: auto-merge, timestamp arbitration, etc.
"""

from __future__ import annotations

import logging
import re

from src.errors.taxonomy import ConflictError

log = logging.getLogger(__name__)

# Blocks owned by the renderer (must match OWNED_BLOCKS in page_manager.py).
OWNED_BLOCKS = (
    "artifact-title",
    "source-system",
    "tags-section",
    "people-section",
    "body-section",
)


def _extract_block(html: str, block_id: str) -> str | None:
    """
    Return the inner text/HTML of a `data-id="<block_id>"` element, or None.

    Uses a simple regex sufficient for the deterministic HTML the renderer
    produces; not a general HTML parser (no external deps required).
    """
    pattern = rf'data-id="{re.escape(block_id)}"[^>]*>(.*?)</(?:div|p|table|span)>'
    match = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else None


class ConflictDetector:
    """
    I-T03: Detect conflicts between the authoritative rendered HTML and the
    live OneNote page HTML.

    `detect(artifact_html, live_html, page_id, artifact_id)` raises
    `ConflictError` if any owned block differs.
    """

    def detect(
        self,
        authoritative_html: str,
        live_html: str,
        page_id: str,
        artifact_id: str,
    ) -> None:
        """
        Compare each owned block between authoritative and live HTML.

        Raises ConflictError if a discrepancy is found in an owned block.
        Silent if only user-notes differ (expected user editing).
        """
        for block_id in OWNED_BLOCKS:
            auth_content = _extract_block(authoritative_html, block_id)
            live_content = _extract_block(live_html, block_id)

            if auth_content is None and live_content is None:
                continue  # Block absent in both — no conflict.

            if auth_content != live_content:
                detail = (
                    f"block '{block_id}' — authoritative: "
                    f"{auth_content!r:.60} / live: {live_content!r:.60}"
                )
                log.warning(
                    "Conflict in owned block '%s' on page %s (artifact %s)",
                    block_id,
                    page_id,
                    artifact_id,
                )
                raise ConflictError(page_id, artifact_id, detail=detail)

        log.debug("No conflict detected for page %s (artifact %s)", page_id, artifact_id)


# ---------------------------------------------------------------------------
# I-T04: Reconciliation task skeleton
# ---------------------------------------------------------------------------

class ReconciliationTask:
    """
    Skeleton reconciliation task.

    Receives a ConflictError and logs it for human review.
    Future strategies (auto-merge, timestamp arbitration) plug in here.

    Usage::
        task = ReconciliationTask()
        task.handle_conflict(conflict_error)
    """

    def handle_conflict(self, conflict: ConflictError) -> None:
        log.warning(
            "[RECONCILIATION REQUIRED] page=%s artifact=%s detail=%s",
            conflict.page_id,
            conflict.artifact_id,
            conflict.detail,
        )
        # Placeholder: real implementations might:
        # - Write a "conflict" flag to the State Store.
        # - Post a notification to a Teams channel.
        # - Queue for a human-review workflow.
