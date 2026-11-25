@echo off
echo ===================================================
echo           Trade-AI Platform Launcher
echo ===================================================
echo.
echo [1/2] Starting Python FastAPI Backend on port 8002...
start "Trade-AI Backend" cmd /k "cd backend && .venv\Scripts\python.exe -m uvicorn main:app --port 8002"

echo [2/2] Starting Vite Frontend on port 5173...
start "Trade-AI Frontend" cmd /k "npm run dev"

echo.
echo Trade-AI is launching!
echo Backend:  http://127.0.0.1:8002
echo Frontend: http://localhost:5173
echo ===================================================
