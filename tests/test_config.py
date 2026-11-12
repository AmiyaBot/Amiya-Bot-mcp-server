import json

import pytest

from src.app import config


@pytest.fixture
def config_paths(tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setattr(config, "FILE_PATH", project)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "global"))
    return (
        project / "data" / "config.json",
        config.resolve_global_config_path(),
        project / "resources" / "config.json",
        project / "config.json",
    )


def write_config(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_portrait_defaults_and_global_file_creation(config_paths):
    cfg = config.load_from_disk()
    assert cfg.PortraitAttributeCardEnabled is False
    assert config.Config(cfg.ProjectRoot, cfg.ResourcePath).PortraitAttributeCardEnabled is False
    assert json.loads(config_paths[1].read_text()) == {}


@pytest.mark.parametrize("value, expected", [
    (True, True), (False, False), ("false", False), ("true", True),
    (None, False), ("invalid", False),
])
def test_portrait_global_override(config_paths, value, expected):
    write_config(config_paths[0], {"PortraitAttributeCardEnabled": True})
    write_config(config_paths[1], {"PortraitAttributeCardEnabled": value})
    state = config.inspect_config_state()
    assert state.config.PortraitAttributeCardEnabled is expected
    assert state.key_sources["PortraitAttributeCardEnabled"] == config_paths[1]
    assert state.active_path == config_paths[1]


def test_config_layers_preserve_other_settings(config_paths):
    for path, enabled in zip(config_paths, [True, False, True, False]):
        write_config(path, {"PortraitAttributeCardEnabled": enabled})
        state = config.inspect_config_state()
        assert state.config.PortraitAttributeCardEnabled is enabled
        assert state.key_sources["PortraitAttributeCardEnabled"] == path
    write_config(config_paths[-1], {"BaseUrl": "https://example.test/"})
    state = config.inspect_config_state()
    assert state.config.PortraitAttributeCardEnabled is True
    assert state.config.BaseUrl == "https://example.test/"
    assert state.layer_paths == config_paths
