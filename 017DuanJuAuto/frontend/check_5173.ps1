$conn = Get-NetTCPConnection -LocalPort 5173 -ErrorAction SilentlyContinue | Select-Object -First 1
if ($conn -and $conn.OwningProcess -ne 0) {
    Stop-Process -Id $conn.OwningProcess -Force -ErrorAction SilentlyContinue
    Write-Host "Killed $($conn.OwningProcess)"
} else {
    Write-Host "Port 5173 free or owned by system"
}
