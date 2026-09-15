import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from meher_resolve_hub.ui import (
    health_workspace,
    history_workspace,
    marker_workspace,
    metadata_workspace,
    rename_workspace,
    settings_workspace,
    still_workspace,
)


class FakeUI:
    """Records declarative UI calls while resolving every referenced factory."""

    def __getattr__(self, kind):
        def factory(*args):
            return {"kind": kind, "args": args}
        return factory


class WorkspaceBuildTests(unittest.TestCase):
    def test_every_workspace_constructs(self):
        ui = FakeUI()
        modules = (
            marker_workspace,
            metadata_workspace,
            rename_workspace,
            still_workspace,
            health_workspace,
            history_workspace,
            settings_workspace,
        )
        for module in modules:
            with self.subTest(module=module.__name__):
                self.assertIsNotNone(module.build(ui))


if __name__ == "__main__":
    unittest.main()
