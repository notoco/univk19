# -*- coding: utf-8 -*-
import os
import sys

import requests
import xbmc
import xbmcgui
import xbmcplugin
import xbmcaddon
import xbmcvfs
import re
import json
import random
import time
import datetime
import math
from base64 import b64decode as getData
from base64 import b64encode as expData
from urllib.parse import urlencode, quote_plus, quote, unquote, parse_qsl

from resources.lib.base import b

base=b(sys.argv[0],int(sys.argv[1]))

base_url=base.base_url
addon_handle= base.addon_handle
params = dict(parse_qsl(sys.argv[2][1:]))
addon = base.addon
PATH=addon.getAddonInfo('path')
PATH_profile=base.PATH_profile
if not xbmcvfs.exists(PATH_profile):
    xbmcvfs.mkdir(PATH_profile)
img_empty=PATH+'/resources/img/empty.png'
img_addon=PATH+'/icon.png'
fanart=PATH+'/resources/img/tlo.jpg'

baseurl=base.baseurl
#apiAuth=base.apiAuth
#client_id=base.client_id

UA=base.UA
hea=base.hea
platform=base.platform
heaWeb=base.heaWeb

def openF(u):
    try:
        f=open(u,'r',encoding = 'utf-8')
    except:
        f=open(u,'w+',encoding = 'utf-8')
    cont=f.read()
    f.close()
    return cont
    
def saveF(u,t):
    with open(u, 'w', encoding='utf-8') as f:
        f.write(t)

def sortMethod():
    sm=''
    m=addon.getSetting('sortContent')
    tb={
        'Najnowsze':'sort=createdAt&order=desc',
        'Najstarsze':'sort=createdAt&order=asc',
        'A-Z':'order=asc',
        'Z-A':'order=desc'
    }
    return tb[m] 
        
def locTime(x):
    y=datetime.datetime(*(time.strptime(x,'%Y-%m-%d %H:%M:%S')[0:6]))
    z=y.strftime('%Y-%m-%d %H:%M')
    return z
    
def strToDate(x):
    return datetime.datetime(*(time.strptime(x, '%Y-%m-%d %H:%M:%S')[0:6]))

mainCategs=[
    ['SERIALE','categList','1','DefaultAddonVideo.png'],
    ['FILMY','categList','3','DefaultAddonVideo.png'],
    ['PROGRAMY','categList','2','DefaultAddonVideo.png'],
    ['DLA DZIECI','categList','4','DefaultAddonVideo.png'],
    ['SPORT','categList','5','DefaultAddonVideo.png'],
    ['NEWS','categList','96','DefaultAddonVideo.png'],
    ['DISCOVERY+','categList','29','DefaultAddonVideo.png'],
    ['EUROSPORT Extra','schedule','24','DefaultAddonVideo.png'],#
    ['TV','tv','live','DefaultTVShows.png'],
    ['Archiwum TV','tv','replay','DefaultTVShows.png'],
    ['Strona główna','mainPage','main','OverlayUnwatched.png'],
    ['Ostatnio dodane','mainPage','recently_added','OverlayUnwatched.png'],
    ['wyszukiwarka','search','','DefaultAddonsSearch.png'],
    ['ULUBIONE','favList','','DefaultMusicRecentlyAdded.png'],
]

category={'1':'seriale-online','2':'programy-online','3':'filmy-online','4':'bajki-dla-dzieci','5':'strefa-sport','96':'news','131':'ostatnio-dodane','29':'discovery-plus','24':'eurosport'}

def main_menu():
    menu=mainCategs    

    for m in menu:
        if m[1]=='categList' or m[1]=='mainPage' or m[1]=='schedule':
            URL=base.build_url({'mode':m[1],'mainCateg':m[2]})
        elif m[1]=='tv' or  m[1]=='tvPla':
            URL=base.build_url({'mode':m[1],'type':m[2]})
        else:
            URL=base.build_url({'mode':m[1]})

        img=img_addon if m[3]=='OverlayUnwatched.png' else ''
        
        setArt={'thumb': '', 'poster': img, 'banner': '', 'icon': m[3], 'fanart':fanart}
        base.addItemList(URL, m[0], setArt, 'video')
    xbmcplugin.endOfDirectory(addon_handle)


def schedule(mc):
    now=datetime.datetime.now()
    for i in range(0,8): 
        date=(now-datetime.timedelta(days=i*1)).strftime('%Y-%m-%d')
        
        setArt={'thumb': '', 'poster': '', 'banner': '', 'icon': 'DefaultYear.png', 'fanart':fanart}
        url=base.build_url({'mode':'categList','mainCateg':mc,'date':date})
        base.addItemList(url, date, setArt, 'video')
    xbmcplugin.endOfDirectory(addon_handle)
    
        
def categList(mc,date=None):
    u=baseurl+'playerapi/item/category/'+mc+'/genre/list?4K=true&platform='+platform
    if mc in ['24']:#ES extra (schedule)
        ds='%s 00:00:00'%(date)
        de='%s 23:59:00'%(date)
        s=datetime.datetime(*(time.strptime(ds,'%Y-%m-%d %H:%M:%S')[0:6])).timestamp()
        e=datetime.datetime(*(time.strptime(de,'%Y-%m-%d %H:%M:%S')[0:6])).timestamp()
        since=str(int(s)*1000)
        till=str(int(e)*1000)
        u+='&airingSince=%s&airingTill=%s'%(since,till)
        
    else:
        since=''
        till=''
     
    resp=requests.get(u,headers=base.heaGen(),cookies=base.cookiesGen()).json()
    arCateg=[['[B]Wszystkie[/B]','all']]
    for c in resp:
        arCateg.append([c['name'],c['id']])
    for ac in arCateg:        
        setArt={'thumb': '', 'poster': '', 'banner': '', 'icon': 'DefaultGenre.png', 'fanart':fanart}
        url = base.build_url({'mode':'contList','mainCateg':mc,'Categ':str(ac[1]),'page':'1','since':since,'till':till})
        base.addItemList(url, ac[0], setArt, 'video')
    xbmcplugin.endOfDirectory(addon_handle)


