"""Simple GUI helpers."""

from __future__ import annotations
from typing import overload, TYPE_CHECKING
import re
from enum import IntFlag, auto as auto_enum
from pathlib import Path
from itertools import product
from io import BytesIO
from xml.etree import ElementTree as ET
from attrs import define, frozen, field, asdict
from xbmc import getSkinDir
from ..ff.tricks import iter_flags, or_reduce
from ..ff.types import TRUE_VALUES, FALSE_VALUES
from ..ff.log_utils import fflog, fflog_exc
if TYPE_CHECKING:
    from typing import Sequence, Iterable, Iterator, ClassVar, TypeAlias
    # from typing_extensions import Pattern


@frozen
class SkinDescr:
    id: str
    font: dict[str, str] = field(factory=dict)


DEFAULT_SKIN = SkinDescr('',
                         font={
                             'heading': 'font13',
                             'normal': 'font13',
                             'small': 'font12',
                             'tiny': 'font10',
                         },
                         )

SKINS: dict[str, SkinDescr] = {skin.id: skin for skin in (
    SkinDescr('skin.estuary',  # Font: NotoSans-Regular
              font={
                  'heading': 'font40_title',  # Size: 40 Style: Bold
                  'normal': 'font13',  # Size: 30 Style: Lighten
                  'small': 'font12',  # Size: 25 Style: Lighten
                  'tiny': 'font10',  # Size: 23 Style: Lighten
              },
              ),
    SkinDescr('skin.arctic.zephyr.2.resurrection.mod',  # Font: RobotoCondensed-Regular
              font={
                  'heading': 'font_title_small',  # Size: 40 Style: Bold
                  'normal': 'font13',  # Size 30
                  'small': 'font_tiny',  # Size: 26
                  'tiny': 'font_tiny_23',  # Size: 23
              },
              ),
    SkinDescr('skin.arctic.fuse',  # Font: RobotoCondensed-Regular
              font={
                  'heading': 'font_head_bold',  # Size: 42 Style: Bold
                  'normal': 'font13',  # Size: 30
                  'small': 'font_mini',  # Size: 26
                  'tiny': 'font_tiny',  # Size: 22
              },
              ),
    SkinDescr('skin.arctic.fuse.2',  # Font: RobotoCondensed-Regular
              font={
                  'heading': 'font_head_bold',  # Size: 40 Style: Bold
                  'normal': 'font13',  # Size: 30
                  'small': 'font_mini',  # Size: 26
                  'tiny': 'font_tiny',  # Size: 23
              },
              ),
    SkinDescr('skin.arctic.horizon.2',  # Font: RobotoCondensed-Regular
              font={
                  'heading': 'font_head_bold',  # Size: 42 Style: Bold
                  'normal': 'font13',  # Size: 30
                  'small': 'font_mini',  # Size: 26
                  'tiny': 'font_tiny',  # Size: 22
              },
              ),
    SkinDescr('skin.aeon.nox.silvo',  # Font: RobotoCondensed-Regular
              font={
                  'heading': 'font16_title_bold',  # Size: 38 Style: Bold
                  'normal': 'font13',  # Size: 30
                  'small': 'font12',  # Size: 26
                  'tiny': 'font11_compact',   # Size: 24
              },
              ),
    SkinDescr('skin.mimic.lr',  # Font: weblysleekuil
              font={
                  'heading': 'font18',  # Size: 40
                  'normal': 'font13',  # Size: 30
                  'small': 'font12',  # Size: 26
                  'tiny': 'font10',   # Size: 21
              },
              ),
    SkinDescr('skin.nimbus',  # Font: Inter-Regular
              font={
                  'heading': 'font40_title',  # Size: 38 Style: Bold
                  'normal': 'font32',  # Size: 30
                  'small': 'font23',  # Size: 25
                  'tiny': 'font12',  # Size: 23
              },
              ),
    SkinDescr('skin.quartz',  # Font: Arial
              font={
                  'heading': 'size26B',  # Size: 39 Style: Bold
                  'normal': 'size20',  # Size: 30
                  'small': 'size17',  # Size: 26
                  'tiny': 'size15',  # Size: 22
              },
              ),
    SkinDescr('skin.bingie',  # Font: Netflix-sans-medium
              font={
                  'heading': 'Bold40',  # Size: 40 Style: Bold
                  'normal': 'font13',  # Size: 30
                  'small': 'font12',  # Size: 26
                  'tiny': 'Reg23',  # Size: 23
              },
              ),
)}

