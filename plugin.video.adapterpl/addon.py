# -*- coding: utf-8 -*-
import os
import sys

import requests
import xbmc
import xbmcgui
import xbmcplugin
import xbmcaddon
import xbmcvfs
import json
#import time
#import datetime
import urllib
from urllib.request import Request, urlopen
from urllib.parse import urlencode, quote_plus, quote, unquote, parse_qsl
import re
from html import unescape

base_url = sys.argv[0]
addon_handle = int(sys.argv[1])
params = dict(parse_qsl(sys.argv[2][1:]))
addon = xbmcaddon.Addon(id='plugin.video.adapterpl')

PATH=addon.getAddonInfo('path')
PATH_profile=xbmcvfs.translatePath(addon.getAddonInfo('profile'))
if not xbmcvfs.exists(PATH_profile):
    xbmcvfs.mkdir(PATH_profile)

img_path=PATH+'/resources/img/'
img_empty=img_path+'empty.png'
fanart=img_path+'fanart.jpg'
img_addon=PATH+'/icon.png'

UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:140.0) Gecko/20100101 Firefox/140.0'

baseurl='https://adapter.pl/'

hea={
    'User-Agent':UA,
}


def cleanTXT(x):
    y=re.compile('(&#[0-9]+?;)').findall(x)
    for yy in y:
        x=x.replace(yy,chr(int(yy[2:-1])))
    x=re.sub(re.compile('<.*?>'),'',x)
    return x

def build_url(query):
    return base_url + '?' + urlencode(query)

def addItemList(url, name, setArt, medType=False, infoLab={}, isF=True, isPla='false', contMenu=False, cmItems=[]):
    li=xbmcgui.ListItem(name)
    li.setProperty("IsPlayable", isPla)
    if medType:
        kodiVer=xbmc.getInfoLabel('System.BuildVersion')
        if kodiVer.startswith('19.'):
            li.setInfo(type=medType, infoLabels=infoLab)
        else:
            types={'video':'getVideoInfoTag','music':'getMusicInfoTag'}
            if medType!=False:
                setMedType=getattr(li,types[medType])
                vi=setMedType()
            
                labels={
                    'year':'setYear', #int
                    'episode':'setEpisode', #int
                    'season':'setSeason', #int
                    'rating':'setRating', #float
                    'mpaa':'setMpaa',
                    'plot':'setPlot',
                    'plotoutline':'setPlotOutline',
                    'title':'setTitle',
                    'originaltitle':'setOriginalTitle',
                    'sorttitle':'setSortTitle',
                    'genre':'setGenres', #list
                    'country':'setCountries', #list
                    'director':'setDirectors', #list
                    'studio':'setStudios', #list
                    'writer':'setWriters',#list
                    'duration':'setDuration', #int (in sec)
                    'tag':'setTags', #list
                    'trailer':'setTrailer', #str (path)
                    'mediatype':'setMediaType',
                    'cast':'setCast', #list        
                }
                
                if 'cast' in infoLab:
                    if infoLab['cast']!=None:
                        cast=[xbmc.Actor(c) for c in infoLab['cast']]
                        infoLab['cast']=cast
                
                for i in list(infoLab):
                    if i in list(labels):
                        setLab=getattr(vi,labels[i])
                        setLab(infoLab[i])
    li.setArt(setArt) 
    if contMenu:
        li.addContextMenuItems(cmItems, replaceItems=False)
    xbmcplugin.addDirectoryItem(handle=addon_handle, url=url, listitem=li, isFolder=isF)
    
def ISAplayer(protocol,stream_url, playHea, isDRM=False, licURL=False):
    import inputstreamhelper
    
    PROTOCOL = protocol
    DRM = 'com.widevine.alpha'
    is_helper = inputstreamhelper.Helper(PROTOCOL, drm=DRM)
    
    pt='application/x-mpegURL' if protocol=='hls' else 'application/xml+dash'
    
    if is_helper.check_inputstream():
        play_item = xbmcgui.ListItem(path=stream_url)                     
        play_item.setMimeType(pt)
        play_item.setContentLookup(False)
        play_item.setProperty('inputstream', is_helper.inputstream_addon)        
        play_item.setProperty("IsPlayable", "true")
        play_item.setProperty('inputstream.adaptive.manifest_type', PROTOCOL)
        play_item.setProperty('inputstream.adaptive.stream_headers', playHea)
        play_item.setProperty('inputstream.adaptive.manifest_headers', playHea)
        if isDRM:
            play_item.setProperty('inputstream.adaptive.license_type', DRM)
            play_item.setProperty('inputstream.adaptive.license_key', licURL)        
    
    xbmcplugin.setResolvedUrl(addon_handle, True, listitem=play_item)

