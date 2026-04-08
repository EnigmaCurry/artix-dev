"""CLI entry point for artix-dev."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from artix_dev.config import InstallConfig


def _ensure_root(config_file: str | None = None) -> None:
    """Re-exec with sudo if not root. Exits if sudo fails."""
    if os.geteuid() == 0:
        return
    # Verify sudo works before re-exec
    result = subprocess.run(
        ["sudo", "-n", "true"], capture_output=True,
    )
    if result.returncode != 0:
        # sudo needs a password — let it prompt
        result = subprocess.run(["sudo", "true"])
        if result.returncode != 0:
            print("Error: sudo authentication failed", file=sys.stderr)
            sys.exit(1)
    # Build the command to re-exec
    # Strip any existing config file args and use the one we have
    cmd_args = [a for a in sys.argv[1:] if not a.endswith(".toml")]
    if config_file:
        cmd_args.append(config_file)
    # Detect if running from a .pyz zipapp vs normal module
    main_script = Path(sys.argv[0]).resolve()
    if main_script.suffix == ".pyz":
        os.execvp("sudo", ["sudo", sys.executable, str(main_script)] + cmd_args)
    else:
        os.execvp("sudo", ["sudo", sys.executable, "-m", "artix_dev"] + cmd_args)

DEFAULT_CONFIG = Path("/root/artix-dev/config.toml")


def usage() -> None:
    print("Usage: artix-dev <command> [options] [config.toml]")
    print()
    print("Commands:")
    print("  install [config.toml]       Phase 1: install from live USB")
    print("  setup [config.toml]         Phase 2: post-install setup (idempotent)")
    print("  --dry-run                   Show what would be done without executing")
    print("  --version                   Show version info")
    print("  dump-config                 Print default config to stdout")
    print()
    print(f"Config defaults to {DEFAULT_CONFIG} if not specified (setup).")
    sys.exit(1)


def _load_config(rest: list[str]) -> tuple[InstallConfig, str | None]:
    """Load config from args or default path. Returns (config, path)."""
    if rest:
        config_file = rest[0]
    elif DEFAULT_CONFIG.exists():
        config_file = str(DEFAULT_CONFIG)
        print(f"Using config: {config_file}")
    else:
        print("Error: no config file specified and "
              f"{DEFAULT_CONFIG} not found", file=sys.stderr)
        sys.exit(1)

    config_path = Path(config_file)
    if not config_path.exists():
        print(f"Error: {config_path} not found", file=sys.stderr)
        sys.exit(1)

    return InstallConfig.load(config_path), config_file


def main() -> None:
    args = sys.argv[1:]
    if not args:
        usage()

    command = args[0]

    if command == "--version":
        from artix_dev._version import BUILD_TIME, REPO, VERSION
        parts = [f"artix-dev {VERSION}"]
        if REPO:
            parts.append(f"({REPO})")
        if BUILD_TIME:
            parts.append(f"built {BUILD_TIME}")
        print(" ".join(parts))

    elif command == "dump-config":
        print(InstallConfig().to_toml())

    elif command == "install":
        rest = args[1:]
        dry_run = "--dry-run" in rest
        rest = [a for a in rest if a != "--dry-run"]

        if not dry_run:
            _ensure_root(None)

        if rest:
            cfg, config_file = _load_config(rest)
        else:
            from artix_dev.tui import run_tui
            saved = DEFAULT_CONFIG
            while True:
                prev_cfg = InstallConfig.load(saved) if saved.exists() else None
                saved_str = str(saved) if saved.exists() else None
                result = run_tui(prev_cfg, config_path=saved_str)
                if result is None:
                    print("Aborted.")
                    sys.exit(1)
                action, cfg = result
                if action == "reset":
                    continue  # re-launch TUI with fresh config
                # Save for next run
                saved.parent.mkdir(parents=True, exist_ok=True)
                cfg.save(saved)
                if action == "save":
                    print(f"Config saved to {saved}")
                    sys.exit(0)
                break  # action == "install"
            config_file = str(saved)
        from artix_dev.phase1 import run_phase1
        run_phase1(cfg, dry_run=dry_run, config_path=config_file)

    elif command == "setup":
        rest = args[1:]
        dry_run = "--dry-run" in rest
        rest = [a for a in rest if a != "--dry-run"]

        cfg, config_file = _load_config(rest)

        if not dry_run:
            _ensure_root(config_file)
        from artix_dev.phase2 import run_phase2
        run_phase2(cfg, dry_run=dry_run)

    else:
        print(f"Unknown command: {command}", file=sys.stderr)
        usage()


if __name__ == "__main__":
    main()
