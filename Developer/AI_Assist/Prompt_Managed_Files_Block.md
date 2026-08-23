# Fresh-session prompt: Managed Files block

I want to implement a new canonical native DGBlocks block for general-purpose managed external
files. Read the attached `Developer/AI_Assist/Summarized_Memory_Bank.md`, then inspect current
working reference blocks before planning or editing. Treat `unfinished_blocks/` as read-only.

Create this separately from `block_pip_library_manager`; do not merge pip/package management into
it. A suitable name is `block_managed_files`, with an FWC named `Wrapper_Managed_Files`.

## Purpose

Dependent blocks declare heavyweight or otherwise externally supplied files that should be copied
from a user-selected local path into an addon-controlled folder instead of being left in Downloads
or another arbitrary location. This is general-purpose and must not use neural-network-specific
naming.

## Required behavior

- Poll dependent blocks through a declaration hook and store live status in RTC.
- Provide `Managed_File_Declaration` with at least:
  - `resource_uid`
  - `display_name`
  - `description`
  - `allowed_file_extensions`
  - `max_file_size_bytes`
  - optional minimum size
  - single/multiple-file policy and maximum count
  - duplicate/replacement policy
  - optional expected SHA-256
- Offer FWC APIs to repoll, query one/all resource infos, test availability, retrieve managed paths,
  request import, request removal, and cancel an operation. Queries must read RTC, not BL mirrors.
- Use Blender's native file browser (`fileselect_add`) and generated extension filters. Revalidate
  every selected path after selection; the UI filter is not a security boundary.
- Store files under the existing addon data preference with addon scope, requesting-block scope,
  and resource UID scope. Sanitize and length-limit path components.
- Copy asynchronously in chunks so Blender remains responsive. Display a native progress popup
  with byte progress and recent log lines, backed by a persistent panel if the popup is closed.
- Worker threads must never touch `bpy`; marshal plain events through a queue to the main thread.
- Copy to staging, flush/close, validate, then atomically promote. Never delete the source before
  the managed copy is verified.
- Compute SHA-256 while copying. Verify `expected_sha256` when provided. Consider optional full
  destination re-read verification without forcing double I/O for every multi-gigabyte file.
- After success, explicitly prompt whether to keep or permanently delete the original. Keeping is
  the safe/default action. Python has no confirmed recycle-bin dependency, so do not imply trash
  behavior. Recheck existence, regular-file status, size/mtime, and hash before deletion.
- Refuse unsafe cases such as source=destination, source inside managed storage, addon files,
  Blender installation files, symlinks unless deliberately supported, traversal, special files,
  insufficient disk space, and changed source files.
- Persist sidecar metadata near managed files; do not persist machine-specific status in `.blend`.
  Rebuild RTC from declarations plus filesystem metadata during repoll. Avoid retaining the user's
  original full source path after the operation completes.
- Add a read-only BL status mirror only if useful for native UI. Filesystem/sidecar + RTC remain
  authoritative.
- Notify only the requesting block after availability, using a primitive `action_token`, rather
  than storing arbitrary continuation closures or Blender IDs.
- Log through block loggers, provide full disk logs, document APIs/security/lifecycle, and add
  tests for path safety, extension/size/count validation, hashing, staging, cancellation, and
  metadata recovery.

Begin with read-only inspection and an implementation plan, then implement and validate the block.
