#!/usr/bin/env bash
# Deploy to the Pixel 2 XL (taimen, LineageOS 22.2 + Magisk).
#
#   devices/pixel2xl/deploy.sh root      root services -> /data/adb (needs USB + adb root)
#   devices/pixel2xl/deploy.sh bootanim  boot animation as a Magisk module (needs USB)
#   devices/pixel2xl/deploy.sh web       dashboard, boot intro, Termux settings (over SSH)
#   devices/pixel2xl/deploy.sh all
#   devices/pixel2xl/deploy.sh status
set -euo pipefail
cd "$(dirname "$0")"
REPO=../..
PHONE="${PHONE:-192.168.43.202}"
SSH=(ssh -p 8022 -o ConnectTimeout=8 "$PHONE")
BOOTANIM="${BOOTANIM:-/Volumes/SSD1G/download/pixel2xl-lineage/bootanimation-pixel.zip}"

adb_root() { adb root >/dev/null; sleep 2; adb wait-for-device; }

root() {
  adb_root
  adb shell 'mkdir -p /data/adb/pixelsrv /data/adb/service.d'
  adb push phonectl.sh termux-services.sh termux-intro.sh /data/adb/pixelsrv/ >/dev/null
  adb push service.sh /data/adb/service.d/pixelsrv.sh >/dev/null
  adb shell 'chmod 755 /data/adb/service.d/pixelsrv.sh /data/adb/pixelsrv/*.sh
    settings put global stay_on_while_plugged_in 3
    locksettings set-disabled true >/dev/null
    dumpsys deviceidle whitelist +com.termux >/dev/null
    ls -l /data/adb/service.d /data/adb/pixelsrv'
  echo "root services installed; they start at next boot"
}

bootanim() {
  adb_root
  [ -f "$BOOTANIM" ] || { echo "missing $BOOTANIM (build with: W=1440 H=2880 tools/build_bootanim.sh ...)"; exit 1; }
  M=/data/adb/modules/customboot
  adb shell "mkdir -p $M/system/product/media"
  printf 'id=customboot\nname=Custom boot animation\nversion=1\nversionCode=1\nauthor=laohan\ndescription=Replaces /product/media/bootanimation.zip (progress bar + boot sound)\n' \
    | adb shell "cat > $M/module.prop"
  adb push "$BOOTANIM" $M/system/product/media/bootanimation.zip >/dev/null
  adb shell "chmod 644 $M/module.prop $M/system/product/media/bootanimation.zip; md5sum $M/system/product/media/bootanimation.zip"
  md5 -q "$BOOTANIM"
  echo "Magisk module installed; active from next boot"
}

web() {
  "${SSH[@]}" 'mkdir -p ~/webstat ~/bin ~/.termux ~/.config/neofetch'
  scp -q -P 8022 $REPO/termux/webstat/server.py $REPO/termux/webstat/index.html "$PHONE":webstat/
  scp -q -P 8022 $REPO/termux/bin/boot-intro "$PHONE":bin/
  scp -q -P 8022 $REPO/termux/dot-termux/termux.properties "$PHONE":.termux/termux.properties
  "${SSH[@]}" 'chmod 700 ~/bin/boot-intro ~/webstat/server.py
    [ -s ~/.config/neofetch/config.conf ] || neofetch --print_config > ~/.config/neofetch/config.conf 2>/dev/null
    sed -i "s/^ascii_distro=.*/ascii_distro=\"android_small\"/" ~/.config/neofetch/config.conf
    pkill -f "python3 .*webstat/[s]erver.py"; echo "dashboard restarting (supervisor relaunches it within 30s)"'
}

case "${1:-}" in
  root) root ;;
  bootanim) bootanim ;;
  web) web ;;
  all) root; bootanim; web ;;
  status)
    adb shell 'tail -n 3 /data/adb/pixelsrv/phonectl.log; ls /data/adb/modules' 2>/dev/null || true
    "${SSH[@]}" 'pgrep -fa "[s]shd$|[w]ebstat"; tail -n 2 ~/webstat.log' ;;
  *) sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'; exit 1 ;;
esac
