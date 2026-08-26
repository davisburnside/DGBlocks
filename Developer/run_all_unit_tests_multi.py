"""
run_all_unit_tests_multi.py — run run_all_unit_tests.py against several Blender executables
and print one aggregated pass/fail matrix, so a version-compatibility regression ("passes on
5.0, fails on 5.1") is visible without reading every version's console output by hand.

Plain Python, no bpy — this drives Blender as a subprocess per version, it does not run
inside Blender itself.

Usage:

    python Developer/run_all_unit_tests_multi.py ^
        --blender "C:\\Program Files\\Blender Foundation\\Blender 5.0\\blender.exe" ^
        --blender "C:\\Program Files\\Blender Foundation\\Blender 5.1\\blender.exe"

(On bash/macOS/Linux, use \\ line continuations and forward-slash paths instead of ^.)

Each version's full JSON summary is written to Developer/.unit_test_results/<label>.json
(gitignored — see .gitignore) and the combined view to .../aggregate.json. Exit code is 0
only if every version passed every test with no collection errors.
"""

import argparse
import json
import pathlib
import subprocess
import sys

THIS_DIR = pathlib.Path(__file__).resolve().parent
RUNNER_SCRIPT = THIS_DIR / "run_all_unit_tests.py"
RESULTS_DIR = THIS_DIR / ".unit_test_results"


def _label_for(blender_path: str) -> str:
    """Use the containing folder name ('Blender 5.0') as a short label; falls back to the exe stem."""
    parent_name = pathlib.Path(blender_path).parent.name
    return (parent_name or pathlib.Path(blender_path).stem).replace(" ", "_")


def _run_one(blender_path: str) -> dict:
    label = _label_for(blender_path)
    out_json = RESULTS_DIR / f"{label}.json"
    out_json.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        # --factory-startup: ignore this Blender version's personal user preferences (other
        # enabled addons, startup file) so a failure here can only be DGBlocks' own fault, not
        # some unrelated addon already enabled in that profile.
        blender_path, "--background", "--factory-startup", "--python-exit-code", "1",
        "--python", str(RUNNER_SCRIPT), "--", "--json", str(out_json),
    ]
    print(f"\n{'=' * 80}\nRunning: {label}  ({blender_path})\n{'=' * 80}")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    print(proc.stdout)
    if proc.returncode not in (0, 1):
        # Anything outside 0/1 means the script itself crashed (import error, addon_enable
        # exception, etc.) rather than tests merely failing — surface stderr for that case.
        print(proc.stderr, file=sys.stderr)

    summary = json.loads(out_json.read_text(encoding="utf-8")) if out_json.exists() else None

    return {
        "label": label,
        "blender_path": blender_path,
        "returncode": proc.returncode,
        "summary": summary,
    }


def _print_matrix(results: list) -> None:
    print("\n" + "=" * 80)
    print("AGGREGATE RESULTS")
    print("=" * 80)

    for r in results:
        summary = r["summary"]
        if summary is None:
            print(f"{r['label']:20s}  CRASHED (returncode={r['returncode']}, no JSON written)")
            continue
        if summary.get("crashed"):
            print(f"{r['label']:20s}  CRASHED: {summary['error']}")
            continue
        totals = summary["totals"]
        blender_version = ".".join(str(v) for v in summary["blender_version"])
        print(
            f"{r['label']:20s}  Blender {blender_version:10s}  "
            f"{totals['passed']}/{totals['tests']} passed, "
            f"{totals['failed']} failed, {totals['skipped']} skipped"
        )

    def _usable_summary(r):
        return r["summary"] and not r["summary"].get("crashed")

    all_test_ids = sorted({
        test["test_id"]
        for r in results if _usable_summary(r)
        for test in r["summary"]["tests"]
    })

    discrepancies = []
    for test_id in all_test_ids:
        statuses = {}
        for r in results:
            if not _usable_summary(r):
                continue
            match = next((t for t in r["summary"]["tests"] if t["test_id"] == test_id), None)
            statuses[r["label"]] = match["status"] if match else "missing"
        if len(set(statuses.values())) > 1:
            discrepancies.append((test_id, statuses))

    if discrepancies:
        print("\n--- Cross-version discrepancies (same test, different outcome) ---")
        for test_id, statuses in discrepancies:
            print(f"  {test_id}")
            for label, status in statuses.items():
                print(f"      {label}: {status}")
    else:
        print("\nNo cross-version discrepancies — every test has the same status on every version run.")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--blender", action="append", required=True,
                         help="Path to a blender executable. Repeat this flag once per version.")
    args = parser.parse_args()

    results = [_run_one(blender_path) for blender_path in args.blender]

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / "aggregate.json").write_text(json.dumps(results, indent=2), encoding="utf-8")

    _print_matrix(results)

    any_failed = any(
        r["summary"] is None
        or r["summary"].get("crashed")
        or r["summary"]["totals"]["failed"] > 0
        or r["summary"]["collection_errors"]
        for r in results
    )
    sys.exit(1 if any_failed else 0)


if __name__ == "__main__":
    main()
