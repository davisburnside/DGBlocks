#!/usr/bin/env python3
"""Code topology cleaner - identify phase.

Scans a Python tree and reports what five cleanup passes *would* change.
Writes nothing. Standard library only.

    python topo.py                        # prompt Y/N per pass
    python topo.py --all --depth 3 src/
    python topo.py --yes A,D --json out.json src/
    python topo.py --selftest

Symbol IDs are "dotted.module::name". Only module-level defs are indexed.
Line numbers are not part of the ID - they change on every rewrite.
"""

from __future__ import annotations

import argparse
import ast
import io
import json
import os
import re
import sys
import tokenize
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path

FEATURES = {
    "A": "Unused functions and variables (N-depth call search)",
    "B": "Single-use annotations, stale marker cleanup",
    "C": "Trailing whitespace",
    "D": "Broken or stale imports",
    "E": "Circular imports",
}

SKIP_DIRS = {".git", ".venv", "venv", "env", "__pycache__", ".tox", ".nox",
             ".mypy_cache", ".pytest_cache", ".ruff_cache", "node_modules",
             "build", "dist", ".eggs", "site-packages"}

# Imports that are legitimately never referenced by name.
SIDE_EFFECT_MODULES = {"__future__", "readline", "rlcompleter", "site"}

# Decorators that register a symbol with a framework; the call site is
# invisible to static analysis, so the definition counts as reachable.
FRAMEWORK_DECOS = ("route", "get", "post", "put", "delete", "patch", "command",
                   "group", "fixture", "task", "hookimpl", "register",
                   "receiver", "app.", "click.", "typer.", "pytest.", "celery.",
                   "property", "overload", "singledispatch", "validator")

MARKER_RE = re.compile(r"^#\s*used[ _-]?by\s*:?\s*(.*)$", re.I)
KEEP_RE = re.compile(r"#\s*topo\s*:\s*keep\b", re.I)
IDENT_RE = re.compile(r"^[A-Za-z_]\w*(\.[A-Za-z_]\w*)*$")
DYNAMIC = {"getattr", "setattr", "globals", "locals", "vars", "eval", "exec",
           "__import__", "import_module"}

# Findings that describe a situation rather than a pending edit. They are
# reported but never counted in "N files would be modified".
REPORT_ONLY = {"beyond_depth", "live_entry_point", "cycle_deferred",
               "ws_in_string", "star_import", "package_reexport"}


# ---------------------------------------------------------------- records

@dataclass
class Sym:
    module: str
    name: str
    kind: str                      # function / class / variable
    line: int                      # first line, decorators included
    end_line: int
    decorators: list = field(default_factory=list)
    exported: bool = False         # in __all__
    conditional: bool = False      # defined inside if/try
    keep: bool = False             # marked `# topo: keep`

    @property
    def sid(self) -> str:
        return f"{self.module}::{self.name}"


@dataclass
class Imp:
    module: str                    # module containing the statement
    local: str                     # name bound here
    src_mod: str                   # module imported from
    src_name: str | None           # None for `import x` form
    level: int                     # relative-import dots
    line: int
    end_line: int
    scope: str                     # module / conditional / type_checking / function
    n_aliases: int
    raw: str
    resolved: str | None = None    # in-project dotted module, if any

    @property
    def is_from(self) -> bool:
        return self.src_name is not None


@dataclass
class Ref:
    """A use of a module-scope name, before cross-module resolution."""
    module: str
    root: str                      # name as bound in the referencing module
    attrs: tuple                   # dotted chain after the root
    line: int
    ctx: str                       # load / store / del
    inside: str | None             # enclosing module-level symbol id


@dataclass
class Mod:
    dotted: str
    path: Path
    is_pkg: bool
    syms: dict = field(default_factory=dict)
    imports: list = field(default_factory=list)
    refs: list = field(default_factory=list)
    markers: dict = field(default_factory=dict)   # name -> (line, raw, [claimed])
    all_names: list | None = None
    all_dynamic: bool = False
    star_import: bool = False
    dynamic_access: bool = False
    strings: list = field(default_factory=list)   # identifier-like literals
    main_block: tuple | None = None
    ws_lines: list = field(default_factory=list)
    string_lines: set = field(default_factory=set)
    n_lines: int = 0
    trailing_blanks: int = 0
    no_final_newline: bool = False
    error: str | None = None


@dataclass
class Finding:
    feature: str
    kind: str
    path: Path
    line: int
    msg: str
    conf: str = "high"             # high / medium / low
    sid: str | None = None
    data: dict = field(default_factory=dict)


# ---------------------------------------------------------------- discovery

def find_files(roots):
    """Yield (path, dotted_name, is_package) for every .py file under roots."""
    seen, out = set(), []
    for root in roots:
        root = Path(root)
        paths = [root] if root.is_file() else [
            Path(d) / f
            for d, dirs, files in os.walk(root)
            if not dirs.__setitem__(slice(None), [x for x in dirs if x not in SKIP_DIRS])
            for f in files if f.endswith(".py")
        ]
        for p in paths:
            p = p.resolve()
            if p.suffix != ".py" or p in seen:
                continue
            seen.add(p)
            # Walk up while the parent is still a package.
            base = p.parent
            while (base / "__init__.py").exists() and base.parent != base:
                base = base.parent
            parts = list(p.relative_to(base).parts)
            if parts[-1] == "__init__.py":
                parts.pop()
            else:
                parts[-1] = parts[-1][:-3]
            out.append((p, ".".join(parts) or base.name, p.name == "__init__.py"))
    return sorted(out)


# ---------------------------------------------------------------- collection

def target_names(node):
    """Names bound by an assignment target."""
    names, stack = [], [node]
    while stack:
        cur = stack.pop()
        if isinstance(cur, ast.Name):
            names.append(cur.id)
        elif isinstance(cur, (ast.Tuple, ast.List)):
            stack.extend(cur.elts)
        elif isinstance(cur, ast.Starred):
            stack.append(cur.value)
    return names


