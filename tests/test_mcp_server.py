import inspect
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from meher_resolve_hub import mcp_server


class MCPServerTests(unittest.TestCase):
    def test_scene_tokens(self):
        self.assertIn("SC04", mcp_server._scene_tokens("4"))
        self.assertIn("SC4.2", mcp_server._scene_tokens("4.2"))

    def test_voice_references_only_use_requested_characters(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "Mike.mp3").write_bytes(b"mike")
            (root / "Sam.wav").write_bytes(b"sam")
            (root / "CJ.mp3").write_bytes(b"cj")

            refs, warnings = mcp_server._voice_references(
                ["Mike", "Sam"], reference_dir=folder
            )

            self.assertEqual(set(refs), {"Mike", "Sam"})
            self.assertNotIn("CJ", refs)
            self.assertEqual(warnings, [])

    def test_voice_reference_limit_is_four(self):
        with self.assertRaisesRegex(RuntimeError, "maximum of four"):
            mcp_server._voice_references(
                ["A", "B", "C", "D", "E"], reference_dir="/tmp"
            )

    def test_openai_key_is_not_mcp_tool_argument(self):
        signature = inspect.signature(mcp_server.analyze_select_speakers_and_mark)
        self.assertNotIn("openai_api_key", signature.parameters)
        self.assertNotIn("api_key", signature.parameters)


if __name__ == "__main__":
    unittest.main()
