@echo off
title NSA Pneutec — Instalador do ERP
color 1F
cls

echo.
echo  ============================================================
echo   NSA PNEUTEC — ERP REFORMADORA DE PNEUS
echo   Instalador Automatico
echo  ============================================================
echo.

:: Verifica se Python esta instalado
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo  [!] Python nao encontrado. Baixando e instalando Python 3.12...
    echo.
    powershell -Command "Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.12.9/python-3.12.9-amd64.exe' -OutFile '%TEMP%\python_installer.exe'"
    echo  Instalando Python (aguarde)...
    %TEMP%\python_installer.exe /quiet InstallAllUsers=0 PrependPath=1 Include_pip=1
    del %TEMP%\python_installer.exe
    echo  Python instalado com sucesso!
    echo.
    :: Atualiza PATH para a sessao atual
    set "PATH=%LOCALAPPDATA%\Programs\Python\Python312;%LOCALAPPDATA%\Programs\Python\Python312\Scripts;%PATH%"
)

echo  [OK] Python encontrado.
echo.
echo  Instalando dependencias (pode demorar alguns minutos na primeira vez)...
echo.

cd /d "%~dp0"
python -m pip install --upgrade pip --quiet
python -m pip install streamlit pandas pdfplumber openpyxl --quiet

if %errorlevel% neq 0 (
    echo.
    echo  [ERRO] Falha ao instalar dependencias.
    echo  Verifique sua conexao com a internet e tente novamente.
    pause
    exit /b 1
)

echo.
echo  [OK] Todas as dependencias instaladas!
echo.

:: Configura inicio automatico com o Windows
echo  Configurando inicio automatico com o Windows...
powershell -Command ^
  "$dir = '%~dp0'; ^
   $vbs = 'Set objShell = CreateObject(\"WScript.Shell\")' + [char]10 + 'objShell.Run \"cmd /c cd /d ' + $dir + ' && python -m streamlit run app.py --server.port=3001 --server.headless=true --server.address=0.0.0.0 --browser.gatherUsageStats=false\", 0, False'; ^
   $vbs | Out-File -FilePath ($dir + 'iniciar_silencioso.vbs') -Encoding ASCII; ^
   $startup = [System.Environment]::GetFolderPath('Startup'); ^
   $ws = New-Object -ComObject WScript.Shell; ^
   $sc = $ws.CreateShortcut($startup + '\ERP NSA Pneutec.lnk'); ^
   $sc.TargetPath = $dir + 'iniciar_silencioso.vbs'; ^
   $sc.WorkingDirectory = $dir; ^
   $sc.Description = 'ERP NSA Pneutec - Inicia automaticamente'; ^
   $sc.Save()"

:: Cria atalho na area de trabalho (abre no navegador)
echo  Criando atalho na Area de Trabalho...
powershell -Command ^
  "$desktop = [System.Environment]::GetFolderPath('Desktop'); ^
   $ws2 = New-Object -ComObject WScript.Shell; ^
   $sc2 = $ws2.CreateShortcut($desktop + '\ERP NSA Pneutec.lnk'); ^
   $sc2.TargetPath = 'http://localhost:3001'; ^
   $sc2.Description = 'Abrir ERP NSA Pneutec no navegador'; ^
   $sc2.IconLocation = 'shell32.dll,14'; ^
   $sc2.Save()"

echo  [OK] Atalho criado na Area de Trabalho!
echo  [OK] Inicio automatico configurado!
echo.
echo  ============================================================
echo   INSTALACAO CONCLUIDA COM SUCESSO!
echo.
echo   O sistema iniciara automaticamente sempre que o
echo   computador for ligado.
echo.
echo   Use o atalho "ERP NSA Pneutec" na Area de Trabalho
echo   para abrir no navegador.
echo  ============================================================
echo.
pause
