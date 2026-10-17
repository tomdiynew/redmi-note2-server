#!/system/bin/sh
# phonectl: root helper for the Redmi Note 2 mini server.
#  1. keeps the battery between CHARGE_LOW% and CHARGE_HIGH% (hysteresis)
#  2. writes root-only info (Wi-Fi SSID/RSSI, IP, charge state) as JSON for the
#     Termux web dashboard
# Started by /system/etc/init/phonectl.rc. Overrides: /data/local/phonectl.conf
#
# MTK quirk (drivers/power/mediatek/battery_common.c): writing "0 1" to
# /proc/mtk_battery_cmd/current_cmd stops charging, "0 0" resumes it.
# NEVER read that file: its read handler forces discharging.

CHARGE_LOW=50
CHARGE_HIGH=60
INTERVAL=15
OUT=/data/data/com.termux/files/home/.phonestat.json
[ -f /data/local/phonectl.conf ] && . /data/local/phonectl.conf

CMD=/proc/mtk_battery_cmd/current_cmd
BAT=/sys/class/power_supply/battery
LOG=/data/local/phonectl.log

log() { echo "$(date '+%F %T') $*" >> $LOG; }

set_charging() {  # $1 = on|off
  if [ "$1" = on ]; then echo "0 0" > $CMD; else echo "0 1" > $CMD; fi
  charging=$1
  log "capacity=$(cat $BAT/capacity)% -> charging $1"
}

json_str() { printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'; }

log "start (low=$CHARGE_LOW high=$CHARGE_HIGH)"
cap=$(cat $BAT/capacity)
if [ "$cap" -ge "$CHARGE_HIGH" ]; then set_charging off; else set_charging on; fi

n=0
while true; do
  cap=$(cat $BAT/capacity)
  if [ "$charging" = on ] && [ "$cap" -ge "$CHARGE_HIGH" ]; then set_charging off
  elif [ "$charging" = off ] && [ "$cap" -le "$CHARGE_LOW" ]; then set_charging on
  fi

  # Wi-Fi details are expensive (dumpsys); refresh every 4th loop
  if [ $((n % 4)) -eq 0 ]; then
    wi=$(dumpsys wifi 2>/dev/null | grep -m1 'mWifiInfo')
    ssid=$(echo "$wi" | sed -n 's/.*mWifiInfo SSID: \([^,]*\),.*/\1/p')
    rssi=$(echo "$wi" | sed -n 's/.*RSSI: \(-\{0,1\}[0-9]*\).*/\1/p')
    speed=$(echo "$wi" | sed -n 's/.*Link speed: \([0-9]*\).*/\1/p')
    freq=$(echo "$wi" | sed -n 's/.*Frequency: \([0-9]*\).*/\1/p')
    ip=$(ip -4 addr show wlan0 2>/dev/null | sed -n 's/.*inet \([0-9.]*\/[0-9]*\).*/\1/p')
    gw=$(ip route get 1.1.1.1 2>/dev/null | sed -n 's/.* via \([0-9.]*\).*/\1/p')
    op=$(getprop gsm.operator.alpha | tr ',' '\n' | grep -v '^$' | head -n 1)
    sim=$(getprop gsm.sim.state)
  fi
  n=$((n + 1))

  tmp=$OUT.tmp
  cat > $tmp <<EOF
{"ts":$(date +%s),"charge_ctl":{"charging":"$charging","low":$CHARGE_LOW,"high":$CHARGE_HIGH},
"wifi":{"ssid":"$(json_str "$ssid")","rssi":${rssi:-null},"link_mbps":${speed:-null},"freq_mhz":${freq:-null},"ip":"$ip","gateway":"$gw"},
"cell":{"operator":"$(json_str "$op")","sim":"$(json_str "$sim")"}}
EOF
  chown u0_a63:u0_a63 $tmp; chmod 644 $tmp; mv $tmp $OUT
  sleep $INTERVAL
done
