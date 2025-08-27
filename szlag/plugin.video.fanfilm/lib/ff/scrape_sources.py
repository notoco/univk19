# -*- coding: utf-8 -*-

import re

from lib.ff import client, control, source_utils
from lib.ff.log_utils import LOGDEBUG, LOGERROR, LOGINFO, LOGWARNING, fflog


######################################################
############ Used for process.
######################################################
# Using these gdriveplayer_domains in prepare_link to be lazy. Some are just fake-makes that i tossed in incase they ever show up lol.
gdriveplayer_domains = [
    "database.gdriveplayer.co",
    "database.gdriveplayer.io",
    "database.gdriveplayer.me",
    "database.gdriveplayer.us",
    "database.gdriveplayer.xyz",
    "database,gdriveplayer.co",
    "database,gdriveplayer.io",
    "database,gdriveplayer.me",
    "database,gdriveplayer.us",
    "database,gdriveplayer.xyz",  # This lines just ghetto made alts incase the api links are fuckered.
    "databasegdriveplayer.co",
    "databasegdriveplayer.io",
    "databasegdriveplayer.me",
    "databasegdriveplayer.us",
    "databasegdriveplayer.xyz",
    "series.databasegdriveplayer.co",
    "series.databasegdriveplayer.io",
    "series.databasegdriveplayer.me",
    "series.databasegdriveplayer.us",
    "series.databasegdriveplayer.xyz",  # Lazy line beisdes the first one lol.
]
gomo_domains = ["playerhost.net", "gomo.to", "gomostream.com", "gomoplayer.com"]
hlspanel_domains = ["hlspanel.xyz"]
linkbin_domains = ["linkbin.me"]
ronemo_domains = ["ronemo.com"]
source_stream_domains = []  # Saved for ramdom odd ones found later lol.
superembed_domains = ["streamembed.net"]
twoembed_domains = ["2embed.ru", "2embed.to", "2embed.cc"]
vidembed_domains = [
    "goload.io",
    "goload.pro",
    "membed1.com",
    "membed.co",
    "membed.net",
    "movembed.cc",
    "vidcloud9.com",
    "vidembed.cc",
    "vidembed.io",
    "vidembed.me",
    "vidembed.net",
    "vidnext.net",
    "vidnode.net",
    "anihdplay.com",
    "gotaku1.com",
    "playtaku.net",
    "playtaku.online",
]
vidlink_domains = ["vidlink.org"]
vidsrc_domains = ["v2.vidsrc.me", "vidsrc.me"]
voxzer_domains = ["voxzer.org"]
######################################################
############ Used for prepare_link.
######################################################
# these redirect to a new domain: clicknupload.click
clicknupload_redir_domains = [
    "clicknupload.click",
    "clicknupload.com",
    "clicknupload.link",
    "clicknupload.me",
    "clicknupload.to",
]
clicknupload_working_domains = [
    "clicknupload.cc",
    "clicknupload.club",
    "clicknupload.co",
    "clicknupload.org",
    "clicknupload.red",
]
######################################################
# Spare Alt  doodstream.co | dood.cx fails and all others redirect to doodstream.com
doodstream_redir_domains = [
    "dood.cx",
    "dood.la",
    "dood.pm",
    "dood.re",
    "dood.sh",
    "dood.so",
    "dood.to",
    "dood.watch",
    "dood.wf",
    "dood.ws",
    "dood.yt",
    "dooood.com",
]
######################################################
entervideo_failing_domains = ["entervideo.net", "eplayvid.com"]
######################################################
# Spare Alt  gotaku1.com, playtaku.net, playtaku.online
goload_failing_domains = [
    "gogohd.pro",
    "goload.io",
    "streamani.net",
    "vidstreaming.io",
    "anihdplay.com",
]
goload_redir_domains = [
    "gembedhd.com",
    "gogo-play.net",
    "gogohd.net",
    "goload.pro",
    "playgo1.cc",
]
goload_failing_domains = goload_failing_domains + goload_redir_domains
######################################################
gomoplayer_failing_domains = ["gomoplayer.com", "tunestream.net"]
######################################################
streamsb_failing_domains = [
    "p1ayerjavseen.com",
    "sbplay1.com",
    "sbplay2.xyz",
    "sbplay.org",
    "sbface.com",
]
streamsb_working_domains = [
    "aintahalu.sbs",
    "arslanrocky.xyz",
    "cloudemb.com",
    "embedsb.com",
    "embedtv.fun",
    "gomovizplay.com",
    "japopav.tv",
    "javplaya.com",
    "javside.com",
    "lvturbo.com",
    "playersb.com",
    "sbanh.com",
    "sbani.pro",
    "sbasian.pro",
    "sbbrisk.com",
    "sbchill.com",
    "sbembed1.com",
    "sbembed.com",
    "sbface.com",
    "sbfast.com",
    "sbfull.com",
    "sbhight.com",
    "sblanh.com",
    "sblongvu.com",
    "sbnet.one",
    "sbone.pro",
    "sbplay2.com",
    "sbplay.one",
    "sbrapid.com",
    "sbrity.com",
    "sbspeed.com",
    "sbthe.com",
    "sbvideo.net",
    "ssbstream.net",
    "streamovies.xyz",
    "streamsb.net",
    "streamsss.net",
    "tubesb.com",
    "tvmshow.com",
    "vidmovie.xyz",
    "vidmoviesb.xyz",
    "viewsb.com",
    "watchsb.com",
]
######################################################
# These redirect to ahvsh.com but swapped to streamhide.com for dupe checks.
streamhide_redir_domains = ["ahvsh.com", "guccihide.com", "louishide.com"]
streamhide_working_domains = [
    "streamhide.com",
    "streamhide.to",
    "movhide.pro",
    "moviesm4u.com",
    "bikurathulw.sbs",
    "javb1.com",
]
######################################################
# Spare Alt  movembed.cc | The redirects goto membed1.com i think but done now to be lazy and for dupe checks.
vidcloud9_failing_domains = [
    "membed.co",
    "vidembed.io",
    "vidembed.me",
    "vidembed.net",
    "vidcloud.icu",
]
vidcloud9_redir_domains = [
    "membed.net",
    "vidcloud9.com",
    "vidembed.cc",
    "vidnext.net",
    "vidnode.net",
]
vidcloud9_failing_domains = vidcloud9_failing_domains + vidcloud9_redir_domains
######################################################
vidcloud_failing_domains = ["vidcloud.pro", "vidcloud.is"]
######################################################
twoembed_failing_domains = ["2embed.ru", "2embed.to"]
######################################################
############ Used for each scrape def.
######################################################
scrape_gdriveplayer = True #control.setting("scrape.gdriveplayer")  # XXX missing setting 'scrape.gdriveplayer'
scrape_gomo = True #control.setting("scrape.gomo")  # XXX missing setting 'scrape.gomo'
scrape_hlspanel = True #control.setting("scrape.hlspanel")  # XXX missing setting 'scrape.hlspanel'
scrape_linkbin = True #control.setting("scrape.linkbin")  # XXX missing setting 'scrape.linkbin'
scrape_ronemo = True #control.setting("scrape.ronemo")  # XXX missing setting 'scrape.ronemo'
scrape_source_stream = True #control.setting("scrape.source_stream")  # XXX missing setting 'scrape.source_stream'
scrape_superembed = True #control.setting("scrape.superembed")  # XXX missing setting 'scrape.superembed'
scrape_twoembed = True #control.setting("scrape.twoembed")  # XXX missing setting 'scrape.twoembed'
scrape_vidembed = True #control.setting("scrape.vidembed")  # XXX missing setting 'scrape.vidembed'
scrape_vidlink = True #control.setting("scrape.vidlink")  # XXX missing setting 'scrape.vidlink'
scrape_vidsrc = True #control.setting("scrape.vidsrc")  # XXX missing setting 'scrape.vidsrc'
scrape_voxzer = True #control.setting("scrape.voxzer")  # XXX missing setting 'scrape.voxzer'
######################################################


