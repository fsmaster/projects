#!/usr/bin/env python3
"""Idempotent Sentry setup: 10 metric monitors and one automation.

Monitors repro-race-1..10: errors dataset, count(), 1-minute window,
HIGH when > 1, default resolve, query `repro:race-<i>`.
Automation repro-race-relay: fires on first seen, regression, reappeared and
resolved, with one sentry_app action aimed at the internal integration.
"""
import sys

from common import MONITORS, PROJECT, api, load_env

TRIGGERS = [
    "first_seen_event",
    "regression_event",
    "reappeared_event",
    "issue_resolved_trigger",
]


def detector_body(i):
    return {
        "name": f"repro-race-{i}",
        "type": "metric_issue",
        "dataSources": [
            {
                "queryType": 0,
                "dataset": "events",
                "query": f"repro:race-{i}",
                "aggregate": "count()",
                "timeWindow": 60,
                "environment": None,
                "eventTypes": ["error"],
            }
        ],
        "conditionGroup": {
            "logicType": "any",
            "conditions": [
                # 75 = HIGH priority, 0 = resolved
                {"type": "gt", "comparison": 1, "conditionResult": 75},
                {"type": "lte", "comparison": 1, "conditionResult": 0},
            ],
        },
        "config": {"detectionType": "static"},
    }


def workflow_body(env, detector_ids):
    return {
        "name": "repro-race-relay",
        "enabled": True,
        "environment": None,
        "config": {"frequency": 0},
        "triggers": {
            "logicType": "any-short",
            "conditions": [
                {"type": t, "comparison": True, "conditionResult": True}
                for t in TRIGGERS
            ],
            "actions": [],
        },
        "actionFilters": [
            {
                "logicType": "any-short",
                "conditions": [],
                "actions": [
                    {
                        # Not "webhook": that one sends event_alert, not metric_alert.
                        "type": "sentry_app",
                        "integrationId": None,
                        "data": {},
                        "config": {
                            "targetType": "sentry_app",
                            "targetDisplay": "repro-metric-race-relay",
                            "targetIdentifier": str(env["SENTRY_APP_ID"]),
                        },
                        "status": "active",
                    }
                ],
            }
        ],
        "detectorIds": detector_ids,
    }


def must(status, data, what):
    if status >= 300:
        sys.exit(f"{what} failed: HTTP {status}: {str(data)[:300]}")
    return data


def main():
    env = load_env()
    org = env["SENTRY_ORG"]
    base = f"/organizations/{org}"

    must(*api(env, "GET", f"/projects/{org}/{PROJECT}/"), "read project")

    existing = must(
        *api(env, "GET", f"{base}/detectors/?per_page=100&query=repro-race"),
        "list monitors",
    )
    by_name = {d["name"]: d["id"] for d in existing}
    ids = []
    for i in range(1, MONITORS + 1):
        body = detector_body(i)
        if body["name"] in by_name:
            det_id = by_name[body["name"]]
            must(*api(env, "PUT", f"{base}/detectors/{det_id}/", body), "update monitor")
            print(f"monitor {i}: updated")
        else:
            created = must(
                *api(env, "POST", f"{base}/projects/{PROJECT}/detectors/", body),
                "create monitor",
            )
            det_id = created["id"]
            print(f"monitor {i}: created")
        ids.append(det_id)

    workflows = must(*api(env, "GET", f"{base}/workflows/?per_page=100"), "list automations")
    current = next((w for w in workflows if w["name"] == "repro-race-relay"), None)
    body = workflow_body(env, ids)
    if current:
        must(*api(env, "PUT", f"{base}/workflows/{current['id']}/", body), "update automation")
        print("automation: updated")
    else:
        must(*api(env, "POST", f"{base}/workflows/", body), "create automation")
        print("automation: created")


if __name__ == "__main__":
    main()
