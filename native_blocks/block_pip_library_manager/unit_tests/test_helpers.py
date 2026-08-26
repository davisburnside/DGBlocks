import logging
import tempfile
import unittest
from pathlib import Path

from ..data_structures import Library_Source_Policy, Python_Library_Requirement_Declaration
from ..helpers import (
    append_recent_log,
    get_required_version_label,
    normalize_distribution_name,
    reject_duplicate_requirement_uids,
    resolve_bundled_wheel_dirs,
    sanitize_path_component,
    validate_requirement,
)


class _Null_Logger:
    """Discards log calls — reject_duplicate_requirement_uids logs on rejection but tests don't need to assert on it."""
    def error(self, *_args, **_kwargs):
        pass


def _make_requirement(uid: str, distribution_name: str = "demo") -> Python_Library_Requirement_Declaration:
    return Python_Library_Requirement_Declaration(
        requirement_uid=uid,
        distribution_name=distribution_name,
        import_names=(distribution_name,),
        feature_label="Demo",
        reason="Test",
    )


class Test_Security_Validation(unittest.TestCase):
    """Path-traversal / injection-style checks — the requirement declaration's actual security boundary."""

    def test_path_components_are_sanitized_and_limited(self):
        """Path components must strip unsafe characters and be truncated to the requested length."""
        self.assertEqual(sanitize_path_component(" My Addon!? "), "My-Addon")
        self.assertEqual(len(sanitize_path_component("a" * 100, 12)), 12)

    def test_bundled_policy_requires_relative_root(self):
        """BUNDLED_ONLY source policy without a bundled_wheel_root must be rejected."""
        declaration = Python_Library_Requirement_Declaration(
            requirement_uid="TEST",
            distribution_name="demo",
            import_names=("demo",),
            required_version="1.0.0",
            feature_label="Demo",
            reason="Test",
            source_policy=Library_Source_Policy.BUNDLED_ONLY,
        )
        with self.assertRaises(ValueError):
            validate_requirement(declaration)

    def test_requirement_rejects_direct_reference_syntax(self):
        """A distribution_name using pip's 'name @ url' direct-reference syntax must be rejected."""
        declaration = Python_Library_Requirement_Declaration(
            requirement_uid="TEST",
            distribution_name="demo @ https://example.invalid/demo.whl",
            import_names=("demo",),
            required_version="1.0.0",
            feature_label="Demo",
            reason="Test",
        )
        with self.assertRaises(ValueError):
            validate_requirement(declaration)

    def test_wheel_root_cannot_escape_requesting_block(self):
        """A bundled_wheel_root using '..' to escape the requesting block's own folder must be rejected."""
        with tempfile.TemporaryDirectory() as temp:
            block_root = Path(temp) / "block"
            block_root.mkdir()
            block_file = block_root / "__init__.py"
            block_file.touch()
            declaration = Python_Library_Requirement_Declaration(
                requirement_uid="TEST",
                distribution_name="demo",
                import_names=("demo",),
                required_version="1.0.0",
                feature_label="Demo",
                reason="Test",
                source_policy=Library_Source_Policy.BUNDLED_ONLY,
                bundled_wheel_root="../outside",
            )
            with self.assertRaises(ValueError):
                resolve_bundled_wheel_dirs(declaration, str(block_file))

    def test_duplicate_requirement_uid_within_a_block_is_rejected(self):
        """Two requirements from the same block sharing a requirement_uid must be dropped, not silently overwritten."""
        declarations = [_make_requirement("dup", "demo-a"), _make_requirement("dup", "demo-b")]
        result = reject_duplicate_requirement_uids("block-test", declarations, _Null_Logger())
        self.assertEqual(result, [])

    def test_distinct_requirement_uids_within_a_block_pass_through(self):
        """Requirements with distinct uids within the same block must pass through unchanged."""
        declarations = [_make_requirement("a"), _make_requirement("b")]
        result = reject_duplicate_requirement_uids("block-test", declarations, _Null_Logger())
        self.assertEqual(result, declarations)


class Test_Requirement_Helpers(unittest.TestCase):
    """General-purpose helpers used while resolving/formatting a requirement — not security-critical."""

    def test_omitted_version_means_latest(self):
        """A requirement with no required_version must validate and label as 'latest'."""
        declaration = Python_Library_Requirement_Declaration(
            requirement_uid="LATEST",
            distribution_name="demo",
            import_names=("demo",),
            feature_label="Demo",
            reason="Test latest",
        )
        validate_requirement(declaration)
        self.assertIsNone(declaration.required_version)
        self.assertEqual(get_required_version_label(declaration.required_version), "latest")

    def test_distribution_names_are_normalized(self):
        """Distribution names must normalize case and separators to pip's canonical form."""
        self.assertEqual(normalize_distribution_name("My_Package.Name"), "my-package-name")

    def test_recent_log_has_fixed_history(self):
        """The recent-log buffer must keep only the last N entries, oldest dropped first."""
        lines = []
        for index in range(8):
            append_recent_log(lines, str(index), history_limit=3)
        self.assertEqual(lines, ["5", "6", "7"])


class Test_Architecture_Invariants(unittest.TestCase):
    """Structural invariants about how this block is built, not about any one requirement."""

    def test_pip_block_does_not_implement_an_in_block_modal_loop(self):
        """This block's own source must never reference modal-operator machinery — it's a background poller, not a modal tool."""
        block_root = Path(__file__).resolve().parent.parent
        source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in block_root.glob("*.py")
        )
        self.assertNotIn("modal_handler_add", source)
        self.assertNotIn("event_timer_add", source)
        self.assertNotIn("def modal(", source)
        self.assertNotIn("invoke_popup", source)


if __name__ == "__main__":
    unittest.main()
