"""
Run CDO executor scenarios against the configured AI Engine.

The runner no longer starts mock_ai_server.py. Set AI_BASE_URL to the real local
or in-cluster AI Engine endpoint before running.
"""
from __future__ import annotations

import glob
import json
import os
import sys
import time


os.environ.setdefault("CDO_K8S_MOCK", "true")

from config import CONFIG  # noqa: E402
from main import Executor  # noqa: E402


_HERE = os.path.dirname(os.path.abspath(__file__))
SCENARIO_DIR = os.path.join(_HERE, "scenarios")
RESOLVED_OUTCOMES = {"auto_resolved", "rolled_back"}


def _parse_duration(s: str) -> int:
    s = s.strip().lower()
    mult = {"h": 3600, "m": 60, "s": 1}
    if s and s[-1] in mult:
        return int(float(s[:-1]) * mult[s[-1]])
    return int(s)


def load_scenarios() -> list[dict]:
    out = []
    for path in sorted(glob.glob(os.path.join(SCENARIO_DIR, "sc*.json"))):
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
        d["_file"] = os.path.basename(path)
        out.append(d)
    return out


def run_once(scenarios: list[dict], verbose: bool = False) -> list[dict]:
    results = []
    for sc in scenarios:
        ex = Executor()
        outcome = ex.handle_incident(
            sc["telemetry_window"], sc["tenant_namespace"],
            correlation_id=sc.get("correlation_id"),
        )
        expected = sc.get("expected_outcome")
        match = outcome == expected
        results.append({
            "file": sc["_file"],
            "scenario": sc.get("scenario"),
            "outcome": outcome,
            "expected": expected,
            "match": match,
            "resolved": outcome in RESOLVED_OUTCOMES,
        })
        if verbose:
            flag = "OK " if match else "XX "
            print(f"  {flag} {sc['_file']:<26} -> {outcome}")
    return results


def summarize(results: list[dict], rounds: int) -> int:
    total = len(results)
    resolved = sum(1 for r in results if r["resolved"])
    matched = sum(1 for r in results if r["match"])
    rate = (resolved / total * 100) if total else 0.0
    mism = [r for r in results if not r["match"]]

    print("\n" + "=" * 60)
    print(f"  Rounds run         : {rounds}")
    print(f"  Incidents injected : {total}")
    print(f"  Auto-resolved      : {resolved}/{total} = {rate:.1f}%  (target >=60%)")
    print(f"  Match expected     : {matched}/{total}")
    print("=" * 60)
    if mism:
        print("  MISMATCH (outcome != expected):")
        seen = set()
        for r in mism:
            if r["file"] in seen:
                continue
            seen.add(r["file"])
            print(f"    {r['file']}: got '{r['outcome']}' expected '{r['expected']}'")

    ok = rate >= 60.0 and not mism
    print(f"\n  RESULT: {'PASS' if ok else 'FAIL'}\n")
    return 0 if ok else 1


def main() -> None:
    duration = 0
    if "--duration" in sys.argv:
        duration = _parse_duration(sys.argv[sys.argv.index("--duration") + 1])

    scenarios = load_scenarios()
    print(f"Loaded {len(scenarios)} scenarios from {SCENARIO_DIR}")
    print(f"AI_BASE_URL={CONFIG.ai_base_url}")
    if len(scenarios) < 10:
        print(f"WARNING: only {len(scenarios)} scenarios (<10).", file=sys.stderr)

    all_results: list[dict] = []
    rounds = 0
    deadline = time.time() + duration
    first = True
    while True:
        all_results += run_once(scenarios, verbose=first)
        first = False
        rounds += 1
        if time.time() >= deadline:
            break
        if duration:
            time.sleep(1)
    sys.exit(summarize(all_results, rounds))


if __name__ == "__main__":
    main()
