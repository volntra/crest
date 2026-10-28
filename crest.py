#!/usr/bin/env python3
"""crest: Rockhopper's declarative package manager (v0.1, diff only)."""

import sys
import tomllib

CONFIG = "/etc/rockhopper/system.toml"
WORLD = "/var/lib/portage/world"


def read_config(path):
    """Return the set of packages system.toml says should be installed."""
    with open(path, "rb") as f:
        config = tomllib.load(f)
    return set(config.get("packages", {}).get("world", []))


def read_world(path):
    """Return the set of packages Portage has recorded as explicitly installed."""
    with open(path) as f:
        return {line.strip() for line in f if line.strip() and not line.startswith("#")}


def diff():
    wanted = read_config(CONFIG)
    installed = read_world(WORLD)

    to_add = sorted(wanted - installed)
    to_remove = sorted(installed - wanted)

    if not to_add and not to_remove:
        print("System matches system.toml. Nothing to do.")
        return

    for pkg in to_add:
        print(f"  + {pkg}")
    for pkg in to_remove:
        print(f"  - {pkg}")
    print(f"\n{len(to_add)} to add, {len(to_remove)} to remove")


def main():
    if len(sys.argv) < 2:
        print("usage: crest <command>\ncommands: diff")
        sys.exit(1)

    command = sys.argv[1]
    if command == "diff":
        diff()
    else:
        print(f"crest: unknown command '{command}'")
        sys.exit(1)


if __name__ == "__main__":
    main()
