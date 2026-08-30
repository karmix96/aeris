$ErrorActionPreference = "Stop"

$attemptId = "m1_storage_move_20260830_001"
$backup = "D:\AERIS_WSL_BACKUPS\Ubuntu_pre_move_20260830_attempt03.vhdx"
$exportMetadata = "D:\AERIS_WSL_BACKUPS\attempt03_metadata.json"
$destination = "D:\WSL\Ubuntu"
$moveMetadata = "D:\AERIS_WSL_BACKUPS\move_attempt01_metadata.json"
$stdout = "D:\AERIS_WSL_BACKUPS\move_attempt01.stdout.txt"
$expectedLength = 39155924992
$expectedSha256 = "a0ec879330d8c65a08eb34f20aa1db932b89943804340428a428b9897c30e9d1"

foreach ($path in @($destination, $moveMetadata, $stdout)) {
    if (Test-Path -LiteralPath $path) {
        throw "Refusing to overwrite existing move artifact: $path"
    }
}

if (-not (Test-Path -LiteralPath $backup)) {
    throw "Verified recovery VHD is missing: $backup"
}
$backupItem = Get-Item -LiteralPath $backup
if ($backupItem.Length -ne $expectedLength) {
    throw "Recovery VHD length changed: $($backupItem.Length), expected $expectedLength"
}

$export = Get-Content -Raw -LiteralPath $exportMetadata | ConvertFrom-Json
if ($export.exit_code -ne 0 -or -not $export.backup_exists) {
    throw "Export metadata does not record a successful backup"
}
if ($export.backup_length_bytes -ne $expectedLength) {
    throw "Export metadata length does not match the governed value"
}
if ($export.backup_sha256.ToLowerInvariant() -ne $expectedSha256) {
    throw "Export metadata hash does not match the governed value"
}

Write-Host "Independently re-hashing the recovery VHD before relocation..."
$independentSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $backup).Hash.ToLowerInvariant()
if ($independentSha256 -ne $expectedSha256) {
    throw "Independent recovery VHD hash does not match the governed value"
}

$distro = Get-ChildItem HKCU:\Software\Microsoft\Windows\CurrentVersion\Lxss |
    ForEach-Object {
        $properties = Get-ItemProperty $_.PSPath
        if ($properties.DistributionName -eq "Ubuntu") { $properties }
    }
if (-not $distro) {
    throw "Ubuntu is not registered"
}
if ($distro.BasePath -notlike "C:\*") {
    throw "Ubuntu is not at the expected pre-move C: location: $($distro.BasePath)"
}

Write-Host "Verified recovery metadata and pre-move registration."
Write-Host "Stopping WSL, then moving Ubuntu to $destination"
wsl.exe --shutdown
Start-Sleep -Seconds 3

$started = Get-Date
$moveOutput = & wsl.exe --manage Ubuntu --move $destination 2>&1
$exitCode = $LASTEXITCODE
$ended = Get-Date
$moveOutput | Out-File -LiteralPath $stdout -Encoding utf8

$postDistro = Get-ChildItem HKCU:\Software\Microsoft\Windows\CurrentVersion\Lxss |
    ForEach-Object {
        $properties = Get-ItemProperty $_.PSPath
        if ($properties.DistributionName -eq "Ubuntu") { $properties }
    }
$postVhd = if ($postDistro) { Join-Path $postDistro.BasePath "ext4.vhdx" } else { $null }
$postVhdExists = if ($postVhd) { Test-Path -LiteralPath $postVhd } else { $false }

$result = [ordered]@{
    schema_version = 1
    attempt_id = $attemptId
    started_at = $started.ToString("o")
    ended_at = $ended.ToString("o")
    elapsed_seconds = ($ended - $started).TotalSeconds
    exit_code = $exitCode
    backup_path = $backup
    expected_backup_sha256 = $expectedSha256
    independent_backup_sha256 = $independentSha256
    source_base_path = $distro.BasePath
    requested_destination = $destination
    registered_base_path_after = if ($postDistro) { $postDistro.BasePath } else { $null }
    registered_vhd_after = $postVhd
    registered_vhd_exists_after = $postVhdExists
    registered_vhd_length_after = if ($postVhdExists) { (Get-Item -LiteralPath $postVhd).Length } else { $null }
    c_free_bytes_after = (Get-Volume -DriveLetter C).SizeRemaining
    d_free_bytes_after = (Get-Volume -DriveLetter D).SizeRemaining
    unregister_used = $false
    cleanup_performed = $false
}
$result | ConvertTo-Json -Depth 4 | Out-File -LiteralPath $moveMetadata -Encoding utf8

if ($exitCode -ne 0 -or -not $postVhdExists) {
    Write-Host "Move FAILED or post-move VHD is unresolved. Evidence and recovery export are retained."
    Write-Host ($result | ConvertTo-Json -Depth 4)
    Read-Host "Press Enter to close"
    exit 1
}

Write-Host "Move command completed and the registered VHD exists at the new location."
Write-Host ($result | ConvertTo-Json -Depth 4)
Write-Host "Reopen Ubuntu/Codex for Linux-side identity and filesystem verification."
Read-Host "Press Enter to close"
