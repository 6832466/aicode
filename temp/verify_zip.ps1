$desktop = [Environment]::GetFolderPath('Desktop')
$zip = Join-Path $desktop 'BatchImageGen.zip'

Write-Host "File: $zip"
$item = Get-Item $zip
Write-Host "Size: $([math]::Round($item.Length / 1MB, 1)) MB"
Write-Host "Modified: $($item.LastWriteTime)"

# List top-level contents of zip
Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = [System.IO.Compression.ZipFile]::OpenRead($zip)
$archive.Entries | Where-Object { $_.FullName -match '^[^/]+/?$' } | Select-Object -First 20 | ForEach-Object {
    $size = if ($_.Length -gt 0) { "$([math]::Round($_.Length / 1KB, 1)) KB" } else { "(dir)" }
    Write-Host "  $($_.FullName) $size"
}
$archive.Dispose()
