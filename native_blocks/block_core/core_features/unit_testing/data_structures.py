
from dataclasses import dataclass, field
from enum import StrEnum, auto
from typing import Optional
import bpy

DEFAULT_SUITE_GROUP_LABEL = "Default"

# ==============================================================================================================================
# STATUS ENUM

class Unit_Test_Status(StrEnum):
    NOT_RUN = auto()
    PASSED  = auto()
    FAILED  = auto()
    ERROR   = auto()
    SKIPPED = auto()

# ==============================================================================================================================
# RTC RECORDS
#
# Four levels, each with its own last_run_at: only bumped by an explicit run AT that exact
# scope (run_all / run_block / run_group / run_one_test) — never by a narrower or broader run.
# Pass/fail summaries shown in the UI are always computed live from Unit_Test_Case_Info entries,
# never cached on these rows, so a summary can never drift from the tests it describes.

@dataclass
class Unit_Test_Case_Info:
    """
    One individual unittest test method, discovered (not necessarily yet run) from a block's
    Unit_Test_Suite_Declaration. test_id is the real unittest dotted id (module.Class.method),
    so it can be re-run standalone via unittest.TestLoader().loadTestsFromName(test_id).
    """
    test_id: str
    short_label: str
    block_id: str
    suite_id: str
    suite_label: str
    suite_group: str = DEFAULT_SUITE_GROUP_LABEL
    cold_start_only: bool = False   # inherited from the owning Unit_Test_Suite_Declaration
    docstring: Optional[str] = None # the test method's own __doc__, read via inspect.getdoc()

    status: Unit_Test_Status = Unit_Test_Status.NOT_RUN
    duration_seconds: float = 0.0
    error_text: Optional[str] = None
    last_run_at: Optional[float] = None


@dataclass
class RTC_Unit_Test_Group_Row_Instance:
    """One per (block_id, suite_group) pair. Only shown as its own subpanel when a block has >1 group."""
    block_id: str
    suite_group: str
    last_run_at: Optional[float] = None
    last_run_duration_seconds: float = 0.0


@dataclass
class RTC_Unit_Test_Block_Row_Instance:
    """
    One per block that subscribes to hook_get_unit_test_declarations.
    is_enabled / last_run_at / last_run_duration_seconds are mirrored to
    DGBLOCKS_PG_Unit_Test_Block_Row (see below) so they persist across file save/reload.
    """
    block_id: str
    label: str
    is_enabled: bool = True
    last_run_at: Optional[float] = None
    last_run_duration_seconds: float = 0.0
    collection_error: Optional[str] = None   # hook_get_unit_test_declarations or a build_suite() raised


@dataclass
class Unit_Test_Run_Report:
    """The 'all tests' level. Only set by Wrapper_Unit_Testing.run_all()."""
    started_at: float
    finished_at: float
    block_ids_run: list = field(default_factory = list)

# ==============================================================================================================================
# BL PROPERTY GROUP

def _callback_unit_test_block_row_enabled_changed(self, context):
    """
    Fired when the user toggles a block's checkbox in the Unit Tests UIList.
    Pushes the new value into RTC through the standard BL->RTC data mirror sync.

    Imported lazily (not at module scope) to avoid an import cycle:
    constants -> ui -> ... -> unit_testing.data_structures
    """
    from ...core_helpers.constants import Core_Block_Loggers, Core_Runtime_Cache_Members
    from ..runtime_cache.feature_wrapper import Wrapper_Runtime_Cache
    from ..loggers.feature_wrapper import get_logger
    from .....addon_helpers.data_structures import Enum_Sync_Events

    if Wrapper_Runtime_Cache.is_cache_flagged_as_syncing(Core_Runtime_Cache_Members.UNIT_TEST_BLOCK_ROWS):
        return

    logger = get_logger(Core_Block_Loggers.UNIT_TESTING)
    Wrapper_Runtime_Cache.resync_single_data_mirror(
        event = Enum_Sync_Events.PROPERTY_UPDATE,
        BL_is_truth_source = True,
        cache_key = Core_Runtime_Cache_Members.UNIT_TEST_BLOCK_ROWS,
        logger = logger,
    )


class DGBLOCKS_PG_Unit_Test_Block_Row(bpy.types.PropertyGroup):
    """
    One persistent row per block with discoverable unit tests.
    Populated/maintained by Wrapper_Unit_Testing. is_enabled is user-editable and gates
    whether this block's tests run as part of 'Run All Unit Tests'.
    """
    block_id: bpy.props.StringProperty()  # type: ignore
    is_enabled: bpy.props.BoolProperty(     # type: ignore
        name = "Enabled",
        default = True,
        description = "Include this block's tests in 'Run All Unit Tests'",
        update = _callback_unit_test_block_row_enabled_changed,
    )
    # 0.0 == "never run" — Blender has no native Optional[float], and format_timestamp_for_ui
    # already treats any falsy timestamp as "Never", so 0.0 and None are interchangeable here.
    last_run_at: bpy.props.FloatProperty(default = 0.0)               # type: ignore
    last_run_duration_seconds: bpy.props.FloatProperty(default = 0.0) # type: ignore
