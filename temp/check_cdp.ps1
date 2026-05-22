$userData = "$env:LOCALAPPDATA\Google\Chrome\User Data"
Write-Host "Searching in: $userData"
$files = Get-ChildItem -Path $userData -Recurse -Filter 'DevToolsActivePort' -ErrorAction SilentlyContinue
if ($files) {
    foreach ($f in $files) {
        Write-Host "Found: $($f.FullName)"
        Write-Host "Content:"
        Get-Content $f.FullName
    }
} else {
    Write-Host "DevToolsActivePort not found anywhere in Chrome User Data"
}

# Also try to read from http endpoint
try {
    $r = Invoke-WebRequest -Uri 'http://127.0.0.1:9222/json/version' -UseBasicParsing -TimeoutSec 3
    Write-Host "HTTP API works:"
    Write-Host $r.Content
} catch {
    Write-Host "HTTP API error: $_"
}

# Check what's actually listening
Write-Host "`nPort 9222 listeners:"
netstat -ano | Select-String ':9222'