def directPlayer(stream_url,heaP=None):
    if heaP!=None:
        stream_url+='|'+heaP
    play_item = xbmcgui.ListItem(path=stream_url)
    play_item.setProperty("IsPlayable", "true")
    xbmcplugin.setResolvedUrl(addon_handle, True, listitem=play_item)


def main_menu():
    resp=requests.get(baseurl,headers=hea).text
    resp1=resp.split('id=\"movie-categories\"')[1].split('</ul')[0]
    items=re.compile('href=\"([^"]+?)\".*>(.*)</a').findall(resp1)
    for i in items:
        setArt={'thumb': '', 'poster': img_addon, 'banner': '', 'icon': 'DefaultAddonVideo.png', 'fanart':fanart}
        url=build_url({'mode':'categList','link':i[0]})
        addItemList(url, i[1], setArt)
    
    items=[
        ['Szukaj','search','DefaultAddonsSearch.png'],
        ['Ulubione','favList','DefaultMusicRecentlyAdded.png'],
    ]
    for j in items:
        setArt={'thumb': '', 'poster': img_addon, 'banner': '', 'icon': j[2], 'fanart':fanart}
        url=build_url({'mode':j[1]})
        addItemList(url, j[0], setArt)
    
    xbmcplugin.endOfDirectory(addon_handle)
'''
def filterList(l):
    items=[
        ['wg gatunku','gatunek'],
        ['wg udogodnienia','dostosowanie']
    ]
    for i in items:
        setArt={'thumb': '', 'poster': img_addon, 'banner': '', 'icon': 'DefaultAddonVideo.png', 'fanart':fanart}
        url=build_url({'mode':'categList','link':l,'filt':i[1]})
        addItemList(url, i[0], setArt)
    
    xbmcplugin.endOfDirectory(addon_handle)
'''    

def categList(l):
    resp=requests.get(l,headers=hea).text
    resp1=resp.split('main-catalog__list')[1].split('</div')[0]
    categs=re.compile('<a href=\"([^"]+?)\".*>(.*)</a>').findall(resp1)
    for c in categs:
        img='DefaultGenre.png'
        setArt={'thumb': img, 'poster': img, 'banner': img, 'icon': img, 'fanart':fanart}
        url=build_url({'mode':'itemList','link':c[0]})
        addItemList(url, c[1], setArt)
    
    xbmcplugin.endOfDirectory(addon_handle)

def getList(resp): #helper
    resp1=resp.split('\"movie-grid\"')[1].split('\"main-subcategory__recommended\"')[0].split('\"media-thumb-full\"')
    for r in resp1:
        if 'media-thumb-full__info' in r:
            img,title=re.compile('<img src=\"([^"]+?)\" alt=\"([^\"]+?)\"').findall(r)[0]
            title=cleanTXT(title)
            link=re.compile('href=\"([^"]+?)\"').findall(r)[0]
            img=re.compile('img src=\"([^"]+?)\"').findall(r)[0]
            desc=re.compile('\"media-thumb-full__excerpt\">([^<]+?)<').findall(r)[0]
            
            iL={'plot':desc,'title':title,'mediatype':'movie'}
            setArt={'thumb': img, 'poster': img, 'banner': '', 'icon': img, 'fanart':fanart}
            url=build_url({'mode':'playVid2','link':link})
            
            cmItems=[
                ('[B]Szczegóły[/B]','RunPlugin(plugin://plugin.video.adapterpl?mode=showDet&link='+link+')'),
                ('[B]Dodaj do ulubionych[/B]','RunPlugin(plugin://plugin.video.adapterpl?mode=favAdd&url='+quote(url)+'&title='+quote(title)+'&iL='+quote(str(iL))+'&setart='+quote(str(setArt))+')'),
                #('[B]Audiowstęp[/B]','RunPlugin(plugin://plugin.video.adapterpl?mode=aud&link='+link+')'),
                
            ]

            addItemList(url, title, setArt, 'video', iL, False, 'false', True, cmItems)
    
    xbmcplugin.setContent(addon_handle, 'videos')     
    xbmcplugin.endOfDirectory(addon_handle)
    
def itemList(l):
    resp=requests.get(l,headers=hea).text
    getList(resp)

