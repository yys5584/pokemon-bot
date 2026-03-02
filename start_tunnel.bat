@echo off
cd /d C:\Users\Administrator\.cloudflared
"C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel run >> C:\Users\Administrator\Desktop\pokemon-bot\cloudflared.log 2>&1
