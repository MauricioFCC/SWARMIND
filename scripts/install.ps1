<#
.SYNOPSIS
    Instalacion completa de entorno de desarrollo para SWARMIND (Windows).

.DESCRIPTION
    Configura el entorno de desarrollo de SWARMIND despues de clonar el
    repositorio. Ejecuta todos los pasos necesarios para dejar el sistema
    operativo y listo para trabajar.

    Pasos que ejecuta:
      1. Verifica Python >= 3.12
      2. Instala uv (gestor de paquetes) si no existe
      3. Instala dependencias del proyecto (uv sync --extra dev)
      4. Crea symlinks de .opencode\ -> ~\.config\opencode\ (cerebro)
         Si los symlinks fallan, usa copia como fallback
      5. Instala git hooks (core.hooksPath)
      6. Verifica que todo funcione (import harness)

.PARAMETER DryRun
    Si se especifica, solo simula los pasos sin hacer cambios reales.

.EXAMPLE
    .\scripts\install.ps1              # Instalacion completa
    .\scripts\install.ps1 -DryRun     # Solo simular

.NOTES
    Requisitos:
      - Windows 10+ (symlinks requieren Developer Mode o admin)
      - Git para Windows
      - PowerShell 5.1+ o PowerShell 7+

    Seguridad:
      - 0 secrets hardcodeados
      - No ejecuta nada destructivo
      - Idempotente: seguro de ejecutar multiples veces

    Codigo: INGLES | Mensajes: ESPANOL
#>

[CmdletBinding()]
param(
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# Colores
# ---------------------------------------------------------------------------
function Write-Step {
    param([string]$Num, [string]$Msg)
    Write-Host "`n[$Num/6] " -NoNewline -ForegroundColor White
    Write-Host $Msg -ForegroundColor White
}
function Write-Ok {
    param([string]$Msg)
    Write-Host "  ✔  " -NoNewline -ForegroundColor Green
    Write-Host $Msg -ForegroundColor Gray
}
function Write-Warn {
    param([string]$Msg)
    Write-Host "  ⚠  " -NoNewline -ForegroundColor Yellow
    Write-Host $Msg -ForegroundColor Gray
}
function Write-Fail {
    param([string]$Msg)
    Write-Host "  ✖  " -NoNewline -ForegroundColor Red
    Write-Host $Msg -ForegroundColor Red
}
function Write-Info {
    param([string]$Msg)
    Write-Host "  ℹ  " -NoNewline -ForegroundColor Cyan
    Write-Host $Msg -ForegroundColor Gray
}

function Stop-Install {
    param([string]$Message)
    Write-Host ""
    Write-Host "INSTALACION FALLIDA:" -ForegroundColor Red
    Write-Host "  $Message" -ForegroundColor Red
    Write-Host ""
    Write-Host "  Revisa los errores arriba." -ForegroundColor Gray
    exit 1
}

# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------
$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir    = Split-Path -Parent $ScriptDir
if ($env:OPENCODE_GLOBAL_DIR) {
    $OpenCodeGlobal = $env:OPENCODE_GLOBAL_DIR
}
else {
    $OpenCodeGlobal = Join-Path $env:USERPROFILE ".config\opencode"
}

# Directorios del cerebro que se enlazan al global
$BrainDirs = @("agents", "skills", "core")

# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "================================================================" -ForegroundColor White
Write-Host "  SWARMIND - Instalacion de entorno de desarrollo" -ForegroundColor White
Write-Host "================================================================" -ForegroundColor White
Write-Host "  Root:   $RootDir"
Write-Host "  Global: $OpenCodeGlobal"
Write-Host "  DryRun: $DryRun"
Write-Host ""

# ============================================================================
# PASO 1: Verificar Python >= 3.12
# ============================================================================
Write-Step 1 "Verificar Python >= 3.12"

$pyVersion = $null
$pyMajor = $null
$pyMinor = $null

$pyCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pyCmd) {
    $pyCmd = Get-Command python3 -ErrorAction SilentlyContinue
}

if ($pyCmd) {
    try {
        $pyVersion = & $pyCmd.Source -c 'import sys; print("{0}.{1}.{2}".format(sys.version_info.major, sys.version_info.minor, sys.version_info.micro))' 2>$null
        $pyMajor = & $pyCmd.Source -c 'import sys; print(sys.version_info.major)' 2>$null
        $pyMinor = & $pyCmd.Source -c 'import sys; print(sys.version_info.minor)' 2>$null
    }
    catch {
        # Python found but command failed
    }
}

if (-not $pyVersion) {
    Stop-Install "Python no encontrado. Instala Python >= 3.12: https://www.python.org/downloads/"
}

