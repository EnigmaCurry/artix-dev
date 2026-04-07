"""Tests for phase1 module structure."""

from unittest.mock import patch, call
import os

from artix_dev.config import InstallConfig, OptionalService, SshPolicy
from artix_dev.phase1 import (
    OPTIONAL_SERVICE_NAMES,
    OPTIONAL_SERVICE_PACKAGES,
    chroot_enable_services,
    chroot_install_optional_services,
    run_phase1,
)


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
    with patch("os.symlink", side_effect=lambda src, dst: symlinks.append(dst)):
        chroot_enable_services(cfg)
    service_names = [os.path.basename(s) for s in symlinks]
    assert "sshd" in service_names
    assert "NetworkManager" in service_names
    assert "lvm2" in service_names


def test_base_services_exclude_sshd_when_disabled():
    cfg = InstallConfig()
    cfg.system.ssh = SshPolicy.DISABLE
    symlinks: list[str] = []
    with patch("os.symlink", side_effect=lambda src, dst: symlinks.append(dst)):
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


def test_optional_services_empty_skips():
    """No packages installed when optional_services is empty."""
    cfg = InstallConfig()
    cfg.optional_services = set()
    # Should not call run_chroot at all
    with patch("artix_dev.phase1.run_chroot") as mock_run:
        chroot_install_optional_services(cfg)
    mock_run.assert_not_called()
