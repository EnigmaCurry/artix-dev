"""Tests for Python script rendering."""

import ast

import pytest

from artix_dev.config import DiskType, InstallConfig, Kernel, SshPolicy
from artix_dev.render import render_phase1


def _valid_config(**overrides) -> InstallConfig:
    """Create a config that passes validation (has SSH keys)."""
    cfg = InstallConfig()
    cfg.system.ssh_authorized_keys = ["ssh-ed25519 AAAA... user@host"]
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


def _parse_and_exec(script: str) -> dict:
    """Parse the script, strip the __main__ block, exec it, return namespace."""
    tree = ast.parse(script)
    tree.body = [
        node for node in tree.body
        if not (
            isinstance(node, ast.If)
            and isinstance(node.test, ast.Compare)
            and any(
                isinstance(c, ast.Constant) and c.value == "__main__"
                for c in node.test.comparators
            )
        )
    ]
    code = compile(tree, "<render>", "exec")
    ns: dict = {}
    exec(code, ns)
    return ns


def test_render_valid_python():
    script = render_phase1(_valid_config())
    ast.parse(script)


def test_render_header():
    script = render_phase1(_valid_config())
    assert script.startswith("#!/usr/bin/env python3\n")
    assert "from __future__ import annotations" in script


def test_render_embeds_config():
    cfg = _valid_config()
    cfg.system.hostname = "mybox"
    cfg.disk.device = "/dev/sda"
    cfg.disk.disk_type = DiskType.OTHER
    cfg.system.kernel = Kernel.ZEN
    script = render_phase1(cfg)

    ns = _parse_and_exec(script)
    restored = ns["InstallConfig"].from_toml(ns["_TOML_CONFIG"])
    assert restored.system.hostname == "mybox"
    assert restored.disk.device == "/dev/sda"
    assert restored.disk.disk_type.value == "other"
    assert restored.system.kernel.value == "linux-zen"


def test_render_config_validates():
    cfg = _valid_config()
    script = render_phase1(cfg)
    ns = _parse_and_exec(script)
    restored = ns["InstallConfig"].from_toml(ns["_TOML_CONFIG"])
    assert restored.validate() == []


def test_render_has_run_phase1():
    script = render_phase1(_valid_config())
    ns = _parse_and_exec(script)
    assert callable(ns["run_phase1"])


def test_render_has_main_block():
    script = render_phase1(_valid_config())
    assert 'if __name__ == "__main__":' in script
    assert "run_phase1(cfg)" in script


def test_render_ssh_keys_embedded():
    cfg = _valid_config()
    cfg.system.ssh_authorized_keys = [
        "ssh-ed25519 AAAA... alice@laptop",
        "ssh-rsa BBBB... bob@desktop",
    ]
    script = render_phase1(cfg)
    ns = _parse_and_exec(script)
    restored = ns["InstallConfig"].from_toml(ns["_TOML_CONFIG"])
    assert restored.system.ssh_authorized_keys == [
        "ssh-ed25519 AAAA... alice@laptop",
        "ssh-rsa BBBB... bob@desktop",
    ]


def test_render_validation_fails_without_keys():
    cfg = InstallConfig()
    cfg.system.ssh = SshPolicy.ENABLE_KEYS_ONLY
    cfg.system.ssh_authorized_keys = []
    with pytest.raises(ValueError, match="ssh_authorized_keys"):
        render_phase1(cfg)


def test_render_features_preserved():
    from artix_dev.config import Feature
    cfg = _valid_config()
    cfg.features = {Feature.NIX, Feature.PODMAN}
    script = render_phase1(cfg)
    ns = _parse_and_exec(script)
    restored = ns["InstallConfig"].from_toml(ns["_TOML_CONFIG"])
    assert {f.value for f in restored.features} == {"nix", "podman"}
