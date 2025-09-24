@echo off
echo Arret de tous les processus Python...
taskkill /F /IM python.exe 2>nul
echo Suppression des fichiers de log...
if exist logs\trading_bot.log del logs\trading_bot.log 2>nul
echo Nettoyage termine !
pause