$ErrorActionPreference = "Stop"

$attemptId = "m1_storage_export_20260830_003"
$backup = "D:\AERIS_WSL_BACKUPS\Ubuntu_pre_move_20260830_attempt03.vhdx"
$metadata = "D:\AERIS_WSL_BACKUPS\attempt03_metadata.json"
$stdout = "D:\AERIS_WSL_BACKUPS\attempt03.stdout.txt"

foreach ($path in @($backup, $metadata, $stdout)) {
    if (Test-Path -LiteralPath $path) {
        throw "Refusing to overwrite existing attempt artifact: $path"
    }
}

Write-Host "Stopping WSL so Ubuntu's VHD is closed consistently..."
wsl.exe --shutdown
Start-Sleep -Seconds 3

$started = Get-Date
Write-Host "Exporting Ubuntu recovery VHD to $backup"
$exportOutput = & wsl.exe --export Ubuntu $backup --format vhd 2>&1
$exitCode = $LASTEXITCODE
$ended = Get-Date
$exportOutput | Out-File -LiteralPath $stdout -Encoding utf8

$exists = Test-Path -LiteralPath $backup
$length = if ($exists) { (Get-Item -LiteralPath $backup).Length } else { $null }
$sha256 = if ($exitCode -eq 0 -and $exists) {
    (Get-FileHash -Algorithm SHA256 -LiteralPath $backup).Hash.ToLowerInvariant()
} else {
    $null
}

$result = [ordered]@{
    schema_version = 1
    attempt_id = $attemptId
    started_at = $started.ToString("o")
    ended_at = $ended.ToString("o")
    elapsed_seconds = ($ended - $started).TotalSeconds
    exit_code = $exitCode
    backup_path = $backup
    backup_exists = $exists
    backup_length_bytes = $length
    backup_sha256 = $sha256
    stdout_path = $stdout
    d_free_bytes_after = (Get-Volume -DriveLetter D).SizeRemaining
    move_attempted = $false
}
$result | ConvertTo-Json -Depth 4 | Out-File -LiteralPath $metadata -Encoding utf8

if ($exitCode -ne 0 -or -not $exists) {
    Write-Host "Export FAILED. Evidence is retained; do not attempt the move."
    Write-Host ($result | ConvertTo-Json -Depth 4)
    Read-Host "Press Enter to close"
    exit 1
}

Write-Host "Export and SHA-256 verification completed."
Write-Host ($result | ConvertTo-Json -Depth 4)
Write-Host "Do NOT move or unregister Ubuntu yet. Reopen Codex for inspection."
Read-Host "Press Enter to close"

