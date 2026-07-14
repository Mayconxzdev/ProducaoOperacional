param(
    [string]$Version = "",
    [string]$IsccPath = "",
    [string]$BuildPythonVersion = "3.12",
    [switch]$SkipTests,
    [switch]$RecreateBuildEnvironment
)

$ErrorActionPreference = "Stop"

# Windows PowerShell 5.1 pode usar uma pagina de codigo antiga por padrao.
try {
    chcp 65001 | Out-Null
    [Console]::InputEncoding = New-Object System.Text.UTF8Encoding($false)
    [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
    $global:OutputEncoding = New-Object System.Text.UTF8Encoding($false)
} catch {
    # A codificacao nao e critica para o build.
}

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $root

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $false)][string[]]$Arguments = @(),
        [Parameter(Mandatory = $true)][string]$FailureMessage
    )

    & $FilePath @Arguments
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        throw "$FailureMessage Codigo de saida: $exitCode."
    }
}

function Test-PythonExecutable {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $false)][string[]]$PrefixArguments = @()
    )

    if ([string]::IsNullOrWhiteSpace($FilePath) -or -not (Test-Path -LiteralPath $FilePath)) {
        return $false
    }

    try {
        & $FilePath @PrefixArguments -c "import sys,struct; raise SystemExit(0 if sys.version_info >= (3,12) and struct.calcsize('P')*8 == 64 else 1)" 2>$null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

function Resolve-UvCommand {
    foreach ($name in @("uv.exe", "uv")) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($command -and -not [string]::IsNullOrWhiteSpace([string]$command.Source)) {
            return [string]$command.Source
        }
    }

    $knownUvPaths = @(
        (Join-Path $env:USERPROFILE ".local\bin\uv.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\uv\uv.exe"),
        (Join-Path $env:APPDATA "uv\bin\uv.exe")
    )
    foreach ($path in $knownUvPaths) {
        if ($path -and (Test-Path -LiteralPath $path)) {
            return $path
        }
    }
    return ""
}

function Resolve-StandalonePython {
    param([string]$RequestedVersion)

    # Nao usar o alias py.exe da pasta WindowsApps. Em algumas instalacoes
    # gerenciadas pelo uv ele e encaminhado incorretamente para python.exe e
    # o caminho do proprio py.exe passa a ser tratado como um script Python.
    $launcherCandidates = @(
        (Join-Path $env:WINDIR "py.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Launcher\py.exe"),
        (Join-Path $env:ProgramFiles "Python Launcher\py.exe")
    ) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }

    foreach ($launcher in $launcherCandidates) {
        $selector = "-$RequestedVersion"
        if (Test-PythonExecutable -FilePath $launcher -PrefixArguments @($selector)) {
            return @{
                FilePath = $launcher
                PrefixArguments = @($selector)
                Description = "Python Launcher real $selector"
            }
        }
    }

    $directCandidates = New-Object System.Collections.Generic.List[string]
    $knownPaths = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python313\python.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python314\python.exe"),
        (Join-Path $env:LOCALAPPDATA "Python\pythoncore-3.12-64\python.exe"),
        (Join-Path $env:LOCALAPPDATA "Python\pythoncore-3.13-64\python.exe"),
        (Join-Path $env:LOCALAPPDATA "Python\pythoncore-3.14-64\python.exe"),
        "C:\Python312\python.exe",
        "C:\Python313\python.exe",
        "C:\Python314\python.exe"
    )
    foreach ($path in $knownPaths) {
        if ($path -and (Test-Path -LiteralPath $path)) {
            $directCandidates.Add($path)
        }
    }

    foreach ($name in @("python.exe", "python", "python3.exe", "python3")) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($command -and $command.Source -and $command.Source -notlike "*\Microsoft\WindowsApps\*") {
            $directCandidates.Add([string]$command.Source)
        }
    }

    foreach ($candidate in ($directCandidates | Select-Object -Unique)) {
        if (Test-PythonExecutable -FilePath $candidate) {
            return @{
                FilePath = $candidate
                PrefixArguments = @()
                Description = $candidate
            }
        }
    }

    throw "Python 3.12 ou superior, 64 bits, nao foi encontrado. Instale o uv ou o Python 64 bits."
}

