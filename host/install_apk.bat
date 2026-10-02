@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

rem  Install APK to the speaker and start the bridge service. ASCII-only.

if exist "%~dp0adb\adb.exe" (
    set "ADB=%~dp0adb\adb.exe"
    goto :have_adb
)
where adb >nul 2>nul
if %errorlevel%==0 (
    set "ADB=adb"
    goto :have_adb
)
if defined ANDROID_HOME (
    set "SDK=%ANDROID_HOME%"
) else if defined ANDROID_SDK_ROOT (
    set "SDK=%ANDROID_SDK_ROOT%"
) else (
    set "SDK=%LOCALAPPDATA%\Android\Sdk"
)
if not exist "%SDK%\platform-tools\adb.exe" (
    echo adb not found. Install Android SDK Platform-Tools or add adb to PATH.
    exit /b 1
)
set "ADB=%SDK%\platform-tools\adb.exe"

:have_adb
rem  NOTE: do not use "for %%F in (literal path)" here - it assigns even when the
rem  file does not exist, so the fallbacks below would never run.
set "APK="
if exist "%~dp0..\dist\LX04-PC-Bridge.apk" set "APK=%~dp0..\dist\LX04-PC-Bridge.apk"
if not defined APK (
    for %%F in ("%~dp0..\app\build\outputs\apk\debug\*.apk") do if not defined APK set "APK=%%~fF"
)
if not defined APK (
    for %%F in ("%~dp0..\app\build\outputs\apk\release\*.apk") do if not defined APK set "APK=%%~fF"
)
if not defined APK (
    echo no APK found. Run: python build_apk.py   (or Build APK in Android Studio)
    exit /b 1
)

echo installing: %APK%
"%ADB%" install -r -t "%APK%"
"%ADB%" shell pm grant com.lx04.pcbridge android.permission.RECORD_AUDIO
"%ADB%" shell appops set com.lx04.pcbridge WRITE_SETTINGS allow
"%ADB%" shell am start-foreground-service -n com.lx04.pcbridge/.BridgeService
echo done. background service started; no need to open the app on the speaker.
