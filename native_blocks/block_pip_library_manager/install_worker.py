import os
import shutil
import subprocess
from importlib import metadata
from pathlib import Path

from .data_structures import RTC_Library_Operation
from .helpers import normalize_distribution_name


def _emit(operation: RTC_Library_Operation, event_type: str, payload=None) -> None:
    operation.worker_queue.put((event_type, payload))


def _remove_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def _activate_staging(staging: Path, target: Path, backup: Path) -> None:
    _remove_path(backup)
    if target.exists():
        os.replace(target, backup)
    try:
        os.replace(staging, target)
    except Exception:
        if backup.exists() and not target.exists():
            os.replace(backup, target)
        raise
    _remove_path(backup)


def run_pip_install_worker(
    operation: RTC_Library_Operation,
    command: list[str],
    target_path: Path,
    staging_path: Path,
    defer_activation: bool = False,
    expected_distribution_name: str = "",
    expected_version: str | None = None,
) -> None:
    """Worker-thread entry point. Never imports or touches bpy."""
    log_path = Path(operation.log_path)
    backup_path = target_path.with_name(f"{target_path.name}.backup-{operation.operation_uid}")
    process = None
    try:
        staging_path.parent.mkdir(parents=True, exist_ok=True)
        _remove_path(staging_path)
        if target_path.is_dir():
            _emit(operation, "LOG", "Copying the current managed environment to staging...")
            shutil.copytree(target_path, staging_path)
        else:
            staging_path.mkdir(parents=True)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        _emit(operation, "STATUS", "INSTALLING")
        with log_path.open("w", encoding="utf-8", errors="replace") as log_file:
            log_file.write("Command: " + subprocess.list2cmdline(command) + "\n\n")
            log_file.flush()
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
            _emit(operation, "PROCESS_STARTED", process)
            assert process.stdout is not None
            for line in iter(process.stdout.readline, ""):
                log_file.write(line)
                log_file.flush()
                _emit(operation, "LOG", line.rstrip())
                if operation.cancel_event.is_set():
                    process.kill()
                    break
            return_code = process.wait()

        if operation.cancel_event.is_set():
            _remove_path(staging_path)
            _emit(operation, "CANCELLED", return_code)
            return
        if return_code != 0:
            _remove_path(staging_path)
            _emit(operation, "ERROR", f"pip exited with code {return_code}")
            return

        _emit(operation, "STATUS", "VERIFYING")
        installed_version = None
        expected_normalized = normalize_distribution_name(expected_distribution_name)
        for distribution in metadata.distributions(path=[str(staging_path)]):
            discovered_name = distribution.metadata.get("Name")
            if discovered_name and normalize_distribution_name(discovered_name) == expected_normalized:
                installed_version = distribution.version
                break
        if installed_version is None:
            _remove_path(staging_path)
            _emit(
                operation,
                "ERROR",
                f"pip did not install distribution '{expected_distribution_name}' in staging",
            )
            return
        if expected_version is not None and installed_version != expected_version:
            _remove_path(staging_path)
            _emit(
                operation,
                "ERROR",
                f"Staged version is {installed_version}; expected exact version {expected_version}",
            )
            return
        _emit(operation, "RESOLVED_VERSION", installed_version)

        if defer_activation:
            pending_path = target_path.with_name(f"{target_path.name}.pending")
            _remove_path(pending_path)
            os.replace(staging_path, pending_path)
            _emit(operation, "RESTART_REQUIRED", 0)
            return

        _emit(operation, "STATUS", "ACTIVATING")
        _activate_staging(staging_path, target_path, backup_path)
        _emit(operation, "FINISHED", return_code)
    except Exception as exc:
        try:
            _remove_path(staging_path)
        except Exception:
            pass
        _emit(operation, "ERROR", str(exc))
    finally:
        _emit(operation, "PROCESS_ENDED", None)