$pyMajorInt = [int]$pyMajor
$pyMinorInt = [int]$pyMinor

if ($pyMajorInt -lt 3 -or ($pyMajorInt -eq 3 -and $pyMinorInt -lt 12)) {
    $msg = 'Python {0} detectado. Se requiere >= 3.12 (3.10 EOL 2026-10-31, numpy 2.5.1 requiere >= 3.12). Descarga: https://www.python.org/downloads/' -f $pyVersion
    Stop-Install $msg
}

Write-Ok "Python $pyVersion"

# ============================================================================
# PASO 2: Verificar/instalar uv
# ============================================================================
Write-Step 2 "Verificar/instalar uv (gestor de paquetes)"

$uvCmd = Get-Command uv -ErrorAction SilentlyContinue
if ($uvCmd) {
    $uvVer = & uv --version 2>$null
    Write-Ok "uv ya instalado: $uvVer"
}
else {
    Write-Warn "uv no encontrado. Instalando via pip..."

    if ($DryRun) {
        Write-Info 'dry-run: pip install uv'
    }
    else {
        try {
            & $pyCmd.Source -m pip install uv --quiet 2>$null
        }
        catch {
            Stop-Install 'Error instalando uv via pip. Instala manualmente: https://docs.astral.sh/uv/getting-started/installation/'
        }

        # Verificar que uv quedo disponible
        $uvCmd = Get-Command uv -ErrorAction SilentlyContinue
        if (-not $uvCmd) {
            # Intentar buscar en rutas comunes de instalacion
            $userScripts = Split-Path -Parent $pyCmd.Source
            $env:PATH = $userScripts + ';' + $env:PATH
            $uvCmd = Get-Command uv -ErrorAction SilentlyContinue
        }

        if (-not $uvCmd) {
            Stop-Install 'uv instalado pero no encontrado en PATH. Agrega el directorio de scripts de Python a tu PATH.'
        }

        $uvVer = & uv --version 2>$null
        Write-Ok "uv instalado: $uvVer"
    }
}

# ============================================================================
# PASO 3: Instalar dependencias
# ============================================================================
Write-Step 3 "Instalar dependencias (uv sync --extra dev)"

if ($DryRun) {
    Write-Info "dry-run: uv sync --extra dev --directory $RootDir"
}
else {
    Push-Location $RootDir
    try {
        & uv sync --extra dev
        if ($LASTEXITCODE -ne 0) { throw "uv sync fallo con codigo $LASTEXITCODE" }
    }
    catch {
        Pop-Location
        Stop-Install 'Error instalando dependencias. Revisa que uv y Python funcionen correctamente.'
    }
    Pop-Location
}

Write-Ok "Dependencias instaladas"

# ============================================================================
# PASO 4: Crear symlinks a opencode global
# ============================================================================
Write-Step 4 'Crear symlinks .opencode -> ~\.config\opencode'

foreach ($dir in $BrainDirs) {
    $Src = Join-Path $RootDir (Join-Path '.opencode' $dir)
    $Dst = Join-Path $OpenCodeGlobal $dir

    if (-not (Test-Path $Src)) {
        Write-Warn "Fuente no existe: $Src - saltando"
        continue
    }

    # Verificar si el symlink ya apunta al destino correcto (idempotente)
    if (Test-Path $Dst -PathType SymbolicLink) {
        $currentTarget = (Get-Item $Dst).Target
        if ($currentTarget -eq $Src) {
            Write-Ok "Symlink $dir ya configurado"
            continue
        }
        Write-Warn "Symlink $dir apunta a $currentTarget - reemplazando"
        if (-not $DryRun) {
            Remove-Item $Dst -Force
        }
    }

    # Si es un directorio real (copia previa), respaldar
    if ((Test-Path $Dst -PathType Container) -and -not (Test-Path $Dst -PathType SymbolicLink)) {
        $ts = [int][double]::Parse((Get-Date -UFormat %s))
        $backup = '{0}.bak.{1}' -f $Dst, $ts
        Write-Warn "Directorio real existe en $Dst - respaldando a $backup"
        if (-not $DryRun) {
            Rename-Item $Dst $backup
        }
    }

    # Crear directorio padre si no existe
    $parentDir = Split-Path -Parent $Dst
    if (-not (Test-Path $parentDir)) {
        if (-not $DryRun) {
            New-Item -ItemType Directory -Path $parentDir -Force | Out-Null
        }
    }

    # Intentar crear symlink (requiere Developer Mode o admin)
    $symlinkCreated = $false
    if (-not $DryRun) {
        try {
            New-Item -ItemType SymbolicLink -Path $Dst -Target $Src -Force -ErrorAction Stop | Out-Null
            $symlinkCreated = $true
        }
        catch {
            $errMsg = $_.Exception.Message
            Write-Warn "Symlink fallo (Developer Mode deshabilitado?): $errMsg"
        }
    }
    else {
        Write-Info "dry-run: New-Item -ItemType SymbolicLink -Path $Dst -Target $Src"
        $symlinkCreated = $true
    }

    if ($symlinkCreated) {
        Write-Ok "Enlazado: $dir -> $Src"
        continue
    }

    # Fallback: copiar directorio completo
    Write-Warn "Fallback: copiando $dir en lugar de symlink..."
    if ($DryRun) {
        Write-Info "dry-run: Copy-Item -Path $Src -Destination $Dst -Recurse"
    }
    else {
        try {
            Copy-Item -Path $Src -Destination $Dst -Recurse -Force -ErrorAction Stop
        }
        catch {
            $errMsg = $_.Exception.Message
            Stop-Install "No se pudo enlazar ni copiar ${dir}: $errMsg"
        }
    }
    Write-Ok "Copiado: $dir (fallback sin symlink)"
}

