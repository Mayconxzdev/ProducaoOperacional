@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================================
echo  Gerador do setup - Producao Operacional 2.3.7
echo ============================================================
echo.
echo O build usa primeiro o uv para criar um Python 3.12 isolado.
echo O alias py.exe do WindowsApps nao sera utilizado.
echo Nenhum pacote sera instalado no Python global.
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File ".\scripts\build_inno_setup.ps1"
set "BUILD_EXIT=%ERRORLEVEL%"

if not "%BUILD_EXIT%"=="0" (
    echo.
    echo O setup nao foi gerado. Leia a mensagem acima.
    echo Para apagar e recriar o ambiente isolado, execute:
    echo powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_inno_setup.ps1 -RecreateBuildEnvironment
    echo.
    pause
    exit /b %BUILD_EXIT%
)

echo.
echo Setup gerado com sucesso na pasta dist.
pause
exit /b 0
