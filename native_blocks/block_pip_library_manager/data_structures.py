from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from queue import Queue
from threading import Event
from types import ModuleType
from typing import Optional


class Library_Source_Policy(StrEnum):
    ONLINE_ONLY = "ONLINE_ONLY"
    BUNDLED_ONLY = "BUNDLED_ONLY"
    PREFER_BUNDLED = "PREFER_BUNDLED"


class Library_Status(StrEnum):
    UNKNOWN = "UNKNOWN"
    NOT_INSTALLED = "NOT_INSTALLED"
    SATISFIED = "SATISFIED"
    VERSION_MISMATCH = "VERSION_MISMATCH"
    CONFLICTING_REQUIREMENTS = "CONFLICTING_REQUIREMENTS"
    IMPORT_ERROR = "IMPORT_ERROR"
    INSTALLING = "INSTALLING"
    INSTALL_FAILED = "INSTALL_FAILED"
    RESTART_REQUIRED = "RESTART_REQUIRED"
    UNSUPPORTED_PLATFORM = "UNSUPPORTED_PLATFORM"
    NO_COMPATIBLE_WHEEL = "NO_COMPATIBLE_WHEEL"
    PIP_UNAVAILABLE = "PIP_UNAVAILABLE"


class Library_Ensure_Result(StrEnum):
    AVAILABLE = "AVAILABLE"
    PROMPTED = "PROMPTED"
    INSTALLING = "INSTALLING"
    RESTART_REQUIRED = "RESTART_REQUIRED"
    CANCELLED = "CANCELLED"
    UNAVAILABLE = "UNAVAILABLE"
    ERROR = "ERROR"


class Library_Operation_Status(StrEnum):
    PREPARING = "PREPARING"
    INSTALLING = "INSTALLING"
    VERIFYING = "VERIFYING"
    ACTIVATING = "ACTIVATING"
    FINISHED = "FINISHED"
    CANCELLED = "CANCELLED"
    ERROR = "ERROR"
    RESTART_REQUIRED = "RESTART_REQUIRED"


@dataclass(frozen=True)
class Python_Library_Requirement_Declaration:
    """One exact, wheel-only Python distribution requirement declared by a block."""

    requirement_uid: str
    distribution_name: str
    import_names: tuple[str, ...]
    required_version: str
    feature_label: str
    reason: str
    source_policy: Library_Source_Policy = Library_Source_Policy.ONLINE_ONLY
    bundled_wheel_root: Optional[str] = None
    allow_online_fallback: bool = False
    # (path relative to bundled_wheel_root, lowercase SHA-256 hex digest)
    bundled_wheel_sha256: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class RTC_Library_Info:
    distribution_name: str
    normalized_name: str
    installed_version: Optional[str]
    install_path: Optional[str]
    status: Library_Status
    required_versions: tuple[str, ...] = ()
    requesting_block_ids: tuple[str, ...] = ()
    error_summary: str = ""
    is_managed_install: bool = False


@dataclass(frozen=True)
class RTC_Library_Requirement_Info:
    namespaced_uid: str
    requirement_uid: str
    requesting_block_id: str
    declaration: Python_Library_Requirement_Declaration
    status: Library_Status
    installed_version: Optional[str] = None
    install_path: Optional[str] = None
    error_summary: str = ""
    requesting_block_module: Optional[ModuleType] = field(default=None, repr=False, compare=False)


@dataclass(frozen=True)
class RTC_Library_Install_Request:
    request_uid: str
    namespaced_requirement_uid: str
    requesting_block_id: str
    action_token: str
    created_timestamp: float


@dataclass
class RTC_Library_Operation:
    operation_uid: str
    request_uid: str
    namespaced_requirement_uid: str
    distribution_name: str
    required_version: str
    target_path: str
    staging_path: str
    log_path: str
    status: Library_Operation_Status = Library_Operation_Status.PREPARING
    recent_log_lines: list[str] = field(default_factory=list)
    total_log_line_count: int = 0
    error_summary: str = ""
    return_code: Optional[int] = None
    restart_required: bool = False
    worker_queue: Queue = field(default_factory=Queue, repr=False, compare=False)
    cancel_event: Event = field(default_factory=Event, repr=False, compare=False)
    process: object = field(default=None, repr=False, compare=False)


@dataclass(frozen=True)
class Managed_Library_Path_State:
    addon_environment_id: str
    environment_root: str
    site_packages_path: str
    python_cache_tag: str
    platform_tag: str
    is_registered: bool
    warning: str = ""


@dataclass(frozen=True)
class Pip_Install_Plan:
    requirement_arg: str
    target_path: Path
    find_links: tuple[Path, ...] = ()
    no_index: bool = False