# ============================================================================
# PASO 5: Instalar git hooks
# ============================================================================
Write-Step 5 "Instalar git hooks"

$gitDir = Join-Path $RootDir '.git'
$hooksDir = Join-Path $RootDir '.githooks'

if (-not (Test-Path $gitDir)) {
    Write-Warn 'No es un repositorio git - saltando hooks'
}
elseif (-not (Test-Path $hooksDir)) {
    Write-Warn 'Directorio .githooks no existe - saltando hooks'
}
else {
    Push-Location $RootDir
    if ($DryRun) {
        Write-Info 'dry-run: git config core.hooksPath .githooks'
    }
    else {
        try {
            & git config core.hooksPath .githooks
            if ($LASTEXITCODE -ne 0) { throw "git config fallo" }
        }
        catch {
            Pop-Location
            Stop-Install "Error configurando git hooks. Verifica que .githooks/ exista."
        }
    }
    Pop-Location
    Write-Ok 'Git hooks configurados (core.hooksPath = .githooks)'
}

# ============================================================================
# PASO 6: Verificacion
# ============================================================================
Write-Host ""
Write-Step 6 "Verificacion final"

if ($DryRun) {
    Write-Info 'dry-run: Se saltaria verificacion de imports'
}
else {
    # Verificar import de harness
    $importOk = $false
    try {
        $result = & $pyCmd.Source -c 'import harness; print("OK")' 2>$null
        if ($LASTEXITCODE -eq 0) {
            $importOk = $true
        }
    }
    catch { }

    if ($importOk) {
        Write-Ok "Import harness exitoso"
    }
    else {
        # Intentar con sys.path explicito
        try {
            $pyCode = "import sys; sys.path.insert(0, r'" + $RootDir + "'); import harness; print('OK')"
            $result = & $pyCmd.Source -c $pyCode 2>$null
            if ($LASTEXITCODE -eq 0) {
                $importOk = $true
            }
        }
        catch { }

        if ($importOk) {
            Write-Ok "Import harness exitoso (con path explicito)"
        }
        else {
            Write-Warn 'import harness fallo. Los hooks de git y opencode funcionaran igualmente.'
            Write-Warn 'Si necesitas importar harness directamente, ejecuta: .venv\Scripts\Activate.ps1'
        }
    }

    # Verificar uv
    $uvCheck = Get-Command uv -ErrorAction SilentlyContinue
    if ($uvCheck) {
        $uvVer = & uv --version 2>$null
        Write-Ok "uv: $uvVer"
    }

    # Verificar symlinks
    foreach ($dir in $BrainDirs) {
        $Dst = Join-Path $OpenCodeGlobal $dir
        if (Test-Path $Dst -PathType SymbolicLink) {
            Write-Ok "Symlink $dir activo"
        }
        elseif (Test-Path $Dst -PathType Container) {
            Write-Ok "Directorio $dir presente (copia)"
        }
        else {
            Write-Warn "$dir no encontrado en $OpenCodeGlobal"
        }
    }
}

# ============================================================================
# Resumen
# ============================================================================
Write-Host ""
Write-Host "================================================================" -ForegroundColor White
Write-Host "  INSTALACION COMPLETADA" -ForegroundColor Green
Write-Host "================================================================" -ForegroundColor White
Write-Host ""
Write-Host "  Proximos pasos:"
Write-Host "    .venv\Scripts\Activate.ps1     # Activar entorno virtual"
Write-Host "    python -m harness --help       # Verificar harness"
Write-Host "    git status                     # Verificar hooks"
Write-Host ""
Write-Host "  Si re-instalaste, reinicia opencode para tomar los cambios."
Write-Host ""
