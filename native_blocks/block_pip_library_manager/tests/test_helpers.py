import tempfile
import unittest
from pathlib import Path

from ..data_structures import Library_Source_Policy, Python_Library_Requirement_Declaration
from ..helpers import (
    append_recent_log,
    normalize_distribution_name,
    resolve_bundled_wheel_dirs,
    sanitize_path_component,
    validate_requirement,
)


class Test_Pip_Library_Helpers(unittest.TestCase):
    def test_distribution_names_are_normalized(self):
        self.assertEqual(normalize_distribution_name("My_Package.Name"), "my-package-name")

    def test_path_components_are_sanitized_and_limited(self):
        self.assertEqual(sanitize_path_component(" My Addon!? "), "My-Addon")
        self.assertEqual(len(sanitize_path_component("a" * 100, 12)), 12)

    def test_bundled_policy_requires_relative_root(self):
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

    def test_recent_log_has_fixed_history(self):
        lines = []
        for index in range(8):
            append_recent_log(lines, str(index), history_limit=3)
        self.assertEqual(lines, ["5", "6", "7"])


if __name__ == "__main__":
    unittest.main()
