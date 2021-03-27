# -*- coding: utf-8 -*-
import control

state = control.get_setting('state')

if state == 'true':
    control.turn_on()
else:
    control.turn_off()