def prepare_link(url):
    if not url:
        return
    url = url.replace(r"\/", "/")
    url = url.replace(r"\\", "")
    url = url.replace("///", "//")
    if url.startswith("//"):
        url = "https:" + url
    if not url.startswith("http"):
        url = re.sub(r"\s+", "", url)
    if not url.startswith("http"):
        # fflog('scrape_sources - prepare_link NOT-link: ' + str(url))
        return
    u = url.replace("//www.", "//")
    try:
        old_domain = re.findall("//(.+?)/", u)[0]
    except:
        # fflog('scrape_sources - prepare_link - old_domain failed-u: ' + str(u))
        return
    if old_domain in clicknupload_redir_domains:
        url = url.replace(old_domain, "clicknupload.org")
    elif old_domain in doodstream_redir_domains:
        url = url.replace(old_domain, "doodstream.com")
    elif old_domain in entervideo_failing_domains:
        url = url.replace(old_domain, "eplayvid.net")
    elif old_domain in gdriveplayer_domains:
        url = url.replace(old_domain, "databasegdriveplayer.xyz")
    elif old_domain in goload_failing_domains:
        url = url.replace(old_domain, "gotaku1.com")
    elif old_domain in gomoplayer_failing_domains:
        url = url.replace(old_domain, "xvideosharing.com")
    elif old_domain in streamhide_redir_domains:
        url = url.replace(old_domain, "streamhide.com")
    elif old_domain in streamsb_failing_domains:
        url = url.replace(old_domain, "embedsb.com")
    elif old_domain in vidcloud9_failing_domains:
        url = url.replace(old_domain, "membed1.com")
    elif old_domain in vidcloud_failing_domains:
        url = url.replace(old_domain, "vidcloud.co")
    elif old_domain in twoembed_failing_domains:
        url = url.replace(old_domain, "2embed.cc")
    elif old_domain == "aparat.cam":
        url = url.replace(old_domain, "wolfstream.tv")
    elif old_domain == "clipwatching.com":
        url = url.replace(old_domain, "highstream.tv")
    elif old_domain == "cloudvid.co":
        url = url.replace(old_domain, "cloudvideo.tv")
    elif old_domain == "fastclick.to":
        url = url.replace(old_domain, "drop.download")
    elif old_domain == "gomostream.com":
        url = url.replace(old_domain, "gomo.to")
    elif old_domain == "sendit.cloud":
        url = url.replace(old_domain, "send.cm")
    elif old_domain == "streamvid.co":
        url = url.replace(old_domain, "streamvid.cc")
    if "//vidcloud.co/embed/" in u:
        url = url.replace(
            "/embed/", "/v/"
        )  # Ghetto fix to get the resolver pattern to notice the url
    # fflog('scrape_sources - prepare_link link: ' + str(url))
    # this log line should log atleast 90% of the source links when used. altho its gonna have dupes and links from before and after various process steps.
    return url