def detCont(x):
    #types: VOD,SERIAL,EPISODE,BANNER,SECTION,LIVE
    title=x['season']['serial']['title'] if x['type']=='EPOSODE' else x['title'] 
    rating=str(x['rating']) if 'rating' in x else ''
    ep=x['episode'] if x['type']=='EPISODE' else 0
    seas=x['season']['number'] if x['type']=='EPISODE' else 0
    descShort=cleanText(x['lead']) if 'lead' in x else ''
    desc=cleanText(x['description']) if 'description' in x else ''
    desc=descShort if desc=='' else desc
    dur=x['duration'] if 'duration' in x else 0
    year=x['year'] if 'year' in x else 0
    country=[c['name'] for c in x['countries']] if 'countries' in x else []
    actors=[c['name'] for c in x['actors']] if 'actors' in x else []
    directors=[c['name'] for c in x['directors']] if 'directors' in x else []
    scriptwriters=[c['name'] for c in x['scriptwriters']] if 'scriptwriters' in x else []
    genre=[c['name'] for c in x['genres']] if 'genres' in x else []
    tags=[c['name'] for c in x['tags']] if 'tags' in x else []
    
    #dostępność
    avail=''
    availLabel=''
    if 'displaySchedules' in x:
        i_cur=[i for i,t in enumerate(x['displaySchedules']) if t['active'] ][0]
        
        if x['displaySchedules'][i_cur]['type']!='SOON':
            if 'payable' in x:
                if x['payable']:
                    avail+='Płatny\n'
                else:
                    avail+='[B][COLOR=yellow]Bezpłatny\n[/COLOR][/B]'
                    if 'payableSince' in x:
                        avail+='[COLOR=yellow]do: %s\n[/COLOR]'%(x['payableSince'])

            if 'since' in x['displaySchedules'][i_cur]:
                avail+='[B]Data publikacji: [/B]'+x['displaySchedules'][i_cur]['since'].split(' ')[0]+'\n'
            
            if x['displaySchedules'][i_cur]['type']=='PREMIERE':
                if 'till' in x['displaySchedules'][i_cur]:
                    avail+='[B]Dostępny do: [/B]'+locTime(x['displaySchedules'][i_cur]['till'])+'\n'
                avail+='[COLOR=yellow]PRAPREMIERA[/COLOR]\n'
            else:
                if 'till' in x['displaySchedules'][i_cur]:
                    avail+='[B]Dostępny do: [/B]'+locTime(x['displaySchedules'][i_cur]['till'])+'\n'
                if x['displaySchedules'][i_cur]['type']=='LAST_BELL':
                    availLabel='LAST_BELL|'+locTime(x['displaySchedules'][i_cur]['till'])
                    avail+='[COLOR=yellow]OSTATNIA SZANSA[/COLOR]\n'
            
        else:
            availLabel='SOON'
            if 'till' in x['displaySchedules'][i_cur]:
                avail+='[COLOR=yellow]WKRÓTCE[/COLOR]\n'
                avail+='[B]Dostępny od: [/B]'+locTime(x['displaySchedules'][i_cur]['till'])+'\n'
            else: #reklamy materiałów z player.pl
                avail+='[COLOR=yellow]OGLĄDAJ w player.pl[/COLOR]\n'
    
    descShort=avail+descShort
    desc=avail+desc
    
    iL={}
    if x['type']=='EPISODE':
        iL={'title': title,'sorttitle': title,'mpaa':rating,'plotoutline':descShort,'plot': desc,'year':year,'genre':genre,'duration':dur*60,'director':directors,'country':country,'cast':actors,'writer':scriptwriters,'season':seas,'episode':ep,'mediatype':'episode'}
    elif x['type'] in ['VOD','SERIAL']:
        iL={'title': title,'sorttitle': title,'mpaa':rating,'plotoutline':descShort,'plot': desc,'year':year,'genre':genre,'duration':dur*60,'director':directors,'country':country,'cast':actors,'writer':scriptwriters,'mediatype':'movie'}
        if x['type']=='SERIAL':
            iL['mediatype']='tvshow'
    else:
        iL={'plot':title}

    return iL,availLabel,tags

def getImg(x):#
    try:
        img=x['pc'][0]['mainUrl']
    except:
        img=''
    if img.startswith('//'):
        img='https:'+img
    return img
    
def titleWithTill(d,t):#data dostępności w tytule
    title=t
    if 'LAST_BELL' in d:
        title=t+' [COLOR=yellow]/do: '+d.split('|')[1]+'/[/COLOR]'
    if 'SOON' in d:
        title='[COLOR=gray]%s[/COLOR]'%(title)

    return title

