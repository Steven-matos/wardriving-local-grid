param(
    [Parameter(Mandatory = $true)]
    [string]$Source,

    [switch]$Move
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = "python"
$Importer = Join-Path $PSScriptRoot "import_wardrive.py"

$argsList = @($Importer, "--source", $Source)
if ($Move) {
    $argsList += "--move"
}

Push-Location $Root
try {
    & $Python @argsList
}
finally {
    Pop-Location
}