def check_host_limit(
    item, items
):  # lazy way to not import source_utils if i dont gotta and a little less code use sorta.
    return source_utils.check_host_limit(item, items)


def check_direct(
    hostDict, url, host=None
):  # unused code saved. now works like is_host_valid but as direct lol.
    try:
        url = prepare_link(url)
        if not url:
            raise Exception()
        host = url if not host else host
        direct_check = tuple(source_utils.supported_video_extensions())
        valid, host = source_utils.is_host_valid(host, hostDict)
        if valid:
            return False, url
        elif "/hls/" in url or url.endswith(direct_check):
            return True, url
        return False, url
    except:
        fflog("check_direct", 1)
        return False, url


def make_direct_item(hostDict, link, host=None, info=None, referer=None, prep=False):
    item = {}
    try:
        if prep:
            link = prepare_link(link)
        if not link:
            return item
        host = link if host is None else host
        info = link if info is None else info
        valid, host = source_utils.is_host_valid(host, hostDict)
        quality, info = source_utils.get_release_quality(link, info)
        if referer:
            link += source_utils.append_headers({"Referer": referer})
        item = {
            "source": host,
            "quality": quality,
            "info": info,
            "language": "en",
            "url": link,
            "direct": True,
            "debridonly": False,
        }
        # fflog('scrape_sources - make_direct_item item: ' + str(item))
        return item
    except:
        fflog("make_direct_item", 1)
        return item