def contList(mc,c,p,v=None,since=None,till=None):
    cnt=addon.getSetting('listCount') if p!='1' else '500'
    #cnt='1000'
    start=(int(p)-1)*int(cnt)
    if c=='all':
        u=baseurl+'playerapi/product/vod/list?'+sortMethod()+'&maxResults='+cnt+'&firstResult='+str(start)+'&category[]='+category[mc]+'&4K=true&platform='+platform
    else:
        u=baseurl+'playerapi/product/vod/list?'+sortMethod()+'&maxResults='+cnt+'&firstResult='+str(start)+'&category[]='+category[mc]+'&genreId[]='+c+'&4K=true&platform='+platform
    if v:
        u+='&vodType[]='+'&vodType[]='.join(eval(v))
    if mc=='131': #ostatnio dodane    
        u=u.replace(sortMethod()+'&','')
        u+='&createdSinceDays=14'

    if since!=None and till!=None: #eurosport extra
        if c=='all':
            u=baseurl+'playerapi/product/vod/list?sort=airingSince&order=asc&airingSince='+since+'&airingTill='+till+'&maxResults='+cnt+'&firstResult='+str(start)+'&category[]='+category[mc]+'&4K=true&platform='+platform #
        else:
            u=baseurl+'playerapi/product/vod/list?sort=airingSince&order=asc&airingSince='+since+'&airingTill='+till+'&maxResults='+cnt+'&firstResult='+str(start)+'&category[]='+category[mc]+'&genreId[]='+c+'&4K=true&platform='+platform #

    u+='&vodFilter[]=AVAILABLE'
    #

    #print(u)
    resp=requests.get(u,headers=base.heaGen(),cookies=base.cookiesGen()).json()
    total=resp['meta']['totalCount']
    if p=='1':
        if total!=0 and len(resp['items'])!=0:
            result=len([r['id'] for r in resp['items'] if not r['payable']])
            if result!=0:
                ratio=int(cnt)/result
                new_cnt=min(int((100*ratio)/100)*100,total,500)
                addon.setSetting('listCount',str(new_cnt))
                if new_cnt!=500:
                    u=u.replace('&maxResults='+cnt,'&maxResults='+str(new_cnt))
                    cnt=str(new_cnt)
                    resp=requests.get(u,headers=base.heaGen(),cookies=base.cookiesGen()).json()

    for r in resp['items']:
        #if not (addon.getSetting('subscr')!='AVOD' and r['id'] not in avails) or not r['payable']:
        if not r['payable']:
            addContToList(r,since=since,till=till)
  
    if start+int(cnt)+1<total:
        vodType='' if v==None else str(v)
        since='' if since==None else since
        till='' if till==None else till
        
        setArt={'thumb': '', 'poster': '', 'banner': '', 'icon': img_empty, 'fanart':fanart}
        url = base.build_url({'mode':'contList','mainCateg':mc,'Categ':c,'page':str(int(p)+1),'vodType':vodType,'since':since,'till':till})
        base.addItemList(url, '[B][COLOR=cyan]>>> Następna strona[/COLOR][/B]', setArt, 'video')
    
    xbmcplugin.setContent(addon_handle, 'videos')    
    xbmcplugin.endOfDirectory(addon_handle)

def sezonList(cid,tit):
    u=baseurl+'playerapi/product/vod/serial/'+cid+'/season/list?4K=true&platform='+platform
    resp=requests.get(u,headers=base.heaGen(),cookies=base.cookiesGen()).json()
    if len(resp)==1: #jeden sezon
        sezId=str(resp[0]['id'])
        episodeList(cid,sezId,tit,'1','yes')
    else:
        for r in resp:
            sez_id=str(r['id'])
            sez_name=r['title']
            if sez_name=='':
                sez_name='sezon '+str(r['number'])
            
            iL={'title': '','sorttitle': '','plot': tit}
            setArt={'thumb': '', 'poster': '', 'banner': '', 'icon': '', 'fanart':fanart}
            url = base.build_url({'mode':'episodeList','cid':cid,'sezId':sez_id,'title':tit,'init':'yes','page':'1'})
            base.addItemList(url, sez_name, setArt, 'video', iL)
        xbmcplugin.setContent(addon_handle, 'videos')
        xbmcplugin.endOfDirectory(addon_handle)    

def episodeList(cid,sezId,tit,pg,init):
    cnt=int(addon.getSetting('epCount'))
    p=int(pg)
    if init=='yes':
        u=baseurl+'playerapi/product/vod/serial/'+cid+'/season/'+sezId+'/episode/list?4K=true&platform='+platform
        resp=requests.get(u,headers=base.heaGen(),cookies=base.cookiesGen()).json()#list
        saveF(PATH_profile+'episodes.txt',str(resp))
    
    resp=eval(openF(PATH_profile+'episodes.txt'))
    total=len(resp)
    start=cnt*(p-1)
    stop=min(cnt*(p-1)+cnt,total)
    for i in range(start,stop):
        r=resp[i]
        if not r['payable']:
            addContToList(r)
    
    nextPage=False        
    if p<math.ceil(total/cnt):
        nextPage=True
        setArt={'thumb': '', 'poster': '', 'banner': '', 'icon': img_empty, 'fanart':fanart}
        url = base.build_url({'mode':'episodeList','init':'no','cid':cid,'sezId':sezId,'title':tit,'page':str(p+1)})
        base.addItemList(url, '[B][COLOR=cyan]>>> Następna strona[/COLOR][/B]', setArt, 'video')
    
    xbmcplugin.setContent(addon_handle, 'videos')
    if not nextPage:
        xbmcplugin.addSortMethod(handle=addon_handle,sortMethod=xbmcplugin.SORT_METHOD_EPISODE)
    xbmcplugin.endOfDirectory(addon_handle)
    
def showDet(eid):#menu kont
    u=baseurl+'playerapi/product/vod/'+eid+'?4K=true&platform='+platform
    resp=requests.get(u,headers=base.heaGen(),cookies=base.cookiesGen()).json()
    iL,availLabel,tags=detCont(resp)
    
    plot='[B]Rok prod:[/B] %s\n'%(str(iL['year']))
    plot+='[B]Kraj:[/B] %s\n'%(', '.join(iL['country']))
    plot+='[B]Gatunek:[/B] %s\n'%(', '.join(iL['genre']))
    plot+='[B]Czas:[/B] %s min.\n'%(str(int(iL['duration']/60)))
    plot+='[B]Ograniczenia wiekowe:[/B] %s lat\n'%(str(iL['mpaa']))
    if len(iL['cast'])>0:
        plot+='[B]Obsada:[/B] %s\n'%(', '.join(iL['cast']))
    if len(iL['director'])>0:
        plot+='[B]Reżyseria:[/B] %s\n'%(', '.join(iL['director']))
    if len(iL['writer'])>0:
        plot+='[B]Scenariusz:[/B] %s\n'%(', '.join(iL['writer']))
    plot+='[B]Tagi:[/B] [I]%s[/I]\n\n'%(', '.join(tags))
    plot+=iL['plot']
    
    dialog = xbmcgui.Dialog()
    dialog.textviewer('Szczegóły', plot)
    

