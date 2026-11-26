#!/usr/bin/env python3
"""Classify received metric_alert webhooks per monitor and open period.

Reads ./local/webhooks.jsonl. Prints one line per open period, using
generated labels (monitor number, period counter) and seconds relative to the
first webhook, so the output is safe to publish.

  OK      one "critical", then one "resolved"
  BUG_A   two or more "resolved" and no "critical"
  OPEN    "critical" only so far (period not closed yet)
  OTHER   anything else (missing resolved, repeated critical, wrong order)

With --ids, also prints the real open-period id per row (for chat only;
never commit that output).
"""
import json
import re
import sys
from collections import OrderedDict

from common import LOCAL


def load():
    rows = []
    with (LOCAL / "webhooks.jsonl").open(encoding="utf-8") as fh:
        for line in fh:
            rec = json.loads(line)
            body = rec.get("body")
            if not isinstance(body, dict):
                continue
            alert = (body.get("data") or {}).get("metric_alert")
            if not alert:
                continue
            name = (alert.get("alert_rule") or {}).get("name") or ""
            match = re.fullmatch(r"repro-race-(\d+)", name)
            if not match:
                continue
            rows.append(
                {
                    "t": rec["received_at"],
                    "monitor": int(match.group(1)),
                    "action": body.get("action"),
                    "period": str(alert.get("id")),
                    "signature_ok": rec.get("signature_ok"),
                }
            )
    return sorted(rows, key=lambda r: r["t"])


def classify(actions):
    crit, res = actions.count("critical"), actions.count("resolved")
    if actions == ["critical", "resolved"]:
        return "OK"
    if crit == 0 and res >= 2:
        return "BUG_A"
    if actions == ["critical"]:
        return "OPEN"
    return "OTHER"


def main():
    show_ids = "--ids" in sys.argv
    rows = load()
    if not rows:
        print("no metric_alert webhooks for repro-race-* yet")
        return
    t0 = rows[0]["t"]
    periods = OrderedDict()
    for row in rows:
        periods.setdefault((row["monitor"], row["period"]), []).append(row)

    counts = {}
    per_monitor = {}
    print("monitor  period  class  webhooks (action@seconds)")
    for (monitor, period), items in periods.items():
        per_monitor[monitor] = per_monitor.get(monitor, 0) + 1
        label = f"m{monitor}-p{per_monitor[monitor]}"
        kind = classify([r["action"] for r in items])
        counts[kind] = counts.get(kind, 0) + 1
        seq = " ".join(f"{r['action']}@{r['t'] - t0:.1f}" for r in items)
        extra = f"  id={period}" if show_ids else ""
        print(f"{monitor:>7}  {label:<7} {kind:<6} {seq}{extra}")

    bad_sig = sum(1 for r in rows if r["signature_ok"] is False)
    checked = sum(1 for r in rows if r["signature_ok"] is not None)
    print()
    print(f"webhooks: {len(rows)}  span: {rows[-1]['t'] - t0:.0f} s  periods: {len(periods)}")
    print("classes: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    print(f"signatures: {checked - bad_sig} ok, {bad_sig} failed, {len(rows) - checked} not checked")


if __name__ == "__main__":
    main()
