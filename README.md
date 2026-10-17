# redmi-note2-server

An old Redmi Note 2 (hermes, MT6795) running as an always-on LAN mini server. It runs LineageOS 14.1 and Termux.

- **Dashboard**: http://192.168.43.247:8080, reachable from anywhere on the LAN. Shows battery, Wi-Fi, CPU, temperatures, memory/storage and 24h trends. Refreshes every 5s.
- **Charge limiter**: keeps the battery between 50% and 60% so that being plugged in all the time doesn't wear out or swell the 2015 battery.
- **SSH**: `ssh -p 8022 192.168.43.247` (Termux, key auth).

## Layout

```
system/phonectl.sh     root service: charge limiter + root-only info -> ~/.phonestat.json
system/phonectl.rc     init service definition (/system/etc/init)
termux/webstat/        dashboard (Python stdlib server + one HTML page)
termux/boot/           Termux:Boot script: wake-lock, sshd, dashboard
deploy.sh              system | web | all | status
```

## Deploy

```bash
./deploy.sh web      # over SSH; restarts the dashboard
./deploy.sh system   # needs USB + adb root; phonectl reloads at next boot
./deploy.sh status
```

To change the charge window, create `/data/local/phonectl.conf` on the phone (for example `CHARGE_LOW=40` / `CHARGE_HIGH=60`), then reboot. Alternatively run `adb shell 'stop phonectl; start phonectl'`.

## Device quirks

- **Never read `/proc/mtk_battery_cmd/current_cmd`.** Its read handler forces discharging. Write `0 1` to stop charging and `0 0` to resume.
- The kernel's iowait counter is broken. Load average also reads ~15 on an idle phone, so CPU % is computed without iowait.
- Normally only 1 of the 8 cores is online (MTK hotplug).
- SELinux is permissive, which is why `phonectl` can run without its own SELinux domain.
- To reach TWRP, hold Vol Up during a reboot. MIUI-era notes and the full partition backup are in `/Volumes/SSD1G/download/redmi-note2-flash/`.
