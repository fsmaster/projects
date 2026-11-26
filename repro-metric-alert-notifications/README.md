# Metric-alert notification repro

Tries to reproduce a metric-alert notification bug on sentry.io: for one open
period of a metric monitor, an internal integration gets two
`metric_alert.resolved` webhooks and no `metric_alert.critical` (called
BUG_A here).

## How it works

- `receiver.py` listens on 127.0.0.1, appends every request to
  `local/webhooks.jsonl` and answers 204 at once. It checks the
  `Sentry-Hook-Signature` header when the client secret is set.
- `setup.py` creates or updates 10 metric monitors (`repro-race-1..10`:
  errors, `count()`, 1-minute window, HIGH when > 1, default resolve, query
  `repro:race-<i>`) and one automation (`repro-race-relay`) that fires on
  first seen, regression, reappeared and resolved, with one `sentry_app`
  action aimed at the internal integration.
- `run.py` sends, per monitor, a burst of 4 errors every 150 s. The monitors
  are staggered by 15 s.
- `analyze.py` groups the webhooks by monitor and open period and labels each
  period OK, BUG_A, OPEN or OTHER. Its output uses generated labels and
  relative seconds only.

## Run it

Put these in `local/.env` (the folder is gitignored): `SENTRY_ORG`,
`SENTRY_AUTH_TOKEN`, the project's client key URL, `SENTRY_APP_SLUG`,
`SENTRY_APP_ID` and, for signature checks, `SENTRY_APP_CLIENT_SECRET`.

```
python3 receiver.py        # behind an HTTPS reverse proxy
python3 setup.py
python3 run.py             # needs sentry-sdk
python3 analyze.py
```

## API notes

- Monitors are created with
  `POST /organizations/<org>/projects/<project>/detectors/`. The org-level
  `/organizations/<org>/detectors/` path accepts GET, PUT and DELETE only.
- The automation action must be of type `sentry_app`. The `webhook` type
  sends `event_alert`, not `metric_alert`.

## Results

See [results/](results/).