def make_item(hostDict, link, host=None, info=None, prep=False):
    item = {}
    try:
        if prep:
            link = prepare_link(link)
        if not link:
            return item
        host = link if host is None else host
        info = link if info is None else info
        valid, host = source_utils.is_host_valid(host, hostDict)
        if valid:
            quality, info = source_utils.get_release_quality(link, info)
            item = {
                "source": host,
                "quality": quality,
                "info": info,
                "language": "en",
                "url": link,
                "direct": False,
                "debridonly": False,
            }
        # else: fflog('scrape_sources - make_item - non-valid link: ' + str(link))
        # fflog('scrape_sources - make_item item: ' + str(item))
        return item
    except:
        fflog("make_item", 1)
        return item


def process(hostDict, link, host=None, info=None):
    sources = []
    try:
        link = prepare_link(link)
        if not link:
            return sources
        host = link if host is None else host
        info = link if info is None else info
        # if 'google' in link:
        # link = googlestream.googlepass(link)
        if any(i in host for i in gdriveplayer_domains):
            # fflog('scrape_sources - process - gdriveplayer link: '+repr(link))
            for source in gdriveplayer(link, hostDict, info=info):
                sources.append(source)
        elif any(i in host for i in gomo_domains):
            # fflog('scrape_sources - process - gomo link: '+repr(link))
            for source in gomo(link, hostDict, info=info):
                sources.append(source)
        elif any(i in host for i in hlspanel_domains):
            # fflog('scrape_sources - process - hlspanel link: '+repr(link))
            for source in hlspanel(link, hostDict, info=info):
                sources.append(source)
        elif any(i in host for i in linkbin_domains):
            # fflog('scrape_sources - process - linkbin link: '+repr(link))
            for source in linkbin(link, hostDict, info=info):
                sources.append(source)
        elif any(i in host for i in ronemo_domains):
            # fflog('scrape_sources - process - ronemo link: '+repr(link))
            for source in ronemo(link, hostDict, info=info):
                sources.append(source)
        elif any(i in host for i in source_stream_domains):
            # fflog('scrape_sources - process - source_stream link: '+repr(link))
            for source in source_stream(link, hostDict, info=info):
                sources.append(source)
        elif any(i in host for i in superembed_domains):
            # fflog('scrape_sources - process - superembed link: '+repr(link))
            for source in superembed(link, hostDict, info=info):
                sources.append(source)
        elif any(i in host for i in twoembed_domains):
            # fflog('scrape_sources - process - twoembed link: '+repr(link))
            for source in twoembed(link, hostDict, info=info):
                sources.append(source)
        elif any(i in host for i in vidembed_domains):
            # fflog('scrape_sources - process - vidembed link: '+repr(link))
            for source in vidembed(link, hostDict, info=info):
                sources.append(source)
        elif any(i in host for i in vidlink_domains):
            # fflog('scrape_sources - process - vidlink link: '+repr(link))
            for source in vidlink(link, hostDict, info=info):
                sources.append(source)
        elif any(i in host for i in vidsrc_domains):
            # fflog('scrape_sources - process - vidsrc link: '+repr(link))
            for source in vidsrc(link, hostDict, info=info):
                sources.append(source)
        elif any(i in host for i in voxzer_domains):
            # fflog('scrape_sources - process - voxzer link: '+repr(link))
            for source in voxzer(link, hostDict, info=info):
                sources.append(source)
        else:
            try:
                item = make_item(hostDict, link, host=host, info=info)
                if item:
                    sources.append(item)
                # else: fflog('scrape_sources - process - non-item link: ' + str(link))
            except:
                fflog("process", 1)
                pass
        return sources
    except Exception:
        fflog("process", 1)
        return sources


def rescrape(url, regex=None):  # unused old code saved.
    try:
        html = client.request(
            link, headers={"User-Agent": client.agent(), "Referer": link}
        )
        if regex:
            link = re.findall(regex, html)[0]
        else:
            link = re.findall(r"(?:file|source)(?:\:)\s*(?:\"|\')(.+?)(?:\"|\')", html)[
                0
            ]
        return link
    except:
        fflog("rescrape", 1)
        return url


