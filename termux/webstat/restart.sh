#!/data/data/com.termux/files/usr/bin/sh
# (Re)start the web dashboard. Kept as a file so pkill never matches the caller.
pkill -f "python3 .*webstat/server.py"
sleep 1
cd ~/webstat && setsid nohup python3 ~/webstat/server.py >> ~/webstat.log 2>&1 < /dev/null &
sleep 2
pgrep -f "python3 .*webstat/server.py" >/dev/null && echo "webstat running on :8080" || { echo "webstat failed"; tail -n 20 ~/webstat.log; }
