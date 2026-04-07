"""Interactive TUI for building an InstallConfig."""

from __future__ import annotations

import os
import subprocess

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Center, Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import (
    Button,
    Checkbox,
    Footer,
    Header,
    Input,
    Label,
    OptionList,
    Pretty,
    RadioButton,
    RadioSet,
    Rule,
    Static,
    TextArea,
)

from artix_dev.config import (
    DEFAULT_EXTRA_PACKAGES,
    DEFAULT_FLATPAK_APPS,
    DiskType,
    Feature,
    InstallConfig,
    Kernel,
    OptionalService,
    SshPolicy,
)


def _list_disks() -> list[dict]:
    """List available block devices."""
    try:
        result = subprocess.run(
            ["lsblk", "-dno", "NAME,SIZE,MODEL,TYPE"],
            capture_output=True, text=True,
        )
        disks = []
        for line in result.stdout.strip().splitlines():
            parts = line.split(None, 3)
            if len(parts) >= 2 and parts[-1].strip() == "disk":
                name = parts[0]
                size = parts[1]
                model = parts[2] if len(parts) >= 4 else ""
                disks.append({
                    "device": f"/dev/{name}",
                    "size": size,
                    "model": model,
                    "type": DiskType.NVME if "nvme" in name else DiskType.OTHER,
                })
        return disks
    except FileNotFoundError:
        return []


class DiskScreen(Screen):
    BINDINGS = [Binding("escape", "back", "Back")]

    def __init__(self, cfg: InstallConfig) -> None:
        super().__init__()
        self.cfg = cfg
        self.disks = _list_disks()

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll():
            yield Label("Select Target Disk", classes="title")
            yield Rule()
            if self.disks:
                options = OptionList(
                    *[f"{d['device']}  {d['size']}  {d['model']}"
                      for d in self.disks],
                    id="disk-list",
                )
                yield options
            else:
                yield Label("No disks detected. Enter device path manually:")
            yield Label("\nDevice path:")
            yield Input(
                value="",
                placeholder="Select a disk above or type a device path",
                id="device",
            )
            yield Label("ESP size:")
            yield Input(value=self.cfg.disk.esp_size, id="esp-size")
            yield Checkbox("Enable SSD TRIM", value=self.cfg.disk.trim, id="trim")
            yield Rule()
            with Center():
                with Horizontal():
                    yield Button("Next", variant="primary", id="next")
        yield Footer()

    @on(OptionList.OptionSelected, "#disk-list")
    def disk_selected(self, event: OptionList.OptionSelected) -> None:
        idx = event.option_index
        disk = self.disks[idx]
        self.query_one("#device", Input).value = disk["device"]

    @on(Button.Pressed, "#next")
    def next_screen(self) -> None:
        self.cfg.disk.device = self.query_one("#device", Input).value
        self.cfg.disk.esp_size = self.query_one("#esp-size", Input).value
        self.cfg.disk.trim = self.query_one("#trim", Checkbox).value
        # Auto-detect disk type
        if "nvme" in self.cfg.disk.device:
            self.cfg.disk.disk_type = DiskType.NVME
        else:
            self.cfg.disk.disk_type = DiskType.OTHER
        self.app.push_screen(LuksScreen(self.cfg))

    def action_back(self) -> None:
        self.app.pop_screen()


class LuksScreen(Screen):
    BINDINGS = [Binding("escape", "back", "Back")]

    def __init__(self, cfg: InstallConfig) -> None:
        super().__init__()
        self.cfg = cfg

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll():
            yield Label("Encryption Settings", classes="title")
            yield Rule()
            yield Label("LUKS cipher:")
            yield Input(value=self.cfg.luks.cipher, id="cipher")
            yield Label("Key size:")
            yield Input(value=str(self.cfg.luks.key_size), id="key-size")
            yield Label("Hash:")
            yield Input(value=self.cfg.luks.hash, id="hash")
            yield Label("Iteration time (ms):")
            yield Input(value=str(self.cfg.luks.iter_time), id="iter-time")
            yield Rule()
            yield Label("LVM boot size:")
            yield Input(value=self.cfg.lvm.boot_size, id="boot-size")
            yield Label("LVM swap size:")
            yield Input(value=self.cfg.lvm.swap_size, id="swap-size")
            yield Rule()
            with Center():
                with Horizontal():
                    yield Button("Next", variant="primary", id="next")
        yield Footer()

    @on(Button.Pressed, "#next")
    def next_screen(self) -> None:
        self.cfg.luks.cipher = self.query_one("#cipher", Input).value
        self.cfg.luks.key_size = int(self.query_one("#key-size", Input).value)
        self.cfg.luks.hash = self.query_one("#hash", Input).value
        self.cfg.luks.iter_time = int(self.query_one("#iter-time", Input).value)
        self.cfg.lvm.boot_size = self.query_one("#boot-size", Input).value
        self.cfg.lvm.swap_size = self.query_one("#swap-size", Input).value
        self.app.push_screen(SystemScreen(self.cfg))

    def action_back(self) -> None:
        self.app.pop_screen()


