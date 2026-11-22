[CmdletBinding()]
param(
    [switch]$Apply,
    [ValidateSet('AzureCli', 'Azd')]
    [string]$DeploymentMode = 'AzureCli',
    [string]$ValuesFile,
    [Parameter(Mandatory)]
    [string]$GeneratedProjectRoot,
    [string]$AdditionalRuntimePrincipalName,
    [Parameter(Mandatory)]
    [string]$OperatorIp
)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\common.ps1"

if (-not $Apply) {
    throw 'Database migration is disabled by default. Re-run with -Apply.'
}

$values = Get-DeploymentValues -DeploymentMode $DeploymentMode -ValuesFile $ValuesFile
Invoke-DeploymentPreflight -DeploymentMode $DeploymentMode -Values $values
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
if (
    $AdditionalRuntimePrincipalName -and
    $AdditionalRuntimePrincipalName -notmatch '^[A-Za-z0-9._-]+$'
) {
    throw 'Additional runtime database principal name contains unsupported characters.'
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
$databaseUrl =
    "postgresql://$encodedUser@$postgresHost`:5432/$database?sslmode=verify-full&sslrootcert=system"
$projectRoot = Assert-GeneratedOrderResolutionProject -ProjectRoot $GeneratedProjectRoot
$backend = Join-Path $projectRoot 'backend'

$previousDatabaseUrl = $env:DATABASE_URL
$previousMigrationDatabaseUrl = $env:MIGRATION_DATABASE_URL
$previousDatabaseAuthMode = $env:DATABASE_AUTH_MODE
$previousDatabasePassword = $env:DATABASE_PASSWORD
$previousDatabaseTlsMode = $env:DATABASE_TLS_MODE
$previousPgSslRootCert = $env:PGSSLROOTCERT
$previousPassword = $env:PGPASSWORD
$operatorRuleCreated = $false
Assert-PostgresClientSupportsSystemRoot
try {
    Add-PostgresOperatorFirewallRule `
        -SubscriptionId $subscriptionId `
        -ResourceGroup $resourceGroup `
        -ServerName $postgresName `
        -OperatorIp $OperatorIp
    $operatorRuleCreated = $true
    $env:DATABASE_URL = $databaseUrl
    $env:MIGRATION_DATABASE_URL = $databaseUrl
    $env:DATABASE_AUTH_MODE = 'password'
    $env:DATABASE_PASSWORD = $token
    $env:DATABASE_TLS_MODE = 'verify-full'
    $env:PGSSLROOTCERT = 'system'
    Push-Location $backend
    try {
        uv run python -m app.infrastructure.migrations upgrade
        if ($LASTEXITCODE -ne 0) { throw 'Platform database migration failed.' }
        uv run python -m app.order_resolution.migrations upgrade
        if ($LASTEXITCODE -ne 0) { throw 'Order Resolution database migration failed.' }
    }
    finally {
        Pop-Location
    }

    $env:PGPASSWORD = $token
    $runtimePrincipals = @($apiIdentityName)
    if ($AdditionalRuntimePrincipalName) {
        $runtimePrincipals += $AdditionalRuntimePrincipalName
    }
    $grantSql = $runtimePrincipals | ForEach-Object {
@"
GRANT CONNECT ON DATABASE "$database" TO "$_";
GRANT USAGE ON SCHEMA public TO "$_";
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO "$_";
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO "$_";
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO "$_";
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO "$_";
"@
    }
    $grantSql = $grantSql -join "`n"
    psql "host=$postgresHost dbname=$database user=$adminName sslmode=verify-full sslrootcert=system" `
        --set ON_ERROR_STOP=1 `
        --command $grantSql
    if ($LASTEXITCODE -ne 0) { throw 'Runtime database grants failed.' }
}
finally {
    $env:DATABASE_URL = $previousDatabaseUrl
    $env:MIGRATION_DATABASE_URL = $previousMigrationDatabaseUrl
    $env:DATABASE_AUTH_MODE = $previousDatabaseAuthMode
    $env:DATABASE_PASSWORD = $previousDatabasePassword
    $env:DATABASE_TLS_MODE = $previousDatabaseTlsMode
    $env:PGSSLROOTCERT = $previousPgSslRootCert
    $env:PGPASSWORD = $previousPassword
    if ($operatorRuleCreated) {
        Remove-PostgresOperatorFirewallRule `
            -SubscriptionId $subscriptionId `
            -ResourceGroup $resourceGroup `
            -ServerName $postgresName
    }
}
