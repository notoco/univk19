
from __future__ import annotations
import os
import sys
import re
from dataclasses import dataclass
from typing import Optional, Union, Sequence, Callable, Tuple, TYPE_CHECKING
if TYPE_CHECKING:
    from .xbmcplugin import PluginDirectory

try:
    from lib.fake.sty import fg, bg, ef, rs
except ImportError:
    from sty import fg, bg, ef, rs

if sys.platform == "win32":
    os.system('')

rs.b = rs.bold_dim


rx_omit_sequences = re.compile(r'((?:\033\[|\x9b)[0-?]*[!-/]*[@-~])')
rx_formating = re.compile(r'\[(?P<tag>\w+)(?: (?P<arg>[^]]+))?\](?P<content>.*?)\[/\1\]')

colors = {
    'aliceblue': 'fff0f8ff',
    'antiquewhite': 'fffaebd7',
    'aqua': 'ff00ffff',
    'aquamarine': 'ff7fffd4',
    'azure': 'fff0ffff',
    'beige': 'fff5f5dc',
    'bisque': 'ffffe4c4',
    'black': 'ff000000',
    'blanchedalmond': 'ffffebcd',
    'blue': 'ff0000ff',
    'blueviolet': 'ff8a2be2',
    'brown': 'ffa52a2a',
    'burlywood': 'ffdeb887',
    'cadetblue': 'ff5f9ea0',
    'chartreuse': 'ff7fff00',
    'chocolate': 'ffd2691e',
    'coral': 'ffff7f50',
    'cornflowerblue': 'ff6495ed',
    'cornsilk': 'fffff8dc',
    'crimson': 'ffdc143c',
    'cyan': 'ff00ffff',
    'darkblue': 'ff00008b',
    'darkcyan': 'ff008b8b',
    'darkgoldenrod': 'ffb8860b',
    'darkgray': 'ffa9a9a9',
    'darkgreen': 'ff006400',
    'darkkhaki': 'ffbdb76b',
    'darkmagenta': 'ff8b008b',
    'darkolivegreen': 'ff556b2f',
    'darkorange': 'ffff8c00',
    'darkorchid': 'ff9932cc',
    'darkred': 'ff8b0000',
    'darksalmon': 'ffe9967a',
    'darkseagreen': 'ff8fbc8f',
    'darkslateblue': 'ff483d8b',
    'darkslategray': 'ff2f4f4f',
    'darkturquoise': 'ff00ced1',
    'darkviolet': 'ff9400d3',
    'deeppink': 'ffff1493',
    'deepskyblue': 'ff00bfff',
    'dimgray': 'ff696969',
    'dodgerblue': 'ff1e90ff',
    'firebrick': 'ffb22222',
    'floralwhite': 'fffffaf0',
    'forestgreen': 'ff228b22',
    'fuchsia': 'ffff00ff',
    'gainsboro': 'ffdcdcdc',
    'ghostwhite': 'fff8f8ff',
    'gold': 'ffffd700',
    'goldenrod': 'ffdaa520',
    'gray': 'ff808080',
    'green': 'ff008000',
    'greenyellow': 'ffadff2f',
    'honeydew': 'fff0fff0',
    'hotpink': 'ffff69b4',
    'indianred': 'ffcd5c5c',
    'indigo': 'ff4b0082',
    'ivory': 'fffffff0',
    'khaki': 'fff0e68c',
    'lavender': 'ffe6e6fa',
    'lavenderblush': 'fffff0f5',
    'lawngreen': 'ff7cfc00',
    'lemonchiffon': 'fffffacd',
    'lightblue': 'ffadd8e6',
    'lightcoral': 'fff08080',
    'lightcyan': 'ffe0ffff',
    'lightgoldenrodyellow': 'fffafad2',
    'lightgrey': 'ffd3d3d3',
    'lightgreen': 'ff90ee90',
    'lightpink': 'ffffb6c1',
    'lightsalmon': 'ffffa07a',
    'lightseagreen': 'ff20b2aa',
    'lightskyblue': 'ff87cefa',
    'lightslategray': 'ff778899',
    'lightsteelblue': 'ffb0c4de',
    'lightyellow': 'ffffffe0',
    'lime': 'ff00ff00',
    'limegreen': 'ff32cd32',
    'linen': 'fffaf0e6',
    'magenta': 'ffff00ff',
    'maroon': 'ff800000',
    'mediumaquamarine': 'ff66cdaa',
    'mediumblue': 'ff0000cd',
    'mediumorchid': 'ffba55d3',
    'mediumpurple': 'ff9370d8',
    'mediumseagreen': 'ff3cb371',
    'mediumslateblue': 'ff7b68ee',
    'mediumspringgreen': 'ff00fa9a',
    'mediumturquoise': 'ff48d1cc',
    'mediumvioletred': 'ffc71585',
    'midnightblue': 'ff191970',
    'mintcream': 'fff5fffa',
    'mistyrose': 'ffffe4e1',
    'moccasin': 'ffffe4b5',
    'navajowhite': 'ffffdead',
    'navy': 'ff000080',
    'none': '00000000',
    'oldlace': 'fffdf5e6',
    'olive': 'ff808000',
    'olivedrab': 'ff6b8e23',
    'orange': 'ffffa500',
    'orangered': 'ffff4500',
    'orchid': 'ffda70d6',
    'palegoldenrod': 'ffeee8aa',
    'palegreen': 'ff98fb98',
    'paleturquoise': 'ffafeeee',
    'palevioletred': 'ffd87093',
    'papayawhip': 'ffffefd5',
    'peachpuff': 'ffffdab9',
    'peru': 'ffcd853f',
    'pink': 'ffffc0cb',
    'plum': 'ffdda0dd',
    'powderblue': 'ffb0e0e6',
    'purple': 'ff800080',
    'red': 'ffff0000',
    'rosybrown': 'ffbc8f8f',
    'royalblue': 'ff4169e1',
    'saddlebrown': 'ff8b4513',
    'salmon': 'fffa8072',
    'sandybrown': 'fff4a460',
    'seagreen': 'ff2e8b57',
    'seashell': 'fffff5ee',
    'sienna': 'ffa0522d',
    'silver': 'ffc0c0c0',
    'skyblue': 'ff87ceeb',
    'slateblue': 'ff6a5acd',
    'slategray': 'ff708090',
    'snow': 'fffffafa',
    'springgreen': 'ff00ff7f',
    'steelblue': 'ff4682b4',
    'tan': 'ffd2b48c',
    'teal': 'ff008080',
    'thistle': 'ffd8bfd8',
    'tomato': 'ffff6347',
    'turquoise': 'ff40e0d0',
    'violet': 'ffee82ee',
    'wheat': 'fff5deb3',
    'white': 'ffffffff',
    'whitesmoke': 'fff5f5f5',
    'yellow': 'ffffff00',
    'yellowgreen': 'ff9acd32',
}


