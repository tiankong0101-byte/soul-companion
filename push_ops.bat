@echo off
set GIT="C:\Program Files\Git\cmd\git.exe"
set REPO=%USERPROFILE%\Desktop\soul-companion
set OUT=%REPO%\push_log.txt

echo === GIT LOG === > "%OUT%"
%GIT% -C "%REPO%" log --oneline -5 >> "%OUT%" 2>&1
echo. >> "%OUT%"

echo === GIT STATUS === >> "%OUT%"
%GIT% -C "%REPO%" status --short >> "%OUT%" 2>&1
echo. >> "%OUT%"

echo === GIT ADD === >> "%OUT%"
%GIT% -C "%REPO%" add -A >> "%OUT%" 2>&1
echo. >> "%OUT%"

echo === GIT COMMIT === >> "%OUT%"
%GIT% -C "%REPO%" commit -m "feat: v5.1 - AnySearch API, URL summary, daily briefing, AI music" >> "%OUT%" 2>&1
echo. >> "%OUT%"

echo === GIT PUSH === >> "%OUT%"
%GIT% -C "%REPO%" push origin main >> "%OUT%" 2>&1
echo. >> "%OUT%"

echo === GIT LOG AFTER === >> "%OUT%"
%GIT% -C "%REPO%" log --oneline -5 >> "%OUT%" 2>&1

echo DONE >> "%OUT%"
