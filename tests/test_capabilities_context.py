import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from meher_resolve_hub.capabilities import CapabilityDetector
from meher_resolve_hub.resolve_context import ResolveContextService
from tests.fakes import FakeProject, FakeResolve, FakeTimeline


class CapabilitiesContextTests(unittest.TestCase):
    def test_context_refreshes_project_timeline_page_and_fps(self):
        timeline = FakeTimeline(); service = ResolveContextService(FakeResolve(FakeProject(timeline))); context = service.get_context()
        self.assertEqual((context.project_name, context.timeline_name, context.current_page), ("Project", "Timeline", "Edit")); self.assertEqual(service.get_project_fps(), 24.0)

    def test_capabilities_are_explicit(self):
        timeline = FakeTimeline(); service = ResolveContextService(FakeResolve(FakeProject(timeline))); caps = CapabilityDetector(service.resolve).detect(service.get_context())
        self.assertTrue(caps["timeline_selection"].supported); self.assertTrue(caps["direct_still_export"].supported); self.assertFalse(caps["marker_custom_data"].supported)


if __name__ == "__main__": unittest.main()
