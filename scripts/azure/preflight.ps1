[CmdletBinding()]
param(
    [ValidateSet('AzureCli', 'Azd')]
    [string]$DeploymentMode = 'AzureCli',
    [switch]$FromAzdEnvironment,
    [string]$SubscriptionId = $env:AZURE_SUBSCRIPTION_ID,
    [string]$TenantId = $env:AZURE_TENANT_ID,
    [string]$ExpectedUser = $env:AZURE_EXPECTED_USER,
    [string]$Location = $env:AZURE_LOCATION
)

$ErrorActionPreference = 'Stop'

if ($FromAzdEnvironment) {
    if ($DeploymentMode -cne 'Azd') {
        throw '-FromAzdEnvironment requires -DeploymentMode Azd.'
    }
    $previousUserAgent = $env:AZURE_DEV_USER_AGENT
    try {
        $env:AZURE_DEV_USER_AGENT = 'microsoft_foundry_skill'
        $values = azd env get-values --no-prompt
    }
    finally {
        $env:AZURE_DEV_USER_AGENT = $previousUserAgent
    }
    foreach ($line in $values) {
        if ($line -match '^([A-Z][A-Z0-9_]*)=(.*)$') {
            $name = $Matches[1]
            $value = $Matches[2].Trim('"')
            if ($name -eq 'AZURE_SUBSCRIPTION_ID') { $SubscriptionId = $value }
            if ($name -eq 'AZURE_TENANT_ID') { $TenantId = $value }
            if ($name -eq 'AZURE_EXPECTED_USER') { $ExpectedUser = $value }
            if ($name -eq 'AZURE_LOCATION') { $Location = $value }
        }
    }
}

if (-not $SubscriptionId -or -not $TenantId -or -not $ExpectedUser -or -not $Location) {
    throw 'AZURE_SUBSCRIPTION_ID, AZURE_TENANT_ID, AZURE_EXPECTED_USER, and AZURE_LOCATION are required.'
}

$identityMode = if ($DeploymentMode -ceq 'AzureCli') { 'azure-cli' } else { 'azd' }
python "$PSScriptRoot\preflight.py" `
    --subscription-id $SubscriptionId `
    --tenant-id $TenantId `
    --expected-user $ExpectedUser `
    --regions $Location `
    --identity-mode $identityMode

if ($LASTEXITCODE -ne 0) {
    throw 'Azure preflight failed.'
}
