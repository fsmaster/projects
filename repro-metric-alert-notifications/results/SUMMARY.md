# Results

BUG_A reproduced: 1 of 82 closed open periods in the first 29 minutes of the
run. Full per-period output is in [run-1.txt](run-1.txt).

| Open periods | OK | BUG_A | Other | Still open |
|---|---|---|---|---|
| 84 | 81 | 1 | 0 | 2 |

All 146 webhooks checked for a signature passed. The receiver answered every
request with 204.

## The hit: monitor 7, its 6th open period

Seconds are relative to the start of that open period.

| Time | What happened |
|---|---|
| 0 s | Open period starts |
| +41 s | Open period ends |
| +43 s | Webhook `metric_alert.resolved` |
| +44 s | Webhook `metric_alert.resolved` (second one, 1.4 s later) |

No `metric_alert.critical` was sent for this period. Both webhooks carried
the same open period, with status resolved and the same close time. The issue
page shows the period as a normal regress-then-resolve.

For comparison, the five earlier periods of the same monitor each got one
`critical` about 30 s after the period started and one `resolved` a few
seconds after it ended. Those periods lasted 56 to 70 s. The BUG_A period was
the shortest of the run at 41 s.

## Reading

Likely cause, not confirmed: the "opened" notification is built from the
state of the open period at send time, not from the transition that triggered
it. When a period closes before its "opened" notification goes out, that
notification is sent as `resolved`, so the integration gets two `resolved`
and never sees `critical`.

## Screenshots

- [bug-a-issue.png](../screenshots/bug-a-issue.png): open periods of
  monitor 7, the hit marked.
- [bug-a-request-log.png](../screenshots/bug-a-request-log.png): the
  integration's request log, two `resolved` for monitor 7 one second apart.
- [bug-a-automation-history.png](../screenshots/bug-a-automation-history.png):
  the automation's history.
- [ok-request-log.png](../screenshots/ok-request-log.png): same log, a normal
  period of monitor 5 marked (`critical`, then `resolved` 30 s later).

Ids in the screenshots are replaced with labels. The request log's Duration
column is Sentry's round-trip time including network and TLS; the receiver
itself answers in a few milliseconds.
