"""Resolve Hub composition root and launch helpers."""

from .capabilities import CapabilityDetector
from .credential_service import OpenAICredentialStore
from .history import OperationHistory
from .logging_service import build_logger
from .navigation import NavigationEngine
from .preferences import Preferences, user_data_dir
from .resolve_context import ResolveContextService
from .selection import SelectionEngine
from .services import (
    HealthService,
    MarkerService,
    MetadataService,
    RenameService,
    SpeakerMarkerService,
    StillService,
)
from .thumbnails import ThumbnailCache


def get_resolve_app(namespace=None):
    namespace = namespace or globals()
    injected = namespace.get("resolve")
    if injected:
        return injected
    try:
        import DaVinciResolveScript as dvr_script
        return dvr_script.scriptapp("Resolve")
    except Exception:
        return None


def get_fusion_app(resolve_app, namespace=None):
    namespace = namespace or globals()
    injected = namespace.get("fusion")
    if injected:
        return injected
    try:
        return resolve_app.Fusion()
    except Exception:
        return None


def get_bmd_module(namespace=None):
    namespace = namespace or globals()
    injected = namespace.get("bmd")
    if injected:
        return injected
    try:
        import BlackmagicFusion
        return BlackmagicFusion
    except Exception:
        return None


class ResolveHubApplication:
    def __init__(self, resolve, fusion, bmd):
        self.resolve, self.fusion, self.bmd = resolve, fusion, bmd
        self.logger = build_logger()
        self.preferences = Preferences(); self.preferences.load()
        self.context = ResolveContextService(resolve)
        self.selection = SelectionEngine(self.context)
        self.navigation = NavigationEngine(self.context)
        self.history = OperationHistory(user_data_dir() / "history.json"); self.history.load()
        cache_folder = self.preferences.get("thumbnails", "cache_folder", "") or None
        self.thumbnails = ThumbnailCache(self.context, cache_folder, self.preferences.get("thumbnails", "enabled", True))
        self.capabilities = CapabilityDetector(resolve)
        self.credentials = OpenAICredentialStore()
        self.markers = MarkerService(self.context, self.history)
        self.speaker_markers = SpeakerMarkerService(self.context)
        self.metadata = MetadataService(self.history)
        self.rename = RenameService(self.history)
        self.stills = StillService(resolve, self.context, self.navigation)
        self.health = HealthService()

    def run(self):
        from .ui.shell import ResolveHubShell
        ResolveHubShell(self).run()


def main(namespace=None):
    resolve = get_resolve_app(namespace)
    if not resolve:
        raise RuntimeError("Meher Flow Resolve Hub could not connect to DaVinci Resolve.")
    fusion = get_fusion_app(resolve, namespace)
    bmd = get_bmd_module(namespace)
    if not fusion or not bmd:
        raise RuntimeError("Resolve Hub needs Resolve Studio's Fusion UI Manager.")
    ResolveHubApplication(resolve, fusion, bmd).run()
