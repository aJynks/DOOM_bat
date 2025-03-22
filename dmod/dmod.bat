@echo off
setlocal enabledelayedexpansion

:: Path and config file variables (without using %name% yet)
set configFilePath=D:\Games\Doom\_ConfigData\
set gzCFG=gz-default.cfg
set gzINI=gz-Default.ini
set gzMouseLook=dmflags 393216
set gzPistol=dmflags3 128
set dsdaCFG=dsda-default.cfg

:: Check if at least one argument (name) is provided
if "%~1"=="" (
    echo ERROR: No name provided.
    echo Usage: dmod "Name" [on] [pistol]
	echo.
	pause
    exit /b 1
)

:: Extract the name (preserving spaces)
set "name=%~1"
shift

:: Default values for optional parameters
set mouseLook=false
set pistol=false

:: Loop through remaining arguments
:loop
if "%1"=="" goto done

if /I "%1"=="on" set mouseLook=true
if /I "%1"=="pistol" set pistol=true

shift
goto loop

:done

:: Set configDir after extracting name
set configDir=%configFilePath%%name%

:: Create the configDir directory if it doesn't exist
if not exist "%configDir%" (
    echo Creating directory: %configDir%
    mkdir "%configDir%"
)
echo Setting up GZ-Doom Setting Files...
echo Checking if GZ-Doom config files exist...
:: Check if the config files exist before copying
    if not exist "%configDir%\gz-%name%.cfg" (
        echo Copying GZ config file gz-default.cfg to %configDir%\gz-%name%.cfg
        copy "%configFilePath%\%gzCFG%" "%configDir%\gz-%name%.cfg"
    ) else (
        echo GZ config file already exists. Skipping copy.
    )

    if not exist "%configDir%\gz-%name%.ini" (
        echo Copying GZ ini file gz-Default.ini to %configDir%\gz-%name%.ini
        copy "%configFilePath%\%gzINI%" "%configDir%\gz-%name%.ini"
    ) else (
        echo GZ ini file already exists. Skipping copy.
    )

    :: Remove read-only attribute from both files
    attrib -r "%configDir%\gz-%name%.cfg"
    attrib -r "%configDir%\gz-%name%.ini"

	:: Append the parameter to the file
	if "%mouseLook%"=="false" (
		echo MouseLook is Disabled.
		echo %gzMouseLook% >> "%configDir%\gz-%name%.cfg"
	)
	
	:: Append the parameter to the file
	if "%pistol%"=="true" (
		echo Pistol Start is Enabled
		echo %gzPistol% >> "%configDir%\gz-%name%.cfg"
	)
	
	:: Edit the CFG line in the INI file
	powershell -Command ^
		"$content = Get-Content -Path '%configDir%\gz-%name%.ini';" ^
		"$content[26] = 'Path=%configDir%\gz-%name%.cfg';" ^
		"$content | Set-Content -Path '%configDir%\gz-%name%.ini'"
	
echo Setting up DSDA-Doom Setting Files....
    echo Checking if DSDA config file exists...

    :: Check if the dsda config file exists before copying
    if not exist "%configDir%\dsda-%name%.cfg" (
        echo Copying DSDA config file dsda-default.cfg to %configDir%\dsda-%name%.cfg
        copy "%configFilePath%\%dsdaCFG%" "%configDir%\dsda-%name%.cfg"
    ) else (
        echo DSDA config file already exists. Skipping copy.
    )

    :: Remove read-only attribute from the copied file
    attrib -r "%configDir%\dsda-%name%.cfg"

endlocal
echo.
pause
