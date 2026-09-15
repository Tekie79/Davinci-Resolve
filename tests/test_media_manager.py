import importlib.util
import tempfile
import unittest
from datetime import datetime
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "Media Manager.py"
SPEC = importlib.util.spec_from_file_location("media_manager", SCRIPT)
media_manager = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(media_manager)


class FakeFolder:
    def __init__(self, name, unique_id, children=None):
        self.name = name
        self.unique_id = unique_id
        self.children = children or []

    def GetName(self):
        return self.name

    def GetUniqueId(self):
        return self.unique_id

    def GetSubFolderList(self):
        return self.children


class FakeMediaPool:
    def __init__(self, root):
        self.root = root
        self.current = root
        self.selected_for_import = None

    def GetRootFolder(self):
        return self.root

    def GetCurrentFolder(self):
        return self.current

    def SetCurrentFolder(self, folder):
        self.current = folder
        return True

    def ImportMedia(self, clip_infos):
        self.selected_for_import = self.current
        return [object()]


class FakeRetryMediaPool(FakeMediaPool):
    def __init__(self, root):
        super().__init__(root)
        self.import_calls = []

    def ImportMedia(self, clip_infos):
        self.import_calls.append(clip_infos)
        if isinstance(clip_infos[0], dict):
            return []
        self.selected_for_import = self.current
        return [object()]


class FakeProject:
    def __init__(self, media_pool):
        self.media_pool = media_pool

    def GetMediaPool(self):
        return self.media_pool


class FakeTimeline:
    def GetName(self):
        return "Main"

    def GetCurrentTimecode(self):
        return "01:00:00:00"


class FakeCaptureProject:
    def __init__(self):
        self.timeline = FakeTimeline()
        self.export_called = False

    def GetCurrentTimeline(self):
        return self.timeline

    def GetName(self):
        return "Project"

    def ExportCurrentFrameAsStill(self, path):
        self.export_called = True
        Path(path).write_bytes(b"png")
        return True


class FakeProjectManager:
    def __init__(self, project):
        self.project = project

    def GetCurrentProject(self):
        return self.project


class FakeResolve:
    def __init__(self, project):
        self.manager = FakeProjectManager(project)

    def GetProjectManager(self):
        return self.manager


class MediaManagerTests(unittest.TestCase):
    def test_png_filename_is_safe_and_has_one_suffix(self):
        self.assertEqual(media_manager.png_filename("  Hero: Shot.PNG.png  "), "Hero_ Shot.png")
        self.assertEqual(media_manager.png_filename(""), "Still.png")

    def test_default_name_uses_timeline_timecode_and_timestamp(self):
        result = media_manager.default_still_name(
            "Main/Edit", "01:02:03:04", datetime(2026, 9, 14, 18, 2, 3)
        )
        self.assertEqual(result, "Main_Edit_01-02-03-04_20260914_180203.png")

    def test_collect_bins_returns_sorted_paths(self):
        root = FakeFolder(
            "Master",
            "root",
            [
                FakeFolder("Z Shots", "z"),
                FakeFolder("Assets", "a", [FakeFolder("Stills", "s")]),
            ],
        )
        paths = [path for path, _folder in media_manager.collect_bins(root)]
        self.assertEqual(
            paths,
            ["Master", "Master / Assets", "Master / Assets / Stills", "Master / Z Shots"],
        )

    def test_collect_bins_protects_against_cycles(self):
        root = FakeFolder("Master", "root")
        child = FakeFolder("Child", "child")
        root.children = [child]
        child.children = [root]
        paths = [path for path, _folder in media_manager.collect_bins(root)]
        self.assertEqual(paths, ["Master", "Master / Child"])

    def test_capture_uses_project_current_frame_export(self):
        project = FakeCaptureProject()
        controller = media_manager.MediaManagerController(FakeResolve(project))
        try:
            context = controller.capture_current_frame()
            self.assertTrue(project.export_called)
            self.assertTrue(controller.preview_path.is_file())
            self.assertEqual(context["timeline"], project.timeline)
        finally:
            controller.cleanup_preview()

    def test_save_without_selected_bin_imports_into_master(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            root = FakeFolder("Master", "root")
            media_pool = FakeMediaPool(root)
            controller = media_manager.MediaManagerController(resolve_app=None)
            preview = temp_path / "preview.png"
            preview.write_bytes(b"png")
            controller.preview_path = preview
            controller.preview_dir = None

            destination = controller.save_and_import(
                FakeProject(media_pool), None, temp_path / "output", "Still"
            )

            self.assertEqual(destination.name, "Still.png")
            self.assertIs(media_pool.selected_for_import, root)

    def test_save_retries_plain_path_when_clip_info_import_is_empty(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            root = FakeFolder("Master", "root")
            media_pool = FakeRetryMediaPool(root)
            controller = media_manager.MediaManagerController(resolve_app=None)
            preview = temp_path / "preview.png"
            preview.write_bytes(b"png")
            controller.preview_path = preview

            controller.save_and_import(
                FakeProject(media_pool), root, temp_path / "output", "Still"
            )

            self.assertIsInstance(media_pool.import_calls[0][0], dict)
            self.assertIsInstance(media_pool.import_calls[1][0], str)


if __name__ == "__main__":
    unittest.main()
