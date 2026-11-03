@echo off
cd /d "%~dp0"
cl /nologo /std:c++17 /O2 /EHsc /LD core.cpp /Fe:core.dll
