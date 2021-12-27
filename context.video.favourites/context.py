import xbmc,xbmcgui,xbmcaddon
import sys
import urllib.request, urllib.parse, urllib.error
import re

def log(x):
    xbmc.log(repr(x),xbmc.LOGERROR)

def remove_formatting(label):
    label = re.sub(r"\[/?[BI]\]",'',label)
    label = re.sub(r"\[/?COLOR.*?\]",'',label)
    return label

def escape( str ):
    str = str.replace("&", "&amp;")
    str = str.replace("", "&gt;")
    str = str.replace("\"", "&quot;")
    return str

def unescape( str ):
    str = str.replace("&lt;","")
    str = str.replace("&quot;","\"")
    str = str.replace("&amp;","&")
    return str

d = xbmcgui.Dialog()

title    = xbmc.getInfoLabel('ListItem.Label')
icon    = xbmc.getInfoLabel('ListItem.Icon')
if not icon:
    icon = ' '
fanart   = xbmc.getInfoLabel('ListItem.Property(Fanart_Image)')
if not fanart:
    fanart = ' '
window   = xbmcgui.getCurrentWindowId()
playable = xbmc.getInfoLabel('ListItem.Property(IsPlayable)').lower() == 'true'
FileNameAndPath = xbmc.getInfoLabel('ListItem.FileNameAndPath')
FolderPath = xbmc.getInfoLabel('ListItem.FolderPath')
DBTYPE = xbmc.getInfoLabel('ListItem.DBTYPE')

#log((FolderPath,FileNameAndPath))
play_url =FileNameAndPath
'''
play_url = ''
if FileNameAndPath.startswith('script'):
    script_params = FileNameAndPath[9:].split('?',1)
    script = script_params[0].strip('/')
    if len(script) == 2:
        params = script_params[1]
        play_url = 'RunScript(%s,%s)' % (script,params) #TODO is this right?
    else:
        play_url = 'RunScript(%s)' % (script)
elif FileNameAndPath.startswith('plugin'):
    if playable:
        play_url = 'PlayMedia("%s")' % FileNameAndPath
    else:
        play_url = 'ActivateWindow(%s,"%s",return)' % (window,FileNameAndPath)
elif DBTYPE in ['set', 'tvshow', 'season' , 'album', 'artist']:
    play_url = 'ActivateWindow(%s,"%s",return)' % (window,FolderPath)
elif DBTYPE in ['video', 'movie', 'episode', 'musicvideo', 'music', 'song']:
    play_url = 'PlayMedia("%s")' % FileNameAndPath
elif FileNameAndPath.startswith('library'):
    if FolderPath.endswith('/'):
        play_url = 'ActivateWindow(%s,"%s",return)' % (window,FileNameAndPath)
    else:
        play_url = 'PlayMedia("%s")' % FileNameAndPath
elif FolderPath.startswith('videodb') or FolderPath.startswith('musicdb'):
    if FolderPath.endswith('/'):
        play_url = 'ActivateWindow(%s,"%s",return)' % (window,FolderPath)
    else:
        play_url = 'PlayMedia("%s")' % FolderPath
elif FileNameAndPath.endswith('/') or FileNameAndPath.endswith('\\'):
    play_url = 'ActivateWindow(%s,"%s",return)' % (window,FileNameAndPath)
else:
    play_url = 'PlayMedia("%s")' % FileNameAndPath
'''
folder = ''
while True:
    if (xbmcaddon.Addon().getSetting('advanced') == 'true'):
        what = d.select('Add to Video Favourites',['[COLOR yellow]Add[/COLOR]','Folder: %s' % folder.strip('/'), 'Name: %s' % title, play_url])
    else:
        what = d.select('Add to Video Favourites',['[COLOR yellow]Add[/COLOR]','Folder: %s' % folder.strip('/')])
    if what == -1:
        break
    if what == 0:
        favourites_file = "special://profile/addon_data/plugin.video.favourites/folders/%sfavourites.xml" % folder
        url = "plugin://plugin.video.favourites/add_favourite/%s/%s/%s/%s/%s/%s" % (urllib.parse.quote_plus(favourites_file),
        urllib.parse.quote_plus(title),urllib.parse.quote_plus(play_url),urllib.parse.quote_plus(icon),urllib.parse.quote_plus(fanart),playable)
        xbmc.executebuiltin("PlayMedia(%s)" % url)
        break
    elif what == 1:
        top_folder = 'special://profile/addon_data/plugin.video.favourites/folders/'
        where = d.browse(0, 'Choose Folder', 'files', '', False, True, top_folder)
        if not where:
            continue
        if not where.startswith(top_folder):
            d.notification("Error","Please keep to the folders path")
        else:
            folder = where.replace(top_folder,'')
    elif what == 2:
        new_title = d.input("Name: %s" % title,title)
        if new_title:
            title = new_title
    elif what == 3:
        p = d.input("Edit",play_url)
        if p:
            play_url = p

