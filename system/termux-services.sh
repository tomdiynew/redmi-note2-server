#!/system/bin/sh
# Supervises sshd and the web dashboard as the Termux user, started by init
# (/system/etc/init/termux-services.rc). Running them under init instead of the
# Termux app means Android's process trimming can't kill them: the app process
# was reaped as "empty" ~35 min after boot, taking its children with it.
export PREFIX=/data/data/com.termux/files/usr
export HOME=/data/data/com.termux/files/home
export PATH=$PREFIX/bin:/system/bin
export TMPDIR=$PREFIX/tmp LANG=en_US.UTF-8
for l in $PREFIX/lib/libtermux-exec-ld-preload.so $PREFIX/lib/libtermux-exec.so; do
  [ -f $l ] && { export LD_PRELOAD=$l; break; }
done
cd $HOME

# keep the CPU awake even if the screen is switched off
echo termux-services > /sys/power/wake_lock 2>/dev/null

while true; do
  # match the full path: on this kernel the process name is a truncated path, so -x sshd never matches
  pgrep -f "^$PREFIX/bin/sshd" >/dev/null || $PREFIX/bin/sshd
  if ! pgrep -f "python3 .*webstat/server.py" >/dev/null; then
    $PREFIX/bin/python3 $HOME/webstat/server.py >> $HOME/webstat.log 2>&1 &
  fi
  sleep 30
done
