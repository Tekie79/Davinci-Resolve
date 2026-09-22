"""Settings workspace layout."""

from .. import theme
from .components import button, color_selector, combo, line_edit, section, tree


def build(ui):
    return ui.VGroup({"ID": "SettingsWorkspace", "Spacing": 7}, [
        section(ui, "Settings"),
        ui.TabBar({"ID": "SettingsTabs", "Expanding": False, "DrawBase": True, "StyleSheet": theme.TABS, "Weight": 0}),
        ui.Stack({"ID": "SettingsStack", "Weight": 1}, [
            ui.VGroup({"Spacing": 7, "StyleSheet": theme.SURFACE}, [
                ui.Label({"Text": "GENERAL", "StyleSheet": theme.SECTION, "Weight": 0}),
                ui.CheckBox({"ID": "SettingRestoreWorkspace", "Text": "Restore last workspace", "Weight": 0}),
                ui.CheckBox({"ID": "SettingRestoreGeometry", "Text": "Restore window geometry", "Weight": 0}),
                ui.CheckBox({"ID": "SettingConfirmBatch", "Text": "Confirm destructive batch operations", "Weight": 0}),
                ui.HGroup({"Spacing": 5, "Weight": 0}, [ui.Label({"Text": "Default selection", "StyleSheet": theme.SUBTITLE}), combo(ui, "SettingDefaultSelection", 1)]),
                ui.Label({"Text": "THUMBNAILS", "StyleSheet": theme.SECTION, "Weight": 0}),
                ui.CheckBox({"ID": "SettingThumbnails", "Text": "Enable thumbnails", "Weight": 0}),
                ui.HGroup({"Spacing": 5, "Weight": 0}, [line_edit(ui, "SettingCacheFolder", "Thumbnail cache folder"), button(ui, "BrowseCacheFolder", "Browse…"), button(ui, "ClearThumbnailCache", "Clear Cache")]),
                ui.VGap(0, 1),
            ]),
            ui.VGroup({"Spacing": 7, "StyleSheet": theme.SURFACE}, [
                ui.Label({"Text": "MARKER PRESETS", "StyleSheet": theme.SECTION, "Weight": 0}),
                ui.HGroup({"Spacing": 5, "Weight": 0}, [ui.Label({"Text": "Default duration", "StyleSheet": theme.SUBTITLE}), line_edit(ui, "SettingMarkerDuration", "frames")]),
                tree(ui, "PresetTree", ("#", "Preset", "Color", "Default Name", "Duration"), 1),
                ui.HGroup({"Spacing": 5, "Weight": 0}, [line_edit(ui, "PresetName", "Preset"), color_selector(ui, "PresetColor", "Blue"), line_edit(ui, "PresetDefaultName", "Default marker name"), line_edit(ui, "PresetDuration", "Frames")]),
                ui.HGroup({"Spacing": 5, "Weight": 0}, [button(ui, "AddPreset", "Add"), button(ui, "UpdatePreset", "Update"), button(ui, "MovePresetUp", "Up"), button(ui, "MovePresetDown", "Down"), button(ui, "DeletePreset", "Delete")]),
            ]),
            ui.VGroup({"Spacing": 7, "StyleSheet": theme.SURFACE}, [
                ui.Label({"Text": "METADATA", "StyleSheet": theme.SECTION, "Weight": 0}),
                ui.HGroup({"Spacing": 5, "Weight": 0}, [ui.Label({"Text": "Required fields", "StyleSheet": theme.SUBTITLE}), line_edit(ui, "SettingRequiredMetadata", "Scene, Take")]),
                ui.Label({"Text": "STILLS", "StyleSheet": theme.SECTION, "Weight": 0}),
                ui.HGroup({"Spacing": 5, "Weight": 0}, [ui.Label({"Text": "Default folder", "StyleSheet": theme.SUBTITLE}), line_edit(ui, "SettingStillFolder", "Output folder")]),
                ui.HGroup({"Spacing": 5, "Weight": 0}, [ui.Label({"Text": "Naming", "StyleSheet": theme.SUBTITLE}), line_edit(ui, "SettingStillTemplate", "{Timeline}_{Timecode}_{Index}")]),
                ui.VGap(0, 1),
            ]),
            ui.VGroup({"Spacing": 10, "StyleSheet": theme.SURFACE}, [
                ui.Label({"Text": "AI / PROVIDERS", "StyleSheet": theme.SECTION, "Weight": 0}),
                ui.Label({
                    "Text": "The API key is stored in the operating-system credential store (macOS Keychain on macOS). It is never written to settings.json or Git.",
                    "WordWrap": True,
                    "StyleSheet": theme.SUBTITLE,
                    "Weight": 0,
                }),
                ui.HGroup({"Spacing": 7, "Weight": 0}, [
                    ui.Label({"Text": "Status", "StyleSheet": theme.SUBTITLE, "Weight": 0}),
                    ui.Label({"ID": "OpenAICredentialStatus", "Text": "Checking…", "StyleSheet": theme.SECTION, "Weight": 1}),
                ]),
                ui.HGroup({"Spacing": 7, "Weight": 0}, [
                    ui.Label({"Text": "API key", "StyleSheet": theme.SUBTITLE, "Weight": 0}),
                    ui.LineEdit({
                        "ID": "SettingOpenAIKey",
                        "PlaceholderText": "Paste key to save/replace — field is cleared after save",
                        "EchoMode": "Password",
                        "StyleSheet": theme.FIELD,
                        "Weight": 1,
                    }),
                ]),
                ui.HGroup({"Spacing": 7, "Weight": 0}, [
                    button(ui, "SaveOpenAIKey", "Save Securely", True),
                    button(ui, "TestOpenAIKey", "Test Connection"),
                    button(ui, "RemoveOpenAIKey", "Remove Key"),
                    ui.HGap(0, 1),
                ]),
                ui.Label({"Text": "SPEAKER DIARIZATION", "StyleSheet": theme.SECTION, "Weight": 0}),
                ui.HGroup({"Spacing": 7, "Weight": 0}, [
                    ui.Label({"Text": "Model", "StyleSheet": theme.SUBTITLE, "Weight": 0}),
                    line_edit(ui, "SettingOpenAIModel", "gpt-4o-transcribe-diarize"),
                ]),
                ui.CheckBox({"ID": "SettingOpenAITranscript", "Text": "Include transcript text in OpenAI speaker-marker notes", "Weight": 0}),
                ui.Label({"Text": "ELEVENLABS / SCRIBE", "StyleSheet": theme.SECTION, "Weight": 0}),
                ui.HGroup({"Spacing": 7, "Weight": 0}, [
                    ui.Label({"Text": "Status", "StyleSheet": theme.SUBTITLE, "Weight": 0}),
                    ui.Label({"ID": "ElevenLabsCredentialStatus", "Text": "Checking…", "StyleSheet": theme.SECTION, "Weight": 1}),
                ]),
                ui.HGroup({"Spacing": 7, "Weight": 0}, [
                    ui.Label({"Text": "API key", "StyleSheet": theme.SUBTITLE, "Weight": 0}),
                    ui.LineEdit({
                        "ID": "SettingElevenLabsKey",
                        "PlaceholderText": "Paste ElevenLabs key to save/replace",
                        "EchoMode": "Password",
                        "StyleSheet": theme.FIELD,
                        "Weight": 1,
                    }),
                ]),
                ui.HGroup({"Spacing": 7, "Weight": 0}, [
                    button(ui, "SaveElevenLabsKey", "Save Securely", True),
                    button(ui, "TestElevenLabsKey", "Test Connection"),
                    button(ui, "RemoveElevenLabsKey", "Remove Key"),
                    ui.HGap(0, 1),
                ]),
                ui.HGroup({"Spacing": 7, "Weight": 0}, [
                    ui.Label({"Text": "Model", "StyleSheet": theme.SUBTITLE, "Weight": 0}),
                    line_edit(ui, "SettingElevenLabsModel", "scribe_v2"),
                    ui.Label({"Text": "Language", "StyleSheet": theme.SUBTITLE, "Weight": 0}),
                    line_edit(ui, "SettingElevenLabsLanguage", "blank = auto"),
                ]),
                ui.HGroup({"Spacing": 7, "Weight": 0}, [
                    ui.Label({"Text": "Speakers", "StyleSheet": theme.SUBTITLE, "Weight": 0}),
                    line_edit(ui, "SettingElevenLabsNumSpeakers", "blank = auto"),
                    ui.CheckBox({"ID": "SettingElevenLabsSpeakerLibrary", "Text": "Use ElevenLabs speaker library", "Weight": 1}),
                ]),
                ui.CheckBox({"ID": "SettingElevenLabsTranscript", "Text": "Include transcript text in ElevenLabs speaker-marker notes", "Weight": 0}),
                ui.Label({
                    "Text": "OpenAI and ElevenLabs are independent providers. Keys stay in the OS credential store and are never saved to settings.json.",
                    "WordWrap": True,
                    "StyleSheet": theme.SUBTITLE,
                    "Weight": 0,
                }),
                ui.VGap(0, 1),
            ]),
        ]),
        ui.HGroup({"Spacing": 5, "Weight": 0}, [button(ui, "SaveSettings", "Save Settings", True), ui.Label({"ID": "SettingsStatus", "Text": "", "StyleSheet": theme.SUBTITLE}), ui.HGap(0, 1)]),
    ])