#: Regex for <window>.
RX_XML_WINDOW = re.compile(r'<\s*(window\b[^>]*)\s*>', flags=re.DOTALL)
#: Regex for window ID.
RX_XML_WIN_ID = re.compile(r'\bid="([^"]*)"', flags=re.DOTALL)
#: Regex for set <font>.
RX_FONT = re.compile(r'(<font\s+(?:"[^"]*"|(?!ff:style)[^>])*\bff:style="([^"]*)"(?:"[^"]*"|(?!ff:)[^>])*>)([^<]*)(</font>)')
#: Regex for Window.Property.
RX_WIN_PROP = re.compile(r'\b(Window)\.(Property)\b')

#: All XML Kodi geometry (position and size) tags.
GEOM_TAGS = {'top', 'bottom', 'left', 'right', 'centerleft', 'centerright', 'centertop', 'centerbottom', 'width', 'height'}
#: All sub-control tags.
SUBCTRL_TAGS = {*GEOM_TAGS, 'visible'}
#: Switch button tags.
SWITCH_BUTTONS_TAGS = {*SUBCTRL_TAGS, 'enable'}


ControlStateKey: TypeAlias = 'Sequence[bool | None]'


AUTO_WINDOW_ID = 5900


@define
class XmlIdGenerator:
    """Simple XML control ID generator."""

    _id: int = 42000

    def __call__(self) -> int:
        """Return new ID."""
        self._id += 1
        return self._id


class ControlState(IntFlag):
    """Control general flag (as enabled, focused...)."""

    ENABLED = auto_enum()
    FOCUSED = auto_enum()
    SELECTED = auto_enum()
    # HAS_FOCUS = FOCUSED

    if TYPE_CHECKING:
        __attr_default_seq: dict[ControlState, Sequence[ControlStateKey]] | None = None

    @property
    def attr(self) -> str:
        return (self.name or '').lower()

    def has_focus(self) -> bool:
        return bool(self & ControlState.FOCUSED)

    def is_enabled(self) -> bool:
        return bool(self & ControlState.ENABLED)

    def is_disabled(self) -> bool:
        return not (self & ControlState.ENABLED)

    def is_selected(self) -> bool:
        return bool(self & ControlState.SELECTED)

    def with_flag(self, flag: ControlState, value: bool) -> ControlState:
        if value:
            return self | flag
        return self & ~flag

    @classmethod
    def _attr_default_seq(cls) -> Iterator[tuple[ControlState, Sequence[ControlStateKey]]]:
        flags = list(iter_flags(ControlState))
        for flag_seq in product(*((ControlState(0), f) for f in reversed(flags))):
            flag = or_reduce(flag_seq)
            yield flag, sorted(product(*((bool(f & flag), None) for f in flags)), key=lambda ff: ff.count(None))

    @classmethod
    def attr_default_seq(cls) -> dict[ControlState, Sequence[ControlStateKey]]:
        """Return default sequence of control states in iter(ControlState) order."""
        if (seq := getattr(cls, '__attr_default_seq', None)) is None:
            cls.__attr_default_seq = seq = dict(cls._attr_default_seq())
        return seq

    @classmethod
    def from_seq(cls, seq: ControlStateKey) -> ControlState | None:
        """Create ControlState from sequence of flags values (True, False). Sequences with any None are ignored."""
        if None in seq:
            return None
        flags = list(iter_flags(cls))
        if len(seq) != len(flags):
            raise ValueError(f'Invalid sequence length {len(seq)} for {cls.__name__}')
        return ControlState(sum((flag for flag, value in zip(flags, seq) if value)))


@frozen(kw_only=True)
class Texture:
    path: str = ''
    color_diffuse: str = ''
    border: str = ''

    if TYPE_CHECKING:
        EMPTY: ClassVar[Texture]

    def format_path(self, state: ControlState, *, switch_state: SwitchState | None) -> str:
        if switch_state is None:
            switch_state_name = ''
            switch_state_value = 0
        else:
            switch_state_name = switch_state.name
            switch_state_value = switch_state.value
        focused = int(state.has_focus())
        return self.path.format(state=switch_state_name, name=switch_state_name, value=switch_state_value,
                                enabled=int(state.is_enabled()), disabled=int(state.is_disabled()),
                                has_focus=focused, focused=focused, focus=focused, selected=int(state.is_selected()),
                                border=self.border.replace(',', '_'), colordiffuse=self.color_diffuse)


