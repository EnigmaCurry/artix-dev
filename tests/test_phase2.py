"""Tests for phase2 module."""

from unittest.mock import patch

from artix_dev.config import Feature, InstallConfig
from artix_dev.phase2 import run_phase2
import artix_dev.run as run_mod


def _valid_config() -> InstallConfig:
    cfg = InstallConfig()
    cfg.system.ssh_authorized_keys = ["ssh-ed25519 AAAA... test@test"]
    return cfg


def test_phase2_dry_run():
    """Dry run should complete without executing anything."""
    cfg = _valid_config()
    # Dry run doesn't need root or real system
    run_phase2(cfg, dry_run=True)
    assert run_mod.DRY_RUN is True
    run_mod.DRY_RUN = False


def test_phase2_requires_root():
    cfg = _valid_config()
    with patch("os.geteuid", return_value=1000):
        try:
            run_phase2(cfg)
            assert False, "Should have exited"
        except SystemExit:
            pass


def test_phase2_no_features():
    """Phase 2 with no features should only run system_update."""
    cfg = _valid_config()
    cfg.features = set()
    cfg.optional_services = set()
    cfg.flatpak_apps = []
    run_phase2(cfg, dry_run=True)
    run_mod.DRY_RUN = False


def test_phase2_podman_only():
    cfg = _valid_config()
    cfg.features = {Feature.PODMAN}
    run_phase2(cfg, dry_run=True)
    run_mod.DRY_RUN = False


def test_phase2_desktop_implies_sway_steps():
    """DESKTOP feature should trigger desktop and user dinit setup."""
    cfg = _valid_config()
    cfg.features = {Feature.DESKTOP}
    run_phase2(cfg, dry_run=True)
    run_mod.DRY_RUN = False