def get_color(color: str) -> Optional[Tuple[int, int, int]]:
    """Get color name or #aarrggbb as (red, green, blue)."""
    if color.startswith('#'):
        color = color[1:]
    else:
        color = colors.get(color.lower(), color)
    try:
        val = int(color, 16)
    except ValueError:
        return None
    return ((val >> 16) & 0xff), ((val >> 8) & 0xff), (val & 0xff)


def text_width(s: str) -> int:
    if s in ('⬅️', '▶️'):
        return 1
    return len(rx_omit_sequences.sub('', s))


def text_multi_line_width(s: str) -> int:
    if s in ('⬅️', '▶️'):
        return 1
    return max((len(rx_omit_sequences.sub('', ln)) for ln in s.split('\n')), default=0)


def text_left(s: str, size: int) -> str:
    if s in ('⬅️', '▶️'):
        return 1
    parts = rx_omit_sequences.split(s)
    out = ''
    width = 0
    for i, p in enumerate(parts):
        out += p
        if i % 2 == 0:
            width += len(p)
            if width > size:
                out = out[:size - width]
            if width >= size:
                break
    return f'{out}{rs.all}'


def formatting(text: str) -> str:
    """Colorize Kodi label text to terminal colors."""
    def cc(m: re.Match) -> str:
        text: str = m['content']
        tag: str = m['tag'].upper()
        arg: str = (m['arg'] or '').strip()
        if tag == 'UPPERCASE':
            return text.upper()
        if tag == 'LOWERCASE':
            return text.lower()
        if tag == 'CAPITALIZE':
            return ''.join(s.capitalize() for s in re.split(r'(\s+)', text))
        # if tag == 'LIGHT':  # use dotted underline
        if tag == 'I':
            return f'{ef.i}{text}{rs.i}'
        if tag == 'B':
            return f'{ef.b}{text}{rs.bold_dim}'
        if tag == 'COLOR':
            c = get_color(arg)
            if c:
                return f'{fg(*c)}{text}{rs.fg}'
        return text

    text = text.replace('[CR]', '\n')
    while True:
        text, nn = rx_formating.subn(cc, text)
        if not nn:
            break
    return text


