#!/usr/bin/env python3
"""
new_worktree.py -- DGBlocks setup tool: task worktrees, block links, Blender profiles.

Lives at <checkout>/Developer/setup/ so every clone and every worktree carries it.
Layout it assumes (all siblings inside one <dev> folder; <dev> itself is NOT a git repo):

    <dev>/
      dgblocks/                     main DGBlocks checkout (any folder name works)
      dgblocks-<task>/              one git worktree per task, created by `new`
      block_<name>/                 one checkout per block repo (Flatypus, yours, ...)

Every DGBlocks checkout gets, inside it:
      external_blocks/block_<name>  -> link (junction on Windows, symlink elsewhere) to <dev>/block_<name>
      .blender-profile/             -> per-checkout Blender prefs + addon link, gitignored

Commands (run from anywhere; paths are derived from this file's location + git):
    new <task> [--from REF]     git worktree add <dev>/<main>-<task> on branch task/<task>, then link
    link [CHECKOUT]             (re)create block links + profile dirs (default: the checkout this file is in)
    list                        show worktrees, blocks, and link status
    remove <task> [--delete-branch] [--force]
                                unlink blocks, then git worktree remove

Runs on any Python 3.9+, or on Blender's bundled Python:
    blender -b --python Developer/setup/new_worktree.py -- new my-task
Stdlib only. git is the only external program. Full docs: README.md beside this file.
"""
from __future__ import annotations

import argparse
import os
import stat
import subprocess
import sys
from pathlib import Path

BLOCK_PREFIX = "block_"
MARKER = Path("addon_config") / "static_settings.py"      # "this is a DGBlocks checkout"
PROFILE_DIRS = ("config", "scripts/addons", "scripts/modules")


# ----------------------------------------------------------------------------- helpers
def die(msg: str) -> "NoReturn":
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def git(*args: str, cwd: Path | None = None, check: bool = True) -> str:
    proc = subprocess.run(["git", *args], cwd=str(cwd) if cwd else None,
                          capture_output=True, text=True)
    if check and proc.returncode != 0:
        die(f"git {' '.join(args)}\n{proc.stderr.strip()}")
    return proc.stdout


def is_dgblocks_checkout(path: Path) -> bool:
    return (path / MARKER).is_file()


def is_link(path: Path) -> bool:
    """True for a symlink or a Windows junction (Python < 3.12 reports junctions as plain dirs)."""
    if path.is_symlink():
        return True
    if os.name == "nt":
        try:
            attrs = os.lstat(path).st_file_attributes
        except (OSError, AttributeError):
            return False
        return bool(attrs & stat.FILE_ATTRIBUTE_REPARSE_POINT)
    return False


def same_target(link: Path, target: Path) -> bool:
    return Path(os.path.realpath(link)) == Path(os.path.realpath(target))


def make_link(link: Path, target: Path) -> None:
    if os.name == "nt":
        import _winapi                      # CPython on Windows; no admin / Developer Mode needed
        _winapi.CreateJunction(str(target), str(link))
    else:
        os.symlink(target, link, target_is_directory=True)


def block_repos(dev: Path) -> list[Path]:
    return sorted(p for p in dev.iterdir()
                  if p.is_dir() and p.name.startswith(BLOCK_PREFIX) and (p / "__init__.py").is_file())


def locate() -> tuple[Path, Path]:
    """(this checkout, main checkout). Works from the main checkout or any linked worktree."""
    here = Path(__file__).resolve().parents[2]          # Developer/setup/new_worktree.py -> checkout
    if not is_dgblocks_checkout(here):
        die(f"this script must live at <checkout>/Developer/setup/; {here} is not a DGBlocks checkout")
    common = Path(git("rev-parse", "--git-common-dir", cwd=here).strip())
    if not common.is_absolute():
        common = here / common
    return here, common.resolve().parent


# ----------------------------------------------------------------------------- commands
def cmd_link(dev: Path, checkout: Path) -> None:
    checkout = checkout.resolve()
    if not is_dgblocks_checkout(checkout):
        die(f"not a DGBlocks checkout (no {MARKER}): {checkout}")
    ext = checkout / "external_blocks"
    ext.mkdir(exist_ok=True)

    blocks = block_repos(dev)
    if not blocks:
        print(f"[!] no {BLOCK_PREFIX}* repos found in {dev} -- nothing to link")
    for repo in blocks:
        link = ext / repo.name
        if is_link(link):
            if same_target(link, repo):
                print(f"[=] {link.relative_to(checkout)} -> {repo}")
            else:
                print(f"[!] {link.relative_to(checkout)} points elsewhere "
                      f"({os.path.realpath(link)}); remove it and re-run")
            continue
        if link.exists():
            die(f"{link} is a real directory, not a link. A block must never be checked out "
                f"inside a DGBlocks checkout; move it to {dev / repo.name} and re-run.")
        make_link(link, repo)
        print(f"[+] {link.relative_to(checkout)} -> {repo}")

    profile = checkout / ".blender-profile"
    for sub in PROFILE_DIRS:
        (profile / sub).mkdir(parents=True, exist_ok=True)
    print(f"[+] {profile.relative_to(checkout)}/ ready (prefs + addon link live here, gitignored)")


