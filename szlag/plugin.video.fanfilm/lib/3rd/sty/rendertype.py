"""
This module contains the default render types.

These can be used to create register classes and custom styling rules.
"""


class RenderType:
    args: list = []


class Sgr(RenderType):
    """
    Define SGR styling rule.

    More info about SGR parameters: https://en.wikipedia.org/wiki/ANSI_escape_code#SGR

    :param num: A SGR number.
    """

    def __init__(self, num: int):
        self.args = [num]


class SgrArgs(RenderType):
    """
    Define SGR styling extended rule, rule with argument.

    Example of underline extension: https://sw.kovidgoyal.net/kitty/underlines/

    :param num:  A SGR number.
    :param args: A list of argument numbers.
    """

    def __init__(self, num: int, *args: int):
        self.args = [num, *args]


class Eightbit(RenderType):
    """
    Define Eightbit color (foreground, background, underline).

    More info about 8-bit terminal colors: https://en.wikipedia.org/wiki/ANSI_escape_code#8-bit

    :param num: Eightbit number.
    """

    def __init__(self, num: int):
        self.args = [num]


class Rgb(RenderType):
    """
    Define RGB color (foreground, background, underline).

    More info about 24-bit terminal colors: https://en.wikipedia.org/wiki/ANSI_escape_code#24-bit

    :param r: Red.
    :param g: Green.
    :param b: Blue.
    """

    def __init__(self, r: int, g: int, b: int):
        self.args = [r, g, b]


# Backward compatibility.
EightbitFg = Eightbit
EightbitBg = Eightbit
RgbFg = Rgb
RgbBg = Rgb
