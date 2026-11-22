[CmdletBinding()]
param(
    [switch]$Apply,
    [ValidateSet('AzureCli', 'Azd')]
    [string]$DeploymentMode = 'AzureCli',
    [string]$ValuesFile,
    [string]$AdditionalPrincipalName,
    [string]$AdditionalPrincipalObjectId,
    [string]$OperatorIp
)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\common.ps1"

if (-not $Apply) {
    throw 'PostgreSQL configuration is disabled by default. Re-run with -Apply.'
}

$values = Get-DeploymentValues -DeploymentMode $DeploymentMode -ValuesFile $ValuesFile
Invoke-DeploymentPreflight -DeploymentMode $DeploymentMode -Values $values
$subscriptionId = Get-RequiredValue $values 'AZURE_SUBSCRIPTION_ID'
$resourceGroup = Get-RequiredValue $values 'AZURE_RESOURCE_GROUP'
$apiAppName = Get-RequiredValue $values 'AZURE_API_CONTAINER_APP_NAME'
$postgresName = Get-RequiredValue $values 'AZURE_POSTGRES_SERVER_NAME'
$postgresHost = Get-RequiredValue $values 'AZURE_POSTGRESQL_HOST'
$adminName = Get-RequiredValue $values 'AZURE_POSTGRES_ADMIN_PRINCIPAL_NAME'
$apiIdentityName = Get-RequiredValue $values 'AZURE_API_IDENTITY_NAME'
$apiIdentityObjectId = Get-RequiredValue $values 'AZURE_API_IDENTITY_PRINCIPAL_ID'

$apiIdentityGuid = [guid]::Empty
if (
    $apiIdentityName -notmatch '^[A-Za-z0-9._-]+$' -or
    -not [guid]::TryParse($apiIdentityObjectId, [ref]$apiIdentityGuid)
) {
    throw 'API managed-identity name or object ID is invalid.'
}
if (($AdditionalPrincipalName -and -not $AdditionalPrincipalObjectId) -or
    ($AdditionalPrincipalObjectId -and -not $AdditionalPrincipalName)) {
    throw 'AdditionalPrincipalName and AdditionalPrincipalObjectId must be supplied together.'
}
$additionalPrincipalGuid = [guid]::Empty
if (
    $AdditionalPrincipalName -and
    (
        $AdditionalPrincipalName -notmatch '^[A-Za-z0-9._-]+$' -or
        -not [guid]::TryParse($AdditionalPrincipalObjectId, [ref]$additionalPrincipalGuid)
    )
) {
    throw 'Additional PostgreSQL principal input is invalid.'
}

$outbound = az containerapp show `
    --subscription $subscriptionId `
    --resource-group $resourceGroup `
    --name $apiAppName `
    --query properties.outboundIpAddresses `
    --output tsv
if ($LASTEXITCODE -ne 0 -or -not $outbound) {
    throw 'Container Apps outbound IP addresses were not returned.'
}

$addresses = @($outbound -split '[,\s]+' | Where-Object { $_ } | Sort-Object -Unique)
$desiredRuleNames = @()
for ($index = 0; $index -lt $addresses.Count; $index++) {
    $address = $addresses[$index]
    if ($address -notmatch '^\d{1,3}(\.\d{1,3}){3}$') {
        throw "Unexpected Container Apps outbound address: $address"
    }
    $ruleName = "container-apps-{0:D2}" -f ($index + 1)
    $desiredRuleNames += $ruleName
    az postgres flexible-server firewall-rule create `
        --subscription $subscriptionId `
        --resource-group $resourceGroup `
        --name $postgresName `
        --rule-name $ruleName `
        --start-ip-address $address `
        --end-ip-address $address `
        --only-show-errors | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Unable to configure PostgreSQL firewall for $address." }
}

$managedRules = @(
    az postgres flexible-server firewall-rule list `
        --subscription $subscriptionId `
        --resource-group $resourceGroup `
        --name $postgresName `
        --query "[?starts_with(name, 'container-apps-')].name" `
        --output tsv
)
if ($LASTEXITCODE -ne 0) {
    throw 'Unable to list managed PostgreSQL firewall rules.'
}
foreach ($ruleName in $managedRules) {
    if ($ruleName -and $ruleName -notin $desiredRuleNames) {
        az postgres flexible-server firewall-rule delete `
            --subscription $subscriptionId `
            --resource-group $resourceGroup `
            --name $postgresName `
            --rule-name $ruleName `
            --yes `
            --only-show-errors | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "Unable to remove stale PostgreSQL firewall rule $ruleName."
        }
    }
}

if (-not $OperatorIp) {
    throw 'OperatorIp is required to create the PostgreSQL managed-identity principal.'
}

if (-not (Get-Command psql -ErrorAction SilentlyContinue)) {
    throw 'psql is required to create the managed-identity database principal.'
}

$token = az account get-access-token `
    --subscription $subscriptionId `
    --resource-type oss-rdbms `
    --query accessToken `
    --output tsv
if ($LASTEXITCODE -ne 0 -or -not $token) {
    throw 'Unable to obtain a PostgreSQL Entra access token.'
}

$previousPassword = $env:PGPASSWORD
$operatorRuleCreated = $false
try {
    Add-PostgresOperatorFirewallRule `
        -SubscriptionId $subscriptionId `
        -ResourceGroup $resourceGroup `
        -ServerName $postgresName `
        -OperatorIp $OperatorIp
    $operatorRuleCreated = $true
    $env:PGPASSWORD = $token
    $additionalPrincipalSql = ''
    if ($AdditionalPrincipalName) {
        $additionalPrincipalSql = @"
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '$AdditionalPrincipalName') THEN
    PERFORM * FROM pg_catalog.pgaadauth_create_principal_with_oid(
      '$AdditionalPrincipalName',
      '$AdditionalPrincipalObjectId',
      'service',
      false,
      false
    );
  END IF;
"@
    }
    $sql = @"
DO `$body`$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '$apiIdentityName') THEN
    PERFORM * FROM pg_catalog.pgaadauth_create_principal_with_oid(
      '$apiIdentityName',
      '$apiIdentityObjectId',
      'service',
      false,
      false
    );
  END IF;
$additionalPrincipalSql
END
`$body`$;
"@
    psql "host=$postgresHost dbname=postgres user=$adminName sslmode=verify-full" `
        --set ON_ERROR_STOP=1 `
        --command $sql
    if ($LASTEXITCODE -ne 0) { throw 'Managed-identity PostgreSQL principal creation failed.' }
}
finally {
    $env:PGPASSWORD = $previousPassword
    if ($operatorRuleCreated) {
        Remove-PostgresOperatorFirewallRule `
            -SubscriptionId $subscriptionId `
            -ResourceGroup $resourceGroup `
            -ServerName $postgresName
    }
}