def cmd_new(dev: Path, main: Path, task: str, base_ref: str | None) -> None:
    if any(c in task for c in '\\/:*?"<>| ') or task.startswith("."):
        die(f"task must be a plain folder-name fragment: {task!r}")
    path = dev / f"{main.name}-{task}"
    branch = f"task/{task}"
    if path.exists():
        die(f"{path} already exists")
    args = ["worktree", "add", str(path), "-b", branch]
    if base_ref:
        args.append(base_ref)
    git(*args, cwd=main)
    print(f"[+] worktree {path} on branch {branch}")
    cmd_link(dev, path)
    print(f"\nDone. Open {path} in a new VS Code window and run 'Blender: Start'.")


def cmd_list(dev: Path, main: Path) -> None:
    blocks = block_repos(dev)
    print(f"dev root : {dev}")
    print(f"main     : {main}")
    print(f"blocks   : {', '.join(b.name for b in blocks) or '(none)'}")
    print("checkouts:")
    porcelain = git("worktree", "list", "--porcelain", cwd=main)
    entries, cur = [], {}
    for line in porcelain.splitlines():
        if not line:
            if cur:
                entries.append(cur)
            cur = {}
        elif line.startswith("worktree "):
            cur["path"] = Path(line[9:])
        elif line.startswith("branch "):
            cur["branch"] = line[7:].replace("refs/heads/", "")
        elif line == "detached":
            cur["branch"] = "(detached)"
    if cur:
        entries.append(cur)
    for e in entries:
        path = e["path"]
        status = []
        for b in blocks:
            link = path / "external_blocks" / b.name
            status.append(f"{b.name}={'ok' if is_link(link) and same_target(link, b) else 'MISSING'}")
        profile = "profile" if (path / ".blender-profile").is_dir() else "no-profile"
        print(f"  {path}  [{e.get('branch', '?')}]  {profile}  {' '.join(status)}")


def cmd_remove(dev: Path, main: Path, task: str, delete_branch: bool, force: bool) -> None:
    path = dev / f"{main.name}-{task}"
    if not path.is_dir():
        die(f"no worktree at {path}")
    if path.resolve() == main.resolve():
        die("refusing to remove the main checkout")
    ext = path / "external_blocks"
    if ext.is_dir():
        for entry in ext.iterdir():
            if is_link(entry):
                os.rmdir(entry)          # removes the link only, never the target's contents
                print(f"[-] unlinked {entry.relative_to(path)}")
    args = ["worktree", "remove", str(path)]
    if force:
        args.append("--force")
    git(*args, cwd=main)
    print(f"[-] worktree {path} removed")
    if delete_branch:
        git("branch", "-d", f"task/{task}", cwd=main)       # -d, not -D: refuses unmerged work
        print(f"[-] branch task/{task} deleted")


# ----------------------------------------------------------------------------- main
def main(argv: list[str]) -> None:
    if "--" in argv:                     # invoked as: blender -b --python new_worktree.py -- <args>
        argv = argv[argv.index("--") + 1:]

    ap = argparse.ArgumentParser(prog="new_worktree.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dev", type=Path, help="dev root (default: parent folder of the main checkout)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("new", help="create a task worktree + links")
    p.add_argument("task")
    p.add_argument("--from", dest="base_ref", help="start branch from this ref (default: HEAD of main)")

    p = sub.add_parser("link", help="(re)create block links + profile dirs in a checkout")
    p.add_argument("checkout", nargs="?", type=Path, help="checkout path (default: the one this file is in)")

    sub.add_parser("list", help="show worktrees, blocks and link status")

    p = sub.add_parser("remove", help="unlink blocks and remove a task worktree")
    p.add_argument("task")
    p.add_argument("--delete-branch", action="store_true")
    p.add_argument("--force", action="store_true", help="remove even with uncommitted changes")

    ns = ap.parse_args(argv)
    here, main_checkout = locate()
    dev = (ns.dev or main_checkout.parent).resolve()

    if ns.cmd == "new":
        cmd_new(dev, main_checkout, ns.task, ns.base_ref)
    elif ns.cmd == "link":
        cmd_link(dev, ns.checkout or here)
    elif ns.cmd == "list":
        cmd_list(dev, main_checkout)
    elif ns.cmd == "remove":
        cmd_remove(dev, main_checkout, ns.task, ns.delete_branch, ns.force)


if __name__ == "__main__":
    main(sys.argv[1:])
