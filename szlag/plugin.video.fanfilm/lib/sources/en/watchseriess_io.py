# -*- coding: UTF-8 -*-
'''
Adapted for Fanfilm
'''
import re

from urllib.parse import parse_qs, urlencode

from lib.ff import cleantitle
from lib.ff import client
from lib.ff import scrape_sources
#from lib.ff.log_utils import LOGDEBUG, LOGERROR, LOGINFO, LOGWARNING, fflog


class source:
    def __init__(self):
        self.priority = 1
        self.language = ["en"]
        self.results = []
        self.domains = ['watchseriess.io', 'watchseriess.net']
        self.base_link = 'https://watchseriess.io'
        self.search_link = '/watchseries/ajax/search?keyword=%s'
        self.notes = 'the site seems to be erroring out on item page loads. kept in the working folder incase it starts working again soon.'


    def movie(self, imdb, title, localtitle, aliases, year):
        url = {'imdb': imdb, 'title': title, 'aliases': aliases, 'year': year}
        url = urlencode(url)
        return url


    def tvshow(self, imdb, tmdb, tvshowtitle, localtvshowtitle, aliases, year):
        url = {'imdb': imdb, 'tvshowtitle': tvshowtitle, 'aliases': aliases, 'year': year}
        url = urlencode(url)
        return url


    def episode(self, url, imdb, tmdb, title, premiered, season, episode):
        if not url:
            return
        url = parse_qs(url)
        url = dict([(i, url[i][0]) if url[i] else (i, '') for i in url])
        url['title'], url['premiered'], url['season'], url['episode'] = title, premiered, season, episode
        url = urlencode(url)
        return url


    def sources(self, url, hostDict, hostprDict):
        try:
            if not url:
                return self.results
            data = parse_qs(url)
            data = dict([(i, data[i][0]) if data[i] else (i, '') for i in data])
            aliases = eval(data['aliases'])
            title = data['tvshowtitle'] if 'tvshowtitle' in data else data['title']
            season, episode = (data['season'], data['episode']) if 'tvshowtitle' in data else ('0', '0')
            year = data['premiered'].split('-')[0] if 'tvshowtitle' in data else data['year']
            search_term = '%s Season %s' % (title, season) if 'tvshowtitle' in data else title
            search_url = self.base_link + self.search_link % cleantitle.get_plus(search_term)
            r = client.request(search_url)
            r = client.parseDOM(r, 'li', attrs={'class': 'video-block'})
            if not r and 'tvshowtitle' in data:
                search_url = self.base_link + self.search_link % cleantitle.get_plus(title)
                r = client.request(search_url)
                r = client.parseDOM(r, 'li', attrs={'class': 'video-block'})
            r = [(client.parseDOM(i, 'a', ret='href'), client.parseDOM(i, 'a', ret='title')) for i in r]
            r = [(i[0][0], i[1][0]) for i in r if len(i[0]) > 0 and len(i[1]) > 0]
            if 'tvshowtitle' in data:
                r = [(i[0], re.findall(r'(.+?) Season (\d+)$', i[1])) for i in r]
                r = [(i[0], i[1][0]) for i in r if len(i[1]) > 0]
                url = [i[0] for i in r if cleantitle.match_alias(i[1][0], aliases) and i[1][1] == season][0]
            else:
                results = [(i[0], i[1], re.findall(r'\((\d{4})', i[1])) for i in r]
                try:
                    r = [(i[0], i[1], i[2][0]) for i in results if len(i[2]) > 0]
                    url = [i[0] for i in r if cleantitle.match_alias(i[1], aliases) and cleantitle.match_year(i[2], year)][0]
                except Exception:
                    url = [i[0] for i in results if cleantitle.match_alias(i[1], aliases)][0]
            url = '/' + url if not url.startswith('/') else url
            url = self.base_link +'%s-episode-%s' % (url, episode)
            html = client.request(url)
            if not 'tvshowtitle' in data:
                try:
                    qual = client.parseDOM(html, 'span', attrs={'class': 'current'})[0]
                except Exception:
                    qual = ''
            else:
                qual = ''
            links = client.parseDOM(html, 'div', attrs={'class': 'anime_muti_link'})[0]
            links = client.parseDOM(links, 'a', ret='data-video')
            for link in links:
                try:
                    for source in scrape_sources.process(hostDict, link, info=qual):
                        if scrape_sources.check_host_limit(source['source'], self.results):
                            continue
                        self.results.append(source)
                except Exception:
                    #fflog('sources', 1)
                    pass
            return self.results
        except Exception:
            #fflog('sources', 1)
            return self.results


    def resolve(self, url):
        return url


