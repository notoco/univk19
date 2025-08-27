
import builtins
import sys
import sysconfig
import importlib
from graphlib import TopologicalSorter
from pathlib import Path
from typing import Optional, Union, Any, List, Dict, Iterable, Iterator, Sequence, TypeVar
from types import ModuleType
from const import const

T = TypeVar('T')

_modules_dependants = {}
_base_import = getattr(builtins, '__ff_import__', builtins.__import__)
builtins.__ff_import__ = _base_import
# _base_import = builtins.__import__
_module_sys_path = {Path(p) for k, p in sysconfig.get_paths().items()
                    if k in ('stdlib', 'platstdlib', 'purelib', 'platlib')}


if sys.version_info >= (3, 9):
    path_is_relative_to = Path.is_relative_to
else:
    def path_is_relative_to(self: Path, other: Path) -> bool:
        other = Path(other)
        return other == self or other in self.parents


# Copy of ff.tricks.cyclic to avoid dependecies.
# Modiled Gareth Rees method.
# See: https://codereview.stackexchange.com/a/86067
def cyclic(*graphs: Union[Dict[T, Iterable[T]], Dict[T, Dict[T, Any]]]) -> bool:
    """
    Return True if the directed graph has a cycle.
    The graph must be represented as a dictionary mapping vertices to
    iterables of neighbouring vertices. For example:

    >>> cyclic({1: (2,), 2: (3,), 3: (1,)})
    True
    >>> cyclic({1: (2,), 2: (3,), 3: (4,)})
    False
    """
    visited = set()
    path = [object()]
    path_set = set(path)
    stack = [{x for g in graphs for x in g}]
    while stack:
        for v in stack[-1]:
            if v in path_set:
                return True
            elif v not in visited:
                visited.add(v)
                path.append(v)
                path_set.add(v)
                stack.append({x for g in graphs for x in g.get(v, ())})
                break
        else:
            path_set.remove(path.pop())
            stack.pop()
    return False


def import_hack(name: str, globals=None, locals=None, fromlist=(), level=0, *args, **kwargs):
    def add(name: str) -> None:
        assert caller
        if not cyclic(_modules_dependants, {name: (caller,)}):
            _modules_dependants.setdefault(name, {})[caller] = None

    caller = None if globals is None else globals.get('__name__')
    mod = _base_import(name, globals, locals, fromlist, level, *args, **kwargs)
    if caller == 'importlib._bootstrap_external':
        return mod
    if mod.__name__ in sys.builtin_module_names:
        return mod
    if (file := getattr(mod, '__file__', '')) and any(path_is_relative_to(Path(file), p) for p in _module_sys_path):
        return mod
    # print(f'{mod.__name__}: {sys.modules[__name__]}: imported {mod} {name=}, from {caller}, {fromlist=} {mod.__name__ != name}')
    if caller:
        if caller.startswith('importlib.'):
            return mod
        add(mod.__name__)

        mod_name = mod.__name__
        while name.startswith(f'{mod_name}.'):
            mod_name = f'{mod_name}.{name[len(mod_name)+1].partition(".")[0]}'
            add(name)
    return mod


# Hacking - monitor import dependencies.
if const.debug.autoreload:
    builtins.__import__ = import_hack

# Import AFTER import_hack.
from .exc import ReloadExit  # noqa: E402


def __reload__(state: Dict[str, Any]) -> None:
    """Recovers base impoty. Called on reloading."""
    if bi := state.get('_base_import'):
        global _base_import
        _base_import = bi

    global _modules_dependants
    _modules_dependants.update(state.get('_modules_dependants', ()))


class ReloadMonitorMeta(type):
    """Meta class for ReloadMonitor."""

    @property
    def reloading(self) -> bool:
        """True, if module is going to reload."""
        return ReloadMonitor._reloading

    @reloading.setter
    def reloading(self, value: bool, /) -> None:
        if ReloadMonitor._reloading != value:
            from ..ff.kotools import reload_event, sleep_event
            ReloadMonitor._reloading = value
            sleep_event.set()
            reload_event.set()


class ReloadMonitor(metaclass=ReloadMonitorMeta):
    """Monitor files for change detect."""

    #: True, if module is going to reload.
    _reloading: bool = False

    def __init__(self, path: Union[Path, Sequence[Path]]) -> None:
        def iter_path(path: Path) -> Iterator[Path]:
            wildcard = '*.py'
            if path.name.endswith('**'):
                path = path.parent
                wildcard = '**/*.py'
            if path.is_dir():
                yield from path.glob(wildcard)
            else:
                if '*' in path.name:
                    yield from path.parent.glob(path.name)
                else:
                    yield path

        paths = path
        if isinstance(paths, str):
            paths = Path(paths)
        if not isinstance(paths, Sequence):
            paths = (paths,)
        #: Fields and theirs modification time.
        self.files: Dict[Path, float] = dict.fromkeys((p for path in paths for p in iter_path(path)), 0)
        # fill modification times
        self._check()

    def _check(self) -> List[Path]:
        """Check if any file changes and return list of changes."""
        changed = []
        for path, last in self.files.items():
            modified = path.stat().st_mtime
            if modified > last:
                self.files[path] = modified
                changed.append(path)
        return changed

    def check(self) -> None:
        """Check if any file changes and raise ReloadExit."""
        changed = self._check()
        if changed:
            raise ReloadExit(changed=changed, files=tuple(self.files), modules=modules_by_files(self.files))

    def raise_reload(self) -> None:
        """Force raise ReloadExit. with all files."""
        all_files = tuple(self.files)
        raise ReloadExit(changed=all_files, files=all_files, modules=modules_by_files(self.files))


def modules_by_files(files: Iterable[Union[Path, str]]) -> Sequence[ModuleType]:
    """Return modules by theris paths in reloading order."""
    def dependants(mods, rec):
        for mod in mods:
            if mod not in rec:
                rec.add(mod)
                subs = _modules_dependants.get(mod, ())
                yield mod, subs
                if subs:
                    yield from dependants(subs, rec)

    files_set = set(map(str, files))
    changed = {mod.__name__ for mod in sys.modules.values() if getattr(mod, '__file__', None) in files_set}
    ts = TopologicalSorter(dict(dependants(changed, set())))
    return tuple(reversed(tuple(sys.modules[m] for m in ts.static_order())))


def reload(*modules: Union[str, ModuleType]) -> None:
    """Reload the module(s)."""
    for mod in modules:
        if isinstance(mod, str):
            mod = sys.modules[mod]
        new = importlib.reload(mod)
        if new and (reloaded := getattr(new, '__reload__', None)):
            reloaded(vars(mod))


def reload_all() -> None:
    """Reload all modules."""
    reload(*_modules_dependants)