@dataclass
class Format:
    fmt: Union[str, Callable[..., str]]

    def format(self, _text: str, *args, **kwargs) -> str:
        if not self.fmt:
            return _text
        if callable(self.fmt):
            return self.fmt(_text, *args, **kwargs)
        try:
            return self.fmt.format(_text, *args, **kwargs)
        except ValueError:
            if kwargs.get('w') == 0:
                return self.fmt.replace(':{w}', '').format(_text, *args, **kwargs)
            raise


def print_table(table: Sequence[Sequence[str]],
                *,
                vformats: Optional[Sequence[str]] = None,
                cformats: Optional[Sequence[str]] = None,
                multi_line: bool = True,
                indent: int = 0,
                ) -> None:
    if table and table[0]:
        ncol = len(table[0])
        if not vformats:
            vformats = [''] * ncol
        if not cformats:
            cformats = ['{}'] * ncol
        if multi_line:
            ww = list(max(map(text_multi_line_width, col)) for col in zip(*table))
        else:
            ww = list(max(map(text_width, col)) for col in zip(*table))
        for i, row in enumerate(table):
            # print('  '.join(Format(cfmt).format(text, i=i, row=i, column=col, vfmt=vfmt, cfmt=cfmt, val=cell, text=text)
            #                 for col, (w, vfmt, cfmt, cell) in enumerate(zip(ww, vformats, cformats, row))
            #                 if (text := Format(vfmt or '{:{w}}').format(cell, w=w+len(cell)-text_width(cell))) is not None))
            cells = [Format(cfmt).format(text, i=i, row=i, column=col, vfmt=vfmt, cfmt=cfmt, val=cell, text=text)
                     for col, (w, vfmt, cfmt, cell) in enumerate(zip(ww, vformats, cformats, row))
                     if (text := Format(vfmt or '{:{w}}').format(cell, w=w+len(cell)-text_width(cell))) is not None]
            if multi_line:
                multi_row = max((c.count('\n') for c in cells), default=0)
            else:
                multi_row = 0
            if multi_row:
                for r in range(multi_row + 1):
                    if indent:
                        print(' ' * indent, end='')
                    print('  '.join(Format(cfmt).format(text, i=i, row=i, column=col, vfmt=vfmt, cfmt=cfmt, val=cell, text=text)
                                    for col, (w, vfmt, cfmt, _cell) in enumerate(zip(ww, vformats, cformats, row))
                                    if ((cell := next(iter(_cell.split('\n')[r:r+1]), '')) is not None
                                        and (text := Format(vfmt or '{:{w}}').format(cell, w=w+len(cell)-text_width(cell))) is not None)))
            else:
                if indent:
                    print(' ' * indent, end='')
                print('  '.join(cells))


