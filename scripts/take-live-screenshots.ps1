# Automated Live Screenshot Pass Script
param(
    [string]$OutputDir = "C:\Users\ASUS\.gemini\antigravity\brain\ecddef6b-27cb-4397-810a-9859b8bd969c"
)

$ErrorActionPreference = "Continue"

Write-Host ">>> Step 1: Connecting to Android device..."
adb connect 127.0.0.1:5555
Start-Sleep -Seconds 2
adb devices

Write-Host ">>> Step 2: Checking boot status..."
for ($i = 0; $i -lt 30; $i++) {
    $boot = (adb -s 127.0.0.1:5555 shell getprop sys.boot_completed 2>&1)
    if ("$boot".Trim() -eq "1") {
        Write-Host ">>> Android OS boot is complete!"
        break
    }
    Start-Sleep -Seconds 2
}

Write-Host ">>> Step 3: Installing Cretona Debug APK..."
$apkPath = "D:\1. UMT\3.5. PLUS26\Cretona\app\build\outputs\apk\debug\app-debug.apk"
adb -s 127.0.0.1:5555 install -r "$apkPath"

Write-Host ">>> Step 4: Launching MainActivity..."
adb -s 127.0.0.1:5555 shell am start -n com.cretona.app.debug/com.cretona.app.MainActivity
Start-Sleep -Seconds 4

function Take-Screen {
    param([string]$Name)
    $remotePath = "/sdcard/$Name.png"
    $localPath = Join-Path $OutputDir "$Name.png"
    adb -s 127.0.0.1:5555 shell screencap -p "$remotePath"
    adb -s 127.0.0.1:5555 pull "$remotePath" "$localPath"
    Write-Host "Captured: $localPath"
}

Write-Host ">>> Step 5: Capturing Home Screen..."
Take-Screen "live_screen_01_home"

Write-Host ">>> Step 6: Navigating to History tab..."
# Tap on History tab (bottom nav item 2, roughly 360, 2800 on 1344x2992 screen)
adb -s 127.0.0.1:5555 shell input tap 400 2800
Start-Sleep -Seconds 2
Take-Screen "live_screen_02_history"

Write-Host ">>> Step 7: Navigating to Credits tab..."
# Tap on Credits tab (bottom nav item 3, roughly 672, 2800)
adb -s 127.0.0.1:5555 shell input tap 672 2800
Start-Sleep -Seconds 2
Take-Screen "live_screen_03_credits"

Write-Host ">>> Step 8: Navigating to Profile / Admin..."
# Tap on Profile tab (bottom nav item 4, roughly 1000, 2800)
adb -s 127.0.0.1:5555 shell input tap 1000 2800
Start-Sleep -Seconds 2
Take-Screen "live_screen_04_profile_admin"

Write-Host ">>> Step 9: Returning to Home..."
adb -s 127.0.0.1:5555 shell input tap 150 2800
Start-Sleep -Seconds 2
Take-Screen "live_screen_05_home_final"

Write-Host ">>> All screenshots successfully captured!"
