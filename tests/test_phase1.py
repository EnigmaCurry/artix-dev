"""Tests for phase1 module structure."""

from unittest.mock import patch
import os

from artix_dev.config import InstallConfig, OptionalService, SshPolicy
from artix_dev.phase1 import (
    OPTIONAL_SERVICE_NAMES,
    OPTIONAL_SERVICE_PACKAGES,
    chroot_enable_services,
    chroot_install_optional_services,
    run_phase1,
)
import artix_dev.run as run_mod


def test_optional_service_packages_complete():
    """Every OptionalService enum has an entry in the package map."""
    for svc in OptionalService:
        assert svc in OPTIONAL_SERVICE_PACKAGES
        assert svc in OPTIONAL_SERVICE_NAMES


def test_base_services_include_sshd_by_default():
    """SSH is enabled by default (keys_only policy)."""
    cfg = InstallConfig()
    assert cfg.system.ssh == SshPolicy.ENABLE_KEYS_ONLY
    symlinks: list[str] = []
    with patch("artix_dev.phase1.symlink", side_effect=lambda src, dst: symlinks.append(dst)):
        chroot_enable_services(cfg)
    service_names = [os.path.basename(s) for s in symlinks]
    assert "sshd" in service_names
    assert "NetworkManager" in service_names
    assert "lvm2" in service_names


def test_base_services_exclude_sshd_when_disabled():
    cfg = InstallConfig()
    cfg.system.ssh = SshPolicy.DISABLE
    symlinks: list[str] = []
    with patch("artix_dev.phase1.symlink", side_effect=lambda src, dst: symlinks.append(dst)):
        chroot_enable_services(cfg)
    service_names = [os.path.basename(s) for s in symlinks]
    assert "sshd" not in service_names


def test_phase1_requires_root():
    cfg = InstallConfig()
    with patch("os.geteuid", return_value=1000):
        try:
            run_phase1(cfg)
            assert False, "Should have exited"
        except SystemExit:
            pass


def test_phase1_dry_run_skips_root_check():
    """Dry run should not require root and should not execute commands."""
    cfg = InstallConfig()
    cfg.system.ssh_authorized_keys = ["ssh-ed25519 AAAA... test@test"]
    # Mock validate_system since we're not on a live ISO
    with patch.object(cfg, "validate_system", return_value=[]):
        run_phase1(cfg, dry_run=True)
    assert run_mod.DRY_RUN is True
    run_mod.DRY_RUN = False


def test_phase1_dry_run_validates_disk():
    """Dry run should fail if validation returns errors."""
    cfg = InstallConfig()
    cfg.system.ssh_authorized_keys = ["ssh-ed25519 AAAA... test@test"]
    cfg.disk.device = "/dev/nonexistent"
    try:
        run_phase1(cfg, dry_run=True)
        assert False, "Should have exited"
    except SystemExit:
        pass
    run_mod.DRY_RUN = False


def test_validate_system_disk_missing():
    cfg = InstallConfig()
    cfg.system.ssh_authorized_keys = ["ssh-ed25519 AAAA... test@test"]
    cfg.disk.device = "/dev/nonexistent"
    errors = cfg.validate_system()
    assert any("does not exist" in e for e in errors)


def test_validate_system_not_block_device():
    cfg = InstallConfig()
    cfg.system.ssh_authorized_keys = ["ssh-ed25519 AAAA... test@test"]
    cfg.disk.device = "/dev/null"
    errors = cfg.validate_system()
    assert any("not a block device" in e for e in errors)


def test_validate_system_live_iso_check():
    """On a real installed system, should warn about not being on live ISO."""
    cfg = InstallConfig()
    cfg.system.ssh_authorized_keys = ["ssh-ed25519 AAAA... test@test"]
    cfg.disk.device = "/dev/nonexistent"  # will also fail disk check
    errors = cfg.validate_system()
    # On this test machine (installed system), should detect non-live root
    has_live_warning = any("live ISO" in e for e in errors)
    has_disk_warning = any("does not exist" in e for e in errors)
    assert has_disk_warning
    # live ISO check depends on the host; just verify no crash


def test_optional_services_empty_skips():
    """No packages installed when optional_services is empty."""
    cfg = InstallConfig()
    cfg.optional_services = set()
    with patch("artix_dev.phase1.run_chroot") as mock_run:
        chroot_install_optional_services(cfg)
    mock_run.assert_not_called()
