$tempDir = "$env:TEMP\chrome-debug-profile"
Write-Host "Temp dir: $tempDir"
Start-Process -FilePath "chrome.exe" -ArgumentList "--remote-debugging-port=9222", "--user-data-dir=$tempDir"
Write-Host "Chrome started with debugging port 9222"
