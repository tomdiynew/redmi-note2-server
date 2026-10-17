#!/usr/bin/env bash
# Deploy to the Redmi Note 2 mini server.
#
#   ./deploy.sh system   push phonectl root service (needs USB + adb root)
#   ./deploy.sh web      push the web dashboard over SSH and restart it
#   ./deploy.sh all      both
#   ./deploy.sh status   show service state
set -euo pipefail
cd "$(dirname "$0")"
PHONE="${PHONE:-192.168.43.247}"
SSH=(ssh -p 8022 -o ConnectTimeout=8 "$PHONE")

system() {
  adb root >/dev/null; sleep 2; adb wait-for-device
  adb shell 'mount -o rw,remount /system'
  adb push system/phonectl.sh /system/bin/phonectl.sh
  adb push system/phonectl.rc /system/etc/init/phonectl.rc
  adb shell 'chmod 755 /system/bin/phonectl.sh; chmod 644 /system/etc/init/phonectl.rc
    chown root:root /system/bin/phonectl.sh /system/etc/init/phonectl.rc
    restorecon /system/bin/phonectl.sh /system/etc/init/phonectl.rc 2>/dev/null
    mount -o ro,remount /system; sync'
  echo "phonectl installed; it starts at next boot (or: adb shell start phonectl)"
}

web() {
  "${SSH[@]}" 'mkdir -p ~/webstat ~/.termux/boot'
  scp -q -P 8022 termux/webstat/server.py termux/webstat/index.html termux/webstat/restart.sh "$PHONE":webstat/
  scp -q -P 8022 termux/boot/start-services "$PHONE":.termux/boot/start-services
  "${SSH[@]}" 'chmod 700 ~/.termux/boot/start-services ~/webstat/server.py ~/webstat/restart.sh; rm -f ~/.termux/boot/start-sshd'
  "${SSH[@]}" '~/webstat/restart.sh'
}

case "${1:-}" in
  system) system ;;
  web) web ;;
  all) system; web ;;
  status)
    adb shell 'getprop init.svc.phonectl; tail -n 5 /data/local/phonectl.log' 2>/dev/null || true
    "${SSH[@]}" 'pgrep -fl "[s]shd|[w]ebstat"; tail -n 3 ~/webstat.log' ;;
  *) sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'; exit 1 ;;
esac
