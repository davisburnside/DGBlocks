import importlib
import os
import site
import sys
import threading
import time
import uuid
from dataclasses import replace
from pathlib import Path
from queue import Empty
from types import ModuleType
from typing import Optional

import bpy

from ...addon_config.static_settings import addon_python_environment_id
from ...addon_helpers.data_structures import Abstract_Feature_Wrapper
from ...addon_helpers.generic_tools import force_redraw_ui, get_addon_preferences
from ..block_core.core_features.hooks.feature_wrapper import Wrapper_Hooks
from ..block_core.core_features.loggers.feature_wrapper import get_logger
from ..block_core.core_features.runtime_cache.feature_wrapper import Wrapper_Runtime_Cache
from .common_declarations import Block_Hook_Sources, Block_Loggers, Block_RTC_Members
from .data_structures import (
    Library_Ensure_Result,
    Library_Operation_Status,
    Library_Source_Policy,
    Library_Status,
    Managed_Library_Path_State,
    Python_Library_Requirement_Declaration,
    RTC_Library_Info,
    RTC_Library_Install_Request,
    RTC_Library_Operation,
    RTC_Library_Requirement_Info,
)
from .helpers import (
    append_recent_log,
    build_managed_paths,
    discover_distributions,
    find_compatible_python_executable,
    get_path_length_warning,
    get_required_version_label,
    iter_loaded_import_conflicts,
    normalize_distribution_name,
    reject_duplicate_requirement_uids,
    resolve_bundled_wheel_dirs,
    validate_requirement,
    verify_declared_wheel_hashes,
)
from .install_worker import run_pip_install_worker


