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
from meher_resolve_hub.ui.components import color_selector


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

    def test_color_selector_places_css_dot_inside_field(self):
        control = color_selector(FakeUI(), "MarkerEditColor", "Blue", 1)
        properties, children = control["args"]
        self.assertEqual(properties["ID"], "MarkerEditColorField")
        child_ids = [child["args"][0].get("ID") for child in children]
        self.assertEqual(child_ids, ["MarkerEditColorDotWrap", "MarkerEditColor", "MarkerEditColorArrow"])
        centered_children = children[0]["args"][1]
        self.assertEqual(centered_children[1]["args"][0]["ID"], "MarkerEditColorDot")



if __name__ == "__main__":
    unittest.main()
