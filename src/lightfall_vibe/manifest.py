"""Plugin manifest for lightfall-vibe."""

from lightfall.plugins.manifest import PluginEntry, PluginManifest

manifest = PluginManifest(
    name="lightfall-vibe",
    version="0.1.0",
    description="Vibe mode: music-reactive UI effects (demo)",
    plugins=[
        PluginEntry(
            type_name="settings",
            name="vibe",
            import_path="lightfall_vibe.settings:VibeSettingsPlugin",
        ),
        PluginEntry(
            type_name="panel",
            name="vibe_spectrum",
            import_path="lightfall_vibe.panel:VibePanelPlugin",
            preload=True,
        ),
    ],
)
