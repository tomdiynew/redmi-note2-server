#!/system/bin/sh
# Once per boot: wake the screen, dismiss any keyguard and open Termux full
# screen running ~/bin/boot-intro in a new foreground session.
sleep 3
input keyevent KEYCODE_WAKEUP
wm dismiss-keyguard
# Android 8+ blocks background service starts; RunCommandService goes foreground itself
am start-foreground-service --user 0 -n com.termux/com.termux.app.RunCommandService \
  -a com.termux.RUN_COMMAND \
  --es com.termux.RUN_COMMAND_PATH /data/data/com.termux/files/home/bin/boot-intro \
  --ez com.termux.RUN_COMMAND_BACKGROUND false
sleep 1
am start --user 0 -n com.termux/.app.TermuxActivity
