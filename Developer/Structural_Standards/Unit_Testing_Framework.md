# DGBlocks — Unit Testing Framework (Design)

> Status: **Engine + UI implemented, all seven blocks wired in, most subgrouped.**
> `core_features/unit_testing/` (FWC, RTC/BL data model, hook, operators, panel — including the
> `[?]` docstring popup, auto-sized/wrapped to the actual text via `blf`) plus a
> `hook_get_unit_test_declarations` subscriber and `unit_tests/` folder in every block that has
> one, most now returning several `Unit_Test_Suite_Declaration`s (one per `suite_group`) instead
> of one lumped suite: `block_core` (30 tests — Data Sync / Registry / Self-Test),
> `block_onscreen_drawing` (19 — Shader Validation / Shader Creation / Geometry Math),
> `block_modal_events` (23 — Modal Lifecycle / Event Classification / Workspace Tools),
> `block_pip_library_manager` (14 — Security / Helpers / Architecture / Install Worker),
> `block_geometry_actions` (17 — Reads / Callbacks & Writes / Storage & Grouping / Curves /
> Serialization). `block_timers` (9) and `block_app_handlers` (12) stay single-group — too few
> tests for subgrouping to earn its keep. 124 tests total, 123 passed / 1 skipped (the GPU
> compile test, see §11 — genuinely can't run under `--background`). `block_debug_console_print`
> stays excluded per the original brief.
>
> Also done: a real validation-hardening pass across every block that collects declarations via
> a hook, not just its tests — `block_timers` (timer_uid must be str, frequency must be a
> non-bool number), `block_app_handlers` (handler_type must be a real `App_Handler_Type` member,
> frequency_filter_seconds must be a non-negative non-bool number), `block_modal_events`
> (`before_modal_start`/`before_modal_end` must be callable when provided, `priority` must be a
> non-bool int, `workspace_tool_ids` must be a tuple/list not a bare string),
> `block_onscreen_drawing` (`space`/`region`/`phase` must actually be their declared enum types),
> `block_pip_library_manager` (a real bug: two requirements from the same block sharing a
> `requirement_uid` were silently overwriting each other in `repoll()`'s dict-keyed-by-uid
> construction — now rejected via the new `reject_duplicate_requirement_uids()`), and
> `Wrapper_Unit_Testing` applying the same standard to its own `Unit_Test_Suite_Declaration`
> input (`_validate_suite_declarations`: non-empty `suite_id`, callable `build_suite`, no
> duplicate `suite_id` within a block). `block_geometry_actions` was deliberately left alone —
> its declarations are direct first-party function-call arguments, not hook-collected from
> arbitrary blocks, and its established philosophy is "never raise, record failures in the
> result" rather than reject upfront; retrofitting raise-on-invalid there would fight that
> existing design rather than extend it.
> The UI/data model described below (master UIList of blocks + per-test detail rows + optional
> subgroup subpanels, with a `last_run_at` at every one of the four scope levels — all/block/
> group/test, plus `cold_start_only` for suites that only make sense in a fresh process)
> supersedes the flatter `Unit_Test_Suite_Result` / `Unit_Test_Run_Report`-only sketch further
> down this doc; treat this status block and the actual code under `core_features/unit_testing/`
> as authoritative over conflicting detail below.
>
> Also done alongside: `addon_helpers/testing_tools.py` (tagged-prefix sweep +
> `Idempotent_BPY_TestCase`, §6) and `addon_helpers/data_tools.assert_unique_by_key` — a shared
> "reject duplicate declaration ids" helper now used by `block_onscreen_drawing`'s
> `_validate_shader_definitions` (reimplemented to use it, and to drop its long-dead, commented-
> out `(space, region, phase)` allowlist check). `block_app_handlers`' `repoll()` merge logic
> was extracted into a standalone `merge_handler_subscriptions()` so it's testable without
> touching `bpy.app.handlers` — the same kind of extraction the original design called for.
> `Developer/run_all_unit_tests.py` (single Blender) and `Developer/run_all_unit_tests_multi.py`
> (N Blender versions, aggregated pass/fail matrix + cross-version discrepancy list) both exist
> and have been run for real.
>
> Companion docs: `Structural_Standards/Block_Structure_Overview.md` (architecture patterns this
> framework must follow), `AI_Assist/Memory_Bank/blockAuthoringGuide.md` (per-block authoring
> recipe), and each block's own `README.md` (what each block actually does — not repeated here).

---

## 1. Goals & constraints (from the brief)

1. Tests run from inside a live Blender session (Python console / Text Editor) **and** from a
   headless `blender --background --python ...` invocation.
2. Most blocks get a standardized `unit_tests/` folder.
3. Each block subscribes to a **new block_core hook** and returns a list of test-suite
   declarations; block_core owns the actual collection + execution.
4. One block's tests failing (or raising during collection) must never stop the others from
   running — total isolation.
5. Every test is idempotent and only temporarily touches scene/RTC data, if at all.
6. `block_onscreen_drawing`'s GPU/shader surface is tiered, not blanket-excluded — see §11's
   table. Declaration validation always runs. Actual shader compile/link (Tier 1) was expected
   to also work headless on the assumption that `--background` binds a real GL context; in
   practice, on Blender 5.0 it raises "GPU functions for drawing are not available in
   background mode" — so Tier 1 cleanly `skipTest`s under `--background` and only actually
   executes interactively. The isolation this was built with (skip, don't fail, on any GPU
   context error) means this was absorbed with zero code changes when reality didn't match the
   assumption — exactly the point of that guard. Offscreen pixel-readback
   rendering is deliberately deferred to a future, separate "visual regression" tier; anything
   requiring a live `SpaceView3D` draw pass (draw handlers actually firing) is permanently out of
   scope — no viewport/redraw loop exists headless, and it isn't reliably scriptable even
   interactively. Same tiering reasoning extends to any other block's purely visual/interactive
   surface.
7. `block_core` is mostly startup/lifecycle code, not runtime logic — its own test surface is
   necessarily small and different in character from the other blocks.
8. `block_debug_console_print` is excluded from the example pass in this document (per request).

---

## 2. Architecture at a glance

```
block_<name>/__init__.py
    def hook_get_unit_test_declarations():
        from .unit_tests.run_tests import build_suite
        return [Unit_Test_Suite_Declaration(suite_id=_BLOCK_ID, build_suite=build_suite)]
                        │
                        │  (discovered by name, like every other hook — see
                        │   Block_Structure_Overview.md §9)
                        ▼
block_core / core_features / unit_testing / feature_wrapper.py
    Wrapper_Unit_Testing.run_all()
        1. Wrapper_Hooks.run_hooked_funcs(hook_get_unit_test_declarations)   # per-block isolation
        2. for each declaration: try: build_suite() + unittest run  except: record as suite error
        3. aggregate → Unit_Test_Run_Report, stash in RTC, print summary
                        ▲
        ┌───────────────┼───────────────────────┐
        │               │                       │
  Python console   UI operator (Core panel)   headless CLI script
  (interactive)     "Run All Unit Tests"        (--background)
```

This is the same **pull-based "hook_get_X" pattern** already used by `block_timers`
(`hook_get_timer_definitions`), `block_onscreen_drawing` (`hook_get_shader_declarations`),
`block_app_handlers` (`hook_get_app_handler_subscriptions`), and `block_modal_events`
(`hook_get_modal_listener_definitions`) — block_core becomes the puller, individual blocks stay
unaware of each other. No new architectural idiom is introduced.

---

## 3. New primitive: `Unit_Test_Suite_Declaration`

Lives in `addon_helpers/data_structures.py`, next to `Hook_Source_Declaration` /
`Logger_Declaration` / `RTC_Member_Declaration` — it's an addon-wide contract type, not
block-specific.

```python
@dataclass(eq=False)
class Unit_Test_Suite_Declaration:
    suite_id: str                                     # unique within its block
    build_suite: Callable[[], "unittest.TestSuite"]    # zero-arg factory, called lazily at collection time
    label: Optional[str] = None                        # display name; defaults to suite_id
    suite_group: Optional[str] = None                  # optional 2nd grouping layer; None -> "Default"
    cold_start_only: bool = False                      # see "Cold-start-only suites" below
```

(`tags` from the original sketch was dropped — nothing needs slow-test filtering yet, and
`suite_group`/`cold_start_only` cover the two real needs that emerged once the UI/data model
was actually built. See §11 and the actual code under `core_features/unit_testing/` for the
current, authoritative shape — this section stays close to it but isn't re-verified line for
line on every change.)

**Why a factory, not a pre-built `TestSuite`:** constructing a suite (importing the test module,
instantiating `TestCase`s) is exactly the kind of thing that can raise — a missing optional bpy
feature, a bad import. Deferring construction to `Wrapper_Unit_Testing.run_all()`'s own
try/except means a broken test *module* degrades to one failed suite entry, not a hook-collection
failure. This mirrors the `build_suite()` function that already exists in
`block_geometry_actions/unit_tests/test_geometry_actions.py`.

**Cold-start-only suites:** some tests only make sense as part of a genuinely fresh, just-booted
Blender process — e.g. asserting something about the `register()` → `init_post_bpy()` boot
sequence itself. Re-triggering that from inside an already-running, already-registered session
(via the panel's Run buttons) isn't safe or meaningful; the addon is already past that point. Mark
the whole suite `cold_start_only=True` and every test in it inherits the flag onto its
`Unit_Test_Case_Info.cold_start_only`. Consequences:
- `Wrapper_Unit_Testing.run_all()` / `run_block_unit_tests()` / `run_group_unit_tests()` /
  `run_one_test()` all take `include_cold_start_only: bool = False` and skip these tests unless
  told otherwise — only `Developer/run_all_unit_tests.py` passes `True`, since every invocation
  of it *is* a fresh process by construction. The interactive operators always use the default.
- The panel greys out (rather than hides) the Run button for any cold-start-only test, and for a
  group/block whose tests are *all* cold-start-only, labeling the test row `(headless only)` —
  clicking it would either no-op or be meaningless, so it shouldn't look clickable.

---

## 4. New hook source

`block_core/core_helpers/constants.py`, added to `Core_Block_Hook_Sources`:

```python
class Core_Block_Hook_Sources(String_Comparable_Mixin):
    ...
    hook_get_unit_test_declarations = Hook_Source_Declaration()  # no args
```

Subscriber contract: return `list[Unit_Test_Suite_Declaration]`, or `[]` if the block currently
has no runnable tests. Naming matches the existing `hook_get_*` family exactly.

---

## 5. New FWC: `Wrapper_Unit_Testing`

New subfolder, same shape as `core_features/hooks/`, `core_features/loggers/`, etc.:

```
block_core/core_features/unit_testing/
├── feature_wrapper.py   # Wrapper_Unit_Testing
├── data_structures.py   # Unit_Test_Suite_Result, Unit_Test_Run_Report
└── ui.py                # subpanel draw helper (optional, see §8b)
```

```python
# data_structures.py
@dataclass
class Unit_Test_Suite_Result:
    block_id: str
    suite_id: str
    label: str
    tests_run: int = 0
    failures: int = 0
    errors: int = 0
    skipped: int = 0
    duration_seconds: float = 0.0
    failure_details: list[tuple[str, str]] = field(default_factory=list)  # (test_id, last line of trace)
    collection_error: Optional[str] = None   # set only if build_suite()/.run() itself raised

    @property
    def is_ok(self) -> bool:
        return self.collection_error is None and self.failures == 0 and self.errors == 0

@dataclass
class Unit_Test_Run_Report:
    started_at: float
    finished_at: float
    suite_results: list[Unit_Test_Suite_Result] = field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        return all(r.is_ok for r in self.suite_results)
```

```python
# feature_wrapper.py  (illustrative — not final)
class Wrapper_Unit_Testing(Abstract_Feature_Wrapper):

    @classmethod
    def _init_wrapper(cls): pass
    @classmethod
    def _remove_wrapper(cls): pass

    @classmethod
    def run_all(cls, verbosity: int = 2) -> Unit_Test_Run_Report:
        logger = get_logger(Core_Block_Loggers.UNIT_TESTING)

        # Headless-safe: guarantee hook subscribers are wired even if the deferred
        # post-bpy timer hasn't ticked yet. init_post_bpy() is guarded/idempotent
        # (see control_plane/feature_wrapper.py), so this is a no-op in the normal
        # interactive case where startup already completed.
        ADDON_METADATA = Wrapper_Runtime_Cache.get_cache(Core_Runtime_Cache_Members.ADDON_METADATA)
        if not ADDON_METADATA.POST_REG_INIT_HAS_RUN:
            Wrapper_Control_Plane.init_post_bpy()

        started_at = time.time()
        declarations_by_block = Wrapper_Hooks.run_hooked_funcs(
            hook_func_name = Core_Block_Hook_Sources.hook_get_unit_test_declarations,
            should_halt_on_exception = False,   # <- layer 1 of isolation, already built into Wrapper_Hooks
        )

        suite_results = [
            cls._run_one_suite(block_id, declaration, verbosity, logger)
            for block_id, declarations in declarations_by_block.items()
            for declaration in (declarations or [])
        ]

        report = Unit_Test_Run_Report(started_at, time.time(), suite_results)
        Wrapper_Runtime_Cache.set_cache(Core_Runtime_Cache_Members.LAST_UNIT_TEST_REPORT, report)
        cls._print_report_summary(report)
        return report

    @classmethod
    def _run_one_suite(cls, block_id, declaration, verbosity, logger) -> Unit_Test_Suite_Result:
        result = Unit_Test_Suite_Result(block_id, declaration.suite_id, declaration.label or declaration.suite_id)
        start = time.time()
        try:
            suite = declaration.build_suite()               # <- layer 2 of isolation
            stream = io.StringIO()
            outcome = unittest.TextTestRunner(stream=stream, verbosity=verbosity).run(suite)
            result.tests_run, result.skipped = outcome.testsRun, len(outcome.skipped)
            result.failures, result.errors = len(outcome.failures), len(outcome.errors)
            result.failure_details = [
                (str(test), trace.strip().splitlines()[-1])
                for test, trace in (outcome.failures + outcome.errors)
            ]
            print(stream.getvalue())   # full unittest output stays visible in console/log, like today
        except Exception as e:
            logger.error(f"Suite '{declaration.suite_id}' (block '{block_id}') raised during collection/run", exc_info=True)
            result.collection_error = str(e)
        result.duration_seconds = time.time() - start
        return result
```

Two extra additions to `block_core/core_helpers/constants.py`:

```python
class Core_Block_Loggers(String_Comparable_Mixin):
    ...
    UNIT_TESTING = Logger_Declaration("INFO")

class Core_Runtime_Cache_Members(String_Comparable_Mixin):
    ...
    LAST_UNIT_TEST_REPORT = RTC_Member_Declaration(None)
```

---

## 6. Shared test-support helpers (new)

`block_geometry_actions/tests/test_helpers.py` already established a good pattern: a
`TEST_PREFIX`-tagged factory + a single cleanup sweep. Rather than every block reimplementing
this, promote the generic parts into `addon_helpers/testing_tools.py` (addon-level, per the
"never imports from any block" rule — this file has no bpy-block awareness, just `bpy.data`):

```python
# addon_helpers/testing_tools.py
TEST_NAME_PREFIX = "DGB_TEST_"

def sweep_test_datablocks(extra_collections: tuple = ()) -> int:
    """Remove every bpy.data.* datablock tagged with TEST_NAME_PREFIX. Returns count removed."""
    removed = 0
    collections = (bpy.data.objects, bpy.data.meshes, bpy.data.curves, *extra_collections)
    for collection in collections:
        if collection is None:
            continue
        for datablock in [d for d in collection if d.name.startswith(TEST_NAME_PREFIX)]:
            collection.remove(datablock)
            removed += 1
    return removed


class Idempotent_BPY_TestCase(unittest.TestCase):
    """Base class: sweeps tagged datablocks before AND after every test, and fails loudly
    if a test leaves any behind (catches a forgotten cleanup before it reaches a real session)."""
    extra_collections: tuple = ()

    def setUp(self):
        sweep_test_datablocks(self.extra_collections)

    def tearDown(self):
        leaked = sweep_test_datablocks(self.extra_collections)
        if leaked:
            self.fail(f"Test leaked {leaked} untracked datablock(s) — clean up in the test body, not tearDown")
```

Per-block test modules keep block-specific fixture *creation* (e.g. `create_test_curve_object()`
stays in `block_geometry_actions`), but reuse the shared sweep/base-class instead of hand-rolling
it again in every block, as `block_pip_library_manager/unit_tests/test_helpers.py` currently does
for its own non-bpy fixtures.

---

## 7. Standardized per-block folder

```
block_<name>/
└── unit_tests/
    ├── __init__.py         # docstring only — never imported by the block itself at register time
    ├── test_helpers.py     # block-specific fixture factories, built on addon_helpers/testing_tools.py
    ├── test_<feature>.py   # one or more unittest.TestCase classes + build_suite()
    └── run_tests.py        # run(verbosity=2) + headless __main__ entrypoint (kept for manual/standalone use)
```

This is `block_geometry_actions/tests/` renamed to `unit_tests/` and generalized — see §10 for
the migration note. `run_tests.py` keeps its existing dual-purpose shape (importable `run()` +
headless `__main__` block); nothing about running one block's suite standalone needs to change.

The block's real `__init__.py` gains exactly one new function, following the same
lazy-import-inside-the-function convention every other `hook_get_*` subscriber uses:

```python
def hook_get_unit_test_declarations():
    from .unit_tests.run_tests import build_suite
    return [Unit_Test_Suite_Declaration(
        suite_id = _BLOCK_ID,
        build_suite = build_suite,
        label = "<Block Display Name>",
    )]
```

Because the import is inside the function body, a syntax error or broken import in
`unit_tests/` **cannot** break block registration — it only surfaces the next time
`hook_get_unit_test_declarations` actually runs, where `Wrapper_Unit_Testing` already expects
and isolates that failure.

---

## 8. Invocation surfaces

### a) Interactive / Python console

```python
from DGBlocks.native_blocks.block_core.core_features.unit_testing.feature_wrapper import Wrapper_Unit_Testing
report = Wrapper_Unit_Testing.run_all()
```

### b) UI button (Core panel)

New operator in `core_helpers/ops.py`:

```python
class DGBLOCKS_OT_Run_All_Unit_Tests(bpy.types.Operator):
    bl_idname = "dgblocks.run_all_unit_tests"
    bl_label = "Run All Unit Tests"
    bl_options = {"REGISTER"}

    def execute(self, context):
        report = Wrapper_Unit_Testing.run_all()
        level = {'INFO'} if report.all_passed else {'ERROR'}
        self.report(level, f"Unit tests: {'all passed' if report.all_passed else 'failures — see console'}")
        force_redraw_ui(context)
        return {"FINISHED"}
```

New subpanel under `DGBLOCKS_PT_Core_Block_Panel`, reading `LAST_UNIT_TEST_REPORT` from RTC —
one row per suite (✓/✗ icon, pass count), the run button, and a "Copy Report" button reusing the
existing `DGBLOCKS_OT_Copy_To_Clipboard` (`rtc_key = "LAST_UNIT_TEST_REPORT"`) pattern already
used by the *All RTC Members* panel.

### c) Headless CLI

New script — proposed location `Developer/run_all_unit_tests.py` (dev tooling, not a block).
Canonical target for verifying this suite is **Blender 5.0** — the addon's declared minimum
(`bl_info.blender = (5, 0, 0)`, see `techContext.md`), chosen deliberately over whatever is
newest on a given dev machine so a passing headless run means the floor version actually works,
not just the newest one installed:

```python
import pathlib, sys
import bpy

addon_dir  = pathlib.Path(__file__).resolve().parent.parent   # .../DGBlocks
addon_name = addon_dir.name
if str(addon_dir.parent) not in sys.path:
    sys.path.insert(0, str(addon_dir.parent))

bpy.ops.preferences.addon_enable(module=addon_name)   # runs register() — pre-bpy init only

from DGBlocks.native_blocks.block_core.core_features.control_plane.feature_wrapper import Wrapper_Control_Plane
Wrapper_Control_Plane.init_post_bpy()   # force the deferred post-bpy pass synchronously — see note below

from DGBlocks.native_blocks.block_core.core_features.unit_testing.feature_wrapper import Wrapper_Unit_Testing
report = Wrapper_Unit_Testing.run_all()
sys.exit(0 if report.all_passed else 1)
```

```bash
blender --background --python-exit-code 1 --python Developer/run_all_unit_tests.py
```

**Why the direct `init_post_bpy()` call matters:** `Wrapper_Control_Plane._init_wrapper()`
schedules `init_post_bpy()` through `bpy.app.timers.register(..., first_interval=0.0001)`
(`control_plane/app_handlers.py`), and hook subscriber wiring
(`Wrapper_Hooks.rebuild_hook_subs_cache()`) only happens inside `init_post_bpy()`. Whether a
`bpy.app.timers` callback gets a chance to fire before a `--background --python script.py`
process exits is not guaranteed — and `block_geometry_actions/tests/run_tests.py` already sidesteps
this exact problem today by hand-seeding RTC instead of relying on the timer. `init_post_bpy()` is
already guarded (`if ADDON_METADATA.POST_REG_INIT_HAS_RUN: ...`), so calling it directly is safe
whether or not the timer has already fired — it's the one call needed to make hook discovery
deterministic in both interactive and headless contexts, and it means our test runner can rely on
the *real* hook system instead of a parallel bypass mechanism.

---

## 9. Authoring rules (promotion checklist for `unit_tests/`)

Mirrors the tone of `blockAuthoringGuide.md` §10's Promotion Checklist:

- [ ] Every test creates its own data in `setUp`/at the top of the test, and removes it before
      the test ends — never assumes or mutates the user's existing scene content.
- [ ] Use `Idempotent_BPY_TestCase` (or an equivalent tagged-prefix sweep) so cleanup is one
      sweep, safe to run in a live user session repeatedly.
- [ ] **Never call a block's master `enable_*` toggle or its `repoll()`/rebuild entrypoint**
      (`Wrapper_Timer_Manager.enable_and_poll_for_timers()`, `Wrapper_Shader_Manager.repoll()`,
      `Wrapper_Modal_Manager.repoll()`, `Wrapper_App_Handlers.repoll()`) from inside a test. Those
      pull declarations from **every currently-registered block**, not just the test's own
      fixtures — in a live session this produces real side effects (draw handlers activate,
      timers start ticking, the modal router starts) outside the test's control, and isn't
      idempotent. Test at the layer below: pure validation functions
      (`validate_timer_definitions`, `_validate_shader_definitions`, the merge logic in
      `feature_app_handlers.py`) and narrow manager methods against manually constructed RTC
      records.
- [ ] A test that cannot be exercised without a live window/viewport/modal context should
      `self.skipTest(...)` with a clear reason rather than asserting on unavailable state —
      `block_geometry_actions/unit_tests/test_geometry_actions.py` already does this for
      Curves-object support.
- [ ] `build_suite()` must not raise at *import* time for a reason that is really just "this
      Blender build lacks feature X" — catch that inside the test method via `skipTest`, not at
      module scope, so one missing feature doesn't take out the whole suite.
- [ ] No test may assume another suite (in this block or another block) ran before or after it.
- [ ] No test leaves an addon preference, scene toggle, or RTC member in a different state than
      it found it — restore explicitly in `tearDown` if a narrow manager method was exercised.

---

## 10. Migrating the two existing prototypes — DONE

- **`block_geometry_actions/unit_tests/`** — folder renamed from `tests/`; `hook_get_unit_test_declarations`
  added to `__init__.py`. `test_helpers.py`'s `TEST_PREFIX` sweep has not been rebased onto
  `addon_helpers/testing_tools.py` (still not required — that shared helper module itself hasn't
  been created yet, see §6).
- **`block_pip_library_manager/unit_tests/`** — folder renamed from `tests/`; gained a new
  `run_tests.py` (`build_suite()` over `Test_Pip_Library_Helpers` + `Test_Pip_Install_Worker`) and
  `hook_get_unit_test_declarations` in `__init__.py`. Test content unchanged.

Both now appear as rows in block_core's Unit Tests panel and run via `Wrapper_Unit_Testing`.
`addon_helpers/testing_tools.py` (§6) is still not built — neither block currently needs it,
since geometry_actions already hand-rolls its own tagged-prefix sweep and pip's tests touch no
bpy state at all.

---

## 11. Example tests per block (excluding `block_debug_console_print`)

Each sketch below targets the pure-function / data-layer surface of the block — consistent with
§9's rule against touching live `repoll()`/`enable_*` machinery — and is illustrative, not final
code.

### `block_core` — meta/invariant tests

Startup-based, not runtime-based, as noted in the brief — so its suite is small and asserts on
*already-live* state rather than exercising lifecycle transitions (registering/unregistering
block_core mid-session isn't something a test should ever do). All of these are read-only, so
idempotency is automatic:

```python
class Test_Block_Registry_Invariants(unittest.TestCase):
    def test_all_registered_blocks_are_valid(self):
        blocks = Wrapper_Runtime_Cache.get_cache(Core_Runtime_Cache_Members.REGISTRY_ALL_BLOCKS)
        invalid = [b.block_id for b in blocks if not b.is_valid]
        self.assertEqual(invalid, [], f"Blocks failed registration: {invalid}")

    def test_hook_sources_have_no_orphaned_subscriber_counts(self):
        # subscriber_count should never be negative or raise when recomputed
        Wrapper_Hooks.rebuild_hook_subs_cache()
        sources = Wrapper_Runtime_Cache.get_cache(Core_Runtime_Cache_Members.REGISTRY_ALL_HOOK_SOURCES)
        self.assertTrue(all(s.subscriber_count >= 0 for s in sources))

class Test_RTC_Key_Resolution(unittest.TestCase):
    def test_enum_and_string_resolve_identically(self):
        self.assertEqual(
            get_actual_rtc_key(Core_Runtime_Cache_Members.REGISTRY_ALL_BLOCKS),
            get_actual_rtc_key("REGISTRY_ALL_BLOCKS"),
        )
```

`test_hook_sources_have_no_orphaned_subscriber_counts` calling `rebuild_hook_subs_cache()` is a
deliberate, narrow exception to the "don't call repoll" rule — it's block_core's own hook
registry, idempotent by construction (it fully recomputes from scratch every call — see
`hooks/feature_wrapper.py`), and touches no other block's live state.

### `block_timers`

```python
class Test_Timer_Definition_Validation(unittest.TestCase):
    def test_duplicate_uid_across_blocks_is_rejected(self):
        defs = [Timer_Definition("DUP", 1.0, lambda t: None), Timer_Definition("DUP", 2.0, lambda t: None)]
        with self.assertRaises(ValueError):
            validate_timer_definitions(defs)

    def test_non_positive_frequency_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_timer_definitions([Timer_Definition("T", 0.0, lambda t: None)])

    def test_blank_uids_are_auto_assigned(self):
        defs = [Timer_Definition("", 1.0, lambda t: None), Timer_Definition("", 1.0, lambda t: None)]
        validated = validate_timer_definitions(defs)  # assuming this returns the resolved list
        self.assertEqual([d.timer_uid for d in validated], ["TIMER_0", "TIMER_1"])

class Test_Timer_Manager_Lookup(unittest.TestCase):
    def setUp(self):
        self._saved = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.TIMERS, should_copy=True)

    def tearDown(self):
        Wrapper_Runtime_Cache.set_cache(Block_RTC_Members.TIMERS, self._saved)

    def test_get_timer_returns_none_for_unknown_uid(self):
        self.assertIsNone(Wrapper_Timer_Manager.get_timer("DGB_TEST_DOES_NOT_EXIST"))
```

`Test_Timer_Definition_Validation` needs no bpy state at all — `Timer_Definition` and
`validate_timer_definitions()` are plain dataclasses/functions. `Test_Timer_Manager_Lookup` saves
and restores the real `TIMERS` RTC list around a read-only lookup, rather than calling
`enable_and_poll_for_timers()`.

### `block_app_handlers`

```python
class Test_Frequency_Filter_Merge(unittest.TestCase):
    def test_minimum_frequency_wins_across_subscribers(self):
        subs = [
            App_Handler_Subscription_Declaration(App_Handler_Type.frame_change_post, frequency_filter_seconds=0.5),
            App_Handler_Subscription_Declaration(App_Handler_Type.frame_change_post, frequency_filter_seconds=0.1),
        ]
        merged = merge_handler_subscriptions(subs)  # see feature_app_handlers.py's actual merge helper
        self.assertEqual(merged[App_Handler_Type.frame_change_post].frequency_filter_seconds, 0.1)

class Test_Reentrancy_Flag_Semantics(unittest.TestCase):
    def test_status_instance_starts_not_executing(self):
        status = RTC_App_Handler_Status_Instance(handler_type_name="save_pre")
        self.assertFalse(status.handler_type_name in Wrapper_Runtime_Cache.get_cache(
            Block_RTC_Members.APP_HANDLERS_CURRENTLY_EXECUTING))
```

(`merge_handler_subscriptions` is a placeholder name — the real merge logic in
`feature_app_handlers.py` should be extracted to, or already exists as, a standalone function so
it's testable without calling `repoll()`.)

### `block_modal_events`

```python
class Test_Workspace_Tool_Placement_Expansion(unittest.TestCase):
    def test_two_placements_expand_to_deterministic_ids(self):
        decl = Workspace_Tool_Definition(
            tool_id="test.tool", label="Test", description="", image_icon_name=None, icon="NONE",
            placements=(Workspace_Tool_Placement("VIEW_3D", "OBJECT"), Workspace_Tool_Placement("VIEW_3D", "EDIT_MESH")),
        )
        ids = [placement_id_for(decl, p) for p in decl.placements]  # see workspace_tools.py
        self.assertEqual(ids, ["test.tool.view_3d.object", "test.tool.view_3d.edit_mesh"])

class Test_Listener_End_Reason_Contract(unittest.TestCase):
    def test_end_info_snapshot_is_immutable(self):
        info = Modal_Listener_End_Info(reason="FINISHED", src_block_id="test")
        with self.assertRaises(Exception):
            info.reason = "CANCELLED"   # only if the dataclass is frozen; adjust/drop if not
```

No modal router is started, no real listener is registered — this exercises the ID-generation and
snapshot dataclasses only.

### `block_onscreen_drawing` — tiered by what actually requires a viewport

Three tiers, cheapest/always-safe to explicitly out of scope — rationale in §1 item 6.

**Tier 0 — declaration validation.** `_validate_shader_definitions()` already runs before any
GPU state is touched:

```python
class Test_Shader_Declaration_Validation(unittest.TestCase):
    def test_duplicate_uid_is_rejected(self):
        decls = [_make_minimal_decl("A"), _make_minimal_decl("A")]
        with self.assertRaises(ValueError):
            _validate_shader_definitions(decls)

    def test_invalid_space_region_phase_combo_is_rejected(self):
        decl = _make_minimal_decl("A", space=Draw_Space_Types.VIEW_3D, region=Draw_Region_Type.HEADER, phase=Draw_Phase_type.POST_VIEW)
        with self.assertRaises(ValueError):
            _validate_shader_definitions([decl])

    def test_exactly_one_of_builtin_or_custom_is_required(self):
        decl = _make_minimal_decl("A", builtin_shader_name=None, custom_shader_class=None)
        with self.assertRaises(ValueError):
            _validate_shader_definitions([decl])

class Test_Shader_Manager_Lookup_Before_Enable(unittest.TestCase):
    def test_get_shader_returns_none_when_nothing_is_live(self):
        self.assertIsNone(Wrapper_Shader_Manager.get_shader("DGB_TEST_DOES_NOT_EXIST"))
```

**Tier 1 — real shader compile/link smoke test.** The actual `gpu.types.GPUShader`/
`GPUShaderCreateInfo` can be built from a declared custom shader's source and asserted to
compile/link, without drawing anything. **Correction after actually running this**: the
assumption that `--background` binds a usable GL context (stated earlier in this doc) does not
hold on Blender 5.0 — it raises "GPU functions for drawing are not available in background
mode." So in practice this tier only executes interactively; under `--background` it always
hits the `skipTest` branch below and the suite still reports OK. Kept as designed rather than
removed, since it's real coverage the moment someone runs the suite from the Python console:

```python
class Test_Shader_Compiles(unittest.TestCase):
    def test_every_declared_custom_shader_compiles(self):
        for decl in _get_all_declared_shaders():
            if decl.custom_shader_class is None:
                continue   # builtins are Blender's own responsibility, not ours to compile-test
            with self.subTest(shader_uid=decl.shader_uid):
                try:
                    shader = gpu.types.GPUShader(
                        decl.custom_shader_class.vertex_source,
                        decl.custom_shader_class.fragment_source,
                    )
                except Exception as e:
                    self.skipTest(f"No usable GPU context on this runner: {e}")
                    return
                self.assertIsNotNone(shader)
```

Nothing here enables drawing, registers a draw handler, or touches a GPU batch/framebuffer — it
stops at "does this GLSL compile," one layer below actual rendering.

**Out of scope, permanently:** anything requiring a live `SpaceView3D` draw pass — draw handler
registration actually firing, per-frame draw callbacks, real projection/view matrices from an
active window. No redraw loop exists headless, and it isn't reliably scriptable even
interactively. Offscreen render + pixel-readback (`GPUOffScreen`) is *technically* possible
headless too, but is deliberately deferred to a future, separate "visual regression" tier outside
`unit_tests/` — not part of this pass.

### `block_pip_library_manager`

Already the most mature test suite in the repo (`test_helpers.py`, `test_install_worker.py`); the
only gap for this framework is wiring, not coverage:

```python
# unit_tests/run_tests.py  (new — mirrors block_geometry_actions' shape)
def build_suite() -> unittest.TestSuite:
    loader, suite = unittest.TestLoader(), unittest.TestSuite()
    for test_case in (Test_Pip_Library_Helpers, Test_Pip_Install_Worker):
        suite.addTests(loader.loadTestsFromTestCase(test_case))
    return suite

def run(verbosity: int = 2) -> bool:
    return unittest.TextTestRunner(verbosity=verbosity).run(build_suite()).wasSuccessful()
```

```python
# __init__.py addition
def hook_get_unit_test_declarations():
    from .unit_tests.run_tests import build_suite
    return [Unit_Test_Suite_Declaration(suite_id=_BLOCK_ID, build_suite=build_suite, label="Pip Library Manager")]
```

Its existing tests already follow every rule in §9 — tempdir-scoped, no live pip installs, no
bpy state touched at all — so no test content needs to change.

### `block_geometry_actions`

Already fully built (`tests/test_geometry_actions.py`, `tests/test_helpers.py`,
`tests/run_tests.py`) and already documented in its own `README.md` §"Tests". Only needs the
folder rename (§10) and the one-function hook subscriber (§7) to join the framework — no test
content changes.

---

## 12. Open questions / next steps

Deliberately unresolved here — for the follow-up implementation pass:

1. Should `tags` (e.g. `"slow"`) drive an actual filter argument on `run_all()` and the UI
   operator now, or stay reserved/unused until something needs it?
2. Does the Core panel's new subpanel belong under *General Settings* or as its own top-level
   subpanel next to *All Blocks* / *All Hooks* / *All Loggers*?
3. Should `Wrapper_Unit_Testing.run_all()` also fire a hook of its own (e.g.
   `hook_after_unit_test_run`) so a CI-adjacent block could react to results, or is the RTC report
   + operator return value sufficient for now?
4. `addon_helpers/testing_tools.py` is new — confirm the "addon_helpers never imports from any
   block" rule (Block_Structure_Overview.md §1) is compatible with it importing only `bpy` and
   stdlib `unittest`, which it is, but worth a second look before it's added.
