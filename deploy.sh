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
  adb push system/termux-services.sh /system/bin/termux-services.sh
  adb push system/termux-services.rc /system/etc/init/termux-services.rc
  adb push system/termux-intro.sh /system/bin/termux-intro.sh
  adb push system/termux-intro.rc /system/etc/init/termux-intro.rc
  adb shell 'cd /system; chmod 755 bin/phonectl.sh bin/termux-services.sh bin/termux-intro.sh
    chmod 644 etc/init/phonectl.rc etc/init/termux-services.rc etc/init/termux-intro.rc
    chown root:root bin/*.sh etc/init/phonectl.rc etc/init/termux-services.rc etc/init/termux-intro.rc
    restorecon bin/phonectl.sh bin/termux-services.sh bin/termux-intro.sh etc/init/phonectl.rc etc/init/termux-services.rc etc/init/termux-intro.rc 2>/dev/null
    mount -o ro,remount /system; sync
    # screen off after 60 s: on MTK "stop charging" means running from the battery,
    # so the screen (~1 W) was most of the battery wear. Services keep a wake lock.
    settings put global stay_on_while_plugged_in 0; settings put system screen_off_timeout 60000'
  echo "installed; init services load at next boot"
}

web() {
  "${SSH[@]}" 'mkdir -p ~/webstat ~/.termux/boot'
  scp -q -P 8022 termux/webstat/server.py termux/webstat/index.html "$PHONE":webstat/
  scp -q -r -P 8022 termux/webstat/icons "$PHONE":webstat/
  "${SSH[@]}" 'mkdir -p ~/bin ~/.termux'
  scp -q -P 8022 termux/bin/boot-intro "$PHONE":bin/
  scp -q -P 8022 termux/dot-termux/termux.properties "$PHONE":.termux/termux.properties
  "${SSH[@]}" 'chmod 700 ~/bin/boot-intro; rm -f ~/bin/rain.py'
  # Pioneer look: robot logo for neofetch, Termux colours, red-scarf prompt in every shell
  "${SSH[@]}" 'mkdir -p ~/.config/neofetch'
  scp -q -P 8022 termux/neofetch/robot.ans "$PHONE":.config/neofetch/robot.ans
  scp -q -P 8022 termux/dot-termux/colors.properties "$PHONE":.termux/colors.properties
  "${SSH[@]}" 'grep -q "pioneer-prompt" ~/.bashrc 2>/dev/null || cat >> ~/.bashrc <<"RC"
# pioneer-prompt: red scarf in front of the prompt
PS1="\[\e[1;31m\]▼\[\e[0m\] \[\e[1;32m\]\u@\h\[\e[0m\]:\[\e[1;33m\]\w\[\e[0m\]\$ "
RC
termux-reload-settings 2>/dev/null || true'
  # optional finale text (your own file, not in git) -> big block letters
  if [ -f termux/boot-lyrics.txt ]; then
    python3 tools/render_bigtext.py termux/boot-lyrics.txt termux/boot-lyrics.ans
    scp -q -P 8022 termux/boot-lyrics.ans "$PHONE":.boot-lyrics.ans
  fi
  if [ -f termux/frpc/frpc.toml ]; then
    scp -q -P 8022 termux/frpc/frpc.toml "$PHONE":.frpc.toml
    "${SSH[@]}" 'chmod 600 ~/.frpc.toml; command -v frpc >/dev/null || pkg install -y frp; pkill -f "bin/[f]rpc " || true'
  fi
  scp -q -P 8022 termux/cloudflared/config.yml "$PHONE":.cloudflared/config.yml
  "${SSH[@]}" 'command -v cloudflared >/dev/null || pkg install -y cloudflared; pkill -f "bin/[c]loudflared " || true'
  "${SSH[@]}" 'chmod 700 ~/webstat/server.py; rm -f ~/.termux/boot/start-sshd ~/.termux/boot/start-services ~/webstat/restart.sh'
  "${SSH[@]}" 'pkill -f "python3 .*webstat/[s]erver.py"; echo "webstat restarting (termux-services supervisor relaunches it within 30s)"'
}

case "${1:-}" in
  system) system ;;
  web) web ;;
  all) system; web ;;
  status)
    adb shell 'getprop init.svc.phonectl; tail -n 5 /data/local/phonectl.log' 2>/dev/null || true
    "${SSH[@]}" 'pgrep -fl "[s]shd|[w]ebstat|[f]rpc|[c]loudflared"; tail -n 3 ~/webstat.log' ;;
  *) sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'; exit 1 ;;
esac
