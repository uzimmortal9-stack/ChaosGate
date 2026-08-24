"""The exposition format must be byte-correct or Prometheus silently drops it."""

import math

from core import metrics
from core.metrics import Counter, Gauge, Histogram, Registry
from core.prometheus import parse_exposition, summarize


def test_counter_renders_and_accumulates():
    reg = Registry()
    c = reg.counter("demo_total", "A demo counter.", ["kind"])
    c.inc(kind="a")
    c.inc(2, kind="a")
    c.inc(kind="b")

    assert c.value(kind="a") == 3.0
    out = reg.render()
    assert "# TYPE demo_total counter" in out
    assert 'demo_total{kind="a"} 3' in out
    assert 'demo_total{kind="b"} 1' in out


def test_counter_rejects_negative():
    reg = Registry()
    c = reg.counter("x_total", "x")
    try:
        c.inc(-1)
    except ValueError:
        return
    raise AssertionError("a counter must refuse to decrease")


def test_gauge_set_inc_dec():
    reg = Registry()
    g = reg.gauge("temp", "t", ["room"])
    g.set(20, room="a")
    g.inc(5, room="a")
    g.dec(2, room="a")
    assert g.value(room="a") == 23.0


def test_histogram_buckets_are_cumulative():
    reg = Registry()
    h = reg.histogram("lat", "latency", [], buckets=(0.1, 0.5, 1.0, math.inf))
    for value in (0.05, 0.2, 0.2, 0.7, 3.0):
        h.observe(value)

    out = reg.render()
    assert 'lat_bucket{le="0.1"} 1' in out
    assert 'lat_bucket{le="0.5"} 3' in out
    assert 'lat_bucket{le="1"} 4' in out
    assert 'lat_bucket{le="+Inf"} 5' in out
    assert "lat_count 5" in out


def test_label_mismatch_is_rejected():
    reg = Registry()
    c = reg.counter("y_total", "y", ["a"])
    try:
        c.inc(b="1")
    except ValueError:
        return
    raise AssertionError("labels must match the declared set")


def test_label_values_are_escaped():
    reg = Registry()
    c = reg.counter("esc_total", "e", ["msg"])
    c.inc(msg='he said "hi"\nand left')
    out = reg.render()
    assert '\\"hi\\"' in out
    assert "\\n" in out
    # Must still parse cleanly.
    assert parse_exposition(out)["valid"]


def test_app_exposition_is_parseable():
    metrics.bootstrap("test")
    metrics.pipeline_runs_total.inc(repo="a/b", trigger="manual", verdict="PASS")
    metrics.load_p95_milliseconds.set(42.5, repo="a/b", engine="k6")
    metrics.stage_duration_seconds.observe(1.5, stage="unit", status="passed")

    parsed = parse_exposition(metrics.render())
    assert parsed["valid"], parsed["errors"]
    assert parsed["sample_count"] > 0

    names = {s["name"] for s in parsed["samples"]}
    assert "chaosgate_pipeline_runs_total" in names
    assert "chaosgate_load_p95_milliseconds" in names
    assert "chaosgate_stage_duration_seconds_bucket" in names


def test_summarize_reports_types():
    summary = summarize(metrics.render())
    assert summary["valid"]
    assert summary["families"] > 0
    assert set(summary["by_type"]) <= {"counter", "gauge", "histogram", "untyped"}


def test_toolchain_gauge_records_availability():
    metrics.record_toolchain({"tools": {"docker": {"available": False}, "git": {"available": True}}})
    assert metrics.toolchain_available.value(tool="docker") == 0
    assert metrics.toolchain_available.value(tool="git") == 1
