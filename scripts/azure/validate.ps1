[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$root = Resolve-Path "$PSScriptRoot\..\.."

Push-Location $root
try {
    az bicep build --file infra\main.bicep --stdout | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Bicep build failed.' }

    az bicep lint --file infra\main.bicep
    if ($LASTEXITCODE -ne 0) { throw 'Bicep lint failed.' }

    python -m unittest discover -s infra\tests -v
    if ($LASTEXITCODE -ne 0) { throw 'Infrastructure contract tests failed.' }
}
finally {
    Pop-Location
}
