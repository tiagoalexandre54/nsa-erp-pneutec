Set objShell = CreateObject("WScript.Shell")
objShell.Run "cmd /c cd /d C:\Users\jogador\erp-reformadora-mes && python -m streamlit run app.py --server.port=3001 --server.headless=true --server.address=0.0.0.0 --browser.gatherUsageStats=false", 0, False
