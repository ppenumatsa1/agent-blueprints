[CmdletBinding()]
param(
    [switch]$Apply,
    [Parameter(Mandatory)]
    [string]$OperatorIp
)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\common.ps1"

if (-not $Apply) {
    throw 'Database migration is disabled by default. Re-run with -Apply.'
}

& "$PSScriptRoot\preflight.ps1" -FromAzdEnvironment
$values = Get-AzdEnvironmentValues
$subscriptionId = Get-RequiredValue $values 'AZURE_SUBSCRIPTION_ID'
$resourceGroup = Get-RequiredValue $values 'AZURE_RESOURCE_GROUP'
$postgresHost = Get-RequiredValue $values 'AZURE_POSTGRESQL_HOST'
$postgresName = Get-RequiredValue $values 'AZURE_POSTGRES_SERVER_NAME'
$database = Get-RequiredValue $values 'AZURE_POSTGRESQL_DATABASE'
$adminName = Get-RequiredValue $values 'AZURE_POSTGRES_ADMIN_PRINCIPAL_NAME'
$apiIdentityName = Get-RequiredValue $values 'AZURE_API_IDENTITY_NAME'

if ($adminName -notmatch '^[A-Za-z0-9._#@-]+$' -or $apiIdentityName -notmatch '^[A-Za-z0-9._-]+$') {
    throw 'Database principal name contains unsupported characters.'
}

$token = az account get-access-token `
    --subscription $subscriptionId `
    --resource-type oss-rdbms `
    --query accessToken `
    --output tsv
if ($LASTEXITCODE -ne 0 -or -not $token) {
    throw 'Unable to obtain a PostgreSQL Entra access token.'
}

$encodedUser = [uri]::EscapeDataString($adminName)
$encodedToken = [uri]::EscapeDataString($token)
$databaseUrl = "postgresql://$encodedUser`:$encodedToken@$postgresHost`:5432/$database?sslmode=require"
$root = Resolve-Path "$PSScriptRoot\..\.."
$backend = Join-Path $root 'blueprints\maf\workflow\backend'

$previousDatabaseUrl = $env:DATABASE_URL
$previousPassword = $env:PGPASSWORD
$operatorRuleCreated = $false
try {
    Add-PostgresOperatorFirewallRule `
        -SubscriptionId $subscriptionId `
        -ResourceGroup $resourceGroup `
        -ServerName $postgresName `
        -OperatorIp $OperatorIp
    $operatorRuleCreated = $true
    $env:DATABASE_URL = $databaseUrl
    Push-Location $backend
    try {
        uv run python -m app.infrastructure.migrations upgrade
        if ($LASTEXITCODE -ne 0) { throw 'Application database migration failed.' }
    }
    finally {
        Pop-Location
    }

    $env:PGPASSWORD = $token
    $grantSql = @"
GRANT CONNECT ON DATABASE "$database" TO "$apiIdentityName";
GRANT USAGE ON SCHEMA public TO "$apiIdentityName";
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO "$apiIdentityName";
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO "$apiIdentityName";
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO "$apiIdentityName";
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO "$apiIdentityName";
"@
    psql "host=$postgresHost dbname=$database user=$adminName sslmode=require" `
        --set ON_ERROR_STOP=1 `
        --command $grantSql
    if ($LASTEXITCODE -ne 0) { throw 'Runtime database grants failed.' }
}
finally {
    $env:DATABASE_URL = $previousDatabaseUrl
    $env:PGPASSWORD = $previousPassword
    if ($operatorRuleCreated) {
        Remove-PostgresOperatorFirewallRule `
            -SubscriptionId $subscriptionId `
            -ResourceGroup $resourceGroup `
            -ServerName $postgresName
    }
}
