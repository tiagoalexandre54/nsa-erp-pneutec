@echo off
title NSA Pneutec — Gerando pacote de distribuicao
color 1F
cls

echo.
echo  Gerando pacote ZIP para distribuicao...
echo.

cd /d "%~dp0"

:: Nome do arquivo ZIP com data
set "DATA=%date:~6,4%%date:~3,2%%date:~0,2%"
set "ARQUIVO=ERP_NSA_Pneutec_%DATA%.zip"
for /f "tokens=*" %%i in ('powershell -Command "[System.Environment]::GetFolderPath(\"Desktop\")"') do set "DESKTOP=%%i"
set "DESTINO=%DESKTOP%\%ARQUIVO%"

powershell -Command ^
  "Compress-Archive -Path '%~dp0*' -DestinationPath '%DESTINO%' -Force ^
   -CompressionLevel Optimal"

if exist "%DESTINO%" (
    echo  [OK] Pacote gerado com sucesso!
    echo.
    echo  Arquivo: %DESTINO%
    echo.
    echo  Para instalar em outro computador:
    echo  1. Copie o arquivo ZIP para o outro PC
    echo  2. Extraia em qualquer pasta (ex: C:\NSA_ERP\)
    echo  3. Execute o arquivo INSTALAR.bat
    echo  4. Depois use o atalho da Area de Trabalho ou RODAR.bat
) else (
    echo  [ERRO] Falha ao gerar o pacote.
)

echo.
pause
