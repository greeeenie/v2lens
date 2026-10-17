"""Generate matching vector and antialiased Windows icons for V2Lens."""
from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent/'assets'
ROOT.mkdir(exist_ok=True)
svg = '''<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 256 256">
<rect width="256" height="256" rx="54" fill="#111315"/>
<rect x="5" y="5" width="246" height="246" rx="49" fill="none" stroke="#34313f" stroke-width="2"/>
<circle cx="108" cy="108" r="61" fill="none" stroke="#b2aafa" stroke-width="18"/>
<path d="m153 153 56 56" fill="none" stroke="#b2aafa" stroke-width="18" stroke-linecap="round"/>
<path d="m80 90 28 38 28-38" fill="none" stroke="#e8e9ec" stroke-width="16" stroke-linecap="round" stroke-linejoin="round"/>
</svg>'''
(ROOT/'v2lens.svg').write_text(svg,encoding='utf-8')
scale=4
image=Image.new('RGBA',(256*scale,256*scale))
draw=ImageDraw.Draw(image)
draw.rounded_rectangle((0,0,1023,1023),radius=54*scale,fill='#111315')
draw.rounded_rectangle((5*scale,5*scale,251*scale,251*scale),radius=49*scale,outline='#34313f',width=2*scale)
# ImageDraw draws an inset stroke; offset the ellipse to match SVG's centered stroke.
draw.ellipse((38*scale,38*scale,178*scale,178*scale),outline='#b2aafa',width=18*scale)
def line(points,color,width):
    points=[(x*scale,y*scale) for x,y in points]
    draw.line(points,fill=color,width=width*scale,joint='curve')
    radius=width*scale/2
    for x,y in points:draw.ellipse((x-radius,y-radius,x+radius,y+radius),fill=color)
line([(153,153),(209,209)],'#b2aafa',18)
line([(80,90),(108,128),(136,90)],'#e8e9ec',16)
image=image.resize((256,256),Image.Resampling.LANCZOS)
image.save(ROOT/'v2lens.png')
image.save(ROOT/'v2lens.ico',sizes=[(n,n) for n in [16,20,24,32,48,64,128,256]])