def linkbin(link, hostDict, info=None):
    sources = []  # Last Tested/Checked: 6-28-2023  Status: Working.
    try:
        if not scrape_linkbin:
            return sources
        html = client.request(
            link, headers={"User-Agent": client.agent(), "Referer": link}
        )
        results = client.parseDOM(html, "li", attrs={"class": "signle-link"})
        results = [
            (client.parseDOM(i, "a", ret="href"), client.parseDOM(i, "a"))
            for i in results
        ]
        results = [
            (i[0][0], i[1][0]) for i in results if len(i[0]) > 0 and len(i[1]) > 0
        ]
        for result in results:
            try:
                url = prepare_link(result[0])
                if not url:
                    continue
                if info:
                    info += " " + result[1]
                else:
                    info = result[1]
                item = make_item(hostDict, url, host=None, info=info)
                if item:
                    sources.append(item)
                # else: fflog('scrape_sources - linkbin - non-item link: ' + str(url))
            except:
                fflog("linkbin", 1)
                pass
        return sources
    except Exception:
        fflog("linkbin", 1)
        return sources


def gomo(link, hostDict, info=None):
    sources = []  # Last Tested/Checked: 6-28-2023  Status: Working.
    try:
        if not scrape_gomo:
            return sources
        domain = re.findall(
            r"(?://|\.)(playerhost\.net|gomo\.to|gomostream\.com|gomoplayer\.com)/", link
        )[0]
        gomo_link = "https://%s/decoding_v3.php" % domain
        result = client.request(
            link, headers={"User-Agent": client.agent(), "Referer": link}
        )
        tc = re.compile("tc = '(.+?)';").findall(result)[0]
        token = re.compile('"_token": "(.+?)",').findall(result)[0]
        post = {"tokenCode": tc, "_token": token}

        def tsd(tokenCode):
            _13x48X = tokenCode
            _71Wxx199 = _13x48X[4:18][::-1]
            return _71Wxx199 + "18" + "432782"

        headers = {
            "Host": domain,
            "Referer": link,
            "User-Agent": client.agent(),
            "x-token": tsd(tc),
        }
        urls = client.request(
            gomo_link, XHR=True, post=post, headers=headers, output="json", timeout="5"
        )
        for url in urls:
            try:
                url = prepare_link(url)
                if not url:
                    continue
                if "gomo.to" in url or "playerhost.net" in url:
                    headers = {"User-Agent": client.agent(), "Referer": url}
                    url = client.request(
                        url, headers=headers, output="geturl", timeout="5"
                    )
                    url = prepare_link(url)
                    if not url:
                        continue
                    if url == "http://ww1.gomoplayer.com/":
                        continue
                    if any(i in url for i in gdriveplayer_domains):
                        for source in gdriveplayer(url, hostDict):
                            sources.append(source)
                    else:
                        item = make_item(hostDict, url, host=None, info=info)
                        if item:
                            sources.append(item)
                        # else: fflog('scrape_sources - gomo - non-item link1: ' + str(url))
                else:
                    item = make_item(hostDict, url, host=None, info=info)
                    if item:
                        sources.append(item)
                    # else: fflog('scrape_sources - gomo - non-item link2: ' + str(url))
            except:
                fflog("gomo", 1)
                pass
        return sources
    except Exception:
        fflog("gomo", 1)
        return sources


def gdriveplayer(link, hostDict, info=None):
    sources = []  # Last Tested/Checked: 6-28-2023  Status: Working.
    try:
        if not scrape_gdriveplayer:
            return sources
        html = client.request(
            link, headers={"User-Agent": client.agent(), "Referer": link}
        )
        servers = client.parseDOM(html, "ul", attrs={"class": "list-server-items"})[0]
        urls = client.parseDOM(servers, "a", ret="href")
        for url in urls:
            try:
                if not url or url.startswith("/player.php"):
                    continue
                url = prepare_link(url)
                if not url:
                    continue
                item = make_item(hostDict, url, host=None, info=info)
                if item:
                    sources.append(item)
                # else: fflog('scrape_sources - gdriveplayer - non-item link: ' + str(url))
            except:
                fflog("gdriveplayer", 1)
                pass
        return sources
    except Exception:
        fflog("gdriveplayer", 1)
        return sources


