import sys
from PIL import Image, ImageDraw, ImageFont
# usage: tools/theme/draw_robot.py OUTDIR  -> robot.ans (truecolor half-blocks) + previews
S=sys.argv[1]
W,H=30,40
G=(124,194,74); GD=(86,150,48); R=(232,50,43); RD=(170,25,22); Wh=(255,255,255); K=(20,20,20); Y=(255,194,61)
im=Image.new("RGBA",(W,H),(0,0,0,0)); d=ImageDraw.Draw(im)
# antenna
d.line([(11,2),(11,5)],fill=GD); d.rectangle([10,0,12,1],fill=Y)
# head
d.rounded_rectangle([3,5,20,15],radius=3,fill=G)
d.line([(5,6),(10,6)],fill=(170,225,120))  # highlight
# eyes + mouth
for ex in (6,13):
    d.rectangle([ex,8,ex+3,11],fill=Wh); d.rectangle([ex+1,9,ex+2,10],fill=K)
d.line([(8,13),(15,13)],fill=GD)
# body
d.rounded_rectangle([5,17,19,31],radius=2,fill=G)
d.line([(7,26),(7,29)],fill=(170,225,120))
# scarf: band at the collar, triangle down the chest, knot
d.rectangle([5,17,19,18],fill=R)
d.polygon([(7,18),(17,18),(12,25)],fill=R)
d.rectangle([11,18,13,20],fill=RD)
d.line([(13,19),(16,23)],fill=R,width=2)  # loose end of the knot
# left arm hanging
d.rounded_rectangle([1,18,3,28],radius=1,fill=G)
# right arm saluting: shoulder -> elbow (out and up) -> hand at the brow
d.line([(20,19),(26,15)],fill=G,width=2)      # upper arm, out to the side
d.line([(26,15),(23,8)],fill=G,width=2)       # forearm up to the brow
d.rectangle([19,5,24,7],fill=G)               # flat hand at the forehead
d.line([(19,5),(24,5)],fill=(170,225,120))
# legs
d.rectangle([8,32,10,37],fill=G); d.rectangle([14,32,16,37],fill=G)
d.rectangle([7,37,10,38],fill=GD); d.rectangle([14,37,17,38],fill=GD)
# MIRROR: the robot faces us, so its right hand (the saluting one) is on our left
im=im.transpose(Image.FLIP_LEFT_RIGHT); d=ImageDraw.Draw(im)
im.save(f"{S}/robot-pix.png")
# preview: big pixels
im.resize((W*14,H*14),Image.NEAREST).save(f"{S}/robot-big.png")
# half-block ANSI (truecolor): each cell = top pixel (fg of ▀) + bottom pixel (bg)
px=im.load(); rows=[]; plain=[]
for y in range(0,H,2):
    line=""; pl=""
    for x in range(W):
        t=px[x,y]; b=px[x,y+1] if y+1<H else (0,0,0,0)
        ta,ba=t[3]>0,b[3]>0
        if not ta and not ba: line+="\033[0m "; pl+=" "
        elif ta and ba:
            line+=f"\033[38;2;{t[0]};{t[1]};{t[2]}m\033[48;2;{b[0]};{b[1]};{b[2]}m▀\033[0m"; pl+="█"
        elif ta: line+=f"\033[0m\033[38;2;{t[0]};{t[1]};{t[2]}m▀\033[0m"; pl+="▀"
        else: line+=f"\033[0m\033[38;2;{b[0]};{b[1]};{b[2]}m▄\033[0m"; pl+="▄"
    rows.append(line.rstrip()); plain.append(pl.rstrip())
open(f"{S}/robot.ans","w").write("\n".join(rows)+"\n")
open(f"{S}/robot-plain.txt","w").write("\n".join(plain)+"\n")
# terminal-like preview with Menlo cell size
f=ImageFont.truetype("/System/Library/Fonts/Menlo.ttc",24); cw,ch=15,30
pv=Image.new("RGB",(W*cw+40,(H//2)*ch+40),(20,6,6))
for cy in range(H//2):
    for x in range(W):
        for half,yy in ((0,cy*2),(1,cy*2+1)):
            c=px[x,yy]
            if c[3]: ImageDraw.Draw(pv).rectangle([20+x*cw,20+cy*ch+half*ch//2,20+x*cw+cw-1,20+cy*ch+half*ch//2+ch//2-1],fill=c[:3])
pv.save(f"{S}/robot-term.png")