Texture.EMPTY = Texture(path='', color_diffuse='', border='')


@frozen(kw_only=True)
class Subcontrol:
    name: str
    textures: dict[ControlState, Texture] = field(factory=dict)

    def texture(self, state: ControlState, /) -> Texture:
        return self.textures.get(state, Texture.EMPTY)

    def texture_path(self, control_state: ControlState, /, *, switch_state: SwitchState) -> str:
        tex = self.textures.get(control_state, Texture.EMPTY)
        return tex.format_path(state=control_state, switch_state=switch_state)


@frozen(kw_only=True)
class SwitchState:
    name: str
    label: str = ''
    value: int = 0
    subcontrols: dict[str, Subcontrol] = field(factory=dict)

    def texture(self, subcontrol: str, state: ControlState, /) -> Texture:
        return self.subcontrols[subcontrol].texture(state)

    def texture_path(self, subcontrol: str, state: ControlState, /) -> str:
        tex = self.subcontrols[subcontrol].texture(state)
        return tex.format_path(state=state, switch_state=self)


@frozen(kw_only=True)
class SwitchStyle:
    name: str
    states: dict[str, SwitchState]
    toggle_order: Sequence[SwitchState]
    subcontrols: Sequence[str]

    #: Set of supported sub-controls (nodes).
    SUPPORTED_SUBCONTROLS: ClassVar[tuple[str]] = ('background', 'icon')

    def first_state(self) -> SwitchState:
        return next(iter(self.states.values()))


@frozen(kw_only=True)
class SwitchStatus:
    """Current switch state settings."""
    state: SwitchState | None = None
    control_state: ControlState = ControlState(-1)


@define
class SwitchData:
    style: SwitchStyle
    state: SwitchState
    control_id: int
    subcontrols_id: dict[str, int] = field(factory=dict)
    control_state: ControlState = ControlState.ENABLED
    applied: SwitchStatus = field(factory=SwitchStatus)

    ENABLED = ControlState.ENABLED
    FOCUSED = ControlState.FOCUSED
    SELECTED = ControlState.SELECTED

    def value(self) -> int:
        """Return switch state value."""
        return self.state.value

    def click(self) -> int:
        """Click the switch: toggle to next state."""
        if not self.style.toggle_order:
            return -1
        index = self.style.toggle_order.index(self.state) + 1
        self.state = self.style.toggle_order[index % len(self.style.toggle_order)]
        return self.state.value

    def set(self, name: str) -> SwitchState:
        """Set switch state by name."""
        if state := self.style.states.get(name):
            self.state = state
            return state
        raise KeyError(f'Switch state {name} not found in {self.style.name} style')

    def is_applied(self) -> bool:
        return self.applied.state is self.state and self.applied.control_state is self.control_state

    def set_applied(self) -> None:
        self.applied = SwitchStatus(state=self.state, control_state=self.control_state)


@frozen(kw_only=True)
class CustomXmlData:
    switch_defines: dict[str, SwitchStyle] = field(factory=dict)
    switches: dict[int, SwitchData] = field(factory=dict)


def new_texture(node: ET.Element | None, default: Texture) -> Texture:
    if node is None:
        return default
    # fflog(f'TEX: {node.text=}, {default.path=}, {node.get("focus")=}')
    return Texture(path=node.text or default.path,
                   color_diffuse=node.get('colordiffuse', default.color_diffuse),
                   border=node.get('border', default.border))


def _new_switch_state(node: ET.Element, *, subcontrols_defs: dict[str, dict[ControlStateKey, Texture]]) -> SwitchState:
    """Create new switch state from XML node."""
    subcontrol_dict = {name: Subcontrol(name=name, textures=_get_textures(node, subcontrol=name, defs=defs))
                       for name, defs in subcontrols_defs.items()}
    return SwitchState(name=node.attrib['name'],
                       value=int(node.get('value', 0)),
                       label=_get_label(node),
                       subcontrols=subcontrol_dict,
                       )


def new_switch(node: ET.Element) -> SwitchStyle | None:
    subcontrols = tuple(name for name in SwitchStyle.SUPPORTED_SUBCONTROLS if node.find(name) is not None)
    subcontrols_defs = {sub: _get_texture_nodes(node, subcontrol=sub) for sub in subcontrols}
    states = [_new_switch_state(state_node, subcontrols_defs=subcontrols_defs)
              for state_node in node.findall('state')]
    if not states:
        return None
    states = {state.name: state for state in states}
    if order_str := node.get('toggle-order'):
        order = tuple(state for name in order_str.split(',') if (state := states.get(name.strip())))
    else:
        order = tuple(states.values())
    return SwitchStyle(name=node.attrib['name'], states=states, toggle_order=order, subcontrols=subcontrols)


