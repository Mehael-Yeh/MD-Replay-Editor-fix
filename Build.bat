@echo off
REM ============================================
REM Build MD-Replay-Editor-fix BepInEx Plugin
REM ============================================
SETLOCAL ENABLEDELAYEDEXPANSION

REM --- Configuration ---
SET PROJECT_NAME=MD-Replay-Editor-fix
SET TARGET_FRAMEWORK=v4.8

REM --- Detect MSBuild ---
WHERE msbuild >nul 2>nul
IF %ERRORLEVEL% NEQ 0 (
    REM Try Visual Studio install paths
    FOR %%P IN (
        "%ProgramFiles%\Microsoft Visual Studio\2022\Community\MSBuild\Current\Bin\MSBuild.exe"
        "%ProgramFiles%\Microsoft Visual Studio\2022\Professional\MSBuild\Current\Bin\MSBuild.exe"
        "%ProgramFiles%\Microsoft Visual Studio\2022\Enterprise\MSBuild\Current\Bin\MSBuild.exe"
        "%ProgramFiles(x86)%\Microsoft Visual Studio\2019\Community\MSBuild\Current\Bin\MSBuild.exe"
        "%ProgramFiles(x86)%\Microsoft Visual Studio\2019\Professional\MSBuild\Current\Bin\MSBuild.exe"
        "%ProgramFiles(x86)%\Microsoft Visual Studio\2019\Enterprise\MSBuild\Current\Bin\MSBuild.exe"
    ) DO (
        IF EXIST "%%~P" (
            SET MSBUILD=%%~P
            GOTO :FOUND_MSBUILD
        )
    )
    ECHO MSBuild not found! Install Visual Studio or .NET Framework SDK.
    ECHO Alternatively set MSBUILD environment variable to msbuild.exe path.
    PAUSE
    EXIT /B 1
) ELSE (
    SET MSBUILD=msbuild
)
:FOUND_MSBUILD

REM --- Locate BepInEx assemblies ---
IF "%BEPINEX_DIR%"=="" (
    IF EXIST ".\lib\BepInEx" (
        SET BEPINEX_DIR=.\lib\BepInEx
    ) ELSE (
        ECHO Looking for BepInEx in common locations...
        FOR %%D IN (
            "%ProgramFiles%\BepInEx"
            "%LOCALAPPDATA%\BepInEx"
            "%APPDATA%\BepInEx"
            ".\lib\BepInEx"
            "..\BepInEx"
        ) DO (
            IF EXIST "%%~D\BepInEx.dll" (
                SET BEPINEX_DIR=%%~D
                GOTO :FOUND_BEPINEX
            )
        )
        ECHO BepInEx assemblies not found!
        ECHO Set BEPINEX_DIR environment variable to the folder containing BepInEx.dll
        PAUSE
        EXIT /B 1
    )
)
:FOUND_BEPINEX
ECHO Using BepInEx from: %BEPINEX_DIR%

REM --- Create output directory ---
IF NOT EXIST "bin\Release" MKDIR "bin\Release"

REM --- Build ---
ECHO Building %PROJECT_NAME%...
"%MSBUILD%" "%PROJECT_NAME%.csproj" /p:Configuration=Release /p:BEPINEX_DIR="%BEPINEX_DIR%" /p:Platform=x64 /t:Rebuild /v:m

IF %ERRORLEVEL% NEQ 0 (
    ECHO Build FAILED!
    PAUSE
    EXIT /B 1
)

ECHO.
ECHO Build successful!
ECHO Output: bin\Release\%PROJECT_NAME%.dll
ECHO.
ECHO === Installation ===
ECHO 1. Copy bin\Release\%PROJECT_NAME%.dll to BepInEx\plugins\
ECHO 2. Copy YgoMasterLoader.dll to BepInEx\plugins\ (if using native hooks)
ECHO 3. Launch Master Duel via BepInEx launcher
ECHO.
PAUSE