def print_item_list(directory: PluginDirectory, *, parent: bool = True, enum: bool = True):
    def mark(item):
        if item.folder:
            return '📁'
        if item.item.getProperty('isPlayable') == 'true':
            return '▶️'
        return '🔷'   # 🚀

    def prog(item):
        vtag = item.item.getVideoInfoTag()
        if vtag.getResumeTime():
            return '◐'
        if vtag.getPlaycount():
            return '✓'
        return ' '

    def title(item):
        label = formatting(item.item.getLabel())
        if item.item.isSelected():
            return f'{bg.da_green}{label}{bg.da_blue}'
        return label

    def title_format(_text, *args, i: int, **kwargs) -> str:
        color = bg.da_green if i in selected else bg.da_blue
        return f'\b{color}{_text}{rs.all}'

    items = directory.items
    vformats = ['', '', '', '']                               # value format
    # cformats = ['{}', '', f'\b{bg.da_blue}{{}}{rs.all}', '{}']  # cell format
    cformats = ['{}', '', title_format, '{}']  # cell format
    selected = {i+1 for i, it in enumerate(items) if it.item.isSelected()}
    if enum:
        vformats.insert(0, '{:>{w}}')
        cformats.insert(0, '{}')
        table = [[f'{i}.', mark(it), prog(it), formatting(it.item.getLabel()), it.url] for i, it in enumerate(items, 1)]
        if parent:
            table.insert(0, ['0.', '⬅️', '', '..', ''])
            # table.append(['0.', '🔷', formatting('[COLOR yellow]Szu[/COLOR][COLOR white]kaj[/COLOR]'), '-'])
    else:
        table = [[mark(it), prog(it), formatting(it.item.getLabel()), it.url] for it in items]
        if parent:
            table.insert(0, ['⬅️', '', '..', ''])
    print(f'== view: {directory.view!r}, category: {directory.category!r}')
    print_table(table, vformats=vformats, cformats=cformats)
    # print(list(map(len, ('📁', '🔷', '📁', '▶️', '⬅️'))))


def print_log(msg: str, level: int) -> None:
    from lib.fake.xbmc import LOGNONE, LOGDEBUG, LOGINFO, LOGWARNING, LOGERROR, LOGFATAL
    colors = {
        LOGNONE: f'{fg(235)}{ef.strike}',
        LOGDEBUG: f'{fg(237)}',
        LOGINFO: f'{fg(244)}',
        LOGWARNING: f'{fg.yellow}{ef.dim}',
        LOGERROR: f'{fg.red}{ef.dim}',
        LOGFATAL: f'{fg.yellow}{bg.red}{ef.dim}',
    }
    col = colors.get(level, f'{bg.blue}{fg.red}')
    print(f'{col}{msg}{rs.all}', file=sys.stderr)


if __name__ == '__main__':
    from .xbmcplugin import _Item
    from xbmcgui import ListItem

    if 1:
        print_table([
            ['yy', 'teraz to będzie\ndużo trudniej', '11'],
            ['aaa', 'coś', '12'],
            # ['x', 'zupełnie nic ciekawego ale za to zajmującego dużo miejsca', '13'],
        ])

    if 0:
        print_item_list([
            _Item('/a/b/c', ListItem('Zupa dębowa'), False),
            _Item('/a/c',   ListItem('Nieco [COLOR yellow]dłuższy[/COLOR] tytuł'), False),
            _Item('/a/e',   ListItem('[B]Nic[/B] [I]to[/I]'), True),
        ])

    if 0:
        s = f'{fg.red}This is red text!{fg.rs}'
        print('-' * len(s))
        print(s)
        print('-' * text_width(s))
