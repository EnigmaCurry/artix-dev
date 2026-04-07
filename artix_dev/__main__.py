"""CLI entry point for artix-dev."""

from __future__ import annotations

import sys
from pathlib import Path

from artix_dev.config import InstallConfig


def usage() -> None:
    print("Usage: artix-dev <command> [options] [config.toml]")
    print()
    print("Commands:")
    print("  install [config.toml]       Run Phase 1 installation (TUI if no config given)")
    print("  install --dry-run <config>  Show what would be done without executing")
    print("  dump-config                 Print default config to stdout")
    sys.exit(1)


def main() -> None:
    args = sys.argv[1:]
    if not args:
        usage()

    command = args[0]

    if command == "dump-config":
        print(InstallConfig().to_toml())

    elif command == "install":
        rest = args[1:]
        dry_run = "--dry-run" in rest
        rest = [a for a in rest if a != "--dry-run"]

        if rest:
            config_path = Path(rest[0])
            if not config_path.exists():
                print(f"Error: {config_path} not found", file=sys.stderr)
                sys.exit(1)
            cfg = InstallConfig.load(config_path)
        else:
            # TODO: launch TUI to build config interactively
            print("Error: interactive TUI not yet implemented", file=sys.stderr)
            print("Provide a config file: artix-dev install <config.toml>", file=sys.stderr)
            sys.exit(1)

        from artix_dev.phase1 import run_phase1
        run_phase1(cfg, dry_run=dry_run)

    else:
        print(f"Unknown command: {command}", file=sys.stderr)
        usage()


if __name__ == "__main__":
    main()
