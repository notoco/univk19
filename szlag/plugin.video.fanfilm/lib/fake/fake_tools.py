
from typing import Optional, Union, Any, Callable, Type, ClassVar, List
from typing import get_origin
from attrs import define, asdict
from ..exc import DeprecatedError

class MISSING:
    pass


@define
class Field:
    name: str
    type: Type
    default: Any = MISSING
    default_factory: Callable = MISSING
    getter: Union[bool, Callable[[], Any]] = True
    setter: Union[bool, Callable[[Any], None]] = True
    first_getter: Union[bool, Callable[[], Any]] = False

    @property
    def attr_name(self) -> str:
        return f'_{self.name}'

    def new_value(self):
        if self.default_factory is not None and self.default_factory is not MISSING:
            return self.default_factory()
        if self.default is not MISSING:
            return self.default
        raise TypeError(f'Attribute {self.name} has no defaulr value')


def field(**kwargs):
    return Field(None, None, **kwargs)


def Factory(default_factory: Callable[[None], Any]):
    return Field(None, None, default_factory=default_factory)


def getsetmethods(cls):
    def __def_init__(self, *args, **kwargs) -> None:
        clsname = f'{self.__class__.__name__}()'
        attributes = self.__attributes__
        if len(args) > len(attributes):
            raise TypeError(f'To much arguemnts in {clsname}, max {len(attributes)}')
        for arg, attr in zip(args, attributes.values()):
            if attr.name in kwargs:
                raise TypeError(f'{clsname} got multiple values for argument {attr.name!r}')
            kwargs[attr.name] = arg
        for attr in attributes.values():
            kwargs.setdefault(attr.name, attr.new_value())
        if kwargs.keys() - attributes.keys():
            aa = ', '.join(f'{a!r}' for a in kwargs.keys() - attributes.keys())
            raise TypeError(f'{clsname} got an unexpected keyword argument {aa}')
        for a in attributes.values():
            try:
                object.__setattr__(self, a.attr_name, kwargs[a.name])
            except KeyError:
                raise TypeError(f'{clsname} missing required argument: {a.name!r}') from None

    def __sub_init__(self, *args, **kwargs) -> None:
        attributes = self.__attributes__
        for attr in attributes.values():
            setattr(self, attr.attr_name, attr.new_value())
        self.__orig_init__(*args, **kwargs)
        for a in attributes.values():
            if getattr(self, a.attr_name, MISSING) is MISSING:
                raise TypeError(f'Missing argument {self.__class__.__name__}.{a.name}')

    def __repr__(self) -> str:
        attrs = ', '.join(f'{a}={v!r}' for a in self.__attributes__ if (v := getattr(self, f'_{a}')) or True)
        return f'{self.__class__.__name__}({attrs})'

    def dumps(self, *, indent: int = 2, margin: int = 0) -> str:
        def dump(vv: Any, margin: int) -> str:
            if isinstance(vv, tuple):
                br = '()'
            elif isinstance(vv, list):
                br = '[]'
            elif isinstance(vv, set):
                br = '{}'
            else:
                return repr(vv)
            if len(vv) <= 1:
                return repr(vv)
            out = '\n'.join(f'{"":{margin+indent}}{v!r}' for v in vv)
            return f'{br[0]}\n{out}\n{"":{margin}}{br[1]}'

        if not indent:
            return repr(self)
        vals = {a: v for a in self.__attributes__ if (v := getattr(self, f'_{a}')) or True}
        out = '\n'.join(f'{"":{margin+indent}}{n:28} = {dump(v, margin=margin+indent)}' for n, v in vals.items())
        return f'FFVTag(\n{out}\n{"":{margin}})'

    def make_xetter(cls, attr: Field):
        def getter(self):
            return getattr(self, aname)

        def first_getter(self):
            lst = getattr(self, aname)
            return lst[0] if lst else attr.default

        def setter(self, value):
            setattr(self, aname, value)

        name = f'{attr.name[0].upper()}{attr.name[1:]}'
        aname = attr.attr_name

        getter.__qualname__ = f'{cls.__name__}.get{name}'
        if attr.getter is True:
            setattr(cls, f'get{name}', getter)
        elif isinstance(attr.getter, str):
            getter.__qualname__ = f'{cls.__name__}.{attr.getter}'
            setattr(cls, attr.getter, getter)
        elif attr.getter:
            setattr(cls, f'get{name}', attr.getter)

        if isinstance(attr.first_getter, str):
            first_getter.__qualname__ = f'{cls.__name__}.{attr.first_getter}'
            setattr(cls, attr.first_getter, first_getter)
        elif attr.first_getter:
            raise ValueError(f'Attribute first item getter failed {attr.first_getter!r}')

        setter.__qualname__ = f'{cls.__name__}.set{name}'
        if attr.setter is True:
            setattr(cls, f'set{name}', setter)
        elif isinstance(attr.setter, str):
            setter.__qualname__ = f'{cls.__name__}.{attr.setter}'
            setattr(cls, attr.setter, setter)
        elif attr.setter:
            setattr(cls, f'set{name}', attr.setter)

    cls.__attributes__: List[Field] = {}
    # keep_hints: set[str] = set()
    for aname, atype in cls.__annotations__.items():
        avalue = getattr(cls, aname, MISSING)
        aorig = get_origin(atype)
        if aorig is not ClassVar:
            if isinstance(avalue, Field):
                attr = Field(**{**asdict(avalue), 'name': aname, 'type': atype})
            else:
                attr = Field(aname, atype, default=avalue)
            cls.__attributes__[aname] = attr
            if avalue != MISSING:
                delattr(cls, aname)
            make_xetter(cls, attr)
    # cls.__annotations__ = {k: v for k, v in cls.__annotations__.items() if k in keep_hints}

    cls.__orig_init__ = getattr(cls, '__init__', object.__init__)
    if cls.__orig_init__ is object.__init__:
        cls.__init__ = __def_init__
    else:
        cls.__init__ = __sub_init__
    if getattr(cls, '__repr__', object.__repr__) is object.__repr__:
        cls.__repr__ = __repr__
    if getattr(cls, 'dumps', None) is None:
        cls.dumps = dumps

    return cls


def deprecated_warning(msg: Optional[str] = None, /) -> None:
    """Warning: deprecated."""
    # from xbmc import log, LOGWARNING
    from lib.ff.log_utils import log, LOGWARNING
    log(msg or 'DEPRECATED', level=LOGWARNING, stack_depth=2)
