param(
    [int]$IntervalSeconds = 10,
    [switch]$Move
)

$ErrorActionPreference = "Stop"
$Seen = @{}

Write-Host "Watching for removable drives. Press Ctrl+C to stop."

while ($true) {
    $drives = Get-CimInstance Win32_LogicalDisk |
        Where-Object { $_.DriveType -eq 2 -and $_.DeviceID } |
        Select-Object -ExpandProperty DeviceID

    foreach ($drive in $drives) {
        $root = "$drive\"
        if (-not $Seen.ContainsKey($root)) {
            $Seen[$root] = $true
            Write-Host "Importing wardrive files from $root"
            $argsList = @("-ExecutionPolicy", "Bypass", "-File", (Join-Path $PSScriptRoot "import_sd.ps1"), "-Source", $root)
            if ($Move) {
                $argsList += "-Move"
            }
            & powershell @argsList
        }
    }

    foreach ($known in @($Seen.Keys)) {
        if (-not (Test-Path $known)) {
            $Seen.Remove($known)
        }
    }

    Start-Sleep -Seconds $IntervalSeconds
}
