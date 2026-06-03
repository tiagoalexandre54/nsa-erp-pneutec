@echo off
title NSA Pneutec — ERP Reformadora
color 1F
cls

echo.
echo  ============================================================
echo   NSA PNEUTEC — ERP REFORMADORA DE PNEUS
echo   Iniciando sistema...
echo  ============================================================
echo.

cd /d "%~dp0"

:: Verifica Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo  [ERRO] Python nao encontrado.
    echo  Execute primeiro o arquivo INSTALAR.bat
    echo.
    pause
    exit /b 1
)

:: Verifica se streamlit esta instalado
python -c "import streamlit" >nul 2>&1
if %errorlevel% neq 0 (
    echo  [!] Dependencias nao instaladas. Instalando agora...
    python -m pip install streamlit pandas pdfplumber openpyxl --quiet
)

echo  Abrindo o navegador automaticamente em 3 segundos...
echo  (Se nao abrir, acesse: http://localhost:3001)
echo.
echo  Para encerrar o sistema, feche esta janela.
echo.

powershell -Command "Start-Sleep 3; Start-Process 'http://localhost:3001'" &

:: Inicia o Streamlit
python -m streamlit run app.py --server.port=3001 --server.headless=true --server.address=0.0.0.0 --browser.gatherUsageStats=false

echo.
echo  Sistema encerrado.
pause
