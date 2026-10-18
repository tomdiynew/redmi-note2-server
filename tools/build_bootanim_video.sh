#!/usr/bin/env bash
# Build bootanimation.zip from a video + a sound that start together.
#
# usage: [W=1080 H=1920] [FW=540 FH=960] [ESRGAN=/path/to/realesrgan-ncnn-vulkan] \
#        tools/build_bootanim_video.sh VIDEO.mp4 SOUND.mp3 OUT.zip
#
# - desc.txt says W x H (the screen); the frames themselves are FW x FH and the
#   bootanimation stretches each one to W x H on the GPU. Full 1080x1920 JPEGs
#   decode at only ~11 fps on the Redmi (MT6795), so a 30 fps video would run
#   ~3x slower than its sound; 540x960 frames keep up. With ESRGAN set, frames
#   are upscaled with realesr-animevideov3-x3 first (only worth it for FW > source).
# - part0 = the video at its own frame rate + audio.wav. Its "c" type means it
#   always plays to the end, even when Android has finished booting, so neither
#   the video nor the sound is cut off. Frames of the last picture are appended
#   until part0 is at least as long as the sound.
# - part1 = the last frame, looped until boot completes.
set -euo pipefail
VIDEO=$1 SOUND=$2 OUT=$3
W=${W:-1080} H=${H:-1920}
FW=${FW:-540} FH=${FH:-960}
FPS=$(ffprobe -v error -select_streams v:0 -show_entries stream=r_frame_rate -of csv=p=0 "$VIDEO" | python3 -c "import sys; n,d=sys.stdin.read().split('/'); print(round(int(n)/int(d)))")
WORK=$(mktemp -d); trap 'rm -rf "$WORK"' EXIT
mkdir -p "$WORK/src" "$WORK/up" "$WORK/part0" "$WORK/part1"

ffmpeg -loglevel error -i "$VIDEO" -vsync 0 "$WORK/src/%05d.png"
SRCDIR=$WORK/src
if [ -n "${ESRGAN:-}" ]; then
  (cd "$(dirname "$ESRGAN")" && ./"$(basename "$ESRGAN")" -i "$WORK/src" -o "$WORK/up" -n realesr-animevideov3 -s 3 -f png >/dev/null 2>&1)
  SRCDIR=$WORK/up
fi
# cover FW x FH (scale, crop the few odd pixels), JPEG for small size
i=0
for f in "$SRCDIR"/*.png; do
  ffmpeg -loglevel error -y -i "$f" -vf "scale=$FW:$FH:force_original_aspect_ratio=increase:flags=lanczos,crop=$FW:$FH" \
    -q:v 4 "$WORK/part0/$(printf %05d $i).jpg"
  i=$((i + 1))
done
frames=$i
last="$WORK/part0/$(printf %05d $((frames - 1))).jpg"

ffmpeg -loglevel error -y -i "$SOUND" -c:a pcm_s16le -ar 48000 -ac 2 "$WORK/part0/audio.wav"
dur=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$WORK/part0/audio.wav")
need=$(python3 -c "import math; print(max($frames, math.ceil(($dur + 0.4) * $FPS)))")
for j in $(seq "$frames" $((need - 1))); do cp "$last" "$WORK/part0/$(printf %05d "$j").jpg"; done
cp "$last" "$WORK/part1/00000.jpg"

printf '%d %d %d\nc 1 0 part0\np 0 0 part1\n' "$W" "$H" "$FPS" > "$WORK/desc.txt"
rm -f "$OUT"; OUT_ABS=$(cd "$(dirname "$OUT")" && pwd)/$(basename "$OUT")
(cd "$WORK" && zip -0 -X -q -r "$OUT_ABS" desc.txt part0 part1)   # stored, not compressed
echo "video $frames frames @ ${FPS} fps, sound ${dur}s -> part0 $need frames; $(du -h "$OUT" | cut -f1)"