def playVid2(l):
    resp=requests.get(l,headers=hea)
    playable=False
    if 'logowanie' in resp.url:
        playable=True
    elif 'id-video=' in resp.text:
        playable=True
    if playable:
        xbmc.executebuiltin('PlayMedia(plugin://plugin.video.adapterpl?mode=playVid&link='+quote(l)+')')
    else:
        xbmc.executebuiltin('Container.Update(plugin://plugin.video.adapterpl?mode=itemList&link='+quote(l)+')')

def playVid(l):
    resp=requests.get(l,headers=hea)
    if 'logowanie' in resp.url:
        xbmcgui.Dialog().notification('Adapter PL', 'Film dostępny po zalogowaniu', xbmcgui.NOTIFICATION_INFO)
        xbmcplugin.setResolvedUrl(addon_handle, False, xbmcgui.ListItem())
    else:
        resp=resp.text
        url_stream=''
        vid=re.compile('id-video=\"([^"]+?)\"').findall(resp)
        vidURL=re.compile('data-video-url=\"([^"]+?)\"').findall(resp)
        #vidHLS=re.compile('data-atende-video-url-hls=\"([^"]+?)\"').findall(resp)
        #vidDASH=re.compile('data-atende-video-url-dash=\"([^"]+?)\"').findall(resp)
        print(vid)
        print(vidURL)
        
        hea.update({'Referer':baseurl,'Origin':baseurl[:-1],'Accept':'*/*','Connection':'keep-alive'})
        
        if len(vid)>0:
            url_stream='https://media.adapter.pl/%s/hls/playlist.m3u8'%(vid[0])
            ISAplayer('hls',url_stream,urlencode(hea))
        elif len(vidURL)>0:
            url_stream=vidURL[0]
        
        
        if url_stream!='':
            if '.m3u' in url_stream:
                protocol='hls'
            elif '.mpd' in url_stream:
                protocol='mpd'
            else:
                protocol=None
            
            if protocol!=None:
                
                resp=requests.get(url_stream,headers=hea).text
                print(url_stream)
                print(resp)
                
                ISAplayer(protocol,url_stream,urlencode(hea))
            else:
                xbmcgui.Dialog().notification('Adapter PL', 'Nieznany protokół', xbmcgui.NOTIFICATION_INFO)
                xbmcplugin.setResolvedUrl(addon_handle, False, xbmcgui.ListItem())
            
        else:
            xbmcgui.Dialog().notification('Adapter PL', 'Brak źródeł', xbmcgui.NOTIFICATION_INFO)
            xbmcplugin.setResolvedUrl(addon_handle, False, xbmcgui.ListItem())
    

def movieDet(resp):#helper
    data={}
    resp1=resp.split('class=\"movie-info\"')[1].split('\"main-single__description\"')[0].split('class=\"movie-info__item\"')
    for r in resp1:
        if 'movie-info__item__heading' in r:
            label=re.compile('\"movie-info__item__heading\">([^<]+?)</p').findall(r)[0]
            val_1=re.compile('\"movie-info__item__text\">([^<]+?)</p>').findall(r)
            val_2=re.compile('\"movie-info__item__url\">([^<]+?)</a>').findall(r)
            val_3=re.compile('\"movie-info__item__entry\">([^<]+?)</li>').findall(r)
            if len(val_1)>0:
                val=', '.join(val_1)
            elif len(val_2)>0:
                val=', '.join(val_2)
            else:
                val=(', '.join(val_3)).replace('\n','').replace(' ','').replace(',',', ')
            data[label]=val
    
    resp2=resp.split('\"main-single__description\"')[1].split('class=\"catcolor\"')
    for r in resp2:
        if 'Opis filmu' in r:
            items=re.compile('<p>([^<]+?)</p>').findall(r)
            val='\n'.join(items)
            data['Opis filmu']=val
    
    return data
    
def showDet(l):
    resp=requests.get(l,headers=hea)
    if '/logowanie' in resp.url:
        plot='Wymagane logowanie'
    
    else:
        try:
            data=movieDet(resp.text)
            
            plot=''
            for d in list(data.keys()):
                plot+='[B]%s: [/B]%s\n'%(d,unescape(data[d]))
        except:
            plot=''
                
    if plot=='':
        plot='Brak danych'
    dialog = xbmcgui.Dialog()
    dialog.textviewer('Szczegóły', plot)
    
