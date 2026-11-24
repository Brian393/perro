"""Category icons: black Font Awesome Free 5 glyph (CC BY 4.0) with a white halo, as small SVG files."""
import re, sys, os
FA = '/media/brian/Gitdisk/git_perro/perro/app/client/node_modules/@fortawesome/fontawesome-free/svgs/solid/'
OUT = sys.argv[1]
ICONS = {'rail': ('train', '#7b3294'), 'yards': ('truck', '#e66101'), 'scrap': ('recycle', '#8c510a'),
         'manufacturing': ('industry', '#c51b7d'), 'warehousing': ('warehouse', '#2166ac'),
         'utilities': ('bolt', '#01665e'), 'municipal': ('landmark', '#4d4d4d')}
os.makedirs(OUT, exist_ok=True)
for cat, (glyph, colour) in ICONS.items():
    src = open(f'{FA}{glyph}.svg').read()
    vb = re.search(r'viewBox="([^"]+)"', src).group(1)
    path = re.search(r'<path d="([^"]+)"', src).group(1)
    # Black glyph with a white halo (stroke drawn under the fill), no disc.
    w, h = map(float, vb.split()[2:])
    halo = max(w, h) * 0.09
    pad = halo
    vb2 = f"{-pad} {-pad} {w + 2 * pad} {h + 2 * pad}"
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 32 32">'
           f'<svg x="1" y="1" width="30" height="30" viewBox="{vb2}">'
           f'<path d="{path}" fill="#111" stroke="#fff" stroke-width="{2 * halo:.0f}" stroke-linejoin="round" paint-order="stroke"/>'
           f'</svg></svg>')
    open(f'{OUT}/ind-{cat}.svg', 'w').write(svg)
print(sorted(os.listdir(OUT)))