class Wrapper_Pip_Library_Manager(Abstract_Feature_Wrapper):
    """Hook-polled, RTC-backed manager for optional wheel dependencies."""

    _operation_monitor_timer_func = None
    _operation_monitor_interval = 0.15

    # ----------------------------------------------------------------------------------
    # Lifecycle

    @classmethod
    def _init_wrapper(cls) -> bool:
        get_logger(Block_Loggers.PIP_LIBRARY_LIFECYCLE).debug(
            "Pip library manager ready; declarations will be polled after startup"
        )
        return True

    @classmethod
    def _remove_wrapper(cls) -> None:
        try:
            timer_func = cls._operation_monitor_timer_func
            if timer_func is not None and bpy.app.timers.is_registered(timer_func):
                bpy.app.timers.unregister(timer_func)
            cls._operation_monitor_timer_func = None
            for operation in cls._operations().values():
                operation.cancel_event.set()
                if operation.process is not None:
                    operation.process.kill()
        except Exception:
            get_logger(Block_Loggers.PIP_LIBRARY_OPERATIONS).error(
                "Failed while cancelling pip operations during teardown", exc_info=True
            )

    # ----------------------------------------------------------------------------------
    # Public query API — all data comes from RTC, never the BL display rows

    @classmethod
    def repoll(cls) -> None:
        logger = get_logger(Block_Loggers.PIP_LIBRARY_LIFECYCLE)
        try:
            site_path = cls._ensure_managed_path()
            discovered = discover_distributions(site_path)
            raw_results = Wrapper_Hooks.run_hooked_funcs(
                Block_Hook_Sources.hook_get_python_library_requirements
            ) or {}

            requirement_infos: dict[str, RTC_Library_Requirement_Info] = {}
            grouped: dict[str, list[RTC_Library_Requirement_Info]] = {}
            for block_id, result in raw_results.items():
                if result is None:
                    continue
                if not isinstance(result, list):
                    logger.warning(
                        f"Requirement hook from '{block_id}' returned {type(result)!r}; expected list"
                    )
                    continue
                block_module = cls._get_registered_block_module(block_id)
                valid_declarations = []
                for declaration in result:
                    if not isinstance(declaration, Python_Library_Requirement_Declaration):
                        logger.warning(f"Ignoring invalid requirement declaration from '{block_id}'")
                        continue
                    valid_declarations.append(declaration)
                for declaration in reject_duplicate_requirement_uids(block_id, valid_declarations, logger):
                    try:
                        validate_requirement(declaration)
                    except Exception as exc:
                        logger.error(f"Invalid requirement from '{block_id}': {exc}")
                        continue
                    namespaced_uid = f"{block_id}:{declaration.requirement_uid}"
                    normalized = normalize_distribution_name(declaration.distribution_name)
                    installed = discovered.get(normalized)
                    required_version = declaration.required_version
                    status = (
                        Library_Status.NOT_INSTALLED
                        if installed is None
                        else Library_Status.SATISFIED
                        if required_version is None or installed[0] == required_version
                        else Library_Status.VERSION_MISMATCH
                    )
                    error_summary = ""
                    if status == Library_Status.SATISFIED:
                        loaded_conflicts = tuple(
                            iter_loaded_import_conflicts(declaration.import_names, site_path)
                        )
                        if loaded_conflicts:
                            status = Library_Status.RESTART_REQUIRED
                            loaded_name, loaded_path = loaded_conflicts[0]
                            error_summary = (
                                f"Import '{loaded_name}' is already loaded from {loaded_path}; "
                                "restart Blender after resolving the conflicting load order"
                            )
                    info = RTC_Library_Requirement_Info(
                        namespaced_uid=namespaced_uid,
                        requirement_uid=declaration.requirement_uid,
                        requesting_block_id=block_id,
                        declaration=declaration,
                        status=status,
                        installed_version=installed[0] if installed else None,
                        install_path=installed[1] if installed else None,
                        error_summary=error_summary,
                        requesting_block_module=block_module,
                    )
                    requirement_infos[namespaced_uid] = info
                    grouped.setdefault(normalized, []).append(info)

            library_infos: dict[str, RTC_Library_Info] = {}
            for normalized, infos in grouped.items():
                version_constraints = {
                    item.declaration.required_version for item in infos
                }
                versions = tuple(sorted(
                    get_required_version_label(version) for version in version_constraints
                ))
                installed = discovered.get(normalized)
                # "latest" plus an exact pin is ambiguous: selecting the latest release could
                # violate the exact requester. Multiple unpinned declarations remain compatible.
                conflict = len(version_constraints) > 1
                status = (
                    Library_Status.CONFLICTING_REQUIREMENTS
                    if conflict
                    else Library_Status.RESTART_REQUIRED
                    if any(item.status == Library_Status.RESTART_REQUIRED for item in infos)
                    else Library_Status.NOT_INSTALLED
                    if installed is None
                    else Library_Status.SATISFIED
                    if None in version_constraints or installed[0] in version_constraints
                    else Library_Status.VERSION_MISMATCH
                )
                error = (
                    "Incompatible exact versions requested"
                    if conflict
                    else next(
                        (item.error_summary for item in infos if item.error_summary), ""
                    )
                )
                library_infos[normalized] = RTC_Library_Info(
                    distribution_name=infos[0].declaration.distribution_name,
                    normalized_name=normalized,
                    installed_version=installed[0] if installed else None,
                    install_path=installed[1] if installed else None,
                    status=status,
                    required_versions=versions,
                    requesting_block_ids=tuple(sorted({item.requesting_block_id for item in infos})),
                    error_summary=error,
                    is_managed_install=installed is not None,
                )
                if conflict:
                    for item in infos:
                        requirement_infos[item.namespaced_uid] = replace(
                            item,
                            status=Library_Status.CONFLICTING_REQUIREMENTS,
                            error_summary=error,
                        )

            Wrapper_Runtime_Cache.set_cache(Block_RTC_Members.REQUIREMENT_INFOS, requirement_infos)
            Wrapper_Runtime_Cache.set_cache(Block_RTC_Members.LIBRARY_INFOS, library_infos)
            cls._sync_status_to_bl()
            logger.info(
                f"Polled {len(requirement_infos)} Python requirement(s), "
                f"{len(library_infos)} distribution(s)"
            )
        except Exception:
            logger.error("Unable to repoll Python library requirements", exc_info=True)

    @classmethod
    def get_library_info(cls, distribution_name: str) -> Optional[RTC_Library_Info]:
        return cls._library_infos().get(normalize_distribution_name(distribution_name))

    @classmethod
    def get_all_library_infos(cls) -> tuple[RTC_Library_Info, ...]:
        return tuple(cls._library_infos().values())

    @classmethod
    def get_requirement_info(
        cls, requirement_uid: str, requesting_block_id: Optional[str] = None
    ) -> Optional[RTC_Library_Requirement_Info]:
        infos = cls._requirement_infos()
        if requesting_block_id:
            return infos.get(f"{requesting_block_id}:{requirement_uid}")
        matches = [item for item in infos.values() if item.requirement_uid == requirement_uid]
        return matches[0] if len(matches) == 1 else None

    @classmethod
    def is_library_installed(
        cls, distribution_name: str, required_version: Optional[str] = None
    ) -> bool:
        info = cls.get_library_info(distribution_name)
        if info is None or info.installed_version is None:
            return False
        return required_version is None or info.installed_version == required_version

    @classmethod
    def is_requirement_satisfied(
        cls, requirement_uid: str, requesting_block_id: Optional[str] = None
    ) -> bool:
        info = cls.get_requirement_info(requirement_uid, requesting_block_id)
        return info is not None and info.status == Library_Status.SATISFIED

    @classmethod
    def get_module(cls, requirement_uid: str, requesting_block_id: str) -> Optional[ModuleType]:
        info = cls.get_requirement_info(requirement_uid, requesting_block_id)
        if info is None or info.status != Library_Status.SATISFIED:
            return None
        modules = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.MODULE_CACHE) or {}
        if info.namespaced_uid in modules:
            return modules[info.namespaced_uid]
        try:
            module = importlib.import_module(info.declaration.import_names[0])
            modules[info.namespaced_uid] = module
            Wrapper_Runtime_Cache.set_cache(Block_RTC_Members.MODULE_CACHE, modules)
            return module
        except Exception as exc:
            get_logger(Block_Loggers.PIP_LIBRARY_LIFECYCLE).error(
                f"Unable to import '{info.declaration.import_names[0]}': {exc}", exc_info=True
            )
            return None

    @classmethod
    def ensure_requirement(
        cls,
        requirement_uid: str,
        requesting_block_id: str,
        action_token: str = "",
        context=None,
    ) -> Library_Ensure_Result:
        info = cls.get_requirement_info(requirement_uid, requesting_block_id)
        if info is None:
            cls.repoll()
            info = cls.get_requirement_info(requirement_uid, requesting_block_id)
        if info is None:
            return Library_Ensure_Result.UNAVAILABLE
        if info.status == Library_Status.SATISFIED:
            return Library_Ensure_Result.AVAILABLE
        if info.status == Library_Status.RESTART_REQUIRED:
            return Library_Ensure_Result.RESTART_REQUIRED
        if info.status == Library_Status.CONFLICTING_REQUIREMENTS:
            return Library_Ensure_Result.UNAVAILABLE
        for operation in cls._operations().values():
            if (
                operation.namespaced_requirement_uid == info.namespaced_uid
                and operation.status
                in {
                    Library_Operation_Status.PREPARING,
                    Library_Operation_Status.INSTALLING,
                    Library_Operation_Status.VERIFYING,
                    Library_Operation_Status.ACTIVATING,
                }
            ):
                return Library_Ensure_Result.INSTALLING
        return cls.prompt_for_requirement(
            requirement_uid, requesting_block_id, action_token, context
        )

    @classmethod
    def prompt_for_requirement(
        cls,
        requirement_uid: str,
        requesting_block_id: str,
        action_token: str = "",
        context=None,
    ) -> Library_Ensure_Result:
        context = context or bpy.context
        if bpy.app.background or threading.current_thread() is not threading.main_thread():
            return Library_Ensure_Result.UNAVAILABLE
        info = cls.get_requirement_info(requirement_uid, requesting_block_id)
        if info is None or context.window_manager is None or context.window is None:
            return Library_Ensure_Result.UNAVAILABLE
        request_uid = uuid.uuid4().hex[:12]
        requests = cls._requests()
        requests[request_uid] = RTC_Library_Install_Request(
            request_uid=request_uid,
            namespaced_requirement_uid=info.namespaced_uid,
            requesting_block_id=requesting_block_id,
            action_token=action_token,
            created_timestamp=time.time(),
        )
        Wrapper_Runtime_Cache.set_cache(Block_RTC_Members.INSTALL_REQUESTS, requests)
        result = bpy.ops.dgblocks.pip_library_confirm_install(
            "INVOKE_DEFAULT", request_uid=request_uid
        )
        return (
            Library_Ensure_Result.PROMPTED
            if "RUNNING_MODAL" in result
            else Library_Ensure_Result.CANCELLED
        )

    @classmethod
    def start_install(cls, request_uid: str) -> Optional[RTC_Library_Operation]:
        request = cls._requests().get(request_uid)
        info = cls._requirement_infos().get(
            request.namespaced_requirement_uid if request else ""
        )
        if request is None or info is None:
            return None
        logger = get_logger(Block_Loggers.PIP_LIBRARY_OPERATIONS)
        try:
            if any(
                operation.status
                in {
                    Library_Operation_Status.PREPARING,
                    Library_Operation_Status.INSTALLING,
                    Library_Operation_Status.VERIFYING,
                    Library_Operation_Status.ACTIVATING,
                }
                for operation in cls._operations().values()
            ):
                raise RuntimeError("Another Python library installation is already active")
            python_exe = find_compatible_python_executable()
            if python_exe is None:
                raise RuntimeError("No compatible Python executable was found for Blender")
            path_state = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.MANAGED_PATH_STATE)
            target = Path(path_state.site_packages_path)
            if target.with_name(f"{target.name}.pending").exists():
                raise RuntimeError(
                    "A pending library environment is waiting for Blender to restart"
                )
            operation_uid = uuid.uuid4().hex[:10]
            staging = target.with_name(f"staging-{operation_uid}")
            log_path = Path(path_state.environment_root) / "logs" / f"pip-{operation_uid}.log"

            command = [
                str(python_exe), "-m", "pip", "install",
                (
                    info.declaration.distribution_name
                    if info.declaration.required_version is None
                    else f"{info.declaration.distribution_name}=={info.declaration.required_version}"
                ),
                "--target", str(staging),
                "--upgrade",
                "--only-binary=:all:", "--no-user", "--no-input",
                "--disable-pip-version-check", "--no-warn-script-location",
            ]
            wheel_dirs = ()
            if info.declaration.source_policy != Library_Source_Policy.ONLINE_ONLY:
                if info.requesting_block_module is None or not info.requesting_block_module.__file__:
                    raise RuntimeError("Requesting block file is unavailable")
                verify_declared_wheel_hashes(
                    info.declaration, info.requesting_block_module.__file__
                )
                wheel_dirs = resolve_bundled_wheel_dirs(
                    info.declaration, info.requesting_block_module.__file__
                )
                if not wheel_dirs:
                    raise RuntimeError("No bundled wheel folder matches this platform and Python ABI")
                for wheel_dir in wheel_dirs:
                    command.extend(["--find-links", str(wheel_dir)])
                if (
                    info.declaration.source_policy == Library_Source_Policy.BUNDLED_ONLY
                    or not info.declaration.allow_online_fallback
                ):
                    command.append("--no-index")

            operation = RTC_Library_Operation(
                operation_uid=operation_uid,
                request_uid=request_uid,
                namespaced_requirement_uid=info.namespaced_uid,
                distribution_name=info.declaration.distribution_name,
                required_version=info.declaration.required_version,
                target_path=str(target),
                staging_path=str(staging),
                log_path=str(log_path),
            )
            operations = cls._operations()
            operations[operation_uid] = operation
            Wrapper_Runtime_Cache.set_cache(Block_RTC_Members.INSTALL_OPERATIONS, operations)
            defer_activation = any(
                name.split(".", 1)[0] in sys.modules
                for name in info.declaration.import_names
            )
            target_resolved = target.resolve()
            for module in tuple(sys.modules.values()):
                module_file = getattr(module, "__file__", None)
                if not module_file:
                    continue
                try:
                    Path(module_file).resolve().relative_to(target_resolved)
                    defer_activation = True
                    break
                except (OSError, ValueError):
                    continue
            worker = threading.Thread(
                target=run_pip_install_worker,
                args=(
                    operation,
                    command,
                    target,
                    staging,
                    defer_activation,
                    info.declaration.distribution_name,
                    info.declaration.required_version,
                ),
                daemon=True,
                name=f"DGBlocks-pip-{operation_uid}",
            )
            worker.start()
            cls._ensure_operation_monitor_running()
            logger.info(
                f"Started wheel install for {operation.distribution_name} "
                f"{get_required_version_label(operation.required_version)}"
            )
            return operation
        except Exception as exc:
            logger.error(f"Unable to start pip install: {exc}", exc_info=True)
            return None

    @classmethod
    def poll_operation(cls, operation_uid: str) -> Optional[RTC_Library_Operation]:
        operation = cls._operations().get(operation_uid)
        if operation is None:
            return None
        while True:
            try:
                event_type, payload = operation.worker_queue.get_nowait()
            except Empty:
                break
            if event_type == "LOG":
                operation.total_log_line_count += 1
                append_recent_log(operation.recent_log_lines, payload)
            elif event_type == "STATUS":
                operation.status = Library_Operation_Status(payload)
            elif event_type == "PROCESS_STARTED":
                operation.process = payload
            elif event_type == "PROCESS_ENDED":
                operation.process = None
            elif event_type == "RESOLVED_VERSION":
                operation.resolved_version = str(payload)
            elif event_type == "FINISHED":
                operation.return_code = payload
                cls._finish_operation(operation)
            elif event_type == "CANCELLED":
                operation.return_code = payload
                operation.status = Library_Operation_Status.CANCELLED
            elif event_type == "RESTART_REQUIRED":
                operation.return_code = payload
                operation.restart_required = True
                operation.status = Library_Operation_Status.RESTART_REQUIRED
            elif event_type == "ERROR":
                operation.error_summary = str(payload)
                operation.status = Library_Operation_Status.ERROR
        return operation

    @classmethod
    def get_operation(cls, operation_uid: str) -> Optional[RTC_Library_Operation]:
        """Return live RTC state without draining queues or causing lifecycle transitions."""
        return cls._operations().get(operation_uid)

    @classmethod
    def get_managed_path_state(cls) -> Optional[Managed_Library_Path_State]:
        """Read the current path state without creating folders or changing sys.path."""
        return Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.MANAGED_PATH_STATE)

    @classmethod
    def _ensure_operation_monitor_running(cls) -> None:
        """Start one main-thread application timer for every active install operation."""
        timer_func = cls._operation_monitor_timer_func
        if timer_func is not None and bpy.app.timers.is_registered(timer_func):
            return

        def _monitor_tick():
            try:
                active_statuses = {
                    Library_Operation_Status.PREPARING,
                    Library_Operation_Status.INSTALLING,
                    Library_Operation_Status.VERIFYING,
                    Library_Operation_Status.ACTIVATING,
                }
                has_active_operation = False
                for operation_uid in tuple(cls._operations().keys()):
                    operation = cls.poll_operation(operation_uid)
                    if operation is not None and operation.status in active_statuses:
                        has_active_operation = True
                force_redraw_ui(bpy.context, only_3Dviewport=False)
                if has_active_operation:
                    return cls._operation_monitor_interval
            except Exception:
                get_logger(Block_Loggers.PIP_LIBRARY_OPERATIONS).error(
                    "Python library operation monitor failed", exc_info=True
                )
                if any(
                    operation.status in {
                        Library_Operation_Status.PREPARING,
                        Library_Operation_Status.INSTALLING,
                        Library_Operation_Status.VERIFYING,
                        Library_Operation_Status.ACTIVATING,
                    }
                    for operation in cls._operations().values()
                ):
                    return cls._operation_monitor_interval
            cls._operation_monitor_timer_func = None
            return None

        cls._operation_monitor_timer_func = _monitor_tick
        bpy.app.timers.register(
            _monitor_tick,
            first_interval=cls._operation_monitor_interval,
            persistent=False,
        )

    @classmethod
    def cancel_operation(cls, operation_uid: str) -> bool:
        operation = cls._operations().get(operation_uid)
        if operation is None:
            return False
        operation.cancel_event.set()
        if operation.process is not None:
            try:
                operation.process.kill()
            except Exception:
                get_logger(Block_Loggers.PIP_LIBRARY_OPERATIONS).error(
                    "Unable to kill pip process", exc_info=True
                )
        return True

    # ----------------------------------------------------------------------------------
    # Internal helpers

    @classmethod
    def _finish_operation(cls, operation: RTC_Library_Operation) -> None:
        info = cls._requirement_infos().get(operation.namespaced_requirement_uid)
        state = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.MANAGED_PATH_STATE)
        imported = False
        if info and state:
            imported = any(
                name.split(".", 1)[0] in sys.modules for name in info.declaration.import_names
            )
            imported = imported or any(
                iter_loaded_import_conflicts(info.declaration.import_names, Path(state.site_packages_path))
            )
        importlib.invalidate_caches()
        cls.repoll()
        if imported:
            operation.restart_required = True
            operation.status = Library_Operation_Status.RESTART_REQUIRED
        else:
            operation.status = Library_Operation_Status.FINISHED
            request = cls._requests().get(operation.request_uid)
            if request and info:
                Wrapper_Hooks.run_hooked_funcs(
                    Block_Hook_Sources.hook_python_library_requirement_available,
                    subscriber_block_id=request.requesting_block_id,
                    should_halt_on_exception=False,
                    requirement_uid=info.requirement_uid,
                    action_token=request.action_token,
                )

    @classmethod
    def _ensure_managed_path(cls) -> Path:
        try:
            prefs = get_addon_preferences(bpy.context)
            base_path = prefs.addon_saved_data_folder
        except (AttributeError, KeyError):
            # Direct package registration in tests/development can occur before Blender has
            # created the AddonPreferences collection entry. Match the declared preference
            # default rather than making metadata discovery fail in that context.
            base_path = os.path.expanduser("~/.blender_dgblocks_data/")
        if not base_path:
            raise RuntimeError("Addon data folder is not configured in Preferences")
        environment_root, site_path = build_managed_paths(base_path, bpy.app.version)
        environment_root.mkdir(parents=True, exist_ok=True)
        pending_path = site_path.with_name(f"{site_path.name}.pending")
        if pending_path.is_dir():
            backup_path = site_path.with_name(f"{site_path.name}.startup-backup")
            import shutil
            if backup_path.exists():
                shutil.rmtree(backup_path)
            if site_path.exists():
                site_path.replace(backup_path)
            try:
                pending_path.replace(site_path)
                if backup_path.exists():
                    shutil.rmtree(backup_path)
            except Exception:
                if backup_path.exists() and not site_path.exists():
                    backup_path.replace(site_path)
                raise
        site_path.mkdir(parents=True, exist_ok=True)
        # Insert before Blender/global site-packages so this addon's managed environment wins
        # when a module has not already been loaded into sys.modules.
        site.addsitedir(str(site_path))
        if str(site_path) in sys.path:
            sys.path.remove(str(site_path))
        sys.path.insert(0, str(site_path))
        state = Managed_Library_Path_State(
            addon_environment_id=addon_python_environment_id,
            environment_root=str(environment_root),
            site_packages_path=str(site_path),
            python_cache_tag=sys.implementation.cache_tag or "unknown",
            platform_tag=sys.platform,
            is_registered=True,
            warning=get_path_length_warning(site_path),
        )
        Wrapper_Runtime_Cache.set_cache(Block_RTC_Members.MANAGED_PATH_STATE, state)
        return site_path

    @classmethod
    def _get_registered_block_module(cls, block_id: str):
        from ..block_core.core_helpers.constants import Core_Runtime_Cache_Members
        blocks = Wrapper_Runtime_Cache.get_cache(
            Core_Runtime_Cache_Members.REGISTRY_ALL_BLOCKS
        ) or []
        match = next((item for item in blocks if item.block_id == block_id), None)
        return match.block_module if match else None

    @classmethod
    def _library_infos(cls):
        return Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.LIBRARY_INFOS) or {}

    @classmethod
    def _requirement_infos(cls):
        return Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.REQUIREMENT_INFOS) or {}

    @classmethod
    def _requests(cls):
        return Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.INSTALL_REQUESTS) or {}

    @classmethod
    def _operations(cls):
        return Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.INSTALL_OPERATIONS) or {}

    @classmethod
    def _sync_status_to_bl(cls) -> None:
        try:
            props = bpy.context.scene.dgblocks_pip_library_manager_props
        except AttributeError:
            return
        props.library_status_rows.clear()
        for info in sorted(cls._library_infos().values(), key=lambda item: item.normalized_name):
            row = props.library_status_rows.add()
            row.distribution_name = info.distribution_name
            row.installed_version = info.installed_version or "—"
            row.required_versions = ", ".join(info.required_versions) or "—"
            row.status = info.status.value
            row.requesting_blocks = ", ".join(info.requesting_block_ids)
            row.error_summary = info.error_summary
