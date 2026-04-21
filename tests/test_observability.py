# J-T06: Observability tests.

from __future__ import annotations

import json
import logging
import threading

import pytest

from src.observability.logging import (
    CorrelationContext,
    LogRecord,
    current_correlation_id,
    log_event,
)
from src.observability.metrics import AuditEntry, AuditLogWriter, MetricsCollector, SyncMetrics


# ---------------------------------------------------------------------------
# Structured log schema (J-T01)
# ---------------------------------------------------------------------------

class TestLogRecord:
    def test_to_dict_contains_required_fields(self):
        rec = LogRecord(
            source_system="InspectionsApp",
            artifact_id="art-1",
            action="page_created",
            outcome="success",
        )
        d = rec.to_dict()
        assert d["source_system"] == "InspectionsApp"
        assert d["artifact_id"] == "art-1"
        assert d["action"] == "page_created"
        assert d["outcome"] == "success"
        assert "timestamp" in d

    def test_timestamp_is_iso_string(self):
        rec = LogRecord(source_system="s", artifact_id=None, action="a", outcome="success")
        d = rec.to_dict()
        assert "T" in d["timestamp"]  # ISO-8601 contains 'T'

    def test_correlation_id_none_when_not_set(self):
        rec = LogRecord(source_system="s", artifact_id=None, action="a", outcome="success")
        assert rec.correlation_id is None

    def test_extra_dict_included(self):
        rec = LogRecord(
            source_system="s",
            artifact_id="a",
            action="act",
            outcome="success",
            extra={"page_id": "p-1"},
        )
        assert rec.to_dict()["extra"]["page_id"] == "p-1"


# ---------------------------------------------------------------------------
# Correlation ID propagation (J-T02)
# ---------------------------------------------------------------------------

class TestCorrelationContext:
    def test_correlation_id_set_within_context(self):
        with CorrelationContext("corr-123"):
            assert current_correlation_id() == "corr-123"

    def test_correlation_id_cleared_after_context(self):
        with CorrelationContext("corr-abc"):
            pass
        assert current_correlation_id() is None

    def test_nested_contexts_restore_outer(self):
        with CorrelationContext("outer"):
            with CorrelationContext("inner"):
                assert current_correlation_id() == "inner"
            assert current_correlation_id() == "outer"

    def test_correlation_id_scoped_per_thread(self):
        results: dict[str, str | None] = {}

        def worker(name: str, cid: str):
            with CorrelationContext(cid):
                import time; time.sleep(0.01)
                results[name] = current_correlation_id()

        t1 = threading.Thread(target=worker, args=("t1", "cid-T1"))
        t2 = threading.Thread(target=worker, args=("t2", "cid-T2"))
        t1.start(); t2.start()
        t1.join(); t2.join()

        assert results["t1"] == "cid-T1"
        assert results["t2"] == "cid-T2"

    def test_log_record_captures_active_correlation_id(self):
        with CorrelationContext("corr-XYZ"):
            rec = LogRecord(source_system="s", artifact_id=None, action="a", outcome="success")
        assert rec.correlation_id == "corr-XYZ"


# ---------------------------------------------------------------------------
# log_event instrumentation (J-T03)
# ---------------------------------------------------------------------------

class TestLogEvent:
    def test_log_event_emits_json(self, caplog):
        rec = LogRecord(source_system="renderer", artifact_id="art-1",
                        action="page_created", outcome="success")
        with caplog.at_level(logging.INFO, logger="onenote_integ"):
            log_event(rec)
        assert caplog.records
        payload = json.loads(caplog.records[-1].message)
        assert payload["action"] == "page_created"

    def test_log_event_json_is_parseable(self, caplog):
        rec = LogRecord(source_system="connector", artifact_id="a", action="x", outcome="failure")
        with caplog.at_level(logging.INFO, logger="onenote_integ"):
            log_event(rec)
        text = caplog.records[-1].message
        parsed = json.loads(text)
        assert parsed["outcome"] == "failure"


# ---------------------------------------------------------------------------
# SyncMetrics (J-T04)
# ---------------------------------------------------------------------------

class TestMetricsCollector:
    def setup_method(self):
        self.collector = MetricsCollector()

    def test_starts_at_zero(self):
        snap = self.collector.snapshot()
        assert snap.events_received == 0

    def test_increment_events_received(self):
        self.collector.increment("events_received")
        assert self.collector.snapshot().events_received == 1

    def test_increment_multiple_fields(self):
        self.collector.increment("pages_created")
        self.collector.increment("patches_applied", 3)
        snap = self.collector.snapshot()
        assert snap.pages_created == 1
        assert snap.patches_applied == 3

    def test_snapshot_is_isolated_copy(self):
        snap1 = self.collector.snapshot()
        self.collector.increment("errors")
        snap2 = self.collector.snapshot()
        assert snap1.errors == 0
        assert snap2.errors == 1

    def test_to_dict_returns_all_fields(self):
        d = SyncMetrics().to_dict()
        expected = {
            "events_received", "pages_created", "patches_applied",
            "conflicts_detected", "dead_letters", "errors",
        }
        assert set(d.keys()) == expected


# ---------------------------------------------------------------------------
# AuditLogWriter (J-T05)
# ---------------------------------------------------------------------------

class TestAuditLogWriter:
    def setup_method(self):
        self.writer = AuditLogWriter()

    def _entry(self, artifact_id="art-1", action="created"):
        return AuditEntry(
            correlation_id="corr-1",
            source_system="InspectionsApp",
            artifact_id=artifact_id,
            event_type="artifact.created.v1",
            page_action=action,
            outcome="success",
        )

    def test_starts_empty(self):
        assert len(self.writer) == 0

    def test_record_increases_count(self):
        self.writer.record(self._entry())
        assert len(self.writer) == 1

    def test_all_returns_all_entries(self):
        self.writer.record(self._entry("a1"))
        self.writer.record(self._entry("a2"))
        assert len(self.writer.all()) == 2

    def test_by_artifact_filters_correctly(self):
        self.writer.record(self._entry("a1"))
        self.writer.record(self._entry("a2"))
        assert len(self.writer.by_artifact("a1")) == 1
        assert self.writer.by_artifact("a1")[0].artifact_id == "a1"

    def test_entry_is_immutable(self):
        entry = self._entry()
        with pytest.raises((AttributeError, TypeError)):
            entry.outcome = "failure"  # type: ignore[misc]