if ([string]::IsNullOrWhiteSpace($Version)) {
    $Version = ([regex]::Match((Get-Content .\pyproject.toml -Raw), '(?m)^version\s*=\s*"(?<v>[^"]+)"').Groups['v'].Value)
}
if ([string]::IsNullOrWhiteSpace($Version)) {
    throw "Versao nao encontrada no pyproject.toml."
}

if ([string]::IsNullOrWhiteSpace($IsccPath)) {
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
        (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe")
    )
    $IsccPath = $candidates | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
}
if ([string]::IsNullOrWhiteSpace($IsccPath) -or -not (Test-Path -LiteralPath $IsccPath)) {
    throw "Inno Setup 6 nao encontrado. Instale o Inno Setup 6 e execute novamente."
}

$config = Get-Content .\config\settings.json -Raw -Encoding UTF8 | ConvertFrom-Json
if (-not [string]::IsNullOrWhiteSpace([string]$config.smtp.password)) {
    throw "settings.json contem senha SMTP. Remova o segredo antes de empacotar."
}

$uvPath = Resolve-UvCommand
$buildEnvironmentRoot = Join-Path $env:LOCALAPPDATA "ProducaoOperacional\BuildEnvironment"
$venvDir = Join-Path $buildEnvironmentRoot ("Python-" + $BuildPythonVersion)
$venvPython = Join-Path $venvDir "Scripts\python.exe"

if ($RecreateBuildEnvironment -and (Test-Path -LiteralPath $venvDir)) {
    Write-Host "Recriando ambiente isolado de build..."
    Remove-Item -LiteralPath $venvDir -Recurse -Force
}

# Um ambiente incompleto ou criado por outra versao deve ser descartado.
if ((Test-Path -LiteralPath $venvDir) -and -not (Test-PythonExecutable -FilePath $venvPython)) {
    Write-Host "O ambiente de build existente e invalido. Recriando..."
    Remove-Item -LiteralPath $venvDir -Recurse -Force
}

if (-not (Test-Path -LiteralPath $venvPython)) {
    New-Item -ItemType Directory -Path $buildEnvironmentRoot -Force | Out-Null

    if (-not [string]::IsNullOrWhiteSpace($uvPath)) {
        Write-Host "uv encontrado: $uvPath"
        Write-Host "Criando ambiente Python $BuildPythonVersion isolado em: $venvDir"
        Write-Host "O uv podera baixar automaticamente o Python solicitado na primeira execucao."

        & $uvPath "venv" $venvDir "--python" $BuildPythonVersion
        $uvVenvExitCode = $LASTEXITCODE

        if ($uvVenvExitCode -ne 0 -or -not (Test-Path -LiteralPath $venvPython)) {
            if (Test-Path -LiteralPath $venvDir) {
                Remove-Item -LiteralPath $venvDir -Recurse -Force
            }
            Write-Host "A primeira criacao falhou. Instalando o Python gerenciado pelo uv e tentando novamente..."
            Invoke-Checked -FilePath $uvPath -Arguments @("python", "install", $BuildPythonVersion) -FailureMessage "Falha ao instalar o Python $BuildPythonVersion com uv."
            Invoke-Checked -FilePath $uvPath -Arguments @("venv", $venvDir, "--python", $BuildPythonVersion) -FailureMessage "Falha ao criar o ambiente virtual com uv."
        }
    } else {
        $basePython = Resolve-StandalonePython -RequestedVersion $BuildPythonVersion
        $basePythonPath = [string]$basePython["FilePath"]
        $basePythonPrefixArguments = [string[]]$basePython["PrefixArguments"]
        Write-Host "uv nao encontrado. Python base: $($basePython['Description'])"
        Write-Host "Criando ambiente isolado em: $venvDir"
        $venvArguments = @($basePythonPrefixArguments) + @("-m", "venv", $venvDir)
        Invoke-Checked -FilePath $basePythonPath -Arguments $venvArguments -FailureMessage "Falha ao criar o ambiente virtual com Python."
    }
}

if (-not (Test-PythonExecutable -FilePath $venvPython)) {
    throw "O ambiente isolado nao possui um Python 64 bits valido em: $venvPython"
}

