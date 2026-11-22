[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$GeneratedProjectRoot,

    [string]$ImageTag = "agent-blueprints-order-resolution-api-import-test",

    [string]$PythonPackageIndex = "https://pypi.org/simple"
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path "$PSScriptRoot\..\..").Path
. "$PSScriptRoot\common.ps1"

$generatedRoot = Assert-GeneratedOrderResolutionProject `
    -ProjectRoot $GeneratedProjectRoot
$dockerfile = Join-Path $root 'infra\docker\order-resolution-api.Dockerfile'

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw 'Docker is required for the generated API image import regression.'
}
$packageIndex = [uri]$PythonPackageIndex
if (
    -not $packageIndex.IsAbsoluteUri -or
    $packageIndex.Scheme -cne 'https' -or
    $packageIndex.UserInfo -or
    $packageIndex.Query -or
    $packageIndex.Fragment
) {
    throw 'PythonPackageIndex must be a credentialless HTTPS package index URL.'
}

$dockerfileSource = Get-Content -LiteralPath $dockerfile -Raw
if (
    $dockerfileSource -notmatch [regex]::Escape(
        'COPY --chown=blueprint:blueprint order_resolution_hosted/'
    ) -or
    $dockerfileSource -notmatch [regex]::Escape(
        'from order_resolution_hosted.bridge import build_workflow_host'
    ) -or
    $dockerfileSource -match '\bPYTHONPATH\b' -or
    $dockerfileSource -match '\bhosted-agent\b'
) {
    throw 'The generated API Dockerfile no longer contains the bounded bridge import contract.'
}

$buildContext = Initialize-GeneratedApiImageContext `
    -ProjectRoot $generatedRoot `
    -DockerfileSource $dockerfile

try {
    Push-Location $buildContext
    docker build `
        --file .azure-api.Dockerfile `
        --tag $ImageTag `
        --build-arg "PYTHON_PACKAGE_INDEX=$PythonPackageIndex" `
        .
    if ($LASTEXITCODE -ne 0) {
        throw 'Generated API Docker image build failed.'
    }

    docker run `
        --rm `
        --entrypoint python `
        $ImageTag `
        -c (
            'from order_resolution_hosted.bridge import build_workflow_host; ' +
            'assert callable(build_workflow_host); print(build_workflow_host.__module__)'
        )
    if ($LASTEXITCODE -ne 0) {
        throw 'Generated API image cannot import the hosted bridge factory.'
    }
}
finally {
    Pop-Location
    docker image rm --force $ImageTag 2>$null | Out-Null
}
