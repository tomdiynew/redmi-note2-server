#!/system/bin/sh
# Magisk service.d entry point for the Pixel 2 XL (taimen, LineageOS 22.2).
# Installed as /data/adb/service.d/pixelsrv.sh; Magisk runs it as root at
# late_start. Android 15 SELinux is enforcing, so these run in Magisk's domain
# instead of as custom init services (which is what the Redmi uses).
DIR=/data/adb/pixelsrv
until [ "$(getprop sys.boot_completed)" = 1 ]; do sleep 2; done

sh $DIR/phonectl.sh &          # 50-60 % charge limiter + root-only info for the dashboard
sh $DIR/termux-services.sh &   # supervise sshd + dashboard as the Termux user
sh $DIR/termux-intro.sh &      # bring Termux to the front with the boot intro
