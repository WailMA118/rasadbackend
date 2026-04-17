@echo off
cd /d "C:\Users\waila\OneDrive\Desktop\backend2"
call .venv\Scripts\activate.bat
python -m uvicorn main:app --reload --port=5000
pause