def bound_names(body):
    """Every name bound in this scope. Returns (bound, declared_global).

    Python scoping is whole-function, not sequential: a name assigned on the
    last line is local for the entire function. So this must run before the
    body is walked. Nested function/class bodies are skipped (own scope) but
    their names are bound here. Comprehension targets are excluded - they get
    their own scope, pushed by the walker.
    """
    bound, glob = set(), set()

    def visit(node):
        for c in ast.iter_child_nodes(node):
            if isinstance(c, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                bound.add(c.name)
                continue
            if isinstance(c, (ast.Lambda, ast.ListComp, ast.SetComp,
                              ast.DictComp, ast.GeneratorExp)):
                continue
            if isinstance(c, ast.Assign):
                for t in c.targets:
                    bound.update(target_names(t))
            elif isinstance(c, (ast.AnnAssign, ast.AugAssign, ast.NamedExpr)):
                bound.update(target_names(c.target))
            elif isinstance(c, (ast.For, ast.AsyncFor)):
                bound.update(target_names(c.target))
            elif isinstance(c, (ast.With, ast.AsyncWith)):
                for it in c.items:
                    if it.optional_vars is not None:
                        bound.update(target_names(it.optional_vars))
            elif isinstance(c, ast.ExceptHandler) and c.name:
                bound.add(c.name)
            elif isinstance(c, (ast.Import, ast.ImportFrom)):
                for a in c.names:
                    if a.name != "*":
                        bound.add(a.asname or a.name.split(".")[0])
            elif isinstance(c, (ast.Global, ast.Nonlocal)):
                glob.update(c.names)
            visit(c)

    for stmt in body:
        visit(ast.Module(body=[stmt], type_ignores=[]))
    return bound, glob


def is_type_checking(test):
    return (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or \
           (isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING")


def args_of(a):
    out = [*a.posonlyargs, *a.args, *a.kwonlyargs]
    if a.vararg:
        out.append(a.vararg)
    if a.kwarg:
        out.append(a.kwarg)
    return out


class Collector(ast.NodeVisitor):
    """Two passes over one module: definitions, then scope-aware references.

    A naive Name-node walk produces garbage, because a local variable called
    `config` is indistinguishable from a module-level `config`. So we keep a
    real scope stack and only emit a reference when the name resolves to
    module scope.
    """

    def __init__(self, mod, tree):
        self.m, self.tree = mod, tree
        self.modlevel = set()                # names visible at module scope
        self.scopes = []                     # [(bound, declared_global)]
        self.inside = [None]                 # enclosing module-level symbol
        self.tc_depth = 0

    # -- pass 1: definitions and module-level imports ---------------------

    def defs(self):
        self._defs(self.tree.body, False)
        self._read_all()
        self.modlevel = set(self.m.syms) | {i.local for i in self.m.imports}

    def _defs(self, body, cond):
        for s in body:
            if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._add(s.name, "function", s, cond, s.decorator_list)
            elif isinstance(s, ast.ClassDef):
                self._add(s.name, "class", s, cond, s.decorator_list)
            elif isinstance(s, ast.Assign):
                for t in s.targets:
                    for n in target_names(t):
                        self._add(n, "variable", s, cond)
            elif isinstance(s, ast.AnnAssign):
                for n in target_names(s.target):
                    self._add(n, "variable", s, cond)
            elif isinstance(s, (ast.Import, ast.ImportFrom)):
                self._imports(s, "type_checking" if self.tc_depth else
                              ("conditional" if cond else "module"))
            elif isinstance(s, (ast.If, ast.Try, ast.With, ast.AsyncWith,
                                ast.For, ast.While)):
                if isinstance(s, ast.If) and isinstance(s.test, ast.Compare) \
                        and isinstance(s.test.left, ast.Name) \
                        and s.test.left.id == "__name__":
                    self.m.main_block = (s.lineno, s.end_lineno or s.lineno)
                    self._defs(s.body, True)
                    continue
                # `if TYPE_CHECKING:` imports never execute, so they cannot
                # cause a runtime circular-import failure.
                if isinstance(s, ast.If) and is_type_checking(s.test):
                    self.tc_depth += 1
                    self._defs(s.body, True)
                    self.tc_depth -= 1
                    self._defs(s.orelse, True)
                    continue
                blocks = [s.body, getattr(s, "orelse", []) or [],
                          getattr(s, "finalbody", []) or []]
                blocks += [h.body for h in getattr(s, "handlers", []) or []]
                for b in blocks:
                    self._defs(b, True)

    def _add(self, name, kind, node, cond, decos=None):
        decos = decos or []
        src = [safe_unparse(d) for d in decos]
        first = min([node.lineno] + [d.lineno for d in decos])
        if name in self.m.syms:          # redefinition: widen the span
            prev = self.m.syms[name]
            prev.end_line = max(prev.end_line, node.end_lineno or node.lineno)
            prev.conditional = prev.conditional or cond
            return
        self.m.syms[name] = Sym(self.m.dotted, name, kind, first,
                                node.end_lineno or node.lineno, src,
                                conditional=cond)

    def _imports(self, s, scope):
        raw = safe_unparse(s)
        if isinstance(s, ast.Import):
            for i, a in enumerate(s.names):
                self.m.imports.append(Imp(
                    self.m.dotted, a.asname or a.name.split(".")[0], a.name,
                    None, 0, s.lineno, s.end_lineno or s.lineno, scope,
                    len(s.names), raw))
        else:
            for i, a in enumerate(s.names):
                if a.name == "*":
                    self.m.star_import = True
                self.m.imports.append(Imp(
                    self.m.dotted, "*" if a.name == "*" else (a.asname or a.name),
                    s.module or "", a.name, s.level or 0, s.lineno,
                    s.end_lineno or s.lineno, scope, len(s.names), raw))

    def _read_all(self):
        for s in self.tree.body:
            targets = (s.targets if isinstance(s, ast.Assign) else
                       [s.target] if isinstance(s, (ast.AnnAssign, ast.AugAssign)) else [])
            if not any(isinstance(t, ast.Name) and t.id == "__all__" for t in targets):
                continue
            v = getattr(s, "value", None)
            names = []
            if isinstance(v, (ast.List, ast.Tuple, ast.Set)):
                for e in v.elts:
                    if isinstance(e, ast.Constant) and isinstance(e.value, str):
                        names.append(e.value)
                    else:
                        self.m.all_dynamic = True
            else:
                self.m.all_dynamic = True
            self.m.all_names = (self.m.all_names or []) + names
        for n in self.m.all_names or []:
            if n in self.m.syms:
                self.m.syms[n].exported = True

    # -- pass 2: references ------------------------------------------------

    def refs(self):
        b, _ = bound_names(self.tree.body)
        self.modlevel |= b
        for s in self.tree.body:
            self.visit(s)

    def _local(self, name):
        for bound, glob in reversed(self.scopes):
            if name in glob:            # `global x` -> module scope
                return False
            if name in bound:
                return True
        return False

    def _emit(self, root, attrs, node, ctx):
        if root in DYNAMIC:
            self.m.dynamic_access = True
        if self._local(root) or root not in self.modlevel:
            return
        self.m.refs.append(Ref(self.m.dotted, root, tuple(attrs),
                               node.lineno, ctx, self.inside[-1]))

    def _scoped(self, node, bound, glob, name=None):
        top = not self.scopes and name in self.m.syms
        self.scopes.append((bound, glob))
        if top:
            self.inside.append(f"{self.m.dotted}::{name}")
        try:
            for s in node:
                self.visit(s)
        finally:
            self.scopes.pop()
            if top:
                self.inside.pop()

    def _func(self, node):
        for d in node.decorator_list:
            self.visit(d)
        for d in [*node.args.defaults, *[x for x in node.args.kw_defaults if x]]:
            self.visit(d)
        for a in args_of(node.args):
            if a.annotation is not None:
                self.visit(a.annotation)
        if node.returns is not None:
            self.visit(node.returns)
        bound, glob = bound_names(node.body)
        bound |= {a.arg for a in args_of(node.args)}
        self._scoped(node.body, bound, glob, node.name)

    visit_FunctionDef = visit_AsyncFunctionDef = _func

    def visit_ClassDef(self, node):
        for d in node.decorator_list:
            self.visit(d)
        for b in [*node.bases, *[k.value for k in node.keywords]]:
            self.visit(b)
        bound, glob = bound_names(node.body)
        self._scoped(node.body, bound, glob, node.name)

    def visit_Lambda(self, node):
        for d in [*node.args.defaults, *[x for x in node.args.kw_defaults if x]]:
            self.visit(d)
        self._scoped([node.body], {a.arg for a in args_of(node.args)}, set())

    def _comp(self, node):
        targets = set()
        for g in node.generators:
            targets.update(target_names(g.target))
        self.visit(node.generators[0].iter)   # evaluated in enclosing scope
        self.scopes.append((targets, set()))
        try:
            for i, g in enumerate(node.generators):
                if i:
                    self.visit(g.iter)
                for c in g.ifs:
                    self.visit(c)
            for part in ("elt", "key", "value"):
                sub = getattr(node, part, None)
                if sub is not None:
                    self.visit(sub)
        finally:
            self.scopes.pop()

    visit_ListComp = visit_SetComp = visit_DictComp = visit_GeneratorExp = _comp

    def visit_Name(self, node):
        ctx = ("store" if isinstance(node.ctx, ast.Store) else
               "del" if isinstance(node.ctx, ast.Del) else "load")
        self._emit(node.id, (), node, ctx)

    def visit_Attribute(self, node):
        attrs, cur = [], node
        while isinstance(cur, ast.Attribute):
            attrs.append(cur.attr)
            cur = cur.value
        if not isinstance(cur, ast.Name):
            return self.generic_visit(node)
        ctx = ("store" if isinstance(node.ctx, ast.Store) else
               "del" if isinstance(node.ctx, ast.Del) else "load")
        self._emit(cur.id, list(reversed(attrs)), node, ctx)

    def visit_Import(self, node):
        if self.scopes:                 # module-level ones came from pass 1
            self._imports(node, "type_checking" if self.tc_depth else "function")

    visit_ImportFrom = visit_Import

    def visit_If(self, node):
        if is_type_checking(node.test):
            self.tc_depth += 1
            for s in node.body:
                self.visit(s)
            self.tc_depth -= 1
            for s in node.orelse:
                self.visit(s)
            return
        self.generic_visit(node)

    def visit_Constant(self, node):
        if isinstance(node.value, str) and IDENT_RE.match(node.value):
            self.m.strings.append(node.value)


def safe_unparse(node):
    try:
        return ast.unparse(node)
    except Exception:
        return "<unparseable>"


def read_text_facts(m, src):
    """Comments, markers, and whitespace - things the AST throws away."""
    lines = src.splitlines()
    m.n_lines = len(lines)
    m.no_final_newline = bool(src) and not src.endswith("\n")
    comments = {}
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.COMMENT:
                if tok.line[:tok.start[1]].strip() == "":
                    comments[tok.start[0]] = tok.string
            elif tok.type == tokenize.STRING and tok.end[0] > tok.start[0]:
                m.string_lines.update(range(tok.start[0], tok.end[0] + 1))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        pass

    m.ws_lines = [i for i, ln in enumerate(lines, 1)
                  if ln.rstrip("\r") != ln.rstrip()]
    m.trailing_blanks = 0
    for ln in reversed(lines):
        if ln.strip():
            break
        m.trailing_blanks += 1

    # Attach `# Used by:` comments to the definition directly below.
    for sym in m.syms.values():
        line = sym.line - 1
        while line in comments:
            text = comments[line]
            if KEEP_RE.search(text):
                sym.keep = True
            mt = MARKER_RE.match(text.strip())
            if mt:
                claimed = [p.strip() for p in re.split(r"[,;]| and ", mt.group(1)) if p.strip()]
                m.markers[sym.name] = (line, text, claimed)
            line -= 1


def load_module(path, dotted, is_pkg):
    try:
        src = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        src = path.read_text(encoding="utf-8", errors="replace")
    m = Mod(dotted, path, is_pkg)
    try:
        tree = ast.parse(src, filename=str(path))
    except SyntaxError as e:
        m.error = f"{e.msg} (line {e.lineno})"
        read_text_facts(m, src)
        return m
    c = Collector(m, tree)
    c.defs()
    c.refs()
    read_text_facts(m, src)
    return m


# ---------------------------------------------------------------- index

class Index:
    def __init__(self, roots, entries=()):
        self.root = Path(roots[0]).resolve()
        if self.root.is_file():
            self.root = self.root.parent
        self.mods = {}
        for path, dotted, is_pkg in find_files(roots):
            self.mods[dotted] = load_module(path, dotted, is_pkg)

        self.syms = {s.sid: s for m in self.mods.values() for s in m.syms.values()}
        self.by_name = defaultdict(list)
        for sid, s in self.syms.items():
            self.by_name[s.name].append(sid)

        for m in self.mods.values():
            for i in m.imports:
                i.resolved = self.resolve_mod(i.src_mod, i.level, m.dotted)

        self.refs_to = defaultdict(list)      # sid -> [(from_mod, from_sid, line)]
        self.graph = defaultdict(set)         # sid -> sids it uses
        self.import_time = defaultdict(set)   # module -> sids used at import time
        self.unresolved = 0
        self._resolve_refs()

        self.edges = [(m.dotted, i.resolved, i.line,
                       i.scope in ("module", "conditional"), i.raw)
                      for m in self.mods.values() for i in m.imports
                      if i.resolved and i.resolved != m.dotted]

        self.soft = defaultdict(list)         # sid -> modules naming it in a string
        for m in self.mods.values():
            for lit in m.strings:
                for sid in self.by_name.get(lit.rsplit(".", 1)[-1], []):
                    self.soft[sid].append(m.dotted)

        self.entries = set()
        self._find_entries(entries)

    # -- module resolution -------------------------------------------------

    def resolve_mod(self, name, level, current):
        if level:
            parts = current.split(".")
            m = self.mods.get(current)
            base = parts if (m and m.is_pkg) else parts[:-1]
            up = level - 1
            if up:
                base = base[:-up] if up <= len(base) else []
            target = ".".join([p for p in base if p] + ([name] if name else []))
        else:
            target = name
        if not target:
            return None
        if target in self.mods:
            return target
        return next((c for c in self.mods if c.endswith("." + target)), None)

    # -- reference resolution ----------------------------------------------

    def _resolve_refs(self):
        for m in self.mods.values():
            binds = {}
            for i in m.imports:
                if i.local != "*":
                    binds.setdefault(i.local, i)
            for r in m.refs:
                target = self._resolve(m, binds, r)
                if target is None:
                    self.unresolved += 1
                    continue
                # `CONFIG = {}` at module level binds the symbol - that is its
                # definition, not a use. Without this every module-level
                # variable looks self-referential and never appears unused.
                # A store from another module, or via `global`, is a real use.
                if r.ctx in ("store", "del") and r.inside is None \
                        and target.split("::")[0] == m.dotted:
                    continue
                self.refs_to[target].append((m.dotted, r.inside, r.line))
                if r.inside:
                    if r.inside != target:
                        self.graph[r.inside].add(target)
                else:
                    self.import_time[m.dotted].add(target)

    def _resolve(self, m, binds, r):
        if r.root in m.syms:                       # defined in this module
            return f"{m.dotted}::{r.root}"
        b = binds.get(r.root)
        if b is None:
            return None
        if b.is_from:
            if not b.resolved:
                return None
            name = b.src_name or b.local
            sid = f"{b.resolved}::{name}"
            if sid in self.syms:
                return sid
            sub = f"{b.resolved}.{name}"           # `from pkg import submodule`
            if sub in self.mods and r.attrs:
                nested = f"{sub}::{r.attrs[0]}"
                if nested in self.syms:
                    return nested
            return self.reexport(b.resolved, name)
        # `import a.b` binds `a`; `import a.b as c` binds `c`.
        head = b.src_mod if b.local != b.src_mod.split(".")[0] else b.src_mod.split(".")[0]
        chain = [head, *r.attrs]
        for i in range(len(chain) - 1, 0, -1):
            mod = self.resolve_mod(".".join(chain[:i]), 0, m.dotted)
            if not mod:
                continue
            sid = f"{mod}::{chain[i]}"
            if sid in self.syms:
                return sid
            hit = self.reexport(mod, chain[i])
            if hit:
                return hit
        return None

    def reexport(self, mod, name, depth=0):
        """`pkg/__init__.py` doing `from .impl import foo` re-exports impl::foo."""
        if depth > 4 or mod not in self.mods:
            return None
        for i in self.mods[mod].imports:
            if i.local == name and i.is_from and i.resolved:
                sid = f"{i.resolved}::{i.src_name or name}"
                return sid if sid in self.syms else \
                    self.reexport(i.resolved, i.src_name or name, depth + 1)
        return None

    # -- entry points ------------------------------------------------------

    def _find_entries(self, extra):
        self.entries.update(e for e in extra if e in self.syms)
        for m in self.mods.values():
            for name in m.all_names or []:
                sid = f"{m.dotted}::{name}"
                if sid in self.syms:
                    self.entries.add(sid)
                    continue
                # A package __init__ usually re-exports rather than defines.
                t = self.reexport(m.dotted, name)
                if t:
                    self.entries.add(t)
                    line = next((i.line for i in m.imports if i.local == name), 1)
                    self.refs_to[t].append((m.dotted, None, line))
                    self.import_time[m.dotted].add(t)
            if m.main_block:
                lo, hi = m.main_block
                for sid, uses in self.refs_to.items():
                    if any(u[0] == m.dotted and lo <= u[2] <= hi for u in uses):
                        self.entries.add(sid)

    # -- queries -----------------------------------------------------------

    def users(self, sid):
        """External references, excluding the symbol's own recursion."""
        return [u for u in self.refs_to.get(sid, []) if u[1] != sid]

    def user_mods(self, sid):
        return {u[0] for u in self.users(sid)}

    def path(self, mod):
        return self.mods[mod].path


# ---------------------------------------------------------------- passes

def roots_of(idx):
    """Symbols that are alive by definition, not by being called."""
    r = set(idx.entries)
    for m in idx.mods.values():
        r |= idx.import_time.get(m.dotted, set())   # import-time code always runs
        for s in m.syms.values():
            if s.keep or s.name.startswith(("test_", "Test")) \
                    or s.name in ("main", "setup", "app") \
                    or (s.name.startswith("__") and s.name.endswith("__")) \
                    or any(d in dec.lower() for dec in s.decorators for d in FRAMEWORK_DECOS):
                r.add(s.sid)
    return r


def why_root(idx, s):
    if s.exported:
        return "listed in __all__"
    if s.keep:
        return "marked `# topo: keep`"
    if s.sid in idx.entries:
        return "declared entry point"
    if s.name.startswith(("test_", "Test")):
        return "test naming convention"
    if s.decorators:
        return f"registered via @{s.decorators[0]}"
    return "conventional entry-point name"


def confidence(idx, s):
    """Reasons a deletion might be wrong. Anything found downgrades it."""
    notes, conf = [], "high"
    m = idx.mods[s.module]
    if idx.soft.get(s.sid):
        notes.append(f"name appears as a string literal in {idx.soft[s.sid][0]}")
        conf = "low"
    if any(x.star_import for x in idx.mods.values()):
        notes.append("project uses `import *`, some uses are invisible")
        conf = "low" if conf == "low" else "medium"
    if m.all_dynamic:
        notes.append(f"{m.dotted} builds __all__ dynamically")
        conf = "low"
    if m.dynamic_access:
        notes.append(f"{m.dotted} uses getattr/globals/eval")
        conf = "medium" if conf == "high" else conf
    if s.decorators:
        notes.append(f"decorated with {', '.join(s.decorators)}")
        conf = "medium" if conf == "high" else conf
    if s.conditional:
        notes.append("defined conditionally")
        conf = "medium" if conf == "high" else conf
    return conf, notes


def pass_a(idx, depth=-1):
    """Unused symbols. Two separate questions, both reported:
    is anything referencing this, and is it reachable within N hops.
    """
    out, roots = [], roots_of(idx)

    def reach(limit):
        dist = {r: 0 for r in roots}
        q = deque(roots)
        while q:
            cur = q.popleft()
            if limit >= 0 and dist[cur] >= limit:
                continue
            for nxt in idx.graph.get(cur, ()):
                if nxt not in dist:
                    dist[nxt] = dist[cur] + 1
                    q.append(nxt)
        return dist

    dist = reach(depth)
    for sid, s in sorted(idx.syms.items()):
        if s.keep or (s.name.startswith("__") and s.name.endswith("__")):
            continue
        users = idx.users(sid)
        if users and sid in dist:
            continue
        if sid in roots and not users:
            # Live by definition - a test, a CLI target, an __all__ export.
            # Report it so a library author can see it; never delete it.
            out.append(Finding("A", "live_entry_point", idx.path(s.module), s.line,
                               f"{s.kind} `{s.name}` has no in-tree callers but is an "
                               f"entry point ({why_root(idx, s)}) - kept", "low", sid))
            continue
        conf, notes = confidence(idx, s)
        if not users:
            msg = f"{s.kind} `{s.name}` is never referenced anywhere in the scanned tree"
            kind = "never_referenced"
        else:
            who = sorted({u[1] or u[0] for u in users})[:3]
            msg = f"{s.kind} `{s.name}` is only referenced by unreachable code ({', '.join(who)})"
            kind = "unreachable"
            conf = "medium" if conf == "high" else conf
        out.append(Finding("A", kind, idx.path(s.module), s.line, msg, conf, sid,
                           {"delete_span": [s.line, s.end_line], "notes": notes,
                            "users": sorted(idx.user_mods(sid))}))

    # Without this pairing, a shallow --depth silently looks like dead code.
    if depth >= 0:
        full = reach(-1)
        for sid in sorted(set(full) - set(dist)):
            s = idx.syms[sid]
            out.append(Finding("A", "beyond_depth", idx.path(s.module), s.line,
                               f"`{s.name}` is live but more than {depth} call(s) from "
                               f"an entry point (reached at depth {full[sid]})",
                               "high", sid, {"actual_depth": full[sid]}))
    return out


def pass_b(idx):
    """Single-use annotations, and markers that no longer match reality."""
    out = []
    for mod, m in sorted(idx.mods.items()):
        for name, s in sorted(m.syms.items()):
            actual = sorted(idx.user_mods(s.sid) - {mod})
            marker = m.markers.get(name)
            if marker is None:
                if len(actual) == 1 and not name.startswith("__"):
                    out.append(Finding("B", "missing_marker", m.path, s.line,
                                       f"`{name}` has exactly one external user - "
                                       f"annotate `# Used by: {actual[0]}`", "high", s.sid,
                                       {"insert_line": s.line,
                                        "comment": f"# Used by: {actual[0]}"}))
                continue
            line, raw, claimed = marker
            claimed = sorted(claimed)
            if not actual:
                out.append(Finding("B", "stale_marker", m.path, line,
                                   f"`{name}` claims `Used by {', '.join(claimed)}` but "
                                   f"nothing outside {mod} references it", "medium", s.sid,
                                   {"delete_line": line}))
            elif claimed != actual:
                out.append(Finding("B", "wrong_marker", m.path, line,
                                   f"`{name}` claims `Used by {', '.join(claimed)}` but "
                                   f"actual users are {', '.join(actual)}", "high", s.sid,
                                   {"replace_line": line, "old": raw,
                                    "new": f"# Used by: {', '.join(actual)}"}))
    return out


def pass_c(idx):
    out = []
    for mod, m in sorted(idx.mods.items()):
        safe = [n for n in m.ws_lines if n not in m.string_lines]
        risky = [n for n in m.ws_lines if n in m.string_lines]
        if safe:
            out.append(Finding("C", "trailing_ws", m.path, safe[0],
                               f"{len(safe)} line(s) with trailing whitespace",
                               "high", None, {"lines": safe}))
        if risky:
            out.append(Finding("C", "ws_in_string", m.path, risky[0],
                               f"{len(risky)} line(s) with trailing whitespace inside a "
                               "multi-line string - stripping would change the value",
                               "low", None, {"lines": risky}))
        if m.trailing_blanks > 1:
            out.append(Finding("C", "trailing_blanks", m.path,
                               m.n_lines - m.trailing_blanks + 1,
                               f"{m.trailing_blanks} blank lines at end of file",
                               "high", None, {"count": m.trailing_blanks}))
        if m.no_final_newline:
            out.append(Finding("C", "no_final_newline", m.path, max(m.n_lines, 1),
                               "file does not end with a newline"))
    return out


def pass_d(idx):
    out = []
    for mod, m in sorted(idx.mods.items()):
        used = {r.root for r in m.refs}
        seen = {}
        for b in m.imports:
            if b.local == "*":
                out.append(Finding("D", "star_import", m.path, b.line,
                                   f"`{b.raw}` hides which names are used",
                                   "medium", None, {}))
                continue

            # name no longer lives where the import says it does
            if b.is_from and b.resolved:
                name = b.src_name or b.local
                sid = f"{b.resolved}::{name}"
                if sid not in idx.syms and f"{b.resolved}.{name}" not in idx.mods \
                        and not idx.reexport(b.resolved, name):
                    cands = [c for c in idx.by_name.get(name, [])
                             if c.split("::")[0] != b.resolved]
                    new_mod = cands[0].split("::")[0] if len(cands) == 1 else None
                    out.append(Finding(
                        "D", "moved_symbol" if cands else "missing_symbol",
                        m.path, b.line,
                        f"`{name}` is not defined in {b.resolved}" +
                        (f"; found in {', '.join(cands[:3])}" if cands else ""),
                        "high" if len(cands) == 1 else "medium", None,
                        {"raw": b.raw, "candidates": cands, "n_aliases": b.n_aliases,
                         "rewrite": f"from {new_mod} import {name}" if new_mod else None}))
            elif b.resolved is None and (b.level or looks_internal(idx, b.src_mod)):
                out.append(Finding("D", "unresolvable", m.path, b.line,
                                   f"cannot resolve module `{'.' * b.level}{b.src_mod}`",
                                   "medium", None, {"raw": b.raw}))

            # unused import
            exempt = (b.src_mod.split(".")[0] in SIDE_EFFECT_MODULES
                      or (m.all_names and b.local in m.all_names)
                      or (b.is_from and b.local == b.src_name and " as " in b.raw))
            if b.local not in used and b.scope in ("module", "conditional") and not exempt:
                in_str = b.local in m.strings
                if m.is_pkg:
                    out.append(Finding("D", "package_reexport", m.path, b.line,
                                       f"`{b.local}` is unused in {mod}, but this is a "
                                       "package __init__ - may be a deliberate re-export",
                                       "low", None, {"raw": b.raw}))
                else:
                    out.append(Finding("D", "unused_import", m.path, b.line,
                                       f"`{b.local}` is imported but never used in {mod}",
                                       "low" if (m.star_import or in_str) else "high", None,
                                       {"raw": b.raw, "local": b.local,
                                        "n_aliases": b.n_aliases}))

            # duplicate binding. `import a.b` and `import a.c` both bind `a`;
            # that is how submodule imports work, not a duplicate.
            binds_pkg = not b.is_from and "." in b.src_mod \
                and b.local == b.src_mod.split(".")[0]
            prev = seen.get(b.local)
            if prev and b.scope in ("module", "conditional") and not binds_pkg:
                pline, psrc = prev
                related = psrc.startswith(b.src_mod + ".") or b.src_mod.startswith(psrc + ".")
                if not related:
                    out.append(Finding("D", "duplicate_import", m.path, b.line,
                                       f"`{b.local}` was already bound on line {pline}",
                                       "high", None, {"first_line": pline, "raw": b.raw}))
            seen.setdefault(b.local, (b.line, b.src_mod))
    return out


def looks_internal(idx, dotted):
    if not dotted:
        return True
    top = dotted.split(".")[0]
    if top in getattr(sys, "stdlib_module_names", ()):
        return False
    return any(m == top or m.startswith(top + ".") for m in idx.mods)


def pass_e(idx):
    """A cycle only breaks at runtime if every edge executes at import time."""
    def adjacency(runtime_only):
        adj = {m: set() for m in idx.mods}
        for src, dst, _, runtime, _ in idx.edges:
            if runtime_only and not runtime:
                continue
            adj[src].add(dst)
        return adj

    def sccs(adj):
        """Iterative Tarjan."""
        idx_of, low, on, stack, out, counter = {}, {}, {}, [], [], 0
        for start in adj:
            if start in idx_of:
                continue
            idx_of[start] = low[start] = counter
            counter += 1
            stack.append(start)
            on[start] = True
            work = [(start, iter(sorted(adj[start])))]
            while work:
                node, kids = work[-1]
                pushed = False
                for k in kids:
                    if k not in adj:
                        continue
                    if k not in idx_of:
                        idx_of[k] = low[k] = counter
                        counter += 1
                        stack.append(k)
                        on[k] = True
                        work.append((k, iter(sorted(adj[k]))))
                        pushed = True
                        break
                    if on.get(k):
                        low[node] = min(low[node], idx_of[k])
                if pushed:
                    continue
                work.pop()
                if work:
                    low[work[-1][0]] = min(low[work[-1][0]], low[node])
                if low[node] == idx_of[node]:
                    comp = []
                    while True:
                        w = stack.pop()
                        on[w] = False
                        comp.append(w)
                        if w == node:
                            break
                    if len(comp) > 1 or node in adj[node]:
                        out.append(sorted(comp))
        return out

    def shortest(adj, comp):
        """A concrete cycle path through the component, for the message."""
        best = None
        for start in sorted(comp):
            prev, q, seen, hit = {}, deque([start]), {start}, None
            while q and hit is None:
                cur = q.popleft()
                for nxt in sorted(adj[cur]):
                    if nxt not in comp:
                        continue
                    if nxt == start:
                        hit = cur
                        break
                    if nxt not in seen:
                        seen.add(nxt)
                        prev[nxt] = cur
                        q.append(nxt)
            if hit is not None:
                chain, node = [], hit
                while node != start:
                    chain.append(node)
                    node = prev[node]
                path = [start, *reversed(chain), start]
                if best is None or len(path) < len(best):
                    best = path
        return best or sorted(comp)

    full, runtime = adjacency(False), adjacency(True)
    fatal_comps = {frozenset(c) for c in sccs(runtime)}
    out = []
    for comp in sccs(full):
        cs = set(comp)
        cycle = shortest(full, cs)
        fatal = any(frozenset(comp) <= f for f in fatal_comps)
        edges = [{"from": a, "to": b, "line": ln, "runtime": rt, "raw": raw}
                 for a, b in zip(cycle, cycle[1:])
                 for s, d, ln, rt, raw in idx.edges if (s, d) == (a, b)]
        anchor_line = next((e["line"] for e in edges if e["from"] == cycle[0]), 1)
        out.append(Finding(
            "E", "cycle_fatal" if fatal else "cycle_deferred",
            idx.path(cycle[0]), anchor_line,
            ("import-time cycle: " if fatal else "cycle broken by deferred imports: ")
            + " -> ".join(cycle),
            "high" if fatal else "medium", None,
            {"cycle": cycle, "edges": edges,
             "fix": "move one edge into a function or under TYPE_CHECKING"
                    if fatal else "already deferred, no runtime failure"}))
    for src, dst, line, _, raw in idx.edges:
        if src == dst:
            out.append(Finding("E", "self_import", idx.path(src), line,
                               f"{src} imports itself", "high", None, {"raw": raw}))
    return out


PASSES = {"A": lambda i, d: pass_a(i, d), "B": lambda i, d: pass_b(i),
          "C": lambda i, d: pass_c(i), "D": lambda i, d: pass_d(i),
          "E": lambda i, d: pass_e(i)}


# ---------------------------------------------------------------- output

MARK = {"high": "!", "medium": "~", "low": "?"}


def report(idx, results, depth, limit):
    for f in sorted(results):
        found = results[f]
        if not found:
            continue
        print(f"\n=== [{f}] {FEATURES[f]} " + "=" * 8)
        grouped = defaultdict(list)
        for x in found:
            grouped[x.path].append(x)
        shown = 0
        for path in sorted(grouped):
            print(f"\n  {rel(path, idx.root)}")
            for x in sorted(grouped[path], key=lambda y: y.line):
                if shown >= limit:
                    print(f"    ... {len(found) - shown} more")
                    break
                print(f"    {MARK[x.conf]} {x.line:>5}  {x.msg}")
                for n in x.data.get("notes", []):
                    print(f"           note: {n}")
                if x.data.get("rewrite"):
                    print(f"           fix:  {x.data['rewrite']}")
                if x.data.get("comment"):
                    print(f"           add:  {x.data['comment']}")
                shown += 1
            if shown >= limit:
                break
    print("\n  legend: ! high confidence   ~ medium   ? low (review manually)")


def preflight(idx, results):
    """The 'before actually running' summary. Report-only kinds are excluded,
    so the file count means exactly what it says."""
    touched = set()
    print("\nPRE-FLIGHT SUMMARY")
    print("-" * 62)
    print(f"  Scanned    {len(idx.mods)} modules, {len(idx.syms)} module-level symbols")
    print(f"  Resolved   {sum(len(v) for v in idx.refs_to.values())} references "
          f"({idx.unresolved} external/unresolved)")
    errors = [(m.dotted, m.error) for m in idx.mods.values() if m.error]
    if errors:
        print(f"  Skipped    {len(errors)} file(s) with syntax errors")
    print()
    for f in sorted(results):
        found = results[f]
        print(f"  [{f}] {FEATURES[f]}")
        if not found:
            print("        nothing found")
            continue
        edits = [x for x in found if x.kind not in REPORT_ONLY]
        files = {x.path for x in edits}
        touched |= files
        conf = Counter(x.conf for x in found)
        print(f"        {len(edits)} pending edit(s) across {len(files)} file(s)   "
              f"[{', '.join(f'{n} {k}' for k, n in conf.most_common())}]")
        for kind, n in Counter(x.kind for x in found).most_common():
            tag = " (report only)" if kind in REPORT_ONLY else ""
            print(f"          - {kind}: {n}{tag}")
    print("\n" + "-" * 62)
    print(f"  TOTAL: {len(touched)} file(s) would be modified.\n")
    for mod, err in errors:
        print(f"  syntax error, skipped: {mod}: {err}")
    return touched


def rel(path, root):
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def to_json(idx, results):
    return {
        "root": str(idx.root),
        "modules": len(idx.mods), "symbols": len(idx.syms),
        "features": {f: [{"kind": x.kind, "path": str(x.path), "line": x.line,
                          "symbol": x.sid, "confidence": x.conf, "message": x.msg,
                          "edit": x.kind not in REPORT_ONLY, "data": x.data}
                         for x in found]
                     for f, found in results.items()},
    }


def ask(q, default=True):
    while True:
        try:
            a = input(f"{q} {'[Y/n]' if default else '[y/N]'} ").strip().lower()
        except EOFError:
            return default
        if not a:
            return default
        if a in ("y", "yes"):
            return True
        if a in ("n", "no"):
            return False


# ---------------------------------------------------------------- selftest

def selftest():
    import tempfile
    import textwrap
    cases = []

    def case(fn):
        cases.append(fn)
        return fn

    def build(td, files, entries=()):
        for name, body in files.items():
            p = Path(td) / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(textwrap.dedent(body).lstrip("\n"))
        return Index([Path(td)], entries)

    def kinds(fs):
        return {x.kind for x in fs}

    def names(fs):
        return {x.sid.split("::")[1] for x in fs if x.sid}

    @case
    def local_var_is_not_a_use(td):
        # The classic false positive: a local shadowing a module-level name.
        i = build(td, {"m.py": """
            CONFIG = {}
            def unrelated():
                CONFIG = compute()
                return CONFIG
            def compute(): return 1
        """})
        assert "CONFIG" in names(pass_a(i)), "module var wrongly considered used"

    @case
    def global_decl_is_a_use(td):
        i = build(td, {"m.py": """
            __all__ = ["bump"]
            COUNTER = 0
            def bump():
                global COUNTER
                COUNTER += 1
        """})
        assert "COUNTER" not in names(pass_a(i))

    @case
    def comprehension_has_own_scope(td):
        i = build(td, {"m.py": """
            __all__ = ["run"]
            ITEMS = [1]
            def run():
                data = [ITEMS for ITEMS in range(3)]
                return data, ITEMS
        """})
        assert "ITEMS" not in names(pass_a(i))

    @case
    def depth_separates_dead_from_distant(td):
        i = build(td, {"m.py": """
            def a(): return b()
            def b(): return c()
            def c(): return 1
            if __name__ == "__main__":
                a()
        """})
        assert not names(pass_a(i, -1))
        assert "beyond_depth" in kinds(pass_a(i, 1))

    @case
    def reexport_through_all_is_an_entry(td):
        i = build(td, {"pkg/__init__.py": 'from .impl import public\n__all__ = ["public"]',
                       "pkg/impl.py": "def public(): pass"})
        assert "never_referenced" not in kinds(pass_a(i))

    @case
    def entry_points_are_never_deleted(td):
        i = build(td, {"m.py": "def test_thing(): pass"})
        f = [x for x in pass_a(i) if x.sid.endswith("test_thing")]
        assert f and f[0].kind == "live_entry_point"

    @case
    def dynamic_access_lowers_confidence(td):
        i = build(td, {"m.py": """
            def handler_x(): pass
            def go(): return getattr(None, "handler_x")
        """})
        f = [x for x in pass_a(i) if x.sid.endswith("handler_x")]
        assert f and f[0].conf == "low"

    @case
    def markers_stale_and_missing(td):
        i = build(td, {"pkg/__init__.py": "",
                       "pkg/a.py": """
                           # Used by: pkg.wrong
                           def target(): pass
                           def plain(): pass
                       """,
                       "pkg/b.py": "from pkg.a import target, plain\nx = target()\ny = plain()"})
        by = {x.sid.split("::")[1]: x for x in pass_b(i)}
        assert by["target"].kind == "wrong_marker"
        assert by["target"].data["new"] == "# Used by: pkg.b"
        assert by["plain"].kind == "missing_marker"

    @case
    def accurate_marker_is_left_alone(td):
        i = build(td, {"pkg/__init__.py": "",
                       "pkg/a.py": """
                           import functools
                           # Used by: pkg.b
                           @functools.cache
                           def target(): pass
                       """,
                       "pkg/b.py": "from pkg.a import target\nv = target()"})
        assert not [x for x in pass_b(i) if x.sid.endswith("target")]

    @case
    def whitespace_in_docstring_is_separate(td):
        i = build(td, {"m.py": 'x = 1   \n\ndef f():\n    """line   \n    more\n    """\n'})
        assert {"trailing_ws", "ws_in_string"} <= kinds(pass_c(i))

    @case
    def detects_moved_symbol(td):
        i = build(td, {"pkg/__init__.py": "", "pkg/old.py": "P = 1",
                       "pkg/new.py": "def moved(): pass",
                       "pkg/user.py": "from pkg.old import moved\nv = moved()"})
        f = [x for x in pass_d(i) if x.kind == "moved_symbol"]
        assert f and f[0].data["rewrite"] == "from pkg.new import moved"

    @case
    def future_import_is_never_unused(td):
        i = build(td, {"m.py": "from __future__ import annotations\ndef f() -> int: return 1\n"})
        assert "unused_import" not in kinds(pass_d(i))

    @case
    def submodule_imports_are_not_duplicates(td):
        i = build(td, {"pkg/__init__.py": "", "pkg/a.py": "", "pkg/b.py": "",
                       "m.py": "import pkg.a\nimport pkg.b\nx = pkg.a\ny = pkg.b\n"})
        assert "duplicate_import" not in kinds(pass_d(i))

    @case
    def annotation_counts_as_import_use(td):
        i = build(td, {"pkg/__init__.py": "", "pkg/t.py": "class Thing: pass",
                       "pkg/u.py": "from pkg.t import Thing\ndef f(x: Thing) -> Thing: return x\n"})
        assert "unused_import" not in kinds(pass_d(i))

    @case
    def fatal_vs_deferred_cycles(td):
        i = build(td, {"pkg/__init__.py": "", "pkg/a.py": "from pkg.b import B\nA = 1",
                       "pkg/b.py": "from pkg.a import A\nB = 2"})
        assert "cycle_fatal" in kinds(pass_e(i))

    @case
    def deferred_cycle_is_not_fatal(td):
        i = build(td, {"pkg/__init__.py": "", "pkg/a.py": "from pkg.b import B\nA = 1",
                       "pkg/b.py": "B = 2\ndef late():\n    from pkg.a import A\n    return A\n"})
        f = pass_e(i)
        assert "cycle_deferred" in kinds(f)
        assert f[0].data["cycle"][0] == f[0].data["cycle"][-1]

    @case
    def type_checking_cycle_is_not_fatal(td):
        i = build(td, {"pkg/__init__.py": "", "pkg/a.py": "from pkg.b import B\nA = 1",
                       "pkg/b.py": """
                           from typing import TYPE_CHECKING
                           if TYPE_CHECKING:
                               from pkg.a import A
                           B = 2
                       """})
        assert "cycle_fatal" not in kinds(pass_e(i))

    @case
    def syntax_error_is_recorded_not_raised(td):
        i = build(td, {"broken.py": "def f(:\n    pass\n"})
        assert i.mods["broken"].error
        for p in (pass_a, pass_b, pass_c, pass_d, pass_e):
            p(i)

    failed = 0
    for fn in cases:
        with tempfile.TemporaryDirectory() as td:
            try:
                fn(td)
                print(f"  PASS  {fn.__name__}")
            except Exception as e:
                failed += 1
                print(f"  FAIL  {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(cases) - failed}/{len(cases)} passed")
    return 1 if failed else 0


# ---------------------------------------------------------------- cli

def main(argv=None):
    p = argparse.ArgumentParser(description="Code topology cleaner (identify phase)")
    p.add_argument("paths", nargs="*", default=["."])
    p.add_argument("--depth", type=int, default=-1,
                   help="call-graph depth for pass A (-1 = unlimited)")
    p.add_argument("--yes", help="skip prompts, run these passes, e.g. --yes A,D")
    p.add_argument("--all", action="store_true")
    p.add_argument("--entry", action="append", default=[], metavar="mod::name",
                   help="treat this symbol as an entry point (repeatable)")
    p.add_argument("--json", type=Path)
    p.add_argument("--limit", type=int, default=40)
    p.add_argument("--quiet", action="store_true", help="summary only")
    p.add_argument("--selftest", action="store_true")
    a = p.parse_args(argv)

    if a.selftest:
        return selftest()

    if a.all:
        chosen = list(FEATURES)
    elif a.yes:
        chosen = [c for c in FEATURES
                  if c in {x.strip().upper() for x in a.yes.replace(",", " ").split()}]
    else:
        print("\nCode topology cleaner - select the passes to run.\n")
        chosen = []
        for f, desc in FEATURES.items():
            print(f"  [{f}] {desc}")
            if ask(f"      Run pass {f}?"):
                chosen.append(f)
            print()
    if not chosen:
        print("No passes selected.")
        return 0

    for path in a.paths:
        if not Path(path).exists():
            print(f"path does not exist: {path}", file=sys.stderr)
            return 2

    print(f"\nIndexing {', '.join(a.paths)} ...", flush=True)
    idx = Index([Path(x) for x in a.paths], a.entry)
    results = {f: PASSES[f](idx, a.depth) for f in chosen}

    if not a.quiet:
        report(idx, results, a.depth, a.limit)
    touched = preflight(idx, results)

    if a.json:
        a.json.write_text(json.dumps(to_json(idx, results), indent=2))
        print(f"  findings written to {a.json}")

    if touched and sys.stdin.isatty() and not (a.yes or a.all):
        if ask("\nApply these changes?", default=False):
            print("\n  The act layer is not implemented yet - nothing was written.")
        else:
            print("\n  No files were modified.")
    return 1 if touched else 0


if __name__ == "__main__":
    raise SystemExit(main())