@echo off
echo ========================================
echo   PDF-OCR-checker - Build Standalone EXE
echo ========================================
echo.
echo Requires: Python, PyInstaller, PyMuPDF, tkinterdnd2
echo.
echo Installing/updating build dependencies...
pip install pyinstaller PyMuPDF tkinterdnd2
echo.
echo Building standalone executable...
cd /d "%~dp0"
python -m PyInstaller --onefile --windowed --name "PDF OCR Checker v1" --collect-all tkinterdnd2 --distpath "..\standalone" --specpath "build_temp" --workpath "build_temp\work" pdf_ocr_checker.py
echo.
echo Cleaning up build files...
rmdir /s /q build_temp 2>nul
echo.
echo ----------------------------------------
echo   Build complete!
echo   The standalone exe is in: ..\standalone\PDF OCR Checker v1.exe
echo ----------------------------------------
pause