def playVid(eid,type,resume,isT,ts,te=None,pid=None): 
    global base
    if pid!=None: #catchup
        u=baseurl+'playerapi/product/'+type+'/epg/'+eid+'?4K=true&platform='+platform
    else:
        u=baseurl+'playerapi/product/'+type+'/'+eid+'?4K=true&platform='+platform

    resp=requests.get(u,headers=base.heaGen(),cookies=base.cookiesGen()).json()

    tid=resp['shareUrl'].replace(baseurl,'').replace(',','_').replace('-','_').replace('/','_')

    if not isT:
        iL,availLabel,tags=detCont(resp)
    
    if isT: #TV
        if pid==None: #live
            u=baseurl+'playerapi/item/'+eid+'/playlist?type=LIVE&page='+tid+'&4K=true&platform='+platform
        else: #catchup
            u=baseurl+'playerapi/item/'+pid+'/playlist?type=CATCHUP&page='+tid+'&4K=true&platform='+platform
    else:
        u=baseurl+'playerapi/item/'+eid+'/playlist?type=MOVIE&page='+tid+'&4K=true&platform='+platform+'&version=3.1'

    resp=requests.get(u,headers=base.heaGen(),cookies=base.cookiesGen()).json()

    if 'code' in resp:
        if resp['code']=='ITEM_NOT_PAID':
            xbmcgui.Dialog().notification('VODpl', 'Brak w pakiecie', xbmcgui.NOTIFICATION_INFO)
        else:
            xbmcgui.Dialog().notification('VODpl', 'Materiał niedostępny: '+resp['code'], xbmcgui.NOTIFICATION_INFO)
        xbmcplugin.setResolvedUrl(addon_handle, False, xbmcgui.ListItem())
        return
            
    protocol='mpd'
    s_url=resp['movie']['video']['sources']['dash']['url']
    hea_player='User-Agent='+UA+'&Referer='+baseurl
    if 'protections' not in resp['movie']['video']:
        drm=False
        protocol='mpd'
        s_url=resp['movie']['video']['sources']['dash']['url']
    elif 'widevine' in resp['movie']['video']['protections']:
        drm=True
        hea.update({'Content-Type':''})
        heaLic=urlencode(hea)
        lic_url=resp['movie']['video']['protections']['widevine']['src']
        #K21
        lic_key='%s|%s|R{SSM}|'%(lic_url,heaLic) 
        #K22
        drm_config=drm_cfg = {
            "com.widevine.alpha": {
                "license": {
                    "server_url": lic_url,
                    "req_headers": heaLic
                }
            }
        }
    else: #EUROSPORT
        drm=False
        protocol='hls'
        s_url=resp['movie']['video']['sources']['hls']['url']
    
    subt=resp['movie']['video']['subtitles'] if 'subtitles' in resp['movie']['video'] else []
    subActive=False
    
    
    if ts !=None: #catchup SC
        base=datetime.datetime(*(time.strptime('2001-01-01 01:00', "%Y-%m-%d %H:%M")[0:6])).timestamp()
        tstart=int(int(ts)-base-60)*1000 #-1min
        tend=int(int(te)-base+5*60)*1000 #+5min
        if '?' not in s_url:
            stream_url=s_url+'?startTime='+str(tstart)+'&stopTime='+str(tend)
        else:
            stream_url=s_url+'&startTime='+str(tstart)+'&stopTime='+str(tend)
        if int(te)>=int(time.time()):
            diff=(int(time.time())-int(ts))*1000
            if '?' not in s_url:
                stream_url=s_url+'?dvr='+str(diff)
            else:
                stream_url=s_url+'&dvr='+str(diff)
    else:
        stream_url=s_url
        if isT and pid==None: #timeshift
            stream_url+='&dvr=7200000'

    
    import inputstreamhelper
    PROTOCOL = protocol
    drmType='com.widevine.alpha'
    is_helper = inputstreamhelper.Helper(PROTOCOL,drmType)
    if is_helper.check_inputstream():
        play_item = xbmcgui.ListItem(path=stream_url)

        if not isT and iL!={}:
            play_item.setInfo(type='video', infoLabels=iL)

        play_item.setMimeType('application/xml+dash')
        play_item.setContentLookup(False)
        play_item.setProperty('inputstream', is_helper.inputstream_addon)
        play_item.setProperty("IsPlayable", "true")
        play_item.setProperty('inputstream.adaptive.manifest_type', PROTOCOL)
        play_item.setProperty('inputstream.adaptive.manifest_headers', hea_player)#K21
        play_item.setProperty('inputstream.adaptive.stream_headers', hea_player)
        if resume!=False: #start od wskazanego momentu (resume)
            play_item.setProperty('ResumeTime', resume)
            play_item.setProperty('TotalTime', '1')

        if ts!=None:
            play_item.setProperty('ResumeTime', '1')
            play_item.setProperty('TotalTime', '1')

        if 'pol' in subt:
            if subt['pol']['default']==True:
                play_item.setSubtitles([subt['pol']['src']])
                subActive=True
                
        #play_item.setSubtitles(sbt_src)
        if drm:
            kodiVer=xbmc.getInfoLabel('System.BuildVersion')
            if not kodiVer.startswith('22.'):
                play_item.setProperty("inputstream.adaptive.license_type", drmType)
                play_item.setProperty("inputstream.adaptive.license_key", lic_key)
            else:
                play_item.setProperty("inputstream.adaptive.drm", json.dumps(drm_config))
                  
        xbmcplugin.setResolvedUrl(addon_handle, True, listitem=play_item)
        
        if subActive==True:
            while not xbmc.Player().isPlaying():
                xbmc.sleep(100)
            xbmc.Player().showSubtitles(True)


