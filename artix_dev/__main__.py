"""CLI entry point for artix-dev."""

from __future__ import annotations

import sys
from pathlib import Path

from artix_dev.config import InstallConfig

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

        cfg, config_file = _load_config(rest)

        from artix_dev.phase1 import run_phase1
        run_phase1(cfg, dry_run=dry_run, config_path=config_file)

    elif command == "setup":
        rest = args[1:]
        dry_run = "--dry-run" in rest
        rest = [a for a in rest if a != "--dry-run"]

        cfg, _ = _load_config(rest)

        from artix_dev.phase2 import run_phase2
        run_phase2(cfg, dry_run=dry_run)

    else:
        print(f"Unknown command: {command}", file=sys.stderr)
        usage()


if __name__ == "__main__":
    main()