def _get_label(node: ET.Element) -> str:
    if label_node := node.find('label'):
        return label_node.text or ''
    return ''


def _get_texture_nodes(node: ET.Element | None, *, subcontrol: str | None) -> dict[ControlStateKey, Texture]:
    def bool_or_none(value: str | None) -> bool | None:
        if value is None:
            return None
        return value.lower() in TRUE_VALUES

    if node is not None and subcontrol:
        node = node.find(subcontrol)
    states = list(iter_flags(ControlState))
    state_attrs = tuple(state.attr for state in states)
    tex_nodes = () if node is None else node.findall('texture')
    return {tuple(bool_or_none(n.get(a))
                  for a in state_attrs): new_texture(n, Texture.EMPTY) for n in tex_nodes}


def _get_textures(node: ET.Element | None, *, subcontrol: str | None, defs: dict[ControlStateKey, Texture]) -> dict[ControlState, Texture]:
    tex_keys = asdict(Texture.EMPTY)
    nodes = _get_texture_nodes(node, subcontrol=subcontrol)
    textures: dict[ControlState, Texture] = {}
    for key, sources in ControlState.attr_default_seq().items():
        data = asdict(Texture.EMPTY)
        # print(f' - {key=}: default: {data}')
        for src in sources:
            tex, def_tex = nodes.get(src), defs.get(src)
            if tex or def_tex:
                # print(f'   - {src=}: anchor texture: {tex}, default texture: {def_tex}')
                for name in tex_keys:
                    if data[name]:
                        pass
                    elif tex and (value := getattr(tex, name)):
                        data[name] = value
                    elif def_tex and (value := getattr(def_tex, name)):
                        data[name] = value
        tex = Texture(**data)
        textures[key] = tex
    return textures


class XmlTree:
    """Simple XML tree helper to get node parent."""

    def __init__(self, node: ET.Element | None) -> None:
        self.parents: dict[ET.Element, ET.Element | None] = {}
        if node is not None:
            self.parse(node)

    def parse(self, node: ET.Element, *, parent: ET.Element | None = None) -> None:
        self.parents[node] = parent
        for elem in node:
            self.parse(elem, parent=node)

    def copy(self, node: ET.Element) -> ET.Element:
        """Copy node."""
        new = ET.Element(node.tag, node.attrib)
        new.text = node.text
        return new

    def parent(self, node: ET.Element) -> ET.Element:
        """Return parent for non-root node."""
        parent = self.parents[node]
        if parent is None:
            raise ValueError(f'Node {node} is root element')
        return node

    def insert(self, anchor: ET.Element, index: int, node: ET.Element | str) -> ET.Element:
        """Insert anchor's sub-node."""
        if isinstance(node, str):
            node = ET.Element(node)
        anchor.insert(index, node)
        self.parents[node] = anchor
        return node

    def append(self, anchor: ET.Element, node: ET.Element | str) -> ET.Element:
        """Append anchor's sub-node."""
        if isinstance(node, str):
            node = ET.Element(node)
        anchor.append(node)
        self.parents[node] = anchor
        return node

    def extend(self, anchor: ET.Element, nodes: Iterable[ET.Element]) -> None:
        """Append anchor's sub-nodes."""
        nodes = tuple(nodes)
        anchor.extend(nodes)
        for node in nodes:
            self.parents[node] = anchor

    def append_default(self, anchor: ET.Element, node: str | ET.Element, *, attrib: dict[str, str] = {}, text: str | None = None) -> ET.Element:
        """Append anchor's default sub-node (if there is no tag)."""
        tag = node if isinstance(node, str) else node.tag
        exists = anchor.find('./{tag}')
        if exists is not None:
            return exists
        if isinstance(node, str):
            node = ET.Element(tag, attrib=attrib)
            node.text = text
        anchor.append(node)
        self.parents[node] = anchor
        return node

    @overload
    def remove(self, anchor: ET.Element, node: ET.Element, /) -> None: ...

    @overload
    def remove(self, node: ET.Element, /) -> None: ...

    def remove(self, anchor: ET.Element, node: ET.Element | None = None, /) -> None:
        """Remove anchor's sub-node."""
        if node is None:
            parent = self.parents[anchor]
            if parent is None:
                return
            anchor, node = parent, anchor
        anchor.remove(node)
        del self.parents[node]

    def _insert_in_parent(self, parent: ET.Element, index: int, node: ET.Element, *, indent: bool | int | str) -> None:
        """Helper. Insert node in the parent with indent."""
        parent.insert(index, node)
        self.parents[node] = parent
        if indent is not False:
            if indent is True:
                if index == 0 or not (indent := (parent[index - 1].tail or '').rpartition('\n')[2]).isspace():
                    indent = ''
            elif isinstance(indent, int):
                indent = ' ' * indent
            node.tail = f'\n{indent}'

    def prepend_slibing(self, anchor: ET.Element, node: ET.Element, *, indent: bool | int | str = False) -> ET.Element:
        """Append node just before anchor."""
        parent = self.parents[anchor]
        if parent is None:
            raise ValueError(f'Node {node} is root element')
        for index, elem in enumerate(parent):
            if elem is anchor:
                self._insert_in_parent(parent, index, node, indent=indent)
                return node
        raise AssertionError(f'Node {anchor} is not in its parent {parent}')

    def append_slibing(self, anchor: ET.Element, node: ET.Element, *, indent: bool | int | str = False) -> ET.Element:
        """Append node just after anchor."""
        parent = self.parents[anchor]
        if parent is None:
            raise ValueError(f'Node {node} is root element')
        for index, elem in enumerate(parent):
            if elem is anchor:
                self._insert_in_parent(parent, index + 1, node, indent=indent)
                return node
        raise AssertionError(f'Node {anchor} is not in its parent {parent}')


