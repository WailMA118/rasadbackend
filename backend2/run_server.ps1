# PowerShell script to run the FastAPI server
Set-Location "C:\Users\waila\OneDrive\Desktop\backend2"
& ".\.venv\Scripts\Activate.ps1"
python -m uvicorn main:app --reload --port=5000