def vidembed(link, hostDict, info=None):
    sources = []  # Last Tested/Checked: 6-28-2023  Status: Working.
    try:
        try:
            if not scrape_vidembed:
                return sources
            html = client.request(
                link, headers={"User-Agent": client.agent(), "Referer": link}
            )
            urls = []
            urls += client.parseDOM(html, "li", ret="data-video")
            urls += client.parseDOM(html, "iframe", ret="src")
            if urls:
                for url in urls:
                    try:
                        url = prepare_link(url)
                        if not url:
                            continue
                        item = make_item(hostDict, url, host=None, info=info)
                        if item:
                            sources.append(item)
                        # else: fflog('scrape_sources - vidembed - non-item link1: ' + str(url))
                    except:
                        fflog("vidembed", 1)
                        pass
        except:
            fflog("vidembed", 1)
            pass
        try:
            item = make_item(hostDict, link, host=None, info=info)
            if item:
                sources.append(item)
            # else: fflog('scrape_sources - vidembed - non-item link2: ' + str(link))
        except:
            fflog("vidembed", 1)
            pass
        return sources
    except Exception:
        fflog("vidembed", 1)
        return sources


def vidlink(link, hostDict, info=None):
    sources = []  # Last Tested/Checked: 6-28-2023  Status: Blocked.(update_views page)
    try:
        if not scrape_vidlink:
            return sources
        postID = link.split("/embed/")[1]
        post_link = "https://vidlink.org/embed/update_views"
        headers = {"User-Agent": client.agent(), "Referer": link}
        ihtml = client.request(
            post_link, post={"postID": postID}, headers=headers, XHR=True
        )
        if ihtml:
            linkcode = client.unpacked(ihtml)
            linkcode = linkcode.replace("\\", "")
            links = re.findall(r'var file1="(.+?)"', linkcode)[0]
            stream_link = links.split("/pl/")[0]
            headers = {"Referer": "https://vidlink.org/", "User-Agent": client.agent()}
            response = client.request(links, headers=headers)
            urls = re.findall(
                r"[A-Z]{10}=\d+x(\d+)\W[A-Z]+=\"\w+\"\s+\/(.+?)\.", response
            )
            if urls:
                for qual, url in urls:
                    url = stream_link + "/" + url + ".m3u8"
                    qual = qual + " " + info if info is not None else qual
                    item = make_item(hostDict, url, host=None, info=qual)
                    if item:
                        sources.append(item)
                    # else: fflog('scrape_sources - vidlink - non-item link: ' + str(url))
        return sources
    except Exception:
        fflog("vidlink", 1)
        return sources


def vidsrc(link, hostDict, info=None):
    sources = []  # Last Tested/Checked: 6-28-2023  Status: Working.
    try:
        if not scrape_vidsrc:
            return sources
        headers = {"User-Agent": client.agent(), "Referer": "https://v2.vidsrc.me/"}
        html = client.request(link, headers=headers)
        items = client.parseDOM(html, "div", ret="data-hash")
        for item in items:
            try:
                item_url = "https://source.vidsrc.me/source/" + item
                item_html = client.request(item_url, headers=headers)
                if not item_html:
                    continue
                item_html = item_html.replace("'", '"')
                item_src = re.findall(r'src:\s*"([^"]+)"', item_html, re.DOTALL)[0]
                item_src = (
                    "https:" + item_src if item_src.startswith("//") else item_src
                )
                item_link = client.request(item_src, headers=headers, output="geturl")
                url = prepare_link(item_link)
                if not url:
                    continue
                item = make_item(hostDict, url, host=None, info=info)
                if item:
                    sources.append(item)
                # else: fflog('scrape_sources - vidsrc - non-item link: ' + str(url))
            except:
                fflog("vidsrc", 1)
                pass
        return sources
    except Exception:
        fflog("vidsrc", 1)
        return sources


def twoembed(link, hostDict, info=None):
    sources = []  # Last Tested/Checked: 6-28-2023  Status: Working.
    try:
        if not scrape_twoembed:
            return sources
        headers = {"User-Agent": client.agent(), "Referer": "https://www.2embed.cc/"}
        link = link.replace("/embed/imdb/tv?id=", "/embed/")
        link = link.replace("/embed/imdb/movie?id=", "/embed/")
        link = link.replace("/embed/tmdb/tv?id=", "/embed/")
        link = link.replace("/embed/tmdb/movie?id=", "/embed/")
        html = client.request(link, headers=headers)
        iframe = client.parseDOM(html, "iframe", ret="src")[0]
        iframe_html = client.request(iframe, headers=headers)
        iframe_unpacked = client.unpacked(iframe_html)
        iframe_sources = re.findall(r"sources:\[(.+?)\]", iframe_unpacked, re.S)[0]
        source_link = re.findall(
            r"(?:file|src)\s*(?:\:)\s*(?:\"|\')(.+?)(?:\"|\')", iframe_sources
        )[0]
        item = make_direct_item(
            hostDict, source_link, host="2embed.cc", info=info, referer=link
        )
        if item:
            sources.append(item)
        # else: fflog('scrape_sources - twoembed - non-item link: ' + str(url))
        return sources
    except Exception:
        fflog("twoembed", 1)
        return sources


def hlspanel(link, hostDict, info=None):
    sources = []
    try:
        if not scrape_hlspanel:
            return sources
        headers = {
            "User-Agent": client.agent(),
            "Referer": link,
            "X-Requested-With": "XMLHttpRequest",
        }
        url_hash = link.split("/video/")[1]
        getvid_link = (
            "https://hlspanel.xyz/player/index.php?data=%s&do=getVideo" % url_hash
        )
        data = {"hash": url_hash, "r": link}
        page = client.request(getvid_link, headers=headers, post=data, output="json")
        url = page["securedLink"]
        item = make_direct_item(hostDict, url, host=None, info=info, referer=link)
        if item:
            sources.append(item)
        return sources
    except Exception:
        fflog("hlspanel", 1)
        return sources


def superembed(link, hostDict, info=None):
    sources = []
    try:
        if not scrape_superembed:
            return sources
        r = client.request(
            link, headers={"User-Agent": client.agent(), "Referer": link}
        )
        i = client.parseDOM(r, "iframe", ret="src")[0]
        p = re.findall(r"""window.atob\('(.+?)'\)""", i)[0]
        link = base64.b64decode(p)
        link = ensure_text(link, errors="ignore")
        url = link.replace(r"\/", "/").replace("///", "//")
        item = make_item(hostDict, url, host=None, info=info)
        if item:
            sources.append(item)
        # else: fflog('scrape_sources - superembed - non-item link: ' + str(url))
        return sources
    except Exception:
        fflog("superembed", 1)
        return sources


def ronemo(link, hostDict, info=None):
    sources = []
    try:
        if not scrape_ronemo:
            return sources
        html = client.request(
            link, headers={"User-Agent": client.agent(), "Referer": link}
        )
        url = re.findall('"link":"(.+?)",', html)[0]
        item = make_direct_item(hostDict, url, host=None, info=info, referer=link)
        if item:
            sources.append(item)
        return sources
    except:
        fflog("ronemo", 1)
        return sources


def voxzer(link, hostDict, info=None):
    sources = []
    try:
        if not scrape_voxzer:
            return sources
        link = link.replace("/view/", "/list/")
        html = client.request(
            link, headers={"User-Agent": client.agent(), "Referer": link}, output="json"
        )
        url = html["link"]
        item = make_direct_item(hostDict, url, host=None, info=info, referer=link)
        if item:
            sources.append(item)
        return sources
    except Exception:
        fflog("voxzer", 1)
        return sources


def source_stream(link, hostDict, info=None):
    sources = []
    try:
        if not scrape_source_stream:
            return sources
        html = client.request(
            link, headers={"User-Agent": client.agent(), "Referer": link}
        )
        url = client.parseDOM(html, "source", ret="src")[0]
        item = make_direct_item(hostDict, url, host=None, info=info, referer=link)
        if item:
            sources.append(item)
        return sources
    except Exception:
        fflog("source_stream", 1)
        return sources
