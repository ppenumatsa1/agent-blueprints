[CmdletBinding()]
param(
    [switch]$Apply,
    [ValidateSet('AzureCli', 'Azd')]
    [string]$DeploymentMode = 'AzureCli',
    [string]$ValuesFile,
    [Parameter(Mandatory)]
    [string]$ApiRevision,
    [Parameter(Mandatory)]
    [string]$WebRevision
)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\common.ps1"

if (-not $Apply) {
    throw 'Rollback is disabled by default. Re-run with -Apply after reviewing the target revisions.'
}

$values = Get-DeploymentValues -DeploymentMode $DeploymentMode -ValuesFile $ValuesFile
Invoke-DeploymentPreflight -DeploymentMode $DeploymentMode -Values $values
$subscriptionId = Get-RequiredValue $values 'AZURE_SUBSCRIPTION_ID'
$resourceGroup = Get-RequiredValue $values 'AZURE_RESOURCE_GROUP'
$apiName = Get-RequiredValue $values 'AZURE_API_CONTAINER_APP_NAME'
$webName = Get-RequiredValue $values 'AZURE_WEB_CONTAINER_APP_NAME'

function Restore-RevisionImage {
    param(
        [string]$AppName,
        [string]$RevisionName
    )
    $image = az containerapp revision show `
        --subscription $subscriptionId `
        --resource-group $resourceGroup `
        --name $AppName `
        --revision $RevisionName `
        --query properties.template.containers[0].image `
        --output tsv
    if ($LASTEXITCODE -ne 0 -or -not $image) {
        throw "Unable to read rollback image from revision $RevisionName."
    }
    if ($image -notmatch '@sha256:[0-9a-f]{64}$') {
        throw "Rollback revision $RevisionName does not use an immutable image digest."
    }
    az containerapp update `
        --subscription $subscriptionId `
        --resource-group $resourceGroup `
        --name $AppName `
        --image $image `
        --only-show-errors | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Rollback failed for $AppName." }
}

Restore-RevisionImage -AppName $apiName -RevisionName $ApiRevision
Restore-RevisionImage -AppName $webName -RevisionName $WebRevision

$healthArguments = @(
    "$PSScriptRoot\health-check.py",
    '--deployment-mode',
    $(if ($DeploymentMode -ceq 'AzureCli') { 'azure-cli' } else { 'azd' })
)
if ($DeploymentMode -ceq 'AzureCli') {
    $healthArguments += @('--values-file', $ValuesFile)
}
python @healthArguments
if ($LASTEXITCODE -ne 0) { throw 'Rollback health verification failed.' }
