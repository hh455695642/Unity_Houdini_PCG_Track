param(
    [string]$McpRepo = 'E:\HoudiniProject\oculairmedia_houdini_mcp',
    [string]$HythonPath = 'D:\Software\Side Effects Software\Houdini 21.0.440\bin\hython.exe',
    [string]$HoudiniStartupScript = 'C:\Users\ruze\Documents\houdini21.0\scripts\123.py',
    [string]$HoudiniHost = '127.0.0.1',
    [int]$HoudiniPort = 18811,
    [int]$McpPort = 3055,
    [int]$StartupTimeoutSeconds = 180
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

function Write-Step {
    param(
        [string]$Status,
        [string]$Message
    )

    Write-Host ("[{0}] {1}" -f $Status, $Message)
}

function Test-TcpListen {
    param([int]$Port)

    return [bool](Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
}

function Get-ListenerInfo {
    param([int]$Port)

    $conn = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $conn) {
        return $null
    }

    $process = Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue
    [PSCustomObject]@{
        Port        = $Port
        PID         = $conn.OwningProcess
        ProcessName = $process.ProcessName
        Path        = $process.Path
    }
}

function Install-HoudiniRpcStartupHook {
    param(
        [string]$Path,
        [int]$Port
    )

    $markerStart = '# <HoudiniMcpStart>'
    $markerEnd = '# <HoudiniMcpEnd>'
    $rpcStartLine = if ($Port -eq 18811) {
        '    hrpyc.start_server(port=18811)'
    }
    else {
        "    hrpyc.start_server(port=$Port)"
    }

    $hook = @"

$markerStart
# Auto-start Houdini RPC for oculairmedia/houdini-mcp.
try:
    import hrpyc
$rpcStartLine
except OSError:
    # Usually means the RPC port is already active.
    pass
except Exception as exc:
    print("[Houdini MCP] Failed to start hrpyc on ${Port}: {}".format(exc))
$markerEnd
"@

    $directory = Split-Path -Path $Path -Parent
    if (-not (Test-Path -LiteralPath $directory)) {
        New-Item -ItemType Directory -Force -Path $directory | Out-Null
    }

    if (Test-Path -LiteralPath $Path) {
        $existing = Get-Content -LiteralPath $Path -Raw -Encoding UTF8
        if ($existing.Contains($markerStart)) {
            Write-Step 'OK' "Houdini RPC startup hook already present: $Path"
            return
        }

        [System.IO.File]::AppendAllText($Path, "`r`n$hook", [System.Text.UTF8Encoding]::new($false))
        Write-Step 'UPDATED' "Appended Houdini RPC startup hook: $Path"
        return
    }

    [System.IO.File]::WriteAllText($Path, $hook.TrimStart(), [System.Text.UTF8Encoding]::new($false))
    Write-Step 'UPDATED' "Created Houdini RPC startup hook: $Path"
}

function Test-HoudiniRpc {
    param(
        [string]$PythonPath,
        [string]$RpcHost,
        [int]$Port
    )

    if (-not (Test-Path -LiteralPath $PythonPath)) {
        throw "Missing hython executable: $PythonPath"
    }

    if (-not (Test-TcpListen -Port $Port)) {
        return [PSCustomObject]@{
            Connected = $false
            Version   = $null
            HipPath   = $null
        Message   = "No listener on $RpcHost`:$Port"
        }
    }

    $code = "import hrpyc; conn,hou=hrpyc.import_remote_module('$RpcHost',$Port,'hou'); print(hou.applicationVersionString()); print(hou.hipFile.path())"
    $output = & $PythonPath -c $code 2>&1
    $exitCode = $LASTEXITCODE

    if ($exitCode -ne 0) {
        return [PSCustomObject]@{
            Connected = $false
            Version   = $null
            HipPath   = $null
            Message   = ($output -join "`n")
        }
    }

    return [PSCustomObject]@{
        Connected = $true
        Version   = [string]$output[0]
        HipPath   = [string]$output[1]
        Message   = 'Connected'
    }
}

function Test-McpHealth {
    param([int]$Port)

    $uri = if ($Port -eq 3055) {
        'http://127.0.0.1:3055/health'
    }
    else {
        "http://127.0.0.1:$Port/health"
    }
    try {
        $response = Invoke-RestMethod -UseBasicParsing -Uri $uri -TimeoutSec 3 -ErrorAction Stop
        return [PSCustomObject]@{
            Healthy = ($response.status -eq 'healthy')
            Uri     = $uri
            Status  = $response.status
            Service = $response.service
            Error   = $null
        }
    }
    catch {
        return [PSCustomObject]@{
            Healthy = $false
            Uri     = $uri
            Status  = $null
            Service = $null
            Error   = $_.Exception.Message
        }
    }
}

function Start-HoudiniMcpServer {
    param(
        [string]$Repo,
        [string]$RpcHost,
        [int]$RpcPort,
        [int]$Port,
        [int]$TimeoutSeconds
    )

    if (-not (Test-Path -LiteralPath $Repo)) {
        throw "Missing oculairmedia Houdini MCP repository: $Repo"
    }

    $uv = Get-Command 'uv' -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $uv) {
        throw 'Missing uv executable. Install uv or add it to PATH before running Houdini MCP preflight.'
    }

    $listener = Get-ListenerInfo -Port $Port
    if ($listener) {
        throw "Port $Port is already occupied by $($listener.ProcessName) (PID $($listener.PID)), but /health is not healthy."
    }

    $previousEnv = @{
        HOUDINI_HOST  = $env:HOUDINI_HOST
        HOUDINI_PORT  = $env:HOUDINI_PORT
        MCP_PORT      = $env:MCP_PORT
        MCP_TRANSPORT = $env:MCP_TRANSPORT
        LOG_LEVEL     = $env:LOG_LEVEL
    }

    try {
        $env:HOUDINI_HOST = $RpcHost
        $env:HOUDINI_PORT = [string]$RpcPort
        $env:MCP_PORT = [string]$Port
        $env:MCP_TRANSPORT = 'http'
        $env:LOG_LEVEL = 'INFO'

        $process = Start-Process `
            -FilePath $uv.Source `
            -ArgumentList @('run', 'python', '-m', 'houdini_mcp') `
            -WorkingDirectory $Repo `
            -WindowStyle Hidden `
            -PassThru

        Write-Step 'STARTED' "Launched Houdini MCP Server via uv (PID $($process.Id))"
    }
    finally {
        foreach ($key in $previousEnv.Keys) {
            if ($null -eq $previousEnv[$key]) {
                Remove-Item -Path "Env:\$key" -ErrorAction SilentlyContinue
            }
            else {
                Set-Item -Path "Env:\$key" -Value $previousEnv[$key]
            }
        }
    }

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        Start-Sleep -Seconds 2
        $health = Test-McpHealth -Port $Port
        if ($health.Healthy) {
            return $health
        }
    } while ((Get-Date) -lt $deadline)

    throw "Houdini MCP Server did not become healthy at http://127.0.0.1:$Port/health within $TimeoutSeconds seconds."
}

Install-HoudiniRpcStartupHook -Path $HoudiniStartupScript -Port $HoudiniPort

$houdiniProcess = Get-Process -Name 'houdini' -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $houdiniProcess) {
    throw "Houdini is not running. The RPC startup hook is installed; start Houdini and rerun this preflight."
}

$rpc = Test-HoudiniRpc -PythonPath $HythonPath -RpcHost $HoudiniHost -Port $HoudiniPort
if (-not $rpc.Connected) {
    throw "Houdini RPC is not available at $HoudiniHost`:$HoudiniPort. The startup hook is installed; restart Houdini once, then rerun this preflight. Detail: $($rpc.Message)"
}

$rpcListener = Get-ListenerInfo -Port $HoudiniPort
Write-Step 'OK' "Houdini RPC connected: $($rpc.Version), hip=$($rpc.HipPath), listener=$($rpcListener.ProcessName) PID $($rpcListener.PID)"

$health = Test-McpHealth -Port $McpPort
if (-not $health.Healthy) {
    Write-Step 'INFO' "Houdini MCP health check is not ready at $($health.Uri); starting local server."
    $health = Start-HoudiniMcpServer -Repo $McpRepo -RpcHost $HoudiniHost -RpcPort $HoudiniPort -Port $McpPort -TimeoutSeconds $StartupTimeoutSeconds
}

$mcpListener = Get-ListenerInfo -Port $McpPort
Write-Step 'OK' "Houdini MCP Server healthy: $($health.Uri), listener=$($mcpListener.ProcessName) PID $($mcpListener.PID)"

[PSCustomObject]@{
    HoudiniProcessId = $houdiniProcess.Id
    RpcPort          = $HoudiniPort
    RpcVersion       = $rpc.Version
    HipPath          = $rpc.HipPath
    McpPort          = $McpPort
    McpHealth        = $health.Status
    McpService       = $health.Service
}
