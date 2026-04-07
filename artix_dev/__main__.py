"""CLI entry point for artix-dev."""

from __future__ import annotations

import sys
from pathlib import Path

from artix_dev.config import InstallConfig


def usage() -> None:
    print("Usage: artix-dev <command> [config.toml]")
    print()
    print("Commands:")
    print("  render <config.toml>    Generate standalone bash install script")
    print("  install <config.toml>   Run Phase 1 installation from live USB")
    print("  dump-config             Print default config to stdout")
    sys.exit(1)


def load_config(args: list[str]) -> InstallConfig:
    if len(args) < 2:
        print("Error: command requires a config file path", file=sys.stderr)
        usage()
    config_path = Path(args[1])
    if not config_path.exists():
        print(f"Error: {config_path} not found", file=sys.stderr)
        sys.exit(1)
    return InstallConfig.load(config_path)


def main() -> None:
    args = sys.argv[1:]
    if not args:
        usage()

    command = args[0]

    if command == "dump-config":
        print(InstallConfig().to_toml())

    elif command == "render":
        cfg = load_config(args)
        from artix_dev.render import render_phase1
        print(render_phase1(cfg))

    elif command == "install":
        cfg = load_config(args)
        from artix_dev.phase1 import run_phase1
        run_phase1(cfg)

    else:
        print(f"Unknown command: {command}", file=sys.stderr)
        usage()


if __name__ == "__main__":
    main()