$pythonInfo = & $venvPython -c "import sys,struct; print(str(sys.version_info.major)+'.'+str(sys.version_info.minor)+'.'+str(sys.version_info.micro)+'|'+str(struct.calcsize('P')*8))"
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace([string]$pythonInfo)) {
    throw "Nao foi possivel validar o Python do ambiente isolado."
}
Write-Host "Python isolado validado: $pythonInfo"

Write-Host "Instalando/atualizando dependencias somente no ambiente isolado..."
if (-not [string]::IsNullOrWhiteSpace($uvPath)) {
    Invoke-Checked -FilePath $uvPath -Arguments @(
        "pip", "install",
        "--python", $venvPython,
        "--upgrade",
        "-r", (Join-Path $root "requirements-dev.txt"),
        "pyinstaller"
    ) -FailureMessage "Falha ao instalar dependencias de build com uv."
} else {
    & $venvPython -m pip --version *> $null
    if ($LASTEXITCODE -ne 0) {
        Invoke-Checked -FilePath $venvPython -Arguments @("-m", "ensurepip", "--upgrade") -FailureMessage "Falha ao habilitar pip no ambiente isolado."
    }
    Invoke-Checked -FilePath $venvPython -Arguments @(
        "-m", "pip", "install",
        "--disable-pip-version-check",
        "--upgrade", "pip", "setuptools", "wheel"
    ) -FailureMessage "Falha ao preparar pip no ambiente isolado."
    Invoke-Checked -FilePath $venvPython -Arguments @(
        "-m", "pip", "install",
        "--disable-pip-version-check",
        "--upgrade",
        "-r", (Join-Path $root "requirements-dev.txt"),
        "pyinstaller"
    ) -FailureMessage "Falha ao instalar dependencias no ambiente isolado."
}

if (-not $SkipTests) {
    Write-Host "Executando testes..."
    $env:QT_QPA_PLATFORM = "offscreen"
    Invoke-Checked -FilePath $venvPython -Arguments @("-m", "pytest", "-q") -FailureMessage "Os testes falharam."
    Invoke-Checked -FilePath $venvPython -Arguments @("-m", "compileall", "-q", "src", "tests", "scripts") -FailureMessage "A verificacao compileall falhou."
}

$buildDir = Join-Path $root "build"
$distDir = Join-Path $root "dist"
$appDir = Join-Path $distDir "Producao_Operacional"
if (Test-Path -LiteralPath $buildDir) {
    Remove-Item -LiteralPath $buildDir -Recurse -Force
}
if (Test-Path -LiteralPath $appDir) {
    Remove-Item -LiteralPath $appDir -Recurse -Force
}
New-Item -ItemType Directory -Path $distDir -Force | Out-Null

Write-Host "Compilando o aplicativo com PyInstaller..."
Invoke-Checked -FilePath $venvPython -Arguments @(
    "-m", "PyInstaller",
    "--noconfirm",
    "--clean",
    "--windowed",
    "--name", "Producao_Operacional",
    "--icon", (Join-Path $root "assets\producao_operacional.ico"),
    "--paths", (Join-Path $root "src"),
    (Join-Path $root "run_app.py")
) -FailureMessage "PyInstaller falhou."

$outputBase = "Producao_Operacional_Setup_v$Version"
Write-Host "Gerando o instalador com Inno Setup..."
& $IsccPath "/DMyAppVersion=$Version" "/DMySourceDir=$appDir" "/DMyOutputDir=$distDir" "/DMyOutputBase=$outputBase" "/DMyAppIcon=$root\assets\producao_operacional.ico" "/DNASRootPrimary=$($config.nas_root)" (Join-Path $root "scripts\Producao_Operacional.iss")
if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup falhou. Codigo de saida: $LASTEXITCODE."
}

$setupPath = Join-Path $distDir ($outputBase + ".exe")
if (-not (Test-Path -LiteralPath $setupPath)) {
    throw "O Inno Setup terminou sem criar o arquivo esperado: $setupPath"
}

$zipPath = Join-Path $distDir ($outputBase + ".zip")
if (Test-Path -LiteralPath $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
}
Compress-Archive -Path @($setupPath, ".\README.md", ".\CHANGELOG.md") -DestinationPath $zipPath -CompressionLevel Optimal

Write-Host ""
Write-Host "Build concluido com sucesso."
Write-Host "Setup: $setupPath"
Write-Host "ZIP:   $zipPath"
