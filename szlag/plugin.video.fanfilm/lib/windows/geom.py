
from typing import Optional, Union, Iterator
from typing_extensions import Self
from attrs import define


@define
class Point:
    x: int
    y: int

    def __len__(self) -> int:
        return 2

    def __iter__(self) -> Iterator[int]:
        return iter((self.x, self.y))

    def __add__(self, other: Union['Point', int]) -> 'Point':
        if isinstance(other, int):
            x = y = other
        elif type(other) is Point:
            x, y = other.x, other.y
        else:
            x, y = other
        return Point(self.x + x, self.y + y)

    def __radd__(self, other: Union['Point', int]) -> 'Point':
        return self.__add__(other)

    def __iadd__(self, other: Union['Point', int]) -> Self:
        if isinstance(other, int):
            x = y = other
        elif type(other) is Point:
            x, y = other.x, other.y
        else:
            x, y = other
        self.x += x
        self.y += y
        return self

    def __sub__(self, other: Union['Point', int]) -> 'Point':
        if isinstance(other, int):
            x = y = other
        elif type(other) is Point:
            x, y = other.x, other.y
        else:
            x, y = other
        return Point(self.x - x, self.y - y)

    def __isub__(self, other: Union['Point', int]) -> Self:
        if isinstance(other, int):
            x = y = other
        elif type(other) is Point:
            x, y = other.x, other.y
        else:
            x, y = other
        self.x -= x
        self.y -= y
        return self

    def __neg__(self) -> 'Point':
        return Point(-self.x, -self.y)


@define
class Size:
    width: int
    height: int

    def __bool__(self) -> bool:
        return self.width > 0 and self.height > 0

    def __len__(self) -> int:
        return 2

    def __iter__(self) -> Iterator[int]:
        return iter((self.width, self.height))

    def __add__(self, other: Union['Size', int]) -> 'Size':
        if isinstance(other, int):
            w = h = other
        elif type(other) is Point:
            w, h = other.width, other.height
        else:
            w, h = other
        return Size(self.width + w, self.height + h)

    def __radd__(self, other: Union['Size', int]) -> 'Size':
        return self.__add__(other)

    def __sub__(self, other: Union['Size', int]) -> 'Size':
        if isinstance(other, int):
            w = h = other
        elif type(other) is Point:
            w, h = other.width, other.height
        else:
            w, h = other
        return Size(max(0, self.width - w), max(0, self.height - h))


@define
class Rect:
    point: Point
    size: Size

    def __bool__(self) -> bool:
        return bool(self.size)

    @property
    def left(self) -> int:
        return self.point.x

    @left.setter
    def left(self, value: int) -> None:
        self.point.x = value

    @property
    def top(self) -> int:
        return self.point.y

    @top.setter
    def top(self, value: int) -> None:
        self.point.y = value

    @property
    def right(self) -> int:
        return self.point.x + self.size.width

    @right.setter
    def right(self, value: int) -> None:
        self.point.x = value - self.size.width

    @property
    def bottom(self) -> int:
        return self.point.y + self.size.height

    @bottom.setter
    def bottom(self, value: int) -> None:
        self.point.y = value - self.size.height

    def move(self, other: Point) -> Self:
        self.point += other
        return self

    def __add__(self, other: Point) -> 'Rect':
        if isinstance(other, Point):
            return Rect(self.point + other, self.size)
        elif isinstance(other, Size):
            return Rect(self.point, self.size + other)
        elif isinstance(other, int):
            return Rect(self.point + other, self.size + 2 * other)
        else:
            raise NotImplementedError(f'Rect + {other.__class__.__name__}')

    def __iadd__(self, other: Point) -> Self:
        if isinstance(other, Point):
            self.point += other
        elif isinstance(other, Size):
            self.size += other
        elif isinstance(other, int):
            self.point += other
            self.size += 2 * other
        else:
            raise NotImplementedError(f'Rect + {other.__class__.__name__}')
        return self

    def __sub__(self, other: Point) -> 'Rect':
        if isinstance(other, Point):
            return Rect(self.point - other, self.size)
        elif isinstance(other, Size):
            return Rect(self.point, self.size - other)
        elif isinstance(other, int):
            return Rect(self.point - other, self.size - 2 * other)
        else:
            raise NotImplementedError(f'Rect - {other.__class__.__name__}')

    def __isub__(self, other: Point) -> Self:
        if isinstance(other, Point):
            self.point -= other
        elif isinstance(other, Size):
            self.size -= other
        elif isinstance(other, int):
            self.point -= other
            self.size -= 2 * other
        else:
            raise NotImplementedError(f'Rect - {other.__class__.__name__}')
        return self
