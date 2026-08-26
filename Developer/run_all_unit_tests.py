"""
run_all_unit_tests.py — headless entry point for the addon-wide unit test pass.

Runs inside a single Blender process. Enables the addon, forces the deferred post-bpy init
synchronously (bpy.app.timers is not guaranteed to fire before a `--background --python
script.py` process exits — see Structural_Standards/Unit_Testing_Framework.md §8c), then
runs every enabled block's tests through block_core's Wrapper_Unit_Testing — the exact same
engine backing the in-Blender "Unit Tests" panel, so headless and interactive runs can never
disagree about what ran or what passed.

Usage (single Blender version):

    blender --background --factory-startup --python-exit-code 1 --python Developer/run_all_unit_tests.py

--factory-startup ignores whatever addons happen to already be enabled in that Blender
version's personal user profile, so a failure here can only be DGBlocks' own fault.

Optional machine-readable summary, consumed by run_all_unit_tests_multi.py to compare runs
across several Blender versions — args after "--" are passed through untouched by Blender:

    blender --background --factory-startup --python-exit-code 1 --python Developer/run_all_unit_tests.py -- --json out.json

Exit code: 0 if every test passed and no block failed to even collect its tests, 1 otherwise.
"""

import argparse
import json
import pathlib
import sys

import bpy


def _parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=str, default=None, help="Write a machine-readable JSON summary to this path")
    return parser.parse_args(argv)


def _blender_version_string() -> str:
    return ".".join(str(part) for part in bpy.app.version)


def _build_hash_string() -> str:
    build_hash = bpy.app.build_hash
    return build_hash.decode() if isinstance(build_hash, bytes) else str(build_hash)


def main():
    args = _parse_args()
    try:
        _run(args)
    except Exception as exc:
        import traceback
        error_text = traceback.format_exc()
        print("=" * 80, file=sys.stderr)
        print(f"run_all_unit_tests.py crashed before/during the test run: {exc}", file=sys.stderr)
        print(error_text, file=sys.stderr)
        print("=" * 80, file=sys.stderr)
        if args.json:
            out_path = pathlib.Path(args.json)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps({
                "crashed": True,
                "error": str(exc),
                "traceback": error_text,
                "blender_version": list(bpy.app.version),
            }, indent=2), encoding="utf-8")
        sys.exit(1)


def _run(args):
    addon_dir = pathlib.Path(__file__).resolve().parent.parent  # .../DGBlocks
    addon_name = addon_dir.name
    if str(addon_dir.parent) not in sys.path:
        sys.path.insert(0, str(addon_dir.parent))

    bpy.ops.preferences.addon_enable(module=addon_name)

    from DGBlocks.native_blocks.block_core.core_features.control_plane.feature_wrapper import Wrapper_Control_Plane
    from DGBlocks.native_blocks.block_core.core_features.unit_testing.feature_wrapper import Wrapper_Unit_Testing

    Wrapper_Control_Plane.init_post_bpy()

    # This process is, by construction, always a genuinely fresh Blender — safe to include
    # cold_start_only suites here even though the interactive "Run All" button never does.
    report = Wrapper_Unit_Testing.run_all(include_cold_start_only=True)

    block_rows = Wrapper_Unit_Testing.get_all_block_rows()
    all_cases = []
    for row in block_rows:
        all_cases.extend(Wrapper_Unit_Testing.get_tests_for_block(row.block_id))

    passed  = [c for c in all_cases if str(c.status) == "passed"]
    failed  = [c for c in all_cases if str(c.status) in ("failed", "error")]
    skipped = [c for c in all_cases if str(c.status) == "skipped"]
    collection_errors = [row for row in block_rows if row.collection_error]

    print("=" * 80)
    print(f"DGBlocks unit tests — Blender {_blender_version_string()} ({_build_hash_string()})")
    print(f"{len(block_rows)} block(s), {len(all_cases)} test(s): "
          f"{len(passed)} passed, {len(failed)} failed/error, {len(skipped)} skipped")
    for row in collection_errors:
        print(f"  [COLLECTION ERROR] {row.block_id}: {row.collection_error}")
    for case in failed:
        print(f"  [FAIL] {case.block_id} :: {case.short_label}: {case.error_text}")
    print("=" * 80)

    if args.json:
        summary = {
            "blender_version": list(bpy.app.version),
            "blender_build_hash": _build_hash_string(),
            "started_at": report.started_at,
            "finished_at": report.finished_at,
            "block_ids_run": report.block_ids_run,
            "totals": {
                "tests": len(all_cases),
                "passed": len(passed),
                "failed": len(failed),
                "skipped": len(skipped),
            },
            "collection_errors": [
                {"block_id": row.block_id, "error": row.collection_error}
                for row in collection_errors
            ],
            "tests": [
                {
                    "test_id": case.test_id,
                    "block_id": case.block_id,
                    "suite_group": case.suite_group,
                    "status": str(case.status),
                    "duration_seconds": case.duration_seconds,
                    "error_text": case.error_text,
                }
                for case in all_cases
            ],
        }
        out_path = pathlib.Path(args.json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(f"Wrote JSON summary to {out_path}")

    all_ok = not failed and not collection_errors
    sys.exit(0 if all_ok else 1)


main()
