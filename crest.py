#!/usr/bin/env python3
"""crest: Rockhopper's declarative package manager (v0.2)."""

import os
import re
import subprocess
import sys
import tomllib

CONFIG = "/etc/rockhopper/system.toml"
WORLD = "/var/lib/portage/world"
SNAPSHOT_DIR = "/.snapshots"


def read_config(path):
    """Return the set of packages system.toml says should be installed."""
    with open(path, "rb") as f:
        config = tomllib.load(f)
    return set(config.get("packages", {}).get("world", []))


def read_world(path):
    """Return the set of packages Portage has recorded as explicitly installed."""
    with open(path) as f:
        return {line.strip() for line in f if line.strip() and not line.startswith("#")}


def compute_diff():
    """Return (to_add, to_remove) as sorted lists."""
    wanted = read_config(CONFIG)
    installed = read_world(WORLD)
    return sorted(wanted - installed), sorted(installed - wanted)


def print_diff(to_add, to_remove):
    for pkg in to_add:
        print(f"  + {pkg}")
    for pkg in to_remove:
        print(f"  - {pkg}")
    print(f"\n{len(to_add)} to add, {len(to_remove)} to remove")


def diff():
    to_add, to_remove = compute_diff()
    if not to_add and not to_remove:
        print("System matches system.toml. Nothing to do.")
        return
    print_diff(to_add, to_remove)


def next_generation():
    """Find the highest gen-N in /.snapshots and return N + 1."""
    numbers = []
    for name in os.listdir(SNAPSHOT_DIR):
        match = re.fullmatch(r"gen-(\d+)", name)
        if match:
            numbers.append(int(match.group(1)))
    return max(numbers, default=-1) + 1


def take_snapshot():
    gen = next_generation()
    path = f"{SNAPSHOT_DIR}/gen-{gen}"
    subprocess.run(["btrfs", "subvolume", "snapshot", "-r", "/", path],
                   check=True, stdout=subprocess.DEVNULL)
    return gen


def run(cmd):
    """Print a command, then run it. Raises an error if it fails."""
    print(f"\n>>> {' '.join(cmd)}")
    subprocess.run(cmd, check=True)


def apply():
    if os.geteuid() != 0:
        print("crest apply must be run as root (try: sudo crest apply)")
        sys.exit(1)

    to_add, to_remove = compute_diff()
    if not to_add and not to_remove:
        print("System matches system.toml. Nothing to do.")
        return

    print_diff(to_add, to_remove)
    answer = input("\nApply these changes? [y/N] ").strip().lower()
    if answer != "y":
        print("Aborted. Nothing was changed.")
        return

    gen = take_snapshot()
    print(f" * Snapshot taken: gen-{gen} (your undo point)")

    try:
        if to_add:
            run(["emerge", "--noreplace", "--verbose", *to_add])
        if to_remove:
            run(["emerge", "--deselect", *to_remove])
            run(["emerge", "--ask", "--depclean", *to_remove])
    except subprocess.CalledProcessError:
        print(f"\ncrest: emerge failed. Your system from before this apply is saved as gen-{gen}.")
        sys.exit(1)

    print("\n * Done.")


def clean():
    """Remove ALL orphaned packages system-wide, with a snapshot first."""
    if os.geteuid() != 0:
        print("crest clean must be run as root (try: sudo crest clean)")
        sys.exit(1)

    gen = take_snapshot()
    print(f" * Snapshot taken: gen-{gen} (your undo point)")
    run(["emerge", "--ask", "--depclean"])


def main():
    if len(sys.argv) < 2:
        print("usage: crest <command>\ncommands: diff, apply, clean")
        sys.exit(1)

    command = sys.argv[1]
    if command == "diff":
        diff()
    elif command == "apply":
        apply()
    elif command == "clean":
        clean()
    else:
        print(f"crest: unknown command '{command}'")
        sys.exit(1)


if __name__ == "__main__":
    main()
