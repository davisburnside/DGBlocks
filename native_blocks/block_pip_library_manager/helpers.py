import hashlib
import os
import platform
import re
import sys
import sysconfig
from importlib import metadata
from pathlib import Path
from typing import Iterable, Optional

from ...addon_config.static_settings import addon_python_environment_id
from .data_structures import Library_Source_Policy, Python_Library_Requirement_Declaration


_NORMALIZE_DISTRIBUTION_RE = re.compile(r"[-_.]+")
_SAFE_PATH_COMPONENT_RE = re.compile(r"[^A-Za-z0-9._-]+")
_VALID_DISTRIBUTION_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_VALID_EXACT_VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.!+_-]*$")


def normalize_distribution_name(name: str) -> str:
    return _NORMALIZE_DISTRIBUTION_RE.sub("-", name.strip()).lower()



def get_required_version_label(required_version: Optional[str]) -> str:
    return required_version or "latest"


def sanitize_path_component(value: str, max_length: int = 48) -> str:
    cleaned = _SAFE_PATH_COMPONENT_RE.sub("-", value.strip()).strip(".-_")
    if not cleaned:
        raise ValueError("Path component contains no usable characters")
    return cleaned[:max_length]


def get_platform_key() -> str:
    machine = platform.machine().lower()
    is_arm = machine in {"arm64", "aarch64"}
    if sys.platform == "win32":
        return "windows-arm64" if is_arm else "windows-x64"
    if sys.platform == "darwin":
        return "macos-arm64" if is_arm else "macos-x64"
    return "linux-arm64" if is_arm else "linux-x64"


def get_short_platform_tag() -> str:
    raw = sysconfig.get_platform().replace("_", "-").replace(".", "-")
    return sanitize_path_component(raw, max_length=32)


def get_python_cache_tag() -> str:
    return sys.implementation.cache_tag or f"py{sys.version_info.major}{sys.version_info.minor}"


def build_managed_paths(base_path: str, blender_version: tuple[int, ...]) -> tuple[Path, Path]:
    addon_id = sanitize_path_component(addon_python_environment_id)
    blender_scope = f"b{blender_version[0]}{blender_version[1]}"
    compatibility_scope = f"{get_python_cache_tag()}-{get_short_platform_tag()}"
    environment_root = (
        Path(base_path).expanduser().resolve()
        / "python_libs"
        / addon_id
        / blender_scope
        / compatibility_scope
    )
    return environment_root, environment_root / "site"


def get_path_length_warning(path: Path) -> str:
    if os.name == "nt" and len(str(path)) >= 160:
        return (
            f"Managed library path is {len(str(path))} characters long; some Windows "
            "wheels may fail to extract or load. Choose a shorter addon data folder."
        )
    return ""


def discover_distributions(search_path: Path) -> dict[str, tuple[str, str]]:
    """Return normalized name -> (version, distribution root) without importing packages."""
    if not search_path.is_dir():
        return {}
    found: dict[str, tuple[str, str]] = {}
    for distribution in metadata.distributions(path=[str(search_path)]):
        name = distribution.metadata.get("Name")
        if not name:
            continue
        try:
            root = str(Path(distribution.locate_file("")).resolve())
        except Exception:
            root = str(search_path)
        found[normalize_distribution_name(name)] = (distribution.version, root)
    return found