def aud(l):
    resp=requests.get(l,headers=hea)
    if '/logowanie' not in resp.url:
        vid=re.compile('id-video=\"([^"]+?)\"').findall(resp.text)
        vv=[v for v in vid if v.endswith('-aw')]
        if len(vv)>0:
            test=True
            url='https://media.adapter.pl/'+vv[0]+'/hls/playlist.m3u8'
            play_item = xbmcgui.ListItem(path=url)
            play_item.setProperty("IsPlayable", "true")
            xbmc.Player().play(url, play_item)
        else:
            test=False
    else:
        test=False
    if not test:
        xbmcgui.Dialog().notification('Adapter PL', 'Audiowstęp niediostępny', xbmcgui.NOTIFICATION_INFO)

def search(q):
    url=baseurl+'?s='+quote_plus(q)
    resp=requests.get(url,headers=hea).text
    if 'Brak wyników wyszukiwania' not in resp:
        getList(resp)
    else:
        xbmcplugin.endOfDirectory(addon_handle)        

#FAV            
def openJSON(u):
    try:
        f=open(u,'r',encoding = 'utf-8')
    except:
        f=open(u,'w+',encoding = 'utf-8')
    cont=f.read()
    f.close()
    try:
        js=eval(cont)
    except:
        js=[]
    return js
    
def saveJSON(u,j):
    with open(u, 'w', encoding='utf-8') as f:
        json.dump(j, f, ensure_ascii=False, indent=4)

def favList():
    fURL=PATH_profile+'ulubione.json'
    js=openJSON(fURL)
    for j in js:
        if 'playVid' in j[0]:
            isPlayable='false'
            isFolder=False
            link=j[0].split('link=')[-1]
        else:
            isPlayable='false'
            isFolder=True
            link=None

        contMenu=True
        cmItems=[
            ('[B]Usuń z ulubionych[/B]','RunPlugin(plugin://plugin.video.adapterpl?mode=favDel&url='+quote(j[0])+')'),
        ]
        if link!=None:
            cmItems.append(('[B]Szczegóły[/B]','RunPlugin(plugin://plugin.video.adapterpl?mode=showDet&link='+link+')'))
        setArt=eval(j[3])
        iL=eval(j[2])
        addItemList(j[0], j[1], setArt, 'video', iL, isFolder, isPlayable, contMenu, cmItems)
        
    xbmcplugin.setContent(addon_handle, 'videos')     
    xbmcplugin.endOfDirectory(addon_handle)

def favDel(c):
    fURL=PATH_profile+'ulubione.json'
    js=openJSON(fURL)
    for i,j in enumerate(js):
        if  j[0]==c:
            del js[i]
    saveJSON(fURL,js)
    xbmc.executebuiltin('Container.Refresh()')

def favAdd(u,t,iL,art):
    fURL=PATH_profile+'ulubione.json'
    js=openJSON(fURL)
    duplTest=False
    for j in js:
        if j[0]==u:
            duplTest=True
    if not duplTest:
        js.append([u,t,iL,art])
        xbmcgui.Dialog().notification('Adapter PL', 'Dodano do ulubionych', xbmcgui.NOTIFICATION_INFO)
    else:
        xbmcgui.Dialog().notification('Adapter PL', 'Materiał jest już w ulubionych', xbmcgui.NOTIFICATION_INFO)
    saveJSON(fURL,js)



mode = params.get('mode', None)

if not mode:
    main_menu()
else:
        
    if mode=='categList':
        link=params.get('link')
        categList(link)
    
    if mode=='itemList':
        link=params.get('link')
        itemList(link)
    
    if mode=='showDet':
        link=params.get('link')
        showDet(link)
    
    if mode=='playVid2':
        link=params.get('link')
        playVid2(link)
    
    if mode=='playVid':
        link=params.get('link')
        playVid(link)
        
    if mode=='search':
        query = xbmcgui.Dialog().input('Szukaj, Podaj tytuł:', type=xbmcgui.INPUT_ALPHANUM)
        xbmcplugin.endOfDirectory(addon_handle, cacheToDisc=False)
        if query:
            xbmc.executebuiltin('Container.Update(plugin://plugin.video.adapterpl/?mode=searchRes&q='+query+')')
        else:
            xbmc.executebuiltin('Container.Update(plugin://plugin.video.adapterpl/,replace)')
    
    if mode=='searchRes':
        q=params.get('q')
        search(q)
    
    if mode=='aud':
        link=params.get('link')
        aud(link)
        
    
    #FAV    
    if mode=='favList':
        favList()
        
    if mode=='favDel':
        u=params.get('url')
        favDel(u)
        
    if mode=='favAdd':
        u=params.get('url')
        t=params.get('title')
        iL=params.get('iL')
        setart=params.get('setart')
        favAdd(u,t,iL,setart)
    