"""The render_sample command pre-renders the seeded run's metrics + tearsheet (deterministic)."""

import json

from django.core.management import call_command


def test_render_sample_writes_metrics_and_tearsheet(tmp_path):
    out = tmp_path / "sample"
    call_command("render_sample", "--output-dir", str(out))

    payload = json.loads((out / "metrics.json").read_text(encoding="utf-8"))
    m = payload["metrics"]
    for key in ("cagr", "sharpe", "sortino", "max_drawdown", "num_trades", "win_rate"):
        assert key in m
    # In/out-of-sample split is present and deterministic on the committed SPY fixture.
    assert m["num_trades"] == 38
    assert {"in_sample", "out_of_sample"} <= set(m["oos"])
    assert m["oos"]["in_sample"]["num_trades"] == 25
    assert m["oos"]["out_of_sample"]["num_trades"] == 13

    html = (out / "tearsheet.html").read_text(encoding="utf-8")
    assert "<html" in html.lower()
    assert len(html) > 1000
