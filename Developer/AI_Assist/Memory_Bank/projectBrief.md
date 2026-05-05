# DGBlocks — Project Brief

> The "north star" doc. If something here changes, every other Memory Bank file
> may need updating. Keep it short. Keep it accurate.

---

## 1. What DGBlocks Is

DGBlocks is a **modular template for Blender addons**. Each feature lives inside
its own self-contained "block" (a Python package), and the main addon is little
more than an ordered list of which blocks to register.

The intent is roughly *"Lego for Blender addons"*:

- **Add a feature** → drop in a new block folder, append it to `_ordered_blocks_list`.
- **Remove a feature** → delete (or just comment out) the block. Other blocks keep working.
- **Share a feature across addons** → copy a block folder verbatim into another DGBlocks-based addon.

A block is *not* "a class" or "a Blender Operator". A block is a **complete
vertical slice** of one capability — its bpy types, its properties, its runtime
data, its loggers, its hook contracts, its UI, and its (un)registration logic.

---

## 2. Core Principles

1. **One block = one purpose.** Resist the urge to bundle.
2. **One-directional dependencies only.** If `block-A` depends on `block-B`,
   `block-B` must never import from `block-A`. Circular references break the
   modularity guarantee.
3. **Communication via hooks, not direct calls.** When `block-A` needs to
   notify other blocks of an event, it triggers a named hook. Subscribers
   implement a function with that name. Neither side knows the other exists at
   import time.
4. **Two-tier data: Blender owns truth, RTC mirrors it.** Persistent state
   lives in `bpy.props` PropertyGroups. Volatile/python-only state lives in the
   thread-safe Runtime Cache (RTC). Sync is explicit, in both directions.
5. **Stateless managers, stateful records.** Feature wrappers are
   classmethod-only "managers". Per-instance data lives in `@dataclass`
   "records" stored in the RTC. This makes breakpoints and console-prints
   readable.
6. **Standardize structure, not behavior.** Every block has the same file
   layout, the same registration shape, the same three enums. *What it does
   inside* is unconstrained.
7. **Hide the framework from end-users.** All this scaffolding should be
   invisible from the Blender UI. The user sees panels, properties, and
   operators — never blocks or wrappers.

---

## 3. Target Audience

- Blender addon developers who have outgrown "single `__init__.py` with
  everything in it" but don't want to invent a new architecture per project.
- Developers who maintain *several* addons and want to share components
  (logging, modal handling, draw handlers, library installers…) between them.
- Teams who want a structure that lets multiple devs work on different blocks
  in parallel without merge thrash.

This template is **not** aimed at users who only need a 50-line operator. It
buys you maintainability at the cost of a non-trivial up-front skeleton.

---

## 4. What Success Looks Like

- A new block can be authored from the existing patterns in **a few hours**,
  not a few days.
- Removing a block is a **one-line edit** to `my_activated_blocks.py` plus a
  folder delete — and nothing else breaks.
- The same block can be **dropped into a different DGBlocks-based addon**
  with no edits other than the block's own configuration.
- A bug report from a user can be diagnosed by **toggling one logger to DEBUG**
  and reading the console.

---

## 5. Out of Scope

- Distribution as a Blender Extension (the post-4.2 system). Possible later,
  not a current requirement.
- Serpens compatibility as a *first-class* feature. Integration is documented
  but manual.
- Multi-process or multi-Blender-instance coordination.
- Storing live `bpy.types.ID` references inside the RTC. Volatile Blender data
  must always be re-resolved by name/path before use.
