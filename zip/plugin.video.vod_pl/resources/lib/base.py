# -*- coding: utf-8 -*-
#import os
#import sys

import xbmc
import xbmcgui#
import xbmcplugin#
import xbmcaddon
import xbmcvfs

import random
import requests

from urllib.parse import urlencode, quote_plus, quote, unquote, parse_qsl

class b:
    def __init__(self, base_url=None, addon_handle=None):
        self.base_url=base_url
        self.addon_handle=addon_handle
        self.UA='playerTV/2.2.2 (455) (Linux; Android 8.0.0; Build/sdk_google_atv_x86) net/sdk_google_atv_x86userdebug 8.0.0 OSR1.180418.025 6695156 testkeys'
        self.hea={
            'User-Agent':self.UA,
            #'Content-Type':'application/x-www-form-urlencoded',
            'accept-encoding':'gzip'
        }
        self.heaWeb={
             'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36'
        }
        self.platform='ANDROID_TV'
        self.baseurl='https://player.pl/'
               
        self.addon=xbmcaddon.Addon(id='plugin.video.vod_pl')
        self.PATH_profile=xbmcvfs.translatePath(self.addon.getAddonInfo('profile'))
        if not xbmcvfs.exists(self.PATH_profile):
            xbmcvfs.mkdir(self.PATH_profile)
            
    def build_url(self, query):
        return self.base_url + '?' + urlencode(query)

    def addItemList(self, url, name, setArt, medType=False, infoLab={}, isF=True, isPla='false', contMenu=False, cmItems=[]):
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
        xbmcplugin.addDirectoryItem(handle=self.addon_handle, url=url, listitem=li, isFolder=isF)
    
    def code_gen(self,x):
        base='0123456789abcdef'
        code=''
        for i in range(0,x):
            code+=base[random.randint(0,15)]
        return code
        
    def heaGen(self):
        CorrelationID='androidTV_'+self.code_gen(8)+'-'+self.code_gen(4)+'-'+self.code_gen(4)+'-'+self.code_gen(4)+'-'+self.code_gen(12)
        hea=self.hea
        hea.update({
            'api-correlationid':CorrelationID,
            'api-deviceuid':self.addon.getSetting('device_uid'),
            'api-deviceinfo':'sdk_google_atv_x86;unknown;Android;8.0.0;Unknown;2.2.2 (455);',
        })

        return hea
        
    def cookiesGen(self):
        c={
            'uid':self.addon.getSetting('uid'),
        }
        return c
  
    