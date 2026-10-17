#!/system/bin/sh
# Supervise sshd and the web dashboard as the Termux user (uid 10207) on the
# Pixel. Same job as the Redmi's init service, but started from Magisk
# service.d and switched to the Termux uid with Magisk su (+ inet group 3003,
# needed for network sockets).
TUID=10207
P=/data/data/com.termux/files/usr
H=/data/data/com.termux/files/home

as_termux() {
  /debug_ramdisk/su $TUID -g $TUID -G 3003 -c "PREFIX=$P HOME=$H TMPDIR=$P/tmp LANG=en_US.UTF-8 \
PATH=$P/bin:/system/bin LD_PRELOAD=$P/lib/libtermux-exec-ld-preload.so; \
export PREFIX HOME TMPDIR LANG PATH LD_PRELOAD; cd $H; $1"
}

echo termux-services > /sys/power/wake_lock   # keep the CPU awake with the screen off

# Files created through Magisk su (e.g. by pkg install) get the bare "s0" label;
# the Termux app itself (untrusted_app, MCS c207...) then can't load them
# ("CANNOT LINK ... libncursesw.so.6 not found"). Relabel the whole tree once per boot.
chcon -R -h u:object_r:app_data_file:s0:c207,c256,c512,c768 /data/data/com.termux/files 2>/dev/null   # -h: relabel symlinks themselves too

while true; do
  pgrep -f "^$P/bin/sshd" >/dev/null || as_termux "$P/bin/sshd"
  if ! pgrep -f "python3 .*webstat/server.py" >/dev/null; then
    as_termux "nohup $P/bin/python3 $H/webstat/server.py >> $H/webstat.log 2>&1 &"
  fi
  sleep 30
done
