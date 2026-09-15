import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from meher_resolve_hub.resolve_context import ResolveContextService
from meher_resolve_hub.selection import SelectionEngine, SelectionUnavailable
from tests.fakes import FakeClip, FakeFolder, FakeMediaPool, FakeProject, FakeResolve, FakeTimeline, FakeTimelineItem


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.clip_a = FakeClip("a", "A"); self.clip_b = FakeClip("b", "B")
        self.item_a = FakeTimelineItem(self.clip_a); self.item_b = FakeTimelineItem(self.clip_b)
        child = FakeFolder("Child", [self.clip_b]); root = FakeFolder("Master", [self.clip_a], [child])
        pool = FakeMediaPool(root, [self.clip_b]); timeline = FakeTimeline([self.item_a, self.item_b])
        self.engine = SelectionEngine(ResolveContextService(FakeResolve(FakeProject(timeline, pool))))

    def test_every_selection_source_is_explicit(self):
        self.assertEqual(self.engine.get_selection("Media Pool Selection").clips, [self.clip_b])
        self.assertEqual(len(self.engine.get_selection("Timeline Selection").timeline_items), 2)
        self.assertEqual(self.engine.get_selection("Current Bin").clips, [self.clip_a])
        self.assertEqual(len(self.engine.get_selection("Current Bin + Sub-Bins").clips), 2)
        self.assertEqual(len(self.engine.get_selection("Current Timeline").clips), 2)

    def test_unknown_source_does_not_fall_back(self):
        with self.assertRaises(SelectionUnavailable): self.engine.get_selection("Anything")


if __name__ == "__main__": unittest.main()
