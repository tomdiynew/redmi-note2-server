#!/usr/bin/env bash
# Build bootanimation.zip: a still picture with a 9 s LOADING progress bar,
# optional boot sound, and a hold at 100% until the sound has finished.
#
# usage: [W=1440 H=2880] tools/build_bootanim.sh PICTURE.png OUT.zip [SOUND.mp3]
#   W/H default to 1080x1920 (Redmi Note 2); Pixel 2 XL is 1440x2880. When the
#   screen's aspect differs from 9:16 the picture is fitted and padded with black.
# needs: ffmpeg, ffprobe, python3, zip (macOS: Arial Bold font)
#
# desc.txt:  "1080 1920 5"   -> width height fps
#            "c 1 0 part0"   -> play part0 once and ALWAYS to completion,
#                               even if Android finished booting earlier
#            "p 0 0 part1"   -> then loop part1 until boot completes
# part0/audio.wav starts together with part0 (Android 7 bootanimation).
set -euo pipefail
PIC=$1 OUT=$2 SOUND=${3:-}
FONT="/System/Library/Fonts/Supplemental/Arial Bold.ttf"
FPS=5 BAR_FRAMES=45            # 45 frames / 5 fps = 9 s for 0 -> 100 %
W=${W:-1080} H=${H:-1920}
# progress-bar geometry was designed on 1080x1920; scale by width, anchor to the bottom
read -r BAND_Y BAND_H BOX_X BOX_Y BOX_W BOX_H BT BAR_X BAR_Y BAR_W BAR_H TXT_Y TXT_L TXT_R FS <<<"$(python3 -c "
k=$W/1080; H=$H
v=[H-148*k,112*k,158*k,H-82*k,764*k,20*k,max(2,2*k),162*k,H-78*k,756*k,12*k,H-130*k,160*k,920*k,32*k]
print(' '.join(str(int(round(x))) for x in v))")"
WORK=$(mktemp -d); trap 'rm -rf "$WORK"' EXIT
mkdir -p "$WORK/part0" "$WORK/part1"

if [ "$W:$H" = "1080:1920" ]; then FIT="scale=1080:1920:flags=lanczos"
else FIT="scale=$W:$H:force_original_aspect_ratio=decrease:flags=lanczos,pad=$W:$H:(ow-iw)/2:(oh-ih)/2:color=black"; fi
ffmpeg -loglevel error -y -i "$PIC" -vf "$FIT" "$WORK/base.png"

for i in $(seq 0 $((BAR_FRAMES - 1))); do
  # ease-out: fast at first, slower near the end
  read -r pct fw <<<"$(python3 -c "t=$i/($BAR_FRAMES-1); p=1-(1-t)**2.2; print(int(round(p*100)), max(1,int($BAR_W*p)))")"
  ffmpeg -loglevel error -y -i "$WORK/base.png" -vf "\
drawbox=x=0:y=$BAND_Y:w=$W:h=$BAND_H:color=black@0.6:t=fill,\
drawbox=x=$BOX_X:y=$BOX_Y:w=$BOX_W:h=$BOX_H:color=white@0.9:t=$BT,\
drawbox=x=$BAR_X:y=$BAR_Y:w=$BAR_W:h=$BAR_H:color=white@0.18:t=fill,\
drawbox=x=$BAR_X:y=$BAR_Y:w=${fw}:h=$BAR_H:color=0xff1a1a@1:t=fill,\
drawtext=fontfile='$FONT':text='LOADING':expansion=none:x=$TXT_L:y=$TXT_Y:fontsize=$FS:fontcolor=white,\
drawtext=fontfile='$FONT':text='${pct}%':expansion=none:x=$TXT_R-tw:y=$TXT_Y:fontsize=$FS:fontcolor=0xff3b30" \
    -q:v 3 "$WORK/part0/$(printf %05d "$i").jpg"
done
last="$WORK/part0/$(printf %05d $((BAR_FRAMES - 1))).jpg"
cp "$last" "$WORK/part1/00000.jpg"

if [ -n "$SOUND" ]; then
  ffmpeg -loglevel error -y -i "$SOUND" -c:a pcm_s16le -ar 48000 -ac 2 "$WORK/part0/audio.wav"
  dur=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$WORK/part0/audio.wav")
  # part0 must last at least as long as the sound (+0.4 s margin): pad with 100 % frames
  need=$(python3 -c "import math; print(math.ceil(($dur + 0.4) * $FPS))")
  for i in $(seq "$BAR_FRAMES" $((need - 1))); do cp "$last" "$WORK/part0/$(printf %05d "$i").jpg"; done
  echo "sound ${dur}s -> part0 = ${need} frames ($(python3 -c "print($need/$FPS)") s)"
fi

printf '%d %d %d\nc 1 0 part0\np 0 0 part1\n' "$W" "$H" "$FPS" > "$WORK/desc.txt"
rm -f "$OUT"
OUT_ABS=$(cd "$(dirname "$OUT")" && pwd)/$(basename "$OUT")
(cd "$WORK" && zip -0 -X -q -r "$OUT_ABS" desc.txt part0 part1)   # must be stored, not compressed
echo "built $OUT ($(du -h "$OUT" | cut -f1))"
