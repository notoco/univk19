# -*- coding: utf-8 -*-
import control

state = control.get_setting('state')

if state == 'true':
    control.ambilight_turn_on()
else:
    control.ambilight_turn_off()