def tv(t):
    url=baseurl+'playerapi/product/packet/element/list?maxResults=100&firstResult=0&category[]=live&categoryId=17&4K=true&platform='+platform#+'&packetId[]=89146&packetId[]=4213427&packetId[]=4252983&packetId[]=2938736'

    url=baseurl+'playerapi/product/live/list?4K=true&platform='+platform
    resp=requests.get(url,headers=base.heaGen(),cookies=base.cookiesGen()).json()

    if t=='live':
        cids=[str(c['id']) for c in resp]
        epg=getEPG(cids)
    for r in resp:
        #subscr=addon.getSetting('subscr')
        show=True

        if 'catchUpDuration' not in r and t=='replay':
            show=False
        if r['payable']: #konta free
            show=False

        if show:        
            name=r['title']
            cid=str(r['id'])
            img=r['images']['pc'][0]['mainUrl']
            if img.startswith('//'):
                img='https:'+img
            if t=='replay':
                isP='false'
                isF=True
                dur=str(r['catchUpDuration'])#w minutach
                URL=base.build_url({'mode':'calendar','cid':cid,'dur':dur})
                epgData=''
            elif t=='live':
                isP='true'
                isF=False
                URL=base.build_url({'mode':'playT','cid':cid})
                epgData=epg[cid]

            iL={'title': name,'sorttitle': name,'plot': epgData}
            setArt={'thumb': img, 'poster': img, 'banner': img, 'icon': img, 'fanart':fanart}
            base.addItemList(URL, name, setArt, 'video', iL, isF, isP)
    
    xbmcplugin.addSortMethod(handle=addon_handle,sortMethod=xbmcplugin.SORT_METHOD_NONE)
    xbmcplugin.addSortMethod(handle=addon_handle,sortMethod=xbmcplugin.SORT_METHOD_TITLE)
    xbmcplugin.endOfDirectory(addon_handle)

def calendar(cid,dur):
    now=datetime.datetime.now()
    cd=int(int(dur)/(24*60))+1
    for i in range(0,cd): 
        date=(now-datetime.timedelta(days=i*1)).strftime('%Y-%m-%d')
        
        setArt={'thumb': '', 'poster': '', 'banner': '', 'icon': 'DefaultYear.png', 'fanart':fanart}
        url=base.build_url({'mode':'programList','cid':cid,'date':date})
        base.addItemList(url, date, setArt, 'video')
    xbmcplugin.endOfDirectory(addon_handle)

def programList(date,cid):    
    t=datetime.datetime(*(time.strptime(date, "%Y-%m-%d")[0:6]))
    ts=str(1000*int(t.timestamp()))
    te=str(1000*int((t+datetime.timedelta(days=1)).timestamp()))
    url=baseurl+'playerapi/product/live/epg/list?liveId[]=%s&since=%s&till=%s&platform=BROWSER'%(cid,ts,te)
    resp=requests.get(url,headers=heaWeb).json()
    def sortFN(i):
        return i['since']
    resp.sort(key=sortFN,reverse=False)
    epg=''
    for r in resp:
        now=int(time.time())
        since=datetime.datetime(*(time.strptime(r['since'], '%Y-%m-%d %H:%M:%S')[0:6])).timestamp()
        till=datetime.datetime(*(time.strptime(r['till'], '%Y-%m-%d %H:%M:%S')[0:6])).timestamp()
        
        nowDate=datetime.datetime.now()
        cuTime=datetime.datetime(*(time.strptime(r['catchupTill'],'%Y-%m-%d %H:%M:%S')[0:6]))
                
        if nowDate<cuTime and since<now:#262140
            title=r['title']
            pid=r['programRecordingId']
            cid=str(r['id'])
            t_s=r['since'].split(' ')[-1][:-3]
            if 'genres' in r:
                if len(r['genres'])>0:
                    title+=' - ' + r['genres'][0]['name']
            name='[B]%s[/B] %s\n'%(t_s,title)
            img=img_addon
            desc=r['description'] if 'description' in r else '...'#        
            
            iL={'title': title,'sorttitle': '','plot': desc}
            setArt={'thumb': img, 'poster': img, 'banner': img, 'icon': img, 'fanart':fanart}
            url=base.build_url({'mode':'playT','pid':pid,'cid':cid})
            
            cmItems=[('[B]Dodaj do ulubionych[/B]','RunPlugin(plugin://plugin.video.vod_pl?mode=favAdd&url='+quote(url)+'&name='+quote(name)+'&art='+quote(str(setArt))+'&iL='+quote(str(iL))+'&cid='+cid+')')]
            
            base.addItemList(url, name, setArt, 'video', iL, False, 'true', True, cmItems)
    
    xbmcplugin.setContent(addon_handle, 'videos') 
    xbmcplugin.endOfDirectory(addon_handle)


def getEPG(c):
    cc='&liveId[]='.join(c)
    
    d=datetime.datetime.now().strftime('%Y-%m-%d')
    t=datetime.datetime(*(time.strptime(d, "%Y-%m-%d")[0:6]))
    ts=str(1000*int(t.timestamp()))
    t1=str(1000*int((t+datetime.timedelta(days=1)).timestamp()))
    t2=str(1000*int((t+datetime.timedelta(days=2)).timestamp()))
    url='%splayerapi/product/live/epg/list?liveId[]=%s&since=%s&till=%s&platform=BROWSER'%(baseurl,cc,ts,t1)
    resp=requests.get(url,headers=heaWeb).json()
    progs=resp
    url='%splayerapi/product/live/epg/list?liveId[]=%s&since=%s&till=%s&platform=BROWSER'%(baseurl,cc,t1,t2)
    resp=requests.get(url,headers=heaWeb).json()
    progs+=resp
    def sortFN(i):
        return i['since']
    progs.sort(key=sortFN,reverse=False)
    now=time.time()
    epg={}
    for r in progs:
        till=datetime.datetime(*(time.strptime(r['till'], '%Y-%m-%d %H:%M:%S')[0:6])).timestamp()
        if till>now:
            t_s=r['since'].split(' ')[-1][:-3]
            title=r['title']
            if 'genres' in r:
                if len(r['genres'])>0:
                    title+=' - ' + r['genres'][0]['name']
            
            epgItem='[B]%s[/B] %s\n'%(t_s,title)
            cid=str(r['live']['id'])
            if cid not in epg:
                epg[cid]=''
            if epgItem not in epg[cid]:
                epg[cid]+=epgItem
    return epg


