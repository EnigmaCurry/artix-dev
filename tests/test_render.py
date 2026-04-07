"""Tests for bash script rendering."""

import pytest

from artix_dev.config import DiskType, Feature, InstallConfig, Kernel, SshPolicy
from artix_dev.render import render_phase1


def _valid_config(**overrides) -> InstallConfig:
    """Create a config that passes validation (has SSH keys)."""
    cfg = InstallConfig()
    cfg.system.ssh_authorized_keys = ["ssh-ed25519 AAAA... user@host"]
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


def test_render_produces_bash():
    script = render_phase1(_valid_config())
    assert script.startswith("#!/bin/bash\n")
    assert "set -euo pipefail" in script


def test_render_contains_all_sections():
    script = render_phase1(_valid_config())
    assert "Partitioning disk" in script
    assert "Setting up LUKS" in script
    assert "Setting up LVM" in script
    assert "Formatting partitions" in script
    assert "Mounting partitions" in script
    assert "Installing base system" in script
    assert "Generating fstab" in script
    assert "Setting root password" in script
    assert "Configuring locale" in script
    assert "Configuring timezone" in script
    assert "Setting hostname" in script
    assert "Configuring mkinitcpio" in script
    assert "Configuring GRUB" in script
    assert "Installing GRUB" in script
    assert "Enabling base dinit services" in script
    assert "Creating user account" in script
    assert "Configuring SSH" in script
    assert "Unmounting and finishing" in script


def test_render_bakes_config_values():
    cfg = _valid_config()
    cfg.disk.device = "/dev/sda"
    cfg.disk.disk_type = DiskType.OTHER
    cfg.system.hostname = "mybox"
    cfg.system.kernel = Kernel.ZEN
    script = render_phase1(cfg)
    assert "DISK=/dev/sda" in script
    assert "PART=/dev/sda" in script
    assert "HOSTNAME=mybox" in script
    assert "KERNEL=linux-zen" in script


def test_render_trim_disabled():
    cfg = _valid_config()
    cfg.disk.trim = False
    script = render_phase1(cfg)
    assert "blkdiscard" not in script
    assert "allow-discards" not in script
    assert "discard" not in script


def test_render_no_capslock():
    cfg = _valid_config()
    cfg.system.caps_lock_remap = False
    script = render_phase1(cfg)
    assert "Caps Lock" not in script
    assert "personal.map" not in script


def test_render_ssh_disabled():
    cfg = _valid_config()
    cfg.system.ssh = SshPolicy.DISABLE
    cfg.system.ssh_authorized_keys = []
    script = render_phase1(cfg)
    assert "Configuring SSH" not in script
    assert "authorized_keys" not in script
    assert "sshd" not in script


def test_render_ssh_password():
    cfg = _valid_config()
    cfg.system.ssh = SshPolicy.ENABLE_PASSWORD
    cfg.system.ssh_authorized_keys = ["ssh-ed25519 AAAA... user@host"]
    script = render_phase1(cfg)
    assert "PasswordAuthentication" not in script
    assert "authorized_keys" in script


def test_render_authorized_keys_in_script():
    cfg = _valid_config()
    cfg.system.ssh_authorized_keys = [
        "ssh-ed25519 AAAA... alice@laptop",
        "ssh-rsa BBBB... bob@desktop",
    ]
    script = render_phase1(cfg)
    assert "ssh-ed25519 AAAA... alice@laptop" in script
    assert "ssh-rsa BBBB... bob@desktop" in script


def test_render_validation_fails_without_keys():
    cfg = InstallConfig()
    cfg.system.ssh = SshPolicy.ENABLE_KEYS_ONLY
    cfg.system.ssh_authorized_keys = []
    with pytest.raises(ValueError, match="ssh_authorized_keys"):
        render_phase1(cfg)


def test_render_root_check():
    script = render_phase1(_valid_config())
    assert "EUID" in script
    assert "must be run as root" in script
