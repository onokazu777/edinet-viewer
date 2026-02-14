@echo off
chcp 65001 >nul
cd /d "%~dp0"
C:\Users\onok\AppData\Local\Python\bin\python.exe -m streamlit run app.py --server.port 8502
