import sys
import tempfile
import unittest
from pathlib import Path

from ..data_structures import RTC_Library_Operation
from ..install_worker import run_pip_install_worker


def _make_operation(root: Path, suffix: str = "") -> RTC_Library_Operation:
    target = root / f"site{suffix}"
    staging = root / f"staging{suffix}"
    return RTC_Library_Operation(
        operation_uid=f"op{suffix}",
        request_uid="request",
        namespaced_requirement_uid="block:test",
        distribution_name="demo-package",
        required_version="1.2.3",
        target_path=str(target),
        staging_path=str(staging),
        log_path=str(root / f"operation{suffix}.log"),
    )


def _fake_install_command(target: Path, version: str = "1.2.3") -> list[str]:
    script = (
        "from pathlib import Path; import sys; "
        "p=Path(sys.argv[1]); p.mkdir(parents=True, exist_ok=True); "
        "d=p/'demo_package-" + version + ".dist-info'; d.mkdir(exist_ok=True); "
        "(d/'METADATA').write_text('Metadata-Version: 2.1\\nName: demo-package\\nVersion: "
        + version + "\\n', encoding='utf-8'); "
        "(p/'demo_package.py').write_text('VALUE=1\\n', encoding='utf-8'); "
        "print('fake install complete')"
    )
    return [sys.executable, "-c", script, str(target)]


def _events(operation: RTC_Library_Operation):
    result = []
    while not operation.worker_queue.empty():
        result.append(operation.worker_queue.get_nowait())
    return result


class Test_Pip_Install_Worker(unittest.TestCase):
    def test_staged_install_preserves_existing_files_and_promotes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            operation = _make_operation(root)
            target = Path(operation.target_path)
            staging = Path(operation.staging_path)
            target.mkdir()
            (target / "existing.txt").write_text("keep", encoding="utf-8")

            run_pip_install_worker(
                operation,
                _fake_install_command(staging),
                target,
                staging,
                False,
                "demo-package",
                "1.2.3",
            )

            events = _events(operation)
            self.assertIn(("FINISHED", 0), events)
            self.assertEqual((target / "existing.txt").read_text(encoding="utf-8"), "keep")
            self.assertTrue((target / "demo_package.py").is_file())
            self.assertFalse(staging.exists())

    def test_wrong_version_is_rejected_without_replacing_target(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            operation = _make_operation(root)
            target = Path(operation.target_path)
            staging = Path(operation.staging_path)
            target.mkdir()
            (target / "marker.txt").write_text("old", encoding="utf-8")

            run_pip_install_worker(
                operation,
                _fake_install_command(staging, version="9.9.9"),
                target,
                staging,
                False,
                "demo-package",
                "1.2.3",
            )

            events = _events(operation)
            self.assertTrue(any(kind == "ERROR" for kind, _ in events))
            self.assertEqual((target / "marker.txt").read_text(encoding="utf-8"), "old")

    def test_deferred_activation_creates_pending_environment(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            operation = _make_operation(root)
            target = Path(operation.target_path)
            staging = Path(operation.staging_path)

            run_pip_install_worker(
                operation,
                _fake_install_command(staging),
                target,
                staging,
                True,
                "demo-package",
                "1.2.3",
            )

            events = _events(operation)
            self.assertIn(("RESTART_REQUIRED", 0), events)
            self.assertTrue(target.with_name("site.pending").is_dir())
            self.assertFalse(target.exists())

    def test_unpinned_install_accepts_and_reports_resolved_version(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            operation = _make_operation(root, suffix="-latest")
            operation.required_version = None
            target = Path(operation.target_path)
            staging = Path(operation.staging_path)

            run_pip_install_worker(
                operation,
                _fake_install_command(staging, version="7.8.9"),
                target,
                staging,
                False,
                "demo-package",
                None,
            )

            events = _events(operation)
            self.assertIn(("RESOLVED_VERSION", "7.8.9"), events)
            self.assertIn(("FINISHED", 0), events)
            self.assertTrue((target / "demo_package.py").is_file())


if __name__ == "__main__":
    unittest.main()