#Wyszukiwarka
def searchResGen(Resp,t,ct):#
    if ct=='Seriale' or ct=='Filmy' :
        res=[r for r in Resp if r['type']==t and r['element']['mainCategory']['name']==ct]
    elif ct=='Programy':
        res=[r for r in Resp if (r['type']=='SERIAL' and r['element']['mainCategory']['name']!='Seriale') or (r['type']=='VOD' and r['element']['mainCategory']['name']!='Filmy' )]
    else:
        res=[r for r in Resp if r['type']==t]
    return res
    
def search():
    qry=xbmcgui.Dialog().input(u'Szukaj (przynajmniej 3 znaki):', type=xbmcgui.INPUT_ALPHANUM)
    if qry:
        u=baseurl+'playerapi/item/search?4K=true&platform='+platform+'&keyword='+qry+'&episodes=true'
        resp=requests.get(u,headers=base.heaGen(),cookies=base.cookiesGen()).json()
        #addon.setSetting('searchResult',str(resp))
        saveF(PATH_profile+'search.txt',str(resp))
        
        s=[
            ['Filmy'+' (%s)'%(len(searchResGen(resp,'VOD','Filmy'))),'VOD|Filmy'],
            ['Seriale'+' (%s)'%(len(searchResGen(resp,'SERIAL','Seriale'))),'SERIAL|Seriale'],
            ['Programy'+' (%s)'%(len(searchResGen(resp,'','Programy'))),'|Programy'],
            ['Odcinki'+' (%s)'%(len(searchResGen(resp,'EPISODE',''))),'EPISODE|']
        ]
        for ss in s:
            setArt={'thumb': '', 'poster': img_addon, 'banner': '', 'icon': 'OverlayUnwatched.png', 'fanart':fanart}
            url = base.build_url({'mode':'searchRes','cat':ss[1]})
            base.addItemList(url, ss[0], setArt, 'video')

        xbmcplugin.endOfDirectory(addon_handle)
    else:
        main_menu()

def searchRes(t,ct):
    res=eval(openF(PATH_profile+'search.txt'))
    res=searchResGen(res,t,ct)
    for r in res:
        addContToList(r['element'])
        
    xbmcplugin.setContent(addon_handle, 'videos')    
    xbmcplugin.endOfDirectory(addon_handle)

#Strona główna/Ostatnio dodane
def mainPage(mc):
    u=baseurl+'playerapi/product/section/list/'+mc+'?4K=true&platform='+platform+'&subscriberData=false&recommendationData=false&firstResult=1'
    resp=requests.get(u,headers=base.heaGen(),cookies=base.cookiesGen()).json()
    for c in resp:
        if 'showTitle' in c:
            if c['showTitle']==True and c['title'] not in ['KONTYNUUJ OGLĄDANIE','ULUBIONE']:                        
                setArt={'thumb': '', 'poster': img_addon, 'banner': '', 'icon': 'OverlayUnwatched.png', 'fanart':fanart}
                url = base.build_url({'mode':'mainPageCateg','mc':mc,'categID':str(c['id'])})
                base.addItemList(url, c['title'], setArt, 'video')
                
    if mc=='recently_added':
        setArt={'thumb': '', 'poster': img_addon, 'banner': '', 'icon': 'OverlayUnwatched.png', 'fanart':fanart}
        url = base.build_url({'mode':'contList','mainCateg':'131','Categ':'all','page':'1','vodType':str(['VOD','EPISODE'])})
        base.addItemList(url, 'Wszystkie', setArt, 'video')
    
    xbmcplugin.endOfDirectory(addon_handle)

def mainPageCateg(mpc,mc):
    u=baseurl+'playerapi/product/section/list/'+mc+'?4K=true&platform='+platform+'&subscriberData=false&recommendationData=false&firstResult=1'
    resp=requests.get(u,headers=base.heaGen(),cookies=base.cookiesGen()).json()
    for r in resp:
        if r['id']==int(mpc):
            for rr in r['items']:
                addContToList(rr)
    xbmcplugin.endOfDirectory(addon_handle)

def sectionList(cid):
    u=baseurl+'playerapi/product/section/'+cid+'?4K=true&platform='+platform+'&firstResult=0&maxResults=50'
    resp=requests.get(u,headers=base.heaGen(),cookies=base.cookiesGen()).json()
    for r in resp['items']:
        addContToList(r)
    xbmcplugin.endOfDirectory(addon_handle)    