def validate_requirement(declaration: Python_Library_Requirement_Declaration) -> None:
    if not declaration.requirement_uid.strip():
        raise ValueError("requirement_uid cannot be empty")
    if not declaration.distribution_name.strip():
        raise ValueError("distribution_name cannot be empty")
    if not _VALID_DISTRIBUTION_NAME_RE.fullmatch(declaration.distribution_name.strip()):
        raise ValueError("distribution_name contains unsupported characters")
    if declaration.required_version is not None:
        if not declaration.required_version.strip():
            raise ValueError("required_version must be None or a non-empty exact version")
        if not _VALID_EXACT_VERSION_RE.fullmatch(declaration.required_version.strip()):
            raise ValueError("required_version must be one exact version without spaces or URLs")
    if not declaration.import_names or any(not name.strip() for name in declaration.import_names):
        raise ValueError("import_names must contain at least one non-empty module name")
    if not isinstance(declaration.source_policy, Library_Source_Policy):
        raise ValueError("source_policy must be a Library_Source_Policy member")
    if declaration.source_policy != Library_Source_Policy.ONLINE_ONLY and not declaration.bundled_wheel_root:
        raise ValueError("A bundled source policy requires bundled_wheel_root")
    if declaration.source_policy == Library_Source_Policy.BUNDLED_ONLY and declaration.allow_online_fallback:
        raise ValueError("BUNDLED_ONLY cannot allow online fallback")


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def resolve_bundled_wheel_dirs(
    declaration: Python_Library_Requirement_Declaration,
    requesting_block_file: str,
) -> tuple[Path, ...]:
    if not declaration.bundled_wheel_root:
        return ()
    block_root = Path(requesting_block_file).resolve().parent
    relative_root = Path(declaration.bundled_wheel_root)
    if relative_root.is_absolute():
        raise ValueError("bundled_wheel_root must be relative to the requesting block")
    wheel_root = (block_root / relative_root).resolve()
    if not _is_relative_to(wheel_root, block_root):
        raise ValueError("bundled_wheel_root resolves outside the requesting block")

    abi = get_python_cache_tag().replace("cpython-", "cp")
    candidates = (
        wheel_root / get_platform_key() / abi,
        wheel_root / "any" / "py3",
    )
    result = []
    for candidate in candidates:
        if candidate.is_dir() and _is_relative_to(candidate.resolve(), block_root):
            result.append(candidate.resolve())
    return tuple(result)


def verify_declared_wheel_hashes(
    declaration: Python_Library_Requirement_Declaration,
    requesting_block_file: str,
) -> None:
    if not declaration.bundled_wheel_sha256:
        return
    block_root = Path(requesting_block_file).resolve().parent
    wheel_root = (block_root / str(declaration.bundled_wheel_root)).resolve()
    for relative_name, expected_digest in declaration.bundled_wheel_sha256:
        wheel_path = (wheel_root / relative_name).resolve()
        if not _is_relative_to(wheel_path, wheel_root) or wheel_path.suffix.lower() != ".whl":
            raise ValueError(f"Invalid bundled wheel hash path: {relative_name}")
        digest = hashlib.sha256()
        with wheel_path.open("rb") as wheel_file:
            for chunk in iter(lambda: wheel_file.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest().lower() != expected_digest.strip().lower():
            raise ValueError(f"SHA-256 mismatch for bundled wheel '{relative_name}'")


def find_compatible_python_executable() -> Optional[Path]:
    names = ("python.exe", "python")
    candidates = []
    for value in (getattr(sys, "_base_executable", None), sys.executable):
        if value and Path(value).name.lower().startswith("python"):
            candidates.append(Path(value))
    for parent in (Path(sys.prefix), Path(sys.base_prefix)):
        for folder in ("bin", ""):
            for name in names:
                candidates.append(parent / folder / name)
    seen = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved in seen or not resolved.is_file():
            continue
        seen.add(resolved)
        return resolved
    return None


def append_recent_log(lines: list[str], new_line: str, history_limit: int = 14) -> None:
    lines.append(new_line.rstrip())
    if len(lines) > history_limit:
        del lines[:-history_limit]


def iter_loaded_import_conflicts(import_names: Iterable[str], managed_site: Path):
    managed_resolved = managed_site.resolve()
    for import_name in import_names:
        top_name = import_name.split(".", 1)[0]
        module = sys.modules.get(top_name)
        module_file = getattr(module, "__file__", None) if module else None
        if not module:
            continue
        if not module_file:
            yield top_name, "<built-in or unknown>"
            continue
        module_path = Path(module_file).resolve()
        if not _is_relative_to(module_path, managed_resolved):
            yield top_name, str(module_path)