def custom_xml(xml_source: Path, xml_path: Path) -> CustomXmlData:
    """Fix window/dialog source XML to handle what kodi can not."""

    def xml_repl(mch: re.Match) -> str:
        win = mch[1]
        if ' xmlns:ff=' not in win:
            win = f'{win} xmlns:ff="ff"'
        if False:
            # Nie wiem czemu modanie jawnie ID działa jeszcze gorzej. Do obadania. [rysson]
            if mid := RX_XML_WIN_ID.search(mch[1]):
                nonlocal orig_win_id
                orig_win_id = mid[1]
            else:
                global AUTO_WINDOW_ID
                nonlocal win_id
                win_id = AUTO_WINDOW_ID = AUTO_WINDOW_ID + 1
                win = f'{win} id="{win_id}"'
        return f'<{win}>'

    def font_repl(mch: re.Match) -> str:
        open, style, value, close = mch.groups()
        font = skin.font.get(style, style)
        return f'{open}{font}{close}'

    def create_switch(xml: XmlTree, node: ET.Element) -> None:
        """Create XML switch from <ff:switch/>."""
        common_nodes = [elem for elem in node if elem.tag in SUBCTRL_TAGS]

        sid = node.attrib['id']
        button = node
        button.tag = 'control'
        button.set('type', 'button')
        switch_name = button.get('{ff}switch', 'checkbox')
        switch = switch_defines.get(switch_name)
        if switch is None:
            xml.remove(node)
            return

        for name in switch.SUPPORTED_SUBCONTROLS:
            if name in switch.subcontrols:
                button.set(f'{{ff}}subcontrol-{name}', (cid := str(id_gen())))
                subcontrol = xml.prepend_slibing(node, ET.Element('control', {
                    'id': cid,
                    'type': 'image',
                    '{ff}control-id': sid,
                    '{ff}subcontrol': name,
                }), indent=True)
                for cn in common_nodes:
                    xml.append(subcontrol, xml.copy(cn))
                texture = switch.first_state().texture(name, ControlState(0))
                xml.append(subcontrol, ET.Element('texture', {'border': texture.border}))
                se = ET.Element('colordiffuse')
                se.text = texture.color_diffuse
                xml.append(subcontrol, se)

        for tag in ('texturenofocus', 'texturefocus'):
            xml.append(button, ET.Element(tag))
        xml.append_default(button, 'align', text='left')
        xml.append_default(button, 'aligny', text='center')
        xml.append_default(button, 'textoffsetx', text=f'{72}')

    checkbox_ids: dict[int, SwitchData] = {}
    switch_defines: dict[str, SwitchStyle] = {}
    skin_id = getSkinDir()
    skin = SKINS.get(skin_id, DEFAULT_SKIN)
    id_gen = XmlIdGenerator()
    orig_win_id = ''
    win_id = ''
    try:
        xml_data = xml_source.read_text(encoding='utf-8')
        xml_data = RX_XML_WINDOW.sub(xml_repl, xml_data)
        xml_data = RX_FONT.sub(font_repl, xml_data)
        if win_id:
            xml_data = RX_WIN_PROP.sub(fr'\1({win_id}).\2', xml_data)
        xml_path.parent.mkdir(parents=True, exist_ok=True)
        xml_bytes = xml_data.encode(encoding='utf-8')
        # xml_path.write_text(xml, encoding='utf-8')
        # load XML
        with BytesIO(xml_bytes) as f:
            tree = ET.parse(f)
            root = tree.getroot()
        xml = XmlTree(root)
        # read all definitions
        if (defs := root.find('{ff}defines')) is not None:
            switch_defines = {sw.name: sw for node in defs.findall('switch') if (sw := new_switch(node))}
        # expand (create) swiches
        for node in root.findall('.//{ff}switch'):
            create_switch(xml, node)
        # scan switches
        if switch_defines:
            for node in root.findall('.//control[@id][@type="button"][@{ff}switch]'):
                if switch := switch_defines.get(node.get('{ff}switch', '')):
                    cid = int(node.attrib['id'])
                    subcontrol_ids = {name: int(sid) for name in switch.subcontrols
                                      if (sid := node.get(f'{{ff}}subcontrol-{name}')) is not None and sid.isdecimal()}
                    checkbox_ids[cid] = SwitchData(style=switch, state=switch.first_state(), control_id=cid,
                                                   subcontrols_id=subcontrol_ids)
        ET.register_namespace('ff', 'ff')
        out = BytesIO()
        tree.write(out, encoding='utf-8', xml_declaration=True)
        xml_bytes = out.getvalue()
        xml_bytes = re.sub(br'\n(?:[ \t]+\r?\n)+', b'\n', xml_bytes)
        xml_path.write_bytes(xml_bytes)
    except IOError:
        fflog_exc()
    return CustomXmlData(switch_defines=switch_defines, switches=checkbox_ids)