def addContToList(r,myList=None,since=None,till=None):#
    isShow=True
    #profile=addon.getSetting('profile_uid')
    
    cid=str(r['id'])
    name=r['title']
    type=r['type']
    img=getImg(r['images'])
    iL,availLabel,tags=detCont(r)
    mod=''
    isPlayable='false'
    isFolder=True
    
    if type=='SERIAL' or type=='VOD': #oznaczenie 4k
        if 'uhd' in r:
            if r['uhd']:
                name+=' [COLOR=deepskyblue][4K][/COLOR]'
    
    if type=='SERIAL':
        mod='sezonList'
        URL = base.build_url({'mode':mod,'cid':cid,'title':name})
    elif type=='VOD':
        if since==None and till==None:
            name=titleWithTill(availLabel,name)
        else: #transmisje Eurosport Extra (type: VOD)
            airingSince=r['airingSince'].split(' ')[1][:-3]
            airingTill=r['airingTill'].split(' ')[1][:-3]
            name='[B]%s - %s[/B] %s'%(airingSince,airingTill,name)
            s=strToDate(r['airingSince'])
            e=strToDate(r['airingTill'])
            now=datetime.datetime.now()
            if now>=s and now<=e:
                name+='[COLOR=yellow] [TRWA][/COLOR]'
        
        mod='playVid'
        URL = base.build_url({'mode':mod,'eid':cid})
        isPlayable='true'
        isFolder=False

    elif type=='EPISODE':
        serial_title=r['season']['serial']['title']
        if name!='': 
            name=serial_title+' | '+name
        else:
            try:
                name=serial_title+' | sez. '+str(r['season']['number'])+' odc. '+str(r['episode'])
            except:
                name=serial_title
        name=titleWithTill(availLabel,name)
        mod='playVid'
        URL = base.build_url({'mode':mod,'eid':cid})
        isPlayable='true'
        isFolder=False
    elif type=='SECTION':
        mod='sectionList'
        URL = base.build_url({'mode':mod,'cid':cid})
    elif type=='BANNER':#do weryfikacji
        if 'urlWeb' in r:
            cid=r['urlWeb'].split(',')[-1]
            if '/kolekcje/' in r['urlWeb']:
                mod='sectionList'
                URL = base.build_url({'mode':mod,'cid':cid})
            else:
                URL = base.build_url({'mode':'mainPage'})
            '''
            elif '/programy' in r['urlWeb'] or '/seriale' in r['urlWeb']:
                mod='sezonList'
                tid=''
                URL = base.build_url({'mode':mod,'cid':cid,'title':name,'tid':tid})
            elif '/filmy' in r['urlWeb']:
                name=titleWithTill(availLabel,name)
                tid=''
                mod='playVid'
                URL = base.build_url({'mode':mod,'eid':cid,'tid':tid})
                isPlayable='true'
                isFolder=False

            '''
    elif type=='LIVE':
        mod='playT'
        URL = base.build_url({'mode':mod,'cid':cid})
        isPlayable='true'
        isFolder=False
    
    if (type=='SERIAL' or type=='VOD' or type=='EPISODE') and availLabel=='SOON':#r['displaySchedules'][i_cur]['type']=='SOON':
        isPlayable='false'
        isFolder=False
        URL = base.build_url({'mode':'noPlay'})
    
    
    
    xbmcplugin.setContent(addon_handle, 'videos')
    
    #iL={'title': '','sorttitle': '','plot': plot}
    setArt={'thumb': img, 'poster': img, 'banner': img, 'icon': img, 'fanart':img}
    
    cmItems = []
    if type=='VOD' or type=='SERIAL' or type=='EPISODE':
        if type!='EPISODE':
            cmItems.append(('[B]Dodaj do ulubionych[/B]','RunPlugin(plugin://plugin.video.vod_pl?mode=favAdd&url='+quote(URL)+'&name='+quote(name)+'&art='+quote(str(setArt))+'&iL='+quote(str(iL))+'&cid='+cid+')'))
        cmItems.append(('[B]Szczegóły[/B]','RunPlugin(plugin://plugin.video.vod_pl?mode=showDet&eid='+cid+')'))
    
       
    if isShow:
        base.addItemList(URL, name, setArt, 'video', iL, isFolder, isPlayable, True, cmItems)

#ULUBIONE KODI
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
        isPlayable='false'
        isFolder=True
        URL=j[0]
        if 'mode=playVid' in URL or 'mode=playT' in URL:
            isPlayable='true'
            isFolder=False

        cmItems=[
            ('[B]Usuń z ulubionych[/B]','RunPlugin(plugin://plugin.video.vod_pl?mode=favDel&url='+quote(j[0])+')'),
            ('[B]Szczegóły[/B]','RunPlugin(plugin://plugin.video.vod_pl?mode=showDet&eid='+j[4]+')')
        ]
        setArt=eval(j[2])
        iL=eval(j[3])
        base.addItemList(URL, j[1], setArt, 'video', iL, isFolder, isPlayable, True, cmItems)
    
    xbmcplugin.setContent(addon_handle, 'videos')     
    xbmcplugin.endOfDirectory(addon_handle)

def favDel(u):
    fURL=PATH_profile+'ulubione.json'
    js=openJSON(fURL)
    for i,j in enumerate(js):
        if  j[0]==u:
            del js[i]
    saveJSON(fURL,js)
    xbmc.executebuiltin('Container.Refresh()')

def favAdd(u,n,a,i,c):
    fURL=PATH_profile+'ulubione.json'
    js=openJSON(fURL)
    duplTest=False
    for j in js:
        if j[0]==u:
            duplTest=True
    if not duplTest:
        js.append([u,n,a,i,c])
        xbmcgui.Dialog().notification('VODpl', 'Dodano do ulubionych', xbmcgui.NOTIFICATION_INFO)
    else:
        xbmcgui.Dialog().notification('VODpl', 'Materiał jest już w ulubionych', xbmcgui.NOTIFICATION_INFO)
    saveJSON(fURL,js)

def expFav():
    from shutil import copy2, copyfile
    fURL=PATH_profile+'ulubione.json'
    targetPATH=xbmcgui.Dialog().browse(0, 'Wybierz lokalizację docelową', '', '', enableMultiple = False)
    #copy2(fURL,targetPATH)
    copyfile(fURL, targetPATH+'ulubione.json')
    xbmcgui.Dialog().notification('VODpl', 'Plik zapisany', xbmcgui.NOTIFICATION_INFO)
    
