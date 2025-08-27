
from typing import Optional, Union, Any, Dict, Iterator, TYPE_CHECKING
from pathlib import Path
from functools import wraps
from fnmatch import fnmatch
from inspect import isfunction
import xbmcvfs


def _reassign(klass: Dict[str, Any]):
    """Hacks on hacks. Copy Path methods to the APath class."""
    def method(meth):
        @wraps(meth)
        def wrapped(self, *args, **kwargs):
            result = meth(self._path, *args, **kwargs)
            if isinstance(result, Path):
                if self._scheme:
                    result = f'{self._scheme}://{self._host}{result}'
                if self._legal:
                    result = xbmcvfs.makeLegalFilename(str(result))
                return APath(result, legal=self._legal)
            return result
        return wrapped

    def getter(name):
        def wrapped(self):
            result = getattr(self._path, name)
            if isinstance(result, Path):
                if self._scheme:
                    result = f'{self._scheme}://{self._host}{result}'
                if self._legal:
                    result = xbmcvfs.makeLegalFilename(str(result))
                return APath(result, legal=self._legal)
            return result
        return property(wrapped)

    extra = {'__truediv__', '__rtruediv__', '__fspath__'}
    for path_class in reversed(Path.__mro__[:-1]):  # omit 'object'
        for name, meth in vars(path_class).items():
            if not name.startswith('_') or name in extra:
                if type(meth) is property:
                    klass[name] = getter(name)
                elif type(meth) is staticmethod:
                    klass[name] = meth
                elif type(meth) is classmethod:
                    klass[name] = getattr(Path, name)
                elif isfunction(meth):
                    klass[name] = method(meth)


if TYPE_CHECKING:
    class APath(str, Path):
        """
        Extended path to keep OS local and remote path at once.

        >>> AnyPath('/tmp/a')
        >>> AnyPath('c:\\a\\b')
        >>> AnyPath('nfs://server/path')
        """

        __slots__ = ('_scheme', '_host', '_path', '_legal')

        _scheme: str
        _host: str
        _path: Path
        _legal: bool

        def __new__(cls, path: Union[str, Path, 'APath'] = '', *, legal: bool = True) -> 'APath': ...
else:
    class APath(str):
        """
        Extended path to keep OS local and remote path at once.

        >>> AnyPath('/tmp/a')
        >>> AnyPath('c:\\a\\b')
        >>> AnyPath('nfs://server/path')
        """

        __slots__ = ('_scheme', '_host', '_path', '_legal')

        _scheme: str
        _host: str
        _path: Path
        _legal: bool

        def __new__(cls, path: Union[str, Path] = '', *, legal: bool = True) -> 'APath':
            if type(path) is APath:
                return path
            obj = str.__new__(cls, path)
            obj._legal = legal
            scheme, sep, spath = obj.partition('://')
            if sep:
                host, _, spath = spath.partition('/')
                obj._scheme = scheme
                obj._host = host
                obj._path = Path(f'/{spath}')
            else:
                obj._scheme = ''
                obj._host = ''
                obj._path = Path(path)
            return obj

        # --- HACKING -- copy Path API to APath
        _reassign(vars())

        # --- Override Path method with xbmcvfs

        def glob(self, pattern: str, *, case_sensitive: Optional[bool] = None) -> Iterator[str]:
            for names in xbmcvfs.listdir(self):
                for name in names:
                    if fnmatch(name, pattern):
                        yield self / name


if __name__ == '__main__':
    print(f'{APath() = }')
    print(f'{APath("/a/b/c") = }')
    print(f'{APath(Path("/a/b/c")) = }')
    print(f'{APath("nfs://srv/a/b/c") = }')
    print(f'{APath("nfs://srv/") = }')
    print(f'{APath("nfs://srv") = }')
    print(f'{APath("nfs://") = }')
    print(APath.home())
    print(f'{APath("/a/b/c").name = }')
    print(f'{APath("/a/b/c").parent = }')
    print(f'{APath("/a/b/c") / "d.e" = }')
    print(f'{APath("/a/b/c") / "/d.e" = }')
    print(f'{APath("nfs://srv/a/b/c") / "d/e" = }')
    print(f'{APath("nfs://srv/a/b/c") / "/d/e" = }')
    print(f'{list(APath("/tmp/").glob("*.py")) = }')
    print(f'{APath("/tmp").exists() = }')
    print(f'{(APath("/") / "tmp").exists() = }')
    print(f'{APath(APath("/a/b/c")) = }')
