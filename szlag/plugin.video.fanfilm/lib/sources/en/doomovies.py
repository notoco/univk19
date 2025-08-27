# -*- coding: utf-8 -*-
'''
Adapted for Fanfilm
'''
import re
from lib.ff import requests

from urllib.parse import parse_qs, urlencode

from lib.ff import cleantitle
from lib.ff import client
from lib.ff import scrape_sources
#from lib.ff.log_utils import LOGDEBUG, LOGERROR, LOGINFO, LOGWARNING, fflog


class source:
    def __init__(self):
        self.results = []
        self.priority = 1
        self.language = ["en"]
        self.domains = ['doomovies.net', 'doomovies.ga']
        self.base_link = 'https://doomovies.net'
        self.search_link = '/search/%s/feed/rss2/'
        self.ajax_link = '/wp-admin/admin-ajax.php'


    def movie(self, imdb, title, localtitle, aliases, year):
        url = {'imdb': imdb, 'title': title, 'aliases': aliases, 'year': year}
        url = urlencode(url)
        return url


    def sources(self, url, hostDict, hostprDict):
        try:
            if not url:
                return self.results
            data = parse_qs(url)
            data = dict([(i, data[i][0]) if data[i] else (i, '') for i in data])
            aliases = eval(data['aliases'])
            title = data['title']
            year = data['year']
            search_url = self.base_link + self.search_link % cleantitle.get_plus(title)
            html = client.request(search_url)
            items = client.parseDOM(html, 'item')
            r = [(client.parseDOM(i, 'link'), client.parseDOM(i, 'title')) for i in items]
            r = [(i[0][0], i[1][0]) for i in r if len(i[0]) > 0 and len(i[1]) > 0]
            #result_url = [i[0] for i in r if cleantitle.match_alias(i[1], aliases)][0]
            result_url = [i[0] for i in r if cleantitle.getsearch(i[1]).lower() in cleantitle.getsearch(title).lower()][0]
            html = client.request(result_url)
            try:
                result_year = client.parseDOM(html, 'span', attrs={'class': 'date'})[0]
                result_year = re.findall(r'(\d{4})', result_year)[0]
                check_year = cleantitle.match_year(result_year, year, data['year'])
            except Exception:
                check_year = 'Failed to find year info.' # Used to fake out the year check code.
            if not check_year:
                return self.results
            try:
                qual = client.parseDOM(html, 'strong', attrs={'class': 'quality'})[0]
            except Exception:
                qual = ''
            self.session = requests.Session()
            customheaders = {
                'Host': self.domains[0],
                'Accept': '*/*',
                'Origin': self.base_link,
                'X-Requested-With': 'XMLHttpRequest',
                'User-Agent': client.agent(),
                'Referer': result_url,
                'Accept-Encoding': 'gzip, deflate',
                'Accept-Language': 'en-US,en;q=0.9'
            }
            post_link = self.base_link + self.ajax_link
            try:
                results = re.compile('''<li id='player-option(.+?)</li>''', re.DOTALL).findall(html)
                for result in results:
                    try:
                        if '/en.png' not in result:
                            continue
                        results = re.compile(r'''data-type=['"](.+?)['"] data-post=['"](.+?)['"] data-nume=['"](\d+)['"]>''', re.DOTALL).findall(result)
                        for data_type, data_post, data_nume in results:
                            try:
                                payload = {'action': 'doo_player_ajax', 'post': data_post, 'nume': data_nume, 'type': data_type}
                                r = self.session.post(post_link, headers=customheaders, data=payload)
                                i = r.json()
                                if not i['type'] == 'iframe':
                                    continue
                                p = i['embed_url'].replace('\\', '')
                                if 'imdb.com' in p:
                                    continue
                                for source in scrape_sources.process(hostDict, p, info=qual):
                                    if scrape_sources.check_host_limit(source['source'], self.results):
                                        continue
                                    self.results.append(source)
                            except Exception:
                                #fflog('sources', 1)
                                pass
                    except Exception:
                        #fflog('sources', 1)
                        pass
            except Exception:
                #fflog('sources', 1)
                pass
            try:
                tbody = client.parseDOM(html, 'tbody')[0]
                tr = client.parseDOM(html, 'tr')
                tr = [i for i in tr if 'English' in i and not any(x in i for x in ['domain=filefactory.com', 'domain=za.gl'])]
                downloads = [(client.parseDOM(i, 'a', attrs={'target': '_blank'}, ret='href'), client.parseDOM(i, 'strong', attrs={'class': 'quality'})) for i in tr]
                downloads = [(i[0][0], i[1][0]) for i in downloads if len(i[0]) > 0 and len(i[1]) > 0]
                for download in downloads:
                    try:
                        link = client.request(download[0], timeout='6', output='geturl')
                        for source in scrape_sources.process(hostDict, link, info=download[1]):
                            if scrape_sources.check_host_limit(source['source'], self.results):
                                continue
                            self.results.append(source)
                    except Exception:
                        #fflog('sources', 1)
                        pass
            except Exception:
                #fflog('sources', 1)
                pass
            print(f'############### DOOMOVIES  RESULT   {repr(self.sources)}')
            return self.results
        except Exception:
            #fflog('sources', 1)
            return self.results


    def resolve(self, url):
        return url


