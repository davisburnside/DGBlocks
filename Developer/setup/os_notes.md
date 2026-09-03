# OS-specific notes

The procedure is the same everywhere; these are the places each OS can bite.

## All platforms

- **Cloud-synced folders are out.** OneDrive, iCloud Drive, Dropbox and Google Drive all
  corrupt or fight `.git` directories (file locks, partial syncs, conflict copies). Git is
  the backup; push to your origin.
- **Path length.** Block packages nest several folders deep. Keep `<dev>` short.
- **Line endings.** DGBlocks ships a `.gitattributes`; leave `core.autocrlf` at its default
  and let the attributes decide. Blender doesn't care either way.
- **Blender version.** The `bl_info` in `__init__.py` names the minimum. Each Blender
  version has its own user-resource tree, so a profile made for 5.0 is not seen by 5.1
  unless you point it there.

## Windows

- **Documents may secretly be OneDrive.** "Known Folder Move" redirects `Documents` into
  `OneDrive\Documents`. Check the real path of your Documents folder before putting `<dev>`
  there; if it's under OneDrive, use something like `C:\dev` instead.
- **Links are junctions.** The script creates directory junctions, which need no
  Administrator rights and no Developer Mode. Python's `os.path.islink` reports them as
  plain directories on Python < 3.12; the script checks the reparse attribute instead.
  Junction targets are absolute, so re-run `link` after moving `<dev>`.
- **260-character path limit.** Symptoms: git says "Filename too long", or a copy silently
  drops deep files. Keep `<dev>` short, and enable long paths:
  `git config --global core.longpaths true`, plus the *Enable Win32 long paths* group policy
  or the `LongPathsEnabled` registry value.
- **Case-insensitive filesystem.** Two files differing only in case can't coexist. Don't
  create them on another OS either.
- **Deleting checkouts.** `Remove-Item -Recurse` and Explorer both delete *through* a
  junction. Always `remove` with the script, or `rmdir` the links first.
- **Blender path** for the VS Code extension:
  `C:\Program Files\Blender Foundation\Blender <ver>\blender.exe`.
- **Python.** Any 3.9+ on PATH runs the script; Blender's own is at
  `<Blender install>\<ver>\python\bin\python.exe`, or use `blender -b --python ... -- <args>`.

## macOS

- **iCloud Drive** syncs `Desktop` and `Documents` when "Desktop & Documents Folders" is on.
  Put `<dev>` under `~/dev` or turn that option off.
- **Links are symlinks**, created without privileges. Deleting a checkout with `rm -rf`
  removes the symlink entry, not the target, so it's safe; the script still unlinks first.
- **Blender path**: `/Applications/Blender.app/Contents/MacOS/Blender`. The extension needs
  the binary inside the bundle, not the `.app`.
- **Gatekeeper**: first launch of a downloaded Blender must be approved once in the GUI.
- **Filesystem is case-insensitive by default** (APFS). Same caveat as Windows.

## Linux

- **Snap and Flatpak Blender are sandboxed.** They may not see `<dev>`, may ignore or
  restrict `BLENDER_USER_*` environment variables, and ship their own Python. Use the
  tarball from blender.org (or a distro package) for development.
- **Links are symlinks.** `rm -rf` on a checkout removes link entries, not targets.
- **Blender path**: wherever you unpacked it, e.g. `~/apps/blender-5.0/blender`.
- **Python**: system `python3` is fine for the script.

## Blender's default user-resource locations

For reference, where things go when nothing is redirected:

| OS | Path |
|---|---|
| Windows | `%APPDATA%\Blender Foundation\Blender\<ver>\` |
| macOS | `~/Library/Application Support/Blender/<ver>/` |
| Linux | `~/.config/blender/<ver>/` |

With the committed settings, only `config/` and `scripts/` are redirected into the
checkout's `.blender-profile/`; `extensions/` and `datafiles/` stay at these defaults.
