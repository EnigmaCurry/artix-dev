"""Tests for config serialization roundtrip."""

from artix_dev.config import (
    DiskType,
    Feature,
    InstallConfig,
    Kernel,
    OptionalService,
)


def test_default_roundtrip():
    original = InstallConfig()
    toml_text = original.to_toml()
    restored = InstallConfig.from_toml(toml_text)

    assert restored.disk.device == original.disk.device
    assert restored.disk.disk_type == original.disk.disk_type
    assert restored.luks.cipher == original.luks.cipher
    assert restored.luks.key_size == original.luks.key_size
    assert restored.lvm.swap_size == original.lvm.swap_size
    assert restored.system.hostname == original.system.hostname
    assert restored.system.kernel == original.system.kernel
    assert restored.sway_home.repo == original.sway_home.repo
    assert restored.features == original.features
    assert restored.optional_services == original.optional_services


def test_custom_values_roundtrip():
    config = InstallConfig()
    config.disk.device = "/dev/vda"
    config.disk.disk_type = DiskType.OTHER
    config.system.hostname = "mybox"
    config.system.username = "alice"
    config.system.kernel = Kernel.ZEN
    config.sway_home.repo = "https://github.com/alice/sway-home"
    config.features = {Feature.NIX, Feature.PODMAN}
    config.optional_services = {OptionalService.NTPD}

    restored = InstallConfig.from_toml(config.to_toml())

    assert restored.disk.device == "/dev/vda"
    assert restored.disk.disk_type == DiskType.OTHER
    assert restored.disk.part_prefix == "/dev/vda"
    assert restored.system.hostname == "mybox"
    assert restored.system.kernel == Kernel.ZEN
    assert restored.kernel_package == "linux-zen"
    assert restored.kernel_headers_package == "linux-zen-headers"
    assert restored.sway_home.repo == "https://github.com/alice/sway-home"
    assert restored.features == {Feature.NIX, Feature.PODMAN}
    assert restored.install_nix is True
    assert restored.install_desktop is False
    assert restored.install_sway_home is False


def test_partition_paths_nvme():
    config = InstallConfig()
    assert config.disk.esp_partition == "/dev/nvme0n1p1"
    assert config.disk.luks_partition == "/dev/nvme0n1p2"


def test_partition_paths_virtio():
    config = InstallConfig()
    config.disk.device = "/dev/vda"
    config.disk.disk_type = DiskType.OTHER
    assert config.disk.esp_partition == "/dev/vda1"
    assert config.disk.luks_partition == "/dev/vda2"


def test_feature_implications():
    config = InstallConfig()
    config.features = {Feature.SWAY_HOME}
    assert config.install_sway_home is True
    assert config.install_nix is True
    assert config.install_desktop is True
    assert config.install_podman is False


def test_empty_features_from_toml():
    toml = '[features]\nenable = []\n'
    config = InstallConfig.from_toml(toml)
    assert config.features == set()


def test_toml_output_readable():
    config = InstallConfig()
    toml_text = config.to_toml()
    assert "[disk]" in toml_text
    assert "[luks]" in toml_text
    assert "[system]" in toml_text
    assert "[sway_home]" in toml_text
    assert "[features]" in toml_text
    assert "[services]" in toml_text
    assert 'kernel = "linux-hardened"' in toml_text
