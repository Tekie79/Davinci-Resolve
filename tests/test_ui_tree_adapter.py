import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from meher_resolve_hub.ui.shell import ResolveHubShell


class FakeTreeItem:
    def __init__(self, index):
        self.Text = [str(index)]
        self.Selected = False


class FakeMethodTree:
    """Matches Resolve's documented CurrentItem()/SelectedItems() API."""

    def __init__(self, count=4):
        self.items = [FakeTreeItem(index) for index in range(count)]
        self.scrolled_to = None

    def CurrentItem(self):
        return next((item for item in self.items if item.Selected), None)

    def SelectedItems(self):
        return [item for item in self.items if item.Selected]

    def TopLevelItemCount(self):
        return len(self.items)

    def TopLevelItem(self, index):
        return self.items[index]

    def ScrollToItem(self, item):
        self.scrolled_to = item


class FakePropertyTree(FakeMethodTree):
    @property
    def CurrentItem(self):
        return next((item for item in self.items if item.Selected), None)

    @property
    def SelectedItems(self):
        return [item for item in self.items if item.Selected]

    @property
    def TopLevelItemCount(self):
        return len(self.items)


class TreeAdapterTests(unittest.TestCase):
    def test_reads_documented_method_api(self):
        tree = FakeMethodTree()
        tree.items[2].Selected = True
        self.assertEqual(ResolveHubShell._tree_current_index(tree), 2)
        self.assertEqual(ResolveHubShell._tree_selected_indices(tree), [2])

    def test_reads_property_api_variant(self):
        tree = FakePropertyTree()
        tree.items[1].Selected = True
        self.assertEqual(ResolveHubShell._tree_current_index(tree), 1)

    def test_programmatic_selection_uses_tree_item_selected(self):
        tree = FakeMethodTree()
        tree.items[0].Selected = True
        self.assertTrue(ResolveHubShell._select_tree_index(tree, 3))
        self.assertEqual(ResolveHubShell._tree_selected_indices(tree), [3])
        self.assertIs(tree.scrolled_to, tree.items[3])

    def test_select_all_and_clear(self):
        tree = FakeMethodTree(3)
        self.assertEqual(ResolveHubShell._set_tree_selection(tree, True), 3)
        self.assertEqual(ResolveHubShell._tree_selected_indices(tree), [0, 1, 2])
        self.assertEqual(ResolveHubShell._set_tree_selection(tree, False), 3)
        self.assertEqual(ResolveHubShell._tree_selected_indices(tree), [])


if __name__ == "__main__":
    unittest.main()