class SystemScreen(Screen):
    BINDINGS = [Binding("escape", "back", "Back")]

    def __init__(self, cfg: InstallConfig) -> None:
        super().__init__()
        self.cfg = cfg

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll():
            yield Label("System Configuration", classes="title")
            yield Rule()
            yield Label("Hostname:")
            yield Input(value=self.cfg.system.hostname, id="hostname")
            yield Label("Username:")
            yield Input(value=self.cfg.system.username, id="username")
            yield Label("Locale:")
            yield Input(value=self.cfg.system.locale, id="locale")
            yield Label("Timezone:")
            yield Input(value=self.cfg.system.timezone, id="timezone")
            yield Label("Tmpfs size (/tmp):")
            yield Input(value=self.cfg.system.tmpfs_size, id="tmpfs-size")
            yield Checkbox(
                "Remap Caps Lock to Control",
                value=self.cfg.system.caps_lock_remap,
                id="capslock",
            )
            yield Rule()
            yield Label("Kernel:")
            with RadioSet(id="kernel"):
                for k in Kernel:
                    yield RadioButton(
                        k.value,
                        value=(k == self.cfg.system.kernel),
                    )
            yield Rule()
            with Center():
                with Horizontal():
                    yield Button("Next", variant="primary", id="next")
        yield Footer()

    @on(Button.Pressed, "#next")
    def next_screen(self) -> None:
        self.cfg.system.hostname = self.query_one("#hostname", Input).value
        self.cfg.system.username = self.query_one("#username", Input).value
        self.cfg.system.locale = self.query_one("#locale", Input).value
        self.cfg.system.timezone = self.query_one("#timezone", Input).value
        self.cfg.system.tmpfs_size = self.query_one("#tmpfs-size", Input).value
        self.cfg.system.caps_lock_remap = self.query_one("#capslock", Checkbox).value
        kernel_set = self.query_one("#kernel", RadioSet)
        if kernel_set.pressed_index >= 0:
            self.cfg.system.kernel = list(Kernel)[kernel_set.pressed_index]
        self.app.push_screen(SshScreen(self.cfg))

    def action_back(self) -> None:
        self.app.pop_screen()


