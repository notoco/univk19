from __future__ import annotations
from typing import List
import sys
import re
from pprint import pformat
import sty
from ...fake.fake_term import print_table, formatting, text_width, text_left
from ...fake.xbmcplugin import _Item
from ..main import parse_args, sty_stdout, apply_args, start_service, stop_service


def show_info(item: _Item, index: int = 0):
    dim = sty.bg(240)
    it = item.item
    print(f'{sty.ef.bold}{sty.fg(35)}-- Info --{sty.rs.all}')
    print(f'[INFO] {index}. url={item.url}, folder={item.folder}, item={it}')
    vtag = it.getVideoInfoTag()
    descr = formatting(str(vtag.getPlot() or '')).replace('\n', f'{dim}[CR]{sty.rs.bg}')
    if text_width(descr) > 199:
        descr = f'{text_left(descr, 197)}{dim}…{sty.rs.bg}'
    print_table((
        ('Label:', repr(it.getLabel())),
        ('Label2:', repr(it.getLabel2())),
        ('Title:', repr(vtag.getTitle())),
        ('TVShowTitle:', repr(vtag.getTVShowTitle())),
        ('Year:', repr(vtag.getYear())),
        ('Duration:', repr(vtag.getDuration())),
        ('Art:', pformat(it.getArt())),
        ('Descr:', descr),
    ))


def show_extra(item: _Item, index: int = 0):
    from ...ff.info import ffinfo, FFItem, MediaRef
    show_info(item=item, index=index)
    print(33*'-')
    print(f'{item=}')
    it: FFItem = item.item
    denorm = MediaRef(it.ref.real_type, it.ffid)
    print(denorm)
    print(ffinfo.find_item(denorm))
    print_table((
        ('Poperties:', pformat(it.getProperties())),
    ))


def tui():
    from ...service.client import service_client
    from ...ff.trakt import make_console_trakt
    from ...fake.fake_api import reset as fake_reset, url_at_index, get_directory, print_last_directory

    def exec_menu(item: _Item, index: int = 0) -> bool:
        nonlocal url
        it = item.item
        cm = it._get_context_menu()
        tab = [('0.', 'Cancel', '')]
        tab.extend((f'{i}.', *m) for i, m in enumerate(cm, 1))
        index_label = f'[{index}] ' if index else ''
        print(f'{sty.ef.bold}{sty.fg(35)}-- Context menu {index_label}--{sty.rs.all}')
        cformats = ['{}', f'\b{sty.bg.da_blue}{{}}{sty.rs.all}', '{}']  # cell format
        print_table(tab, cformats=cformats)
        target = ''
        if args.run:
            while True:
                try:
                    cmd = input('Enter menu number: ')
                except EOFError:
                    sys.exit()
                if cmd.isdigit():
                    index = int(cmd)
                    if not index:
                        break
                    if 1 <= index < len(cm) + 1:
                        target = cm[index - 1][1]
                        break
                print(f'{sty.fg.red}Invalid number{sty.rs.all}')
        if (mch := re.fullmatch(r'RunPlugin\((.*)\)', target)):
            fake_reset()
            history.append(url)
            url = mch[1]
            return True
        elif args.run:
            print(f'{sty.ef.bold}{sty.bg(23)}-- {url} --{sty.rs.all}')
            print_last_directory()
        return False

    args = parse_args()
    # print(args)

    sty_stdout()
    apply_args(args)
    # print(sys.argv)

    make_console_trakt()

    url = args.url
    history: List[str] = []
    if args.service:
        service = start_service()
    else:
        service = None
        service_client.__class__.LOG_EXCEPTION = False
    try:
        while True:
            u0, sep, u2 = url.partition('?')
            sys.argv = [u0, args.handle, sep+u2, args.resume]
            print(f'{sty.ef.bold}{sty.bg(23)}-- {url} --{sty.rs.all}')
            if args.xxx:  # --- XXX ---  tests & debug  --- XXX ---
                return test_xxx()

            try:
                from ...main import main
                main(sys.argv)
            except EOFError:
                break
            if args.info:
                item = get_directory().items[args.info-1]
                show_info(item, args.info)
                args.info = None
            if args.extra_info:
                item = get_directory().items[args.extra_info-1]
                show_extra(item, args.extra_info)
                args.extra_info = None
            if args.menu == -1:
                for i, item in enumerate(get_directory().items, 1):
                    exec_menu(item, i)
                args.menu = None
            elif args.menu:
                item = get_directory().items[args.menu-1]
                redirect = exec_menu(item, args.menu)
                args.menu = None
                if redirect:
                    continue
            if args.run:
                try:
                    while True:
                        cmd = input('Enter list number: ')
                        if cmd.strip():
                            break
                        print_last_directory()
                except EOFError:
                    break
                if cmd[-1:] in 'iI' and cmd[:-1].isdigit():
                    index = int(cmd[:-1])
                    if index:
                        try:
                            item = get_directory().items[index-1]
                            it = item.item
                        except IndexError:
                            print(f'{sty.fg.red}Invalid number{sty.rs.all}')
                        else:
                            show_info(item, index)
                elif cmd[-1:] in 'cmCM' and cmd[:-1].isdigit():
                    index = int(cmd[:-1])
                    if index:
                        try:
                            item = get_directory().items[index-1]
                        except IndexError:
                            print(f'{sty.fg.red}Invalid number{sty.rs.all}')
                        else:
                            exec_menu(item, index)
                elif cmd.isdigit():
                    index = int(cmd)
                    if index:
                        try:
                            history.append(url)
                            url = url_at_index(index - 1)
                        except IndexError:
                            print(f'{sty.fg.red}Invalid number{sty.rs.all}')
                    else:
                        if history:
                            url = history.pop()
                        else:
                            url = '/'
                fake_reset()
            else:
                break
    finally:
        if service:
            stop_service(service)

        from lib.ff.kotools import destroy_xmonitor
        destroy_xmonitor()


