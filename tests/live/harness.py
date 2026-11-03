"""Tiny runner shared by the live scripts: run a step, record pass/fail, write the report JSON."""

from __future__ import annotations

import json
import os
import sys
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRATCH = os.path.join(ROOT, "scratch")
sys.path.insert(0, ROOT)

results: list[dict] = []


def step(label: str, fn, *args, expect_error: str = "", **kwargs):
    try:
        value = fn(*args, **kwargs)
    except Exception as err:  # noqa: BLE001 - every outcome is recorded
        ok = bool(expect_error) and expect_error in str(err)
        results.append({"step": label, "ok": ok, "error": f"{type(err).__name__}: {err}"})
        print(("PASS" if ok else "FAIL"), label, "->", err)
        if not ok:
            traceback.print_exc()
        return None
    ok = not expect_error
    results.append({"step": label, "ok": ok})
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    print(("PASS" if ok else "FAIL"), label, "->", text[:200])
    return value


def check(label: str, ok: bool, detail: str = "") -> None:
    results.append({"step": label, "ok": ok, "detail": detail})
    print(("PASS" if ok else "FAIL"), label, detail)


def finish(report: str) -> int:
    with open(os.path.join(SCRATCH, f"{report}.json"), "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=1)
    failed = [r for r in results if not r["ok"]]
    print(f"\n{len(results) - len(failed)}/{len(results)} passed.")
    return 1 if failed else 0
