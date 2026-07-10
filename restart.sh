#!/bin/bash
kill $(ps aux | grep 'licita.api:app' | grep -v grep | awk '{print $2}') 2>/dev/null
sleep 2
cd /home/web2a/LICITA
nohup venv/bin/python -m uvicorn licita.api:app --host 127.0.0.1 --port 8090 > /tmp/licita.log 2>&1 & disown
sleep 3
ps aux | grep 'licita.api' | grep -v grep
echo '✅ OK'