def test_xxx(self) -> None:
    from ..ff.db import state
    from ..ff.info import ffinfo
    from ..service.client import service_client

    def test1():
        state.set('zz', value=dict(x=1, y=2), module='xxx')
        state.get('zz', module='xxx')
        state.multi_set({'aa': 42, 'bb': 44}, module='xxx')
        from threading import Thread
        def kick():
            import time
            time.sleep(1)
            print('set 1 ...................', flush=True)
            state.set(module='xxx', key='ee', value=1)
            time.sleep(1)
            print('set 2 ...................', flush=True)
            state.set(module='xxx', key='ee', value=2)
        Thread(target=kick).start()
        print('wait ....................', flush=True)
        state.wait_for_value('ee', module='xxx', value=2)
        print('hit .....................')
        print(service_client.state_get('xxx'), flush=True)

    def test2():
        from ..defs import MediaRef
        from ..ff.db import dump_value_and_type, load_value
        x, t = dump_value_and_type(MediaRef('show', 123, 42))
        print(f'{x = }, {t = }')
        y = load_value(x, type=t)
        print(f'{y = }')
        state.set(module='v', key='x', value=MediaRef('show', 123, 42))
        z = state.get(module='v', key='x')
        print(f'{z = }')
        print(f'{state.get_all(module="v") = }')

    def test3():
        import json
        from ..defs import MediaRef
        from ..ff.item import FFItem
        from ..service.misc import JsonEncoder
        # it = FFItem(MediaRef('movie', 123123))
        it = ffinfo.find_item(MediaRef('movie', 100_402_431))  # , progress=ffinfo.Progress.FULL)
        j = it.__to_json__()
        dj = json.dumps(j, indent=2, cls=JsonEncoder)
        dx = json.loads(dj)
        x = FFItem.__from_json__(dx)
        print(dj)
        print(f'{x.ref=}')
        print(f'{x.progress=}')
        # breakpoint()
        # service_client.plugin_request_exit(folder=[it])

    test3()
