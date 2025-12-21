@echo off
echo ========================================
echo Restaurant App Diagnostic Tool
echo ========================================
echo.

echo [1/5] Checking if backend is running...
curl -s http://localhost:5000/api/me >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] Backend is running on port 5000
) else (
    echo [FAIL] Backend is NOT running on port 5000
    echo        Fix: cd api and run: python app.py
)
echo.

echo [2/5] Checking if frontend dev server is running...
curl -s http://localhost:8080 >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] Frontend is running on port 8080
) else (
    echo [FAIL] Frontend is NOT running on port 8080
    echo        Fix: cd web and run: npm run dev
)
echo.

echo [3/5] Testing API connectivity from frontend...
curl -s http://localhost:8080/api/me >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] Frontend can reach backend API
) else (
    echo [FAIL] Frontend CANNOT reach backend API
    echo        This means Vite proxy is not working
    echo        Fix: Restart dev server with: npm run dev
)
echo.

echo [4/5] Checking database connection...
echo (Skipping - requires Python import)
echo.

echo [5/5] Summary
echo ========================================
echo.
echo If backend is NOT running:
echo   cd api
echo   python app.py
echo.
echo If frontend is NOT running:
echo   cd web
echo   npm run dev
echo.
echo If both are running but API unreachable:
echo   1. Stop dev server (Ctrl+C)
echo   2. Restart: npm run dev
echo.
echo After fixing, test these URLs:
echo   - http://localhost:8080/login (should work)
echo   - http://localhost:8080/dashboard (should work)
echo   - http://localhost:5000/api/me (should return JSON)
echo.
pause
