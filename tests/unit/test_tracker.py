import pytest

from involve_benchling.testing import CleanupError, ResourceTracker


def test_cleanup_runs_lifo():
    order = []
    tracker = ResourceTracker()
    tracker.track("first", lambda: order.append("first"))
    tracker.track("second", lambda: order.append("second"))
    tracker.cleanup()
    assert order == ["second", "first"]
    assert len(tracker) == 0


def test_failures_do_not_stop_other_cleanups():
    order = []
    tracker = ResourceTracker()
    tracker.track("ok-1", lambda: order.append("ok-1"))
    tracker.track("boom", lambda: 1 / 0)
    tracker.track("ok-2", lambda: order.append("ok-2"))
    with pytest.raises(CleanupError) as exc:
        tracker.cleanup()
    assert order == ["ok-2", "ok-1"]
    assert len(exc.value.failures) == 1
    assert exc.value.failures[0][0] == "boom"
