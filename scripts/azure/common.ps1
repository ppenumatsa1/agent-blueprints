function Get-AzdEnvironmentValues {
    $previousUserAgent = $env:AZURE_DEV_USER_AGENT
    try {
        $env:AZURE_DEV_USER_AGENT = 'microsoft_foundry_skill'
        $lines = azd env get-values --no-prompt
        if ($LASTEXITCODE -ne 0) { throw 'Unable to read the selected azd environment.' }
    }
    finally {
        $env:AZURE_DEV_USER_AGENT = $previousUserAgent
    }

    $values = @{}
    foreach ($line in $lines) {
        if ($line -match '^([A-Z][A-Z0-9_]*)=(.*)$') {
            $values[$Matches[1]] = $Matches[2].Trim('"')
        }
    }
    return $values
}

function Get-DeploymentValues {
    param(
        [ValidateSet('AzureCli', 'Azd')]
        [string]$DeploymentMode,
        [string]$ValuesFile
    )
    if ($DeploymentMode -ceq 'Azd') {
        return Get-AzdEnvironmentValues
    }
    if (-not $ValuesFile) {
        throw 'ValuesFile is required in AzureCli mode.'
    }
    $resolved = Resolve-Path -LiteralPath $ValuesFile
    $values = Get-Content -LiteralPath $resolved -Raw | ConvertFrom-Json -AsHashtable
    if (-not ($values -is [hashtable])) {
        throw 'ValuesFile must contain one JSON object.'
    }
    return $values
}

function Invoke-DeploymentPreflight {
    param(
        [ValidateSet('AzureCli', 'Azd')]
        [string]$DeploymentMode,
        [hashtable]$Values
    )
    if ($DeploymentMode -ceq 'Azd') {
        & "$PSScriptRoot\preflight.ps1" `
            -DeploymentMode Azd `
            -FromAzdEnvironment | Out-Null
        return
    }
    & "$PSScriptRoot\preflight.ps1" `
        -DeploymentMode AzureCli `
        -SubscriptionId (Get-RequiredValue $Values 'AZURE_SUBSCRIPTION_ID') `
        -TenantId (Get-RequiredValue $Values 'AZURE_TENANT_ID') `
        -ExpectedUser (Get-RequiredValue $Values 'AZURE_EXPECTED_USER') `
        -Location (Get-RequiredValue $Values 'AZURE_LOCATION') | Out-Null
}

function Assert-GeneratedOrderResolutionProject {
    param(
        [Parameter(Mandatory)]
        [string]$ProjectRoot
    )
    $resolved = (Resolve-Path -LiteralPath $ProjectRoot).Path
    foreach ($relative in @(
        'backend\Dockerfile',
        'backend\app',
        'frontend\Dockerfile',
        'frontend\nginx.conf',
        'hosted-agent\main.py',
        'hosted-agent\requirements.txt',
        'hosted-agent\src\order_resolution_hosted',
        'scripts\foundry\publish_order_resolution_hosted.py'
    )) {
        if (-not (Test-Path -LiteralPath (Join-Path $resolved $relative))) {
            throw "Generated Order Resolution source is missing: $relative"
        }
    }
    return $resolved
}

function Get-RequiredValue {
    param(
        [hashtable]$Values,
        [string]$Name
    )
    $value = $Values[$Name]
    if (-not $value) { throw "Missing azd environment value: $Name" }
    return $value
}

function Assert-PublicIpv4 {
    param(
        [Parameter(Mandatory)]
        [string]$Address
    )
    $parsed = $null
    if (
        -not [System.Net.IPAddress]::TryParse($Address, [ref]$parsed) -or
        $parsed.AddressFamily -ne [System.Net.Sockets.AddressFamily]::InterNetwork
    ) {
        throw 'OperatorIp must be one public IPv4 address.'
    }
    $bytes = $parsed.GetAddressBytes()
    $isPrivateOrReserved = (
        $bytes[0] -eq 0 -or
        $bytes[0] -eq 10 -or
        $bytes[0] -eq 127 -or
        ($bytes[0] -eq 100 -and $bytes[1] -ge 64 -and $bytes[1] -le 127) -or
        ($bytes[0] -eq 169 -and $bytes[1] -eq 254) -or
        ($bytes[0] -eq 172 -and $bytes[1] -ge 16 -and $bytes[1] -le 31) -or
        ($bytes[0] -eq 192 -and $bytes[1] -eq 168) -or
        $bytes[0] -ge 224
    )
    if ($isPrivateOrReserved) {
        throw 'OperatorIp must be one public IPv4 address.'
    }
}

function Add-PostgresOperatorFirewallRule {
    param(
        [Parameter(Mandatory)]
        [string]$SubscriptionId,
        [Parameter(Mandatory)]
        [string]$ResourceGroup,
        [Parameter(Mandatory)]
        [string]$ServerName,
        [Parameter(Mandatory)]
        [string]$OperatorIp
    )
    Assert-PublicIpv4 -Address $OperatorIp
    az postgres flexible-server firewall-rule create `
        --subscription $SubscriptionId `
        --resource-group $ResourceGroup `
        --name $ServerName `
        --rule-name 'deployment-operator' `
        --start-ip-address $OperatorIp `
        --end-ip-address $OperatorIp `
        --only-show-errors | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw 'Unable to configure the temporary PostgreSQL operator firewall rule.'
    }
}

function Remove-PostgresOperatorFirewallRule {
    param(
        [Parameter(Mandatory)]
        [string]$SubscriptionId,
        [Parameter(Mandatory)]
        [string]$ResourceGroup,
        [Parameter(Mandatory)]
        [string]$ServerName
    )
    $rule = az postgres flexible-server firewall-rule list `
        --subscription $SubscriptionId `
        --resource-group $ResourceGroup `
        --name $ServerName `
        --query "[?name == 'deployment-operator'].name | [0]" `
        --output tsv
    if ($LASTEXITCODE -ne 0) {
        throw 'Unable to inspect the temporary PostgreSQL operator firewall rule.'
    }
    if ($rule) {
        az postgres flexible-server firewall-rule delete `
            --subscription $SubscriptionId `
            --resource-group $ResourceGroup `
            --name $ServerName `
            --rule-name 'deployment-operator' `
            --yes `
            --only-show-errors | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw 'Unable to remove the temporary PostgreSQL operator firewall rule.'
        }
    }
}
