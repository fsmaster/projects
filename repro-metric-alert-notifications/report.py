#!/usr/bin/env python3
"""Final report: join received webhooks with Sentry's open periods.

Writes results/summary.json (generated labels and relative numbers only, safe
to publish). With --detail, also prints id-level details for every BUG_A,
DROP and OTHER period and for one OK period. That output is for chat only;
never commit it.

Classes, per closed open period:
  OK      one "critical", then one "resolved"
  BUG_A   two or more "resolved" and no "critical"
  DROP    fewer webhooks than expected (critical or resolved missing)
  OTHER   anything else
  OPEN    the period has not ended yet
"""
import json
import re
import sys
from datetime import datetime, timedelta, timezone

from common import HERE, LOCAL, MONITORS, api, load_env

PERIOD_ID_OFFSET = 10**10  # webhook metric_alert.id = offset + open period id


def ts(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00").replace(" ", "T")).timestamp()


def iso(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def load_webhooks():
    rows = []
    for line in (LOCAL / "webhooks.jsonl").open(encoding="utf-8"):
        rec = json.loads(line)
        body = rec.get("body")
        if not isinstance(body, dict):
            continue
        data = body.get("data") or {}
        alert = data.get("metric_alert")
        if not alert:
            continue
        name = (alert.get("alert_rule") or {}).get("name") or ""
        if not re.fullmatch(r"repro-race-\d+", name):
            continue
        headers = {k.lower(): v for k, v in rec["headers"].items()}
        rows.append(
            {
                "t": rec["received_at"],
                "monitor": name,
                "action": body.get("action"),
                "period": str(int(alert["id"]) - PERIOD_ID_OFFSET),
                "status": alert.get("status"),
                "description_text": data.get("description_text"),
                "request_id": headers.get("request-id"),
                "signature_ok": rec.get("signature_ok"),
            }
        )
    return sorted(rows, key=lambda r: r["t"])


def classify(actions, closed):
    crit, res = actions.count("critical"), actions.count("resolved")
    if not closed:
        return "OPEN"
    if actions == ["critical", "resolved"]:
        return "OK"
    if crit == 0 and res >= 2:
        return "BUG_A"
    if crit + res < 2:
        return "DROP"
    return "OTHER"


def pct(values, p):
    if not values:
        return None
    values = sorted(values)
    idx = min(len(values) - 1, max(0, round(p / 100 * (len(values) - 1))))
    return round(values[idx], 1)


def window(start, end, pad=90):
    fmt = "%Y-%m-%dT%H:%M:%S"
    a = datetime.fromtimestamp(start - 5, timezone.utc).strftime(fmt)
    b = datetime.fromtimestamp((end or start) + pad, timezone.utc).strftime(fmt)
    return a, b


def detail(env, base, workflow_id, p):
    # Ids are printed on purpose here: this output is for chat only.
    a, b = window(p["start"], p["end"], pad=25)
    print(f"--- {p['class']}  {p['monitor']}  group={p['group']}  open_period={p['id']}")
    print(f"    dateStarted={iso(p['start'])}  dateEnded={iso(p['end']) if p['end'] else None}")
    _, reqs = api(env, "GET", f"/sentry-apps/{env['SENTRY_APP_SLUG']}/webhook-requests/?per_page=100&start={a}&end={b}")
    by_req = {r["requestId"]: r for r in reqs} if isinstance(reqs, list) else {}
    for w in p["webhooks"]:
        r = by_req.get(w["request_id"]) or {}
        sent = iso(ts(r["date"])) if r.get("date") else "not in request log"
        print(
            f"    webhook action={w['action']} status={w['status']} sentry_sent={sent} "
            f"received={iso(w['t'])} http={r.get('responseCode')} text={w['description_text']!r}"
        )
    _, hist = api(env, "GET", f"{base}/workflows/{workflow_id}/group-history/?per_page=100&start={a}&end={b}")
    for h in hist if isinstance(hist, list) else []:
        if h["group"]["id"] == p["group"]:
            print(f"    workflow fires in window: count={h.get('count')} lastTriggered={h.get('lastTriggered')}")
    _, acts = api(env, "GET", f"{base}/issues/{p['group']}/activities/")
    for act in reversed((acts or {}).get("activity", [])):
        when = ts(act["dateCreated"])
        if p["start"] - 5 <= when <= (p["end"] or p["start"]) + 25:
            print(f"    activity {act['type']} at {iso(when)}")


def main():
    env = load_env()
    base = f"/organizations/{env['SENTRY_ORG']}"
    hooks = load_webhooks()
    sends = [json.loads(l) for l in (LOCAL / "sends.jsonl").open(encoding="utf-8")]
    run_start, run_end = sends[0]["sent_at"], sends[-1]["sent_at"]

    _, detectors = api(env, "GET", f"{base}/detectors/?per_page=100&query=repro-race")
    _, workflows = api(env, "GET", f"{base}/workflows/?per_page=100")
    workflow_id = next(w["id"] for w in workflows if w["name"] == "repro-race-relay")

    periods = []
    for det in detectors:
        if not re.fullmatch(r"repro-race-\d+", det["name"]):
            continue
        _, rows = api(env, "GET", f"{base}/open-periods/?detectorId={det['id']}&per_page=100")
        for row in rows:
            start = ts(row["start"])
            if start < run_start - 5:
                continue  # opened before this run's first burst
            mine = [h for h in hooks if h["period"] == str(row["id"])]
            end = ts(row["end"]) if row.get("end") else None
            periods.append(
                {
                    "monitor": det["name"],
                    "group": str((det.get("latestGroup") or {}).get("id")),
                    "id": str(row["id"]),
                    "start": start,
                    "end": end,
                    "webhooks": mine,
                    "class": classify([h["action"] for h in mine], end is not None),
                }
            )
    periods.sort(key=lambda p: p["start"])

    counts = {}
    for p in periods:
        counts[p["class"]] = counts.get(p["class"], 0) + 1
    crit = [h["t"] - p["start"] for p in periods for h in p["webhooks"] if h["action"] == "critical"]
    res = [h["t"] - p["end"] for p in periods if p["class"] == "OK" for h in p["webhooks"] if h["action"] == "resolved"]
    dur = [p["end"] - p["start"] for p in periods if p["end"]]
    bug = [p for p in periods if p["class"] == "BUG_A"]
    checked = [h for h in hooks if h["signature_ok"] is not None]

    summary = {
        "conclusion": (
            f"BUG_A reproduced in {len(bug)} of {sum(1 for p in periods if p['end'])} closed open periods: "
            "two metric_alert.resolved webhooks and no metric_alert.critical for one open period."
            if bug
            else "BUG_A not reproduced in this run."
        )
        + (
            f" DROP in {counts['DROP']} period(s): metric_alert.critical never sent, only metric_alert.resolved."
            if counts.get("DROP")
            else ""
        ),
        "cycles": len(sends),
        "monitors": MONITORS,
        "run_seconds": round(run_end - run_start),
        "open_periods": len(periods),
        "counts": {k: counts.get(k, 0) for k in ("OK", "BUG_A", "DROP", "OTHER", "OPEN")},
        "latency_seconds": {
            "critical_after_period_start": {"p50": pct(crit, 50), "p95": pct(crit, 95), "max": pct(crit, 100)},
            "resolved_after_period_end": {"p50": pct(res, 50), "max": pct(res, 100)},
            "open_period_length": {"min": pct(dur, 0), "max": pct(dur, 100)},
        },
        "abnormal_periods": [
            {
                "class": p["class"],
                "monitor": int(p["monitor"].rsplit("-", 1)[1]),
                "open_period_length": round(p["end"] - p["start"], 1),
                "webhooks": [
                    {"action": h["action"], "seconds_after_period_start": round(h["t"] - p["start"], 1)}
                    for h in p["webhooks"]
                ],
            }
            for p in periods
            if p["class"] in ("BUG_A", "DROP", "OTHER")
        ],
        "signatures": {"ok": sum(1 for h in checked if h["signature_ok"]), "failed": sum(1 for h in checked if not h["signature_ok"])},
    }
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))

    if "--detail" in sys.argv:
        shown_ok = False
        for p in periods:
            if p["class"] in ("BUG_A", "DROP", "OTHER"):
                detail(env, base, workflow_id, p)
        for p in bug[:1] or periods[:1]:
            # The same monitor's latest OK period, for contrast. The latest one,
            # because Sentry's request log only keeps the most recent entries.
            for q in periods:
                if q["class"] == "OK" and q["monitor"] == p["monitor"]:
                    ok = q
                    shown_ok = True
            if shown_ok:
                detail(env, base, workflow_id, ok)


if __name__ == "__main__":
    main()
