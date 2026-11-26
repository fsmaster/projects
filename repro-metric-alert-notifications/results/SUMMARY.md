# Results

Two kinds of wrong notification showed up in one 28-minute run (112 bursts,
112 open periods). In both, the integration never got `metric_alert.critical`.
Numbers are in [summary.json](summary.json), per-period webhook output in
[run-1.txt](run-1.txt).

| Open periods | OK | BUG_A | DROP | Other |
|---|---|---|---|---|
| 112 | 110 | 1 | 1 | 0 |

- **BUG_A**: two `metric_alert.resolved` and no `metric_alert.critical`.
- **DROP**: one `metric_alert.resolved` and no `metric_alert.critical`.

All 223 signed webhooks passed the signature check. The receiver answered
every request with 204.

## Normal timing

| | p50 | p95 | max |
|---|---|---|---|
| `critical` webhook after the period starts | 29.9 s | 42.5 s | 58.7 s |
| `resolved` webhook after the period ends | 4.3 s | | 7.2 s |

Open periods lasted 13.4 to 96.1 s. So the "opened" notification normally
goes out about 30 s late, and the "closed" one about 4 s late. A period
shorter than that 30 s gap is closed before its "opened" notification is
handled.

## BUG_A: monitor 7, open period of 40.6 s

Seconds are relative to the start of the open period.

| Time | What happened |
|---|---|
| 0 s | Open period starts; issue activity "regression" |
| +40.6 s | Open period ends; issue activity "resolved" |
| +41.1 s | Automation fires twice (both fires fall after the end) |
| +43.2 s | Webhook `resolved`, text says the count was 4.0 |
| +44.7 s | Webhook `resolved`, text says the count was 0.0 |

The first webhook is the "opened" notification with the wrong action: its
text carries the breaching value (4.0), but its action and status say
resolved. The automation did not fire at all while the period was open.

## DROP: monitor 9, open period of 13.4 s

| Time | What happened |
|---|---|
| 0 s | Open period starts; issue activity "regression" |
| +13.4 s | Open period ends; issue activity "resolved" |
| +15.3 s | Automation fires once |
| +19.4 s | Webhook `resolved`, text says the count was 0.0 |

The automation fired once, not twice, and Sentry's own request log has no
`critical` attempt for this period. The "opened" notification was never
produced.

## Reading

Likely cause, not confirmed in code: the automation handles the "opened"
transition late, and by then it reads the current state of the open period,
not the transition that triggered it. If the period has already closed, the
"opened" notification either goes out as `resolved` (BUG_A) or is not sent at
all (DROP). Both hits were among the shortest periods of the run.

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
