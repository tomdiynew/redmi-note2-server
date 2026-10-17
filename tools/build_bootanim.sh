#!/usr/bin/env bash
# Build bootanimation.zip: a still picture with a 9 s LOADING progress bar,
# optional boot sound, and a hold at 100% until the sound has finished.
#
# usage: tools/build_bootanim.sh PICTURE.png OUT.zip [SOUND.mp3]
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
WORK=$(mktemp -d); trap 'rm -rf "$WORK"' EXIT
mkdir -p "$WORK/part0" "$WORK/part1"

ffmpeg -loglevel error -y -i "$PIC" -vf "scale=1080:1920:flags=lanczos" "$WORK/base.png"

for i in $(seq 0 $((BAR_FRAMES - 1))); do
  # ease-out: fast at first, slower near the end
  read -r pct fw <<<"$(python3 -c "t=$i/($BAR_FRAMES-1); p=1-(1-t)**2.2; print(int(round(p*100)), max(1,int(756*p)))")"
  ffmpeg -loglevel error -y -i "$WORK/base.png" -vf "\
drawbox=x=0:y=1772:w=1080:h=112:color=black@0.6:t=fill,\
drawbox=x=158:y=1838:w=764:h=20:color=white@0.9:t=2,\
drawbox=x=162:y=1842:w=756:h=12:color=white@0.18:t=fill,\
drawbox=x=162:y=1842:w=${fw}:h=12:color=0xff1a1a@1:t=fill,\
drawtext=fontfile='$FONT':text='LOADING':expansion=none:x=160:y=1790:fontsize=32:fontcolor=white,\
drawtext=fontfile='$FONT':text='${pct}%':expansion=none:x=920-tw:y=1790:fontsize=32:fontcolor=0xff3b30" \
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

printf '1080 1920 %d\nc 1 0 part0\np 0 0 part1\n' "$FPS" > "$WORK/desc.txt"
rm -f "$OUT"
OUT_ABS=$(cd "$(dirname "$OUT")" && pwd)/$(basename "$OUT")
(cd "$WORK" && zip -0 -X -q -r "$OUT_ABS" desc.txt part0 part1)   # must be stored, not compressed
echo "built $OUT ($(du -h "$OUT" | cut -f1))"
