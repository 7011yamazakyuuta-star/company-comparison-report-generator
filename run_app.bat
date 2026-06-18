@echo off
setlocal
cd /d "%~dp0"
set "PYTHON310=C:\Users\7011y\AppData\Local\Programs\Python\Python310\python.exe"
if exist "%PYTHON310%" (
  "%PYTHON310%" -m streamlit run app.py --server.port 8501 --server.headless true
) else (
  py -3.10 -m streamlit run app.py --server.port 8501 --server.headless true
)
endlocal
