#!/usr/bin/env bash
# Install the built theme overlays (theme/out/*.apk) on the Redmi over adb and
# make them the default: Android 7 only trusts overlays found in /vendor/overlay
# at boot, so this needs root (remount /system) and a real reboot.
# Also removes the current wallpaper so the overlaid default_wallpaper is used,
# and Trebuchet's icon cache (it would keep showing the old icons).
set -euo pipefail
cd "$(dirname "$0")/../.."
ADB=${ADB:-adb}
$ADB root >/dev/null; sleep 3; $ADB wait-for-device
$ADB shell 'mount -o rw,remount /system && mkdir -p /system/vendor/overlay && chmod 755 /system/vendor/overlay'
$ADB push theme/out/*.apk /system/vendor/overlay/ >/dev/null
$ADB shell 'chmod 644 /system/vendor/overlay/*.apk; sync
  rm -f /data/system/users/0/wallpaper /data/system/users/0/wallpaper_orig /data/system/users/0/wallpaper_info.xml
  rm -f /data/data/com.cyanogenmod.trebuchet/databases/app_icons.db*
  reboot'
echo "installed $(ls theme/out/*.apk | wc -l) overlays; rebooting"
