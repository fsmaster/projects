#!/usr/bin/env python3
"""Run loop: per monitor, a burst of 4 errors, wait 150 s, repeat.

The 10 monitors are staggered by 15 s. Every burst is logged to
./local/sends.jsonl so webhook times can be compared with send times.
"""
import json
import threading
import time

import sentry_sdk

from common import CLIENT_KEY_VAR, LOCAL, MONITORS, load_env

BURST = 4
PERIOD_S = 150
STAGGER_S = 15

_lock = threading.Lock()


class ReproError(Exception):
    pass


def log_send(record):
    with _lock:
        with (LOCAL / "sends.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, separators=(",", ":")) + "\n")


def worker(i):
    time.sleep((i - 1) * STAGGER_S)
    burst_no = 0
    while True:
        started = time.time()
        burst_no += 1
        for n in range(BURST):
            with sentry_sdk.new_scope() as scope:
                scope.set_tag("repro", f"race-{i}")
                try:
                    raise ReproError(f"repro race-{i} burst {burst_no} event {n + 1}")
                except ReproError as exc:
                    sentry_sdk.capture_exception(exc)
        sentry_sdk.flush(timeout=10)
        log_send({"sent_at": started, "monitor": i, "burst": burst_no, "events": BURST})
        time.sleep(max(0.0, PERIOD_S - (time.time() - started)))


def main():
    env = load_env()
    sentry_sdk.init(env[CLIENT_KEY_VAR], default_integrations=False, traces_sample_rate=0)
    threads = [threading.Thread(target=worker, args=(i,), daemon=True) for i in range(1, MONITORS + 1)]
    for t in threads:
        t.start()
    print("run loop started", flush=True)
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()
