@echo off
set GIT="C:\Program Files\Git\cmd\git.exe"
set REPO=%USERPROFILE%\Desktop\soul-companion
set OUT=%REPO%\push_log.txt

echo === REMOVE TEMP FILES === > "%OUT%"
del /q "%REPO%\push_log.txt" 2>nul
del /q "%REPO%\push_ops.bat" 2>nul

echo === GIT ADD === >> "%OUT%"
%GIT% -C "%REPO%" add -A >> "%OUT%" 2>&1

echo === GIT STATUS === >> "%OUT%"
%GIT% -C "%REPO%" status --short >> "%OUT%" 2>&1

echo === GIT COMMIT (cleanup) === >> "%OUT%"
%GIT% -C "%REPO%" commit -m "chore: remove temp push files" >> "%OUT%" 2>&1

echo === GIT PUSH === >> "%OUT%"
%GIT% -C "%REPO%" push origin main >> "%OUT%" 2>&1

echo === FINAL LOG === >> "%OUT%"
%GIT% -C "%REPO%" log --oneline -5 >> "%OUT%" 2>&1

echo DONE >> "%OUT%"
