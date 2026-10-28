#!/usr/bin/env python3
"""crest: Rockhopper's declarative package manager (v0.3)."""

import os
import re
import subprocess
import sys
import tomllib

import portage
from portage.exception import InvalidAtom

CONFIG = "/etc/rockhopper/system.toml"
WORLD = "/var/lib/portage/world"
SNAPSHOT_DIR = "/.snapshots"

# Rockhopper palette, only used when printing to a real terminal
if sys.stdout.isatty():
    PINE = "\033[38;2;42;140;116m"
    PINE_LIGHT = "\033[38;2;79;184;156m"
    BEAK = "\033[38;2;232;105;46m"
    EYE = "\033[38;2;210;56;63m"
    RESET = "\033[0m"
else:
    PINE = PINE_LIGHT = BEAK = EYE = RESET = ""


def info(msg):
    print(f" {PINE_LIGHT}*{RESET} {msg}")


def warn(msg):
    print(f" {BEAK}!{RESET} {msg}")


def error(msg):
    print(f" {EYE}!!{RESET} {msg}")


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


def find_unknown(packages):
    """Return the packages Portage can't find (typos, removed, or masked)."""
    portdb = portage.db[portage.root]["porttree"].dbapi
    unknown = []
    for pkg in packages:
        try:
            if not portdb.match(pkg):
                unknown.append(pkg)
        except InvalidAtom:
            unknown.append(pkg)
    return unknown


def print_diff(to_add, to_remove):
    for pkg in to_add:
        print(f"  {PINE}+{RESET} {pkg}")
    for pkg in to_remove:
        print(f"  {EYE}-{RESET} {pkg}")
    print(f"\n{len(to_add)} to add, {len(to_remove)} to remove")


def report_unknown(unknown):
    print()
    for pkg in unknown:
        error(f"unknown or masked package: {pkg}")


def require_root(command):
    if os.geteuid() != 0:
        error(f"crest {command} must be run as root (try: sudo crest {command})")
        sys.exit(1)


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
    print(f"\n{PINE}>>>{RESET} {' '.join(cmd)}")
    subprocess.run(cmd, check=True)


def diff():
    to_add, to_remove = compute_diff()
    if not to_add and not to_remove:
        info("System matches system.toml. Nothing to do.")
        return
    print_diff(to_add, to_remove)
    unknown = find_unknown(to_add)
    if unknown:
        report_unknown(unknown)


def apply():
    require_root("apply")

    to_add, to_remove = compute_diff()
    if not to_add and not to_remove:
        info("System matches system.toml. Nothing to do.")
        return

    print_diff(to_add, to_remove)

    unknown = find_unknown(to_add)
    if unknown:
        report_unknown(unknown)
        error("Fix system.toml and try again. Nothing was changed.")
        sys.exit(1)

    answer = input("\nApply these changes? [y/N] ").strip().lower()
    if answer != "y":
        info("Aborted. Nothing was changed.")
        return

    gen = take_snapshot()
    info(f"Snapshot taken: gen-{gen} (your undo point)")

    try:
        if to_add:
            run(["emerge", "--noreplace", "--verbose", *to_add])
        if to_remove:
            run(["emerge", "--deselect", *to_remove])
            run(["emerge", "--ask", "--depclean", *to_remove])
    except subprocess.CalledProcessError:
        error(f"emerge failed. Your system from before this apply is saved as gen-{gen}.")
        sys.exit(1)

    info("Done.")


def clean():
    """Remove ALL orphaned packages system-wide, with a snapshot first."""
    require_root("clean")
    gen = take_snapshot()
    info(f"Snapshot taken: gen-{gen} (your undo point)")
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
        error(f"unknown command '{command}'")
        sys.exit(1)


if __name__ == "__main__":
    main()
