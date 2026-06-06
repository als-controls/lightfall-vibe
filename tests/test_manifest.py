"""The manifest is discoverable via the lightfall.plugins entry point."""

from importlib.metadata import entry_points


def test_manifest_declares_settings_and_panel():
    from lightfall_vibe.manifest import manifest

    types = {(entry.type_name, entry.name) for entry in manifest.plugins}
    assert ("settings", "vibe") in types
    assert ("panel", "vibe_spectrum") in types


def test_manifest_import_paths_resolve():
    from importlib import import_module

    from lightfall_vibe.manifest import manifest

    for entry in manifest.plugins:
        module_name, _, class_name = entry.import_path.partition(":")
        module = import_module(module_name)
        assert hasattr(module, class_name)


def test_entry_point_registered():
    eps = entry_points(group="lightfall.plugins")
    names = {ep.name for ep in eps}
    assert "lightfall_vibe" in names