def impFav():
    from shutil import copy2,copyfile
    fURL=PATH_profile+'ulubione.json'
    sourcePATH=xbmcgui.Dialog().browse(1, 'Wybierz plik', '', '.json', enableMultiple = False)
    copyfile(sourcePATH,fURL)
    #copy2(sourcePATH,fURL)
    xbmcgui.Dialog().notification('VODpl', 'Plik zapisany', xbmcgui.NOTIFICATION_INFO)    

def cleanText(t):
    toDel=['<p>','</p>','<strong>','</strong>']
    for d in toDel:
        t=t.replace(d,'')
    t=t.replace('<br>',' ').replace('&oacute;','ó').replace('&ouml;','ö').replace('&nbsp;',' ').replace('&ndash;',' - ')
    t=re.sub('<([^<]+?)>','',t)
    return t 

def m3u_gen():
    file_name = addon.getSetting('fname')
    path_m3u = addon.getSetting('path_m3u')
    if file_name == '' or path_m3u == '':
        xbmcgui.Dialog().notification('VODpl', 'Podaj nazwę pliku oraz katalog docelowy.', xbmcgui.NOTIFICATION_ERROR)
        return
    xbmcgui.Dialog().notification('VODpl', 'Generuję listę M3U.', xbmcgui.NOTIFICATION_INFO)
    data = '#EXTM3U\n'
    
    url=baseurl+'playerapi/product/live/list?4K=true&platform='+platform
    resp=requests.get(url,headers=base.heaGen(),cookies=base.cookiesGen()).json()

    for r in resp:
        chImg=r['images']['pc'][0]['mainUrl']
        if chImg.startswith('//'):
            chImg='https:'+chImg
        chName=r['title']
        cid=str(r['id'])
        if 'catchUpDuration' in r:
            cuDur=int(r['catchUpDuration']/(24*60))
            data += '#EXTINF:0 tvg-id="%s" tvg-logo="%s" group-title="VODpl" catchup="append" catchup-source="&s={utc:Ymd_HMS}&e={utcend:Ymd_HMS}" catchup-days="%s" catchup-correction="0.0",%s\nplugin://plugin.video.vod_pl?mode=playT&cid=%s\n' %(chName,chImg,cuDur,chName,cid)
        else:
            data += '#EXTINF:0 tvg-id="%s" tvg-logo="%s" group-title="VODpl" ,%s\nplugin://plugin.video.vod_pl?mode=playT&cid=%s\n' %(chName,chImg,chName,cid)
        
    f = xbmcvfs.File(path_m3u + file_name, 'w')
    f.write(data)
    f.close()
    xbmcgui.Dialog().notification('VODpl', 'Wygenerowano listę M3U', xbmcgui.NOTIFICATION_INFO)

  
mode = params.get('mode', None)

if not mode:
    if addon.getSetting('uid')=='' or addon.getSetting('uid')==None:
        addon.setSetting('uid',base.code_gen(32))
        addon.setSetting('device_uid',base.code_gen(16))
    main_menu()
else:
    if mode=='schedule':
        mc=params.get('mainCateg')
        schedule(mc)
    
    if mode=='categList':
        mc=params.get('mainCateg')
        date=params.get('date')
        categList(mc,date)
        
    if mode=='contList':
        mc=params.get('mainCateg')
        c=params.get('Categ')
        pg=params.get('page')
        vt=params.get('vodType')
        since=params.get('since')
        till=params.get('till')
        contList(mc,c,pg,vt,since,till)
    
    if mode=='sezonList':
        cid=params.get('cid')
        tit=params.get('title')
        sezonList(cid,tit)
    
    if mode=='episodeList':
        cid=params.get('cid')
        sezId=params.get('sezId')
        tit=params.get('title')
        pg=params.get('page')
        init=params.get('init')
        episodeList(cid,sezId,tit,pg,init)
    
    if mode=='showDet':
        eid=params.get('eid')
        showDet(eid)
        
    if mode=='playVid':
        eid=params.get('eid')
        playVid(eid,'vod',False,False,None)
    
    if mode=='tv':
        t=params.get('type')
        tv(t)
    
    if mode=='calendar':
        cid=params.get('cid')
        dur=params.get('dur')
        calendar(cid,dur)
    
    if mode=='programList':
        d=params.get('date')
        c=params.get('cid')
        programList(d,c)
        
    if mode=='playT':
        cid=params.get('cid')
        ts=None
        te=None
        s=params.get('s')
        e=params.get('e')
        pid=params.get('pid')
        if s!=None and e!=None:
            co=int(addon.getSetting('cuOffset'))
            ts=str(int((datetime.datetime(*(time.strptime(s, "%Y%m%d_%H%M%S")[0:6]))+datetime.timedelta(hours=co)).timestamp()))
            te=str(int((datetime.datetime(*(time.strptime(e, "%Y%m%d_%H%M%S")[0:6]))+datetime.timedelta(hours=co)).timestamp()))
        playVid(cid,'live',False,True,ts,te,pid)

    
    if mode=='noPlay':
        pass
    
    if mode=='search':
        search()
    
    if mode=='searchRes':
        type,contType=params.get('cat').split('|')
        searchRes(type,contType)
        
    if mode=='mainPage':
        mc=params.get('mainCateg')
        mainPage(mc)
    
    if mode=='mainPageCateg':
        mpc=params.get('categID')
        mc=params.get('mc')
        mainPageCateg(mpc,mc)
        
    if mode=='sectionList':
        cid=params.get('cid')
        sectionList(cid)
        
    if mode=='favList':
        favList()
        
    if mode=='favDel':
        url=params.get('url')
        favDel(url)
        
    if mode=='favAdd':
        u=params.get('url')
        n=params.get('name')
        a=params.get('art')
        i=params.get('iL')
        c=params.get('cid')
        favAdd(u,n,a,i,c)
        
    if mode=='expFav':
        expFav()
        
    if mode=='impFav':
        impFav()
        
    if mode=='m3u_gen':
        m3u_gen()
  