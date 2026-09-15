"""Small cross-workspace utilities."""

import re
from pathlib import Path

INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_filename_component(value, fallback="Still"):
    value = INVALID_FILENAME_CHARS.sub("_", str(value or ""))
    value = re.sub(r"\s+", " ", value).strip().rstrip(". ")
    return value or fallback


def png_filename(value):
    value = str(value or "").strip()
    while value.lower().endswith(".png"):
        value = value[:-4]
    return safe_filename_component(value, "Still") + ".png"


def collect_bins(root_folder):
    result, visited = [], set()

    def visit(folder, parent_path):
        try:
            identity = str(folder.GetUniqueId())
        except Exception:
            identity = str(id(folder))
        if identity in visited:
            return
        visited.add(identity)
        try:
            name = str(folder.GetName())
        except Exception:
            name = "Bin"
        path = name if not parent_path else parent_path + " / " + name
        result.append((path, folder))
        try:
            children = list(folder.GetSubFolderList() or [])
        except Exception:
            children = []
        children.sort(key=lambda child: str(child.GetName()).casefold())
        for child in children:
            visit(child, path)

    visit(root_folder, "")
    return result


def same_proxy(left, right):
    if left is None or right is None:
        return False
    for name in ("GetUniqueId", "GetMediaId"):
        try:
            return str(getattr(left, name)()) == str(getattr(right, name)())
        except Exception:
            continue
    return left is right


def find_exported_png(folder, preferred_path=None):
    if preferred_path and Path(preferred_path).is_file():
        return Path(preferred_path)
    candidates = list(Path(folder).glob("*.png")) + list(Path(folder).glob("*.PNG"))
    return max(candidates, key=lambda value: value.stat().st_mtime_ns) if candidates else None


def proxy_id(proxy, fallback=""):
    for name in ("GetUniqueId", "GetMediaId"):
        try:
            value = getattr(proxy, name)()
            if value not in (None, ""):
                return str(value)
        except Exception:
            continue
    return fallback or str(id(proxy))

