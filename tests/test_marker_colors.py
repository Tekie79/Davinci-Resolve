import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from meher_resolve_hub.constants import MARKER_COLOR_HEX, MARKER_COLORS
from meher_resolve_hub.marker_colors import hex_color_rgba, marker_color_dot_style, marker_color_rgba
from meher_resolve_hub import theme


class MarkerColorTests(unittest.TestCase):
    def test_palette_covers_every_resolve_marker_color(self):
        self.assertEqual(set(MARKER_COLORS), set(MARKER_COLOR_HEX))

    def test_dot_uses_css_background_and_round_radius(self):
        style = marker_color_dot_style("Blue")
        self.assertIn("background-color:%s" % MARKER_COLOR_HEX["Blue"], style)
        self.assertIn("border-radius:4px", style)
        self.assertIn("border:0", style)
        self.assertNotIn("png", style.lower())

    def test_all_filter_uses_neutral_css_dot(self):
        style = marker_color_dot_style("All")
        self.assertIn("background-color:#737A84", style)

    def test_native_list_color_uses_normalized_rgba(self):
        color = marker_color_rgba("Red")
        self.assertEqual(color["A"], 1.0)
        self.assertTrue(all(0.0 <= color[channel] <= 1.0 for channel in ("R", "G", "B")))
        self.assertEqual(hex_color_rgba("#3A3A40")["A"], 1.0)

    def test_marker_selection_uses_neutral_highlight(self):
        self.assertIn("background:#3A3A40", theme.MARKER_TREE)
        self.assertNotIn("item:selected{background:#3A3A40;color:", theme.MARKER_TREE)
        self.assertIn("QTreeWidget QLineEdit{background:#0B0B0C;color:#FFFFFF", theme.MARKER_TREE)
        self.assertIn("border:2px solid #C58A35", theme.MARKER_TREE)
        self.assertNotIn("background:#5F4525", theme.MARKER_TREE)


if __name__ == "__main__":
    unittest.main()
