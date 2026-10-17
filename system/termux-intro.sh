#!/system/bin/sh
# Once per boot (sys.boot_completed=1): bring Termux to the front, full screen,
# running ~/bin/boot-intro in a new foreground session.
sleep 3   # let the launcher finish drawing first
wm dismiss-keyguard   # lock screen is disabled, but make sure nothing covers Termux
am startservice --user 0 -n com.termux/com.termux.app.RunCommandService \
  -a com.termux.RUN_COMMAND \
  --es com.termux.RUN_COMMAND_PATH /data/data/com.termux/files/home/bin/boot-intro \
  --ez com.termux.RUN_COMMAND_BACKGROUND false
sleep 1
am start --user 0 -n com.termux/.app.TermuxActivity