if __name__ == '__main__':
    if 0:
        from typing import Any
        def cart(seq2: Sequence[Sequence[Any]]) -> Iterator[Sequence[Any]]:
            """Print sequence."""
            end = [len(seq) for seq in seq2]
            index = [0] * len(seq2)
            while True:
                seq = [seq2[i][index[i]] for i in range(len(seq2))]
                yield seq
                for i in range(len(index) - 1, -1, -1):
                    index[i] += 1
                    if index[i] < end[i]:
                        break
                    if not i:
                        return
                    index[i] = 0
        print(list(cart(("AB", "C", "EFG"))))
        print(list(cart(((False, None), (True, None), (None,)))))
        print(list(product("AB", "C", "EFG")))
        print(list(product((False, None), (True, None), (None,))))
    elif 1:
        x = custom_xml(Path('~/work/kodi/xulek/plugin.video.fanfilm/resources/skins/Default/1080i/NewList.xml').expanduser(), Path('/tmp/a.xml'))
        print(x)
    elif 0:
        def pp(cond):
            return ''.join(('-' if v is None else str(v) for v in cond))

        flags = list(iter_flags(ControlState))
        flags.reverse()
        print(f'{flags=}')
        # print(list(product(*((None, 0, 1),)*len(flags))))
        defaults = {}
        for cond in product(*((None, 0, 1),)*len(flags)):
            src = []
            for i in range(len(flags)):
                if cond[i] is not None:
                    par = list(cond)
                    par[i] = None
                    src.append(pp(par))
                    # print(f'{pp(cond)}: <- {pp(par)}')
            # print(f'{pp(cond)}: !!')
            print(f'{pp(cond)}: {", ".join(src)}')
            defaults[cond] = ...
        # print(defaults)
    elif 1:
        def pp(cond):
            return ''.join(('-' if v is None else str(v) for v in cond))
        # for key in ControlState.attr_default_seq():
        #     print(key)
        for key, depends in ControlState.attr_default_seq().items():
            print(f'{str(key):25s}: {depends}')
        # print('-----------------------')
        # values = {tuple(key.values()): tuple(tuple(s.values()) for s in seq)
        #           for key, seq in ControlState.attr_default_seq()}
        # for key, depends in values.items():
        #     print(key, depends)
