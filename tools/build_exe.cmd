@echo off
REM Buduje jednoplikowy rezur.exe (PyInstaller).
REM Wymagane raz:  python -m pip install pyinstaller
cd /d "%~dp0.."
echo [1/2] PyInstaller...
python -m PyInstaller --clean --noconfirm packaging\rezur.spec
if errorlevel 1 (
  echo [blad] budowanie nie powiodlo sie.
  exit /b 1
)
echo [2/2] quick-test...
dist\rezur.exe list-fixes >nul
if errorlevel 1 (
  echo [blad] dist\rezur.exe nie odpowiada.
  exit /b 1
)
echo.
echo Gotowe: dist\rezur.exe
echo Test:   dist\rezur.exe info --save "%%APPDATA%%\EldenRing\76561198000000000\ER0000.sl2"
