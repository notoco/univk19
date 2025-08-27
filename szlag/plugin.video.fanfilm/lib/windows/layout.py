

from .geom import Rect


class FControl:

    def __init__(self):
        pass

    def alloc(self, rect: Rect) -> None:
        pass


class FLayout(FControl):

    def __init__(self):
        super().__init__()
        self.items = []

    @classmethod
    def from_str(cls, layout: str) -> 'FLayout':
        pass

    def add(self, item: FControl) -> None:
        self.items = []


class FVBox(FLayout):

    def add(self, item: FControl) -> None:
        self.items.append(item)
