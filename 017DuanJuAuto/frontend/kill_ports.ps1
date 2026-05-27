$ports = @(5173, 5174, 5175, 5176, 5177, 8200)
foreach ($port in $ports) {
    $conn = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($conn) {
        $owner = $conn.OwningProcess
        if ($owner -ne 0) {
            Stop-Process -Id $owner -Force -ErrorAction SilentlyContinue
            Write-Host "Killed PID $owner on port $port"
        }
    } else {
        Write-Host "Port $port is free"
    }
}
