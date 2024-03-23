# -*- coding: utf-8 -*-
import xbmc
import control

state = control.get_setting('state')

if state == 'true':
    control.ambilight_turn_on()
else:
    control.ambilight_turn_off()
    
xbmc.executebuiltin('RunScript(script.notoco.helper,amb_start)')
