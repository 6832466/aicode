$desktop = [Environment]::GetFolderPath('Desktop')
Write-Host "Desktop: $desktop"
Get-ChildItem $desktop -Filter '*gemini_cat*' | Select-Object Name, Length, LastWriteTime