class SshScreen(Screen):
    BINDINGS = [Binding("escape", "back", "Back")]

    def __init__(self, cfg: InstallConfig) -> None:
        super().__init__()
        self.cfg = cfg

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll():
            yield Label("SSH Configuration", classes="title")
            yield Rule()
            yield Label("SSH policy:")
            with RadioSet(id="ssh-policy"):
                for p in SshPolicy:
                    labels = {
                        "keys_only": "Keys only (disable password auth)",
                        "password": "Password auth enabled",
                        "disable": "Disable SSH entirely",
                    }
                    yield RadioButton(
                        labels[p.value],
                        value=(p == self.cfg.system.ssh),
                    )
            yield Rule()
            yield Label("Authorized public keys (one per line):")
            yield TextArea(
                "\n".join(self.cfg.system.ssh_authorized_keys),
                id="ssh-keys",
            )
            yield Rule()
            with Center():
                with Horizontal():
                    yield Button("Next", variant="primary", id="next")
        yield Footer()

    @on(Button.Pressed, "#next")
    def next_screen(self) -> None:
        policy_set = self.query_one("#ssh-policy", RadioSet)
        if policy_set.pressed_index >= 0:
            self.cfg.system.ssh = list(SshPolicy)[policy_set.pressed_index]
        keys_text = self.query_one("#ssh-keys", TextArea).text
        self.cfg.system.ssh_authorized_keys = [
            line.strip() for line in keys_text.splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        self.app.push_screen(FeaturesScreen(self.cfg))

    def action_back(self) -> None:
        self.app.pop_screen()


class FeaturesScreen(Screen):
    BINDINGS = [Binding("escape", "back", "Back")]

    def __init__(self, cfg: InstallConfig) -> None:
        super().__init__()
        self.cfg = cfg

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll():
            yield Label("Features", classes="title")
            yield Rule()
            for f in Feature:
                labels = {
                    "podman": "Rootless Podman containers",
                    "libvirt": "QEMU/libvirt virtual machines",
                    "nix": "Nix package manager",
                    "desktop": "Sway desktop + audio + greetd",
                    "sway_home": "sway-home dotfiles (implies Nix + Desktop)",
                    "flatpak": "Flatpak + Flathub",
                }
                yield Checkbox(
                    labels[f.value],
                    value=(f in self.cfg.features),
                    id=f"feat-{f.value}",
                )
            yield Rule()
            yield Label("Optional Services")
            yield Rule()
            for s in OptionalService:
                yield Checkbox(
                    s.value,
                    value=(s in self.cfg.optional_services),
                    id=f"svc-{s.value}",
                )
            yield Rule()
            with Center():
                with Horizontal():
                    yield Button("Next", variant="primary", id="next")
        yield Footer()

    @on(Button.Pressed, "#next")
    def next_screen(self) -> None:
        self.cfg.features = {
            f for f in Feature
            if self.query_one(f"#feat-{f.value}", Checkbox).value
        }
        self.cfg.optional_services = {
            s for s in OptionalService
            if self.query_one(f"#svc-{s.value}", Checkbox).value
        }
        self.app.push_screen(SwayHomeScreen(self.cfg))

    def action_back(self) -> None:
        self.app.pop_screen()


class SwayHomeScreen(Screen):
    BINDINGS = [Binding("escape", "back", "Back")]

    def __init__(self, cfg: InstallConfig) -> None:
        super().__init__()
        self.cfg = cfg

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll():
            yield Label("sway-home & GRUB Settings", classes="title")
            yield Rule()
            yield Label("sway-home git repo:")
            yield Input(value=self.cfg.sway_home.repo, id="repo")
            yield Label("Clone path:")
            yield Input(value=self.cfg.sway_home.clone_path, id="clone-path")
            yield Rule()
            yield Label("GRUB timeout (seconds):")
            yield Input(value=str(self.cfg.grub.timeout), id="grub-timeout")
            yield Label("GRUB graphics mode:")
            yield Input(value=self.cfg.grub.gfxmode, id="grub-gfxmode")
            yield Rule()
            with Center():
                with Horizontal():
                    yield Button("Next", variant="primary", id="next")
        yield Footer()

    @on(Button.Pressed, "#next")
    def next_screen(self) -> None:
        self.cfg.sway_home.repo = self.query_one("#repo", Input).value
        self.cfg.sway_home.clone_path = self.query_one("#clone-path", Input).value
        self.cfg.grub.timeout = int(self.query_one("#grub-timeout", Input).value)
        self.cfg.grub.gfxmode = self.query_one("#grub-gfxmode", Input).value
        self.app.push_screen(ReviewScreen(self.cfg))

    def action_back(self) -> None:
        self.app.pop_screen()


class ReviewScreen(Screen):
    BINDINGS = [Binding("escape", "back", "Back")]

    def __init__(self, cfg: InstallConfig) -> None:
        super().__init__()
        self.cfg = cfg

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll():
            yield Label("Review Configuration", classes="title")
            yield Rule()
            yield Static(self.cfg.to_toml(), id="toml-preview")
            yield Rule()
            errors = self.cfg.validate()
            if errors:
                yield Label("Validation Errors:", classes="error-title")
                for err in errors:
                    yield Label(f"  - {err}", classes="error")
                yield Rule()
            with Center():
                with Horizontal():
                    yield Button("Install", variant="primary", id="install")
                    yield Button("Save Config", variant="default", id="save")
        yield Footer()

    @on(Button.Pressed, "#install")
    def do_install(self) -> None:
        errors = self.cfg.validate()
        if errors:
            self.notify("Fix validation errors before installing", severity="error")
            return
        self.app.result = ("install", self.cfg)
        self.app.exit()

    @on(Button.Pressed, "#save")
    def do_save(self) -> None:
        self.app.result = ("save", self.cfg)
        self.app.exit()

    def action_back(self) -> None:
        self.app.pop_screen()


class ArtixInstaller(App):
    CSS = """
    Screen {
        align: center top;
    }
    VerticalScroll {
        max-width: 80;
        width: 100%;
    }
    .title {
        text-style: bold;
        color: $accent;
        margin: 1 0;
    }
    .error-title {
        text-style: bold;
        color: $error;
    }
    .error {
        color: $error;
    }
    Button {
        margin: 1 1;
    }
    Input, TextArea {
        margin: 0 0 1 0;
    }
    Checkbox, RadioButton {
        margin: 0 0 0 2;
    }
    #toml-preview {
        margin: 1 2;
        padding: 1 2;
        background: $surface;
    }
    """
    TITLE = "artix-dev installer"
    BINDINGS = [Binding("q", "quit", "Quit")]

    def __init__(self, cfg: InstallConfig | None = None) -> None:
        super().__init__()
        self.cfg = cfg or InstallConfig()
        self.result: tuple[str, InstallConfig] | None = None

    def on_mount(self) -> None:
        self.push_screen(DiskScreen(self.cfg))


def run_tui(cfg: InstallConfig | None = None) -> tuple[str, InstallConfig] | None:
    """Run the TUI and return (action, config) or None if quit."""
    app = ArtixInstaller(cfg)
    app.run()
    return app.result
