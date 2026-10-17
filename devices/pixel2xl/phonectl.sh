#!/system/bin/sh
# Pixel 2 XL root helper (started by service.sh):
#  1. keeps the battery between CHARGE_LOW% and CHARGE_HIGH%
#  2. writes root-only info (Wi-Fi SSID/RSSI, IP, charge state) as JSON for the
#     Termux dashboard (same format as the Redmi's phonectl)
# Snapdragon/PMI8998: battery/charging_enabled=0 stops charging the battery
# while USB keeps powering the phone.  Overrides: /data/adb/pixelsrv/phonectl.conf

CHARGE_LOW=50
CHARGE_HIGH=60
INTERVAL=15
TUID=10207
OUT=/data/data/com.termux/files/home/.phonestat.json
[ -f /data/adb/pixelsrv/phonectl.conf ] && . /data/adb/pixelsrv/phonectl.conf

BAT=/sys/class/power_supply/battery
LOG=/data/adb/pixelsrv/phonectl.log

log() { echo "$(date '+%F %T') $*" >> $LOG; }
set_charging() {  # $1 = on|off
  if [ "$1" = on ]; then echo 1 > $BAT/charging_enabled; else echo 0 > $BAT/charging_enabled; fi
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
  # the charger HAL resets charging_enabled to 1 after boot (and on replug): re-assert it
  want=1; [ "$charging" = off ] && want=0
  if [ "$(cat $BAT/charging_enabled)" != "$want" ]; then
    echo $want > $BAT/charging_enabled
    log "charging_enabled was reset by the system; re-applied $want"
  fi

  # Wi-Fi details: every 4th loop, or every loop until an SSID shows up
  if [ $((n % 4)) -eq 0 ] || [ -z "$ssid" ]; then
    wi=$(dumpsys wifi 2>/dev/null | grep -m1 'mWifiInfo')
    ssid=$(echo "$wi" | sed -n 's/.*mWifiInfo SSID: "\([^"]*\)".*/\1/p')
    rssi=$(echo "$wi" | sed -n 's/.*RSSI: \(-\{0,1\}[0-9]*\).*/\1/p')
    speed=$(echo "$wi" | sed -n 's/.*, Link speed: \([0-9]*\)Mbps.*/\1/p')
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
  chown $TUID:$TUID $tmp; chmod 644 $tmp; chcon u:object_r:app_data_file:s0:c207,c256,c512,c768 $tmp 2>/dev/null
  mv $tmp $OUT
  sleep $INTERVAL
done
