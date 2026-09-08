@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM ============================================================
REM _run_-_Doom mod weapon showcases.bat
REM ROBUST PLAYLIST RUNNER
REM ============================================================
REM - One yt-dlp call per video/tier
REM - Firefox cookies re-read for each check/download
REM - 5 format fallbacks
REM - Broken partials restart from zero
REM - Terminal unavailable/no-format errors are detected BEFORE
REM   wasting time on all 5 tiers
REM - Unavailable/missing videos are shown in a compact RED block
REM   and recorded with a reason in _failed.log
REM - Optional quality ceiling: -4k, -1440p, -1080p, -720p,
REM   -480p, -360p. No option = best available.
REM ============================================================

set "URL=https://www.youtube.com/watch?v=6Mjr9hY0hYA&list=PLXKryJGC0Om3DIh90swKqtuxkXY4FbRz9"
set "ARCHIVE=_vid-downloaded.log"
set "FAILLOG=_failed.log"

REM -- tuning ---------------------------------------------------
set "RETRY_SLEEP=15"
set "RETRIES=5"
set "DELAY_MIN=30"
set "DELAY_RANGE=61"
set "CHUNK=1M"

REM -- optional quality ceiling ---------------------------------
set "QUALITY=best"
set "MAXH="
call :parse_args %*
if errorlevel 1 goto :bail

REM -- ANSI colours (supported by normal modern Windows consoles)
for /F "delims=" %%E in ('echo prompt $E^| cmd') do set "ESC=%%E"
set "RED=!ESC![91m"
set "YELLOW=!ESC![93m"
set "GREEN=!ESC![92m"
set "RESET=!ESC![0m"

REM -- dependency checks ----------------------------------------
where yt-dlp.exe >nul 2>&1
if errorlevel 1 (
    echo !RED![ERROR] yt-dlp.exe not found on PATH.!RESET!
    goto :bail
)
where ffmpeg.exe >nul 2>&1
if errorlevel 1 (
    echo !RED![ERROR] ffmpeg.exe not found on PATH.!RESET!
    goto :bail
)
where deno.exe >nul 2>&1
if errorlevel 1 (
    echo !YELLOW![WARN] deno.exe not found on PATH.!RESET!
    echo        YouTube JS challenges may fail without it.
    echo        Install with: choco install deno
    echo.
)

echo Updating yt-dlp...
yt-dlp.exe -U
echo.

echo ========================================================
echo   DOOM MOD WEAPON SHOWCASES - ROBUST RUNNER
echo ========================================================
echo   Folder      : %CD%
echo   Archive     : %ARCHIVE%
echo   Problem log : %FAILLOG%
echo   Retries     : %RETRIES% per format tier
echo   Delay       : %DELAY_MIN%-90 s between videos
echo   Partials    : restart from zero
echo   Cookies     : Firefox, refreshed per video/tier
echo   Fallback    : 5 format tiers per video
if defined MAXH (
    echo   Quality     : up to !QUALITY! ^(falls down automatically^)
) else (
    echo   Quality     : best available
)
echo ========================================================
echo.
echo Make sure Firefox is logged into YouTube.
echo.

REM -- enumerate playlist ---------------------------------------
set "IDLIST=%TEMP%\tfx_ids_%RANDOM%_%RANDOM%.tmp"

echo Enumerating playlist ^(metadata only^)...
yt-dlp.exe ^
    --flat-playlist ^
    --print "%%(id)s" ^
    --ignore-errors ^
    --no-warnings ^
    --yes-playlist ^
    --playlist-items 1-9999 ^
    --cookies-from-browser firefox ^
    "%URL%" > "!IDLIST!" 2>nul

if not exist "!IDLIST!" (
    echo !RED![ERROR] Could not enumerate playlist.!RESET!
    goto :bail
)

set "TOTAL=0"
for /f "usebackq tokens=*" %%I in ("!IDLIST!") do set /a TOTAL+=1
echo Found !TOTAL! videos.
echo.

REM -- main loop ------------------------------------------------
set "IDX=0"
set "GOT=0"
set "SKIPPED=0"
set "FAILED=0"
set "UNAVAILABLE=0"

if exist "!FAILLOG!" del "!FAILLOG!" >nul 2>&1

for /f "usebackq tokens=*" %%I in ("!IDLIST!") do (
    set /a IDX+=1
    set "VID=%%I"
    set "PAD=00!IDX!"
    set "PAD=!PAD:~-3!"

    findstr /C:"youtube !VID!" "!ARCHIVE!" >nul 2>&1
    if not errorlevel 1 (
        set /a SKIPPED+=1
        echo [!PAD!/!TOTAL!] skip - already downloaded
    ) else (
        call :try_video
    )
)

del "!IDLIST!" >nul 2>&1
goto :wrap_up

REM ============================================================
REM try_video - first classify terminal availability failures,
REM then walk the format tiers only if the video is obtainable.
REM ============================================================
:try_video
echo.
echo --------------------------------------------------------
echo [!PAD!/!TOTAL!] https://www.youtube.com/watch?v=!VID!
echo --------------------------------------------------------

set "OK=0"
set "TERMINAL=0"
set "WHY="

call :availability_check
if "!TERMINAL!"=="1" (
    set /a UNAVAILABLE+=1
    call :report_unavailable
    goto :video_wait
)

if defined MAXH (
    call :attempt "bv*[height<=?!MAXH!]+ba/b[height<=?!MAXH!]"                 "1/5  best <= !QUALITY!"
    call :attempt "bv*[height<=?!MAXH!][vcodec^=vp9]+ba/b[height<=?!MAXH!]"   "2/5  VP9 <= !QUALITY!"
    call :attempt "bv*[height<=?!MAXH!][vcodec^=avc1]+ba/b[height<=?!MAXH!]"  "3/5  AVC <= !QUALITY!"
    call :attempt "bv*[height<=?!MAXH!][fps<=30]+ba/b[height<=?!MAXH!]"       "4/5  30fps <= !QUALITY!"
    call :attempt "b[height<=?!MAXH!]"                                       "5/5  single <= !QUALITY!"
) else (
    call :attempt "bv*+ba/bv*+b/b"                 "1/5  best available"
    call :attempt "bv*[vcodec^=vp9]+ba"            "2/5  force VP9"
    call :attempt "bv*[height<=1080][fps<=30]+ba"  "3/5  1080p30"
    call :attempt "bv*[height<=720]+ba"             "4/5  720p"
    call :attempt "b"                               "5/5  single stream"
)

if "!OK!"=="1" (
    set /a GOT+=1
    echo !GREEN!  ^>^> OK  ^(tier !WINTIER!^)!RESET!
) else (
    set /a FAILED+=1
    echo.
    echo !YELLOW!************************************************************!RESET!
    echo !YELLOW!*** DOWNLOAD FAILED - ALL 5 FORMAT TIERS EXHAUSTED ***!RESET!
    echo !YELLOW!*** https://www.youtube.com/watch?v=!VID!!RESET!
    echo !YELLOW!************************************************************!RESET!
    >>"!FAILLOG!" echo [FAILED] !VID! ^| all 5 format tiers exhausted ^| https://www.youtube.com/watch?v=!VID!
)

:video_wait
set /a "WAIT=!DELAY_MIN! + (!RANDOM! %% !DELAY_RANGE!)"
echo   waiting !WAIT!s before next video...
timeout /t !WAIT! /nobreak >nul
goto :eof

REM ============================================================
REM availability_check
REM A lightweight extraction check. Only recognised terminal
REM availability/access/no-format conditions short-circuit tiers.
REM Other transient errors are allowed through to the tier logic.
REM ============================================================
:availability_check
set "PROBE=%TEMP%\tfx_probe_!RANDOM!_!RANDOM!.tmp"

yt-dlp.exe ^
    --simulate ^
    --no-playlist ^
    --cookies-from-browser firefox ^
    "https://www.youtube.com/watch?v=!VID!" > "!PROBE!" 2>&1

REM Probe output stays hidden; only our clean classified message is shown.
findstr /I /C:"This video is private" /C:"Private video" "!PROBE!" >nul 2>&1
if not errorlevel 1 (
    set "TERMINAL=1"
    set "WHY=PRIVATE VIDEO"
)

if "!TERMINAL!"=="0" (
    findstr /I /C:"This video has been removed" /C:"removed by the uploader" /C:"has been removed" "!PROBE!" >nul 2>&1
    if not errorlevel 1 (
        set "TERMINAL=1"
        set "WHY=REMOVED / DELETED VIDEO"
    )
)

if "!TERMINAL!"=="0" (
    findstr /I /C:"members-only" /C:"Join this channel" /C:"members only" "!PROBE!" >nul 2>&1
    if not errorlevel 1 (
        set "TERMINAL=1"
        set "WHY=MEMBERS-ONLY / ACCESS RESTRICTED"
    )
)

if "!TERMINAL!"=="0" (
    findstr /I /C:"not available in your country" /C:"blocked in your country" /C:"not available in your region" "!PROBE!" >nul 2>&1
    if not errorlevel 1 (
        set "TERMINAL=1"
        set "WHY=REGION BLOCKED"
    )
)

if "!TERMINAL!"=="0" (
    findstr /I /C:"Sign in to confirm your age" /C:"age-restricted" /C:"age restricted" "!PROBE!" >nul 2>&1
    if not errorlevel 1 (
        set "TERMINAL=1"
        set "WHY=AGE / LOGIN RESTRICTED"
    )
)

if "!TERMINAL!"=="0" (
    findstr /I /C:"Sign in to confirm you're not a bot" /C:"confirm you are not a bot" "!PROBE!" >nul 2>&1
    if not errorlevel 1 (
        set "TERMINAL=1"
        set "WHY=YOUTUBE BOT CHECK / COOKIE ACCESS ISSUE"
    )
)

if "!TERMINAL!"=="0" (
    findstr /I /C:"Video unavailable" "!PROBE!" >nul 2>&1
    if not errorlevel 1 (
        set "TERMINAL=1"
        set "WHY=VIDEO UNAVAILABLE - possibly deleted, private, blocked, or otherwise inaccessible"
    )
)

if "!TERMINAL!"=="0" (
    findstr /I /C:"No video formats found" /C:"No formats found" "!PROBE!" >nul 2>&1
    if not errorlevel 1 (
        set "TERMINAL=1"
        set "WHY=NO VIDEO FORMATS - availability/access problem; format retries cannot help"
    )
)

del "!PROBE!" >nul 2>&1
goto :eof

REM ============================================================
REM report_unavailable
REM ============================================================
:report_unavailable
echo.
echo !RED!============================================================!RESET!
echo !RED!  VIDEO UNAVAILABLE!RESET!
echo !RED!------------------------------------------------------------!RESET!
echo !RED!  ID     : !VID!!RESET!
echo !RED!  Reason : !WHY!!RESET!
echo !RED!  Action : skipped - format retries cannot fix availability!RESET!
echo !RED!  URL    : https://www.youtube.com/watch?v=!VID!!RESET!
echo !RED!============================================================!RESET!
echo.
>>"!FAILLOG!" echo [UNAVAILABLE] !VID! ^| !WHY! ^| https://www.youtube.com/watch?v=!VID!
goto :eof

REM ============================================================
REM attempt - one format tier
REM %~1 = format selector   %~2 = human label
REM ============================================================
:attempt
if "!OK!"=="1" goto :eof

echo.
echo   [tier %~2]

yt-dlp.exe ^
    --format "%~1" ^
    --merge-output-format mp4 ^
    --download-archive "!ARCHIVE!" ^
    --write-description ^
    --no-continue ^
    --retries !RETRIES! ^
    --fragment-retries !RETRIES! ^
    --extractor-retries 3 ^
    --retry-sleep !RETRY_SLEEP! ^
    --http-chunk-size !CHUNK! ^
    --ignore-errors ^
    --ignore-no-formats-error ^
    --progress ^
    --no-playlist ^
    --cookies-from-browser firefox ^
    -o "!PAD! - %%(title)s.%%(ext)s" ^
    "https://www.youtube.com/watch?v=!VID!"

findstr /C:"youtube !VID!" "!ARCHIVE!" >nul 2>&1
if not errorlevel 1 (
    set "OK=1"
    set "WINTIER=%~2"
    goto :eof
)

REM Tier failed - clear debris so the next tier starts clean.
del "!PAD! - *.f*.mp4"   >nul 2>&1
del "!PAD! - *.f*.webm"  >nul 2>&1
del "!PAD! - *.part"     >nul 2>&1
del "!PAD! - *.ytdl"     >nul 2>&1
goto :eof

REM ============================================================
REM parse_args - optional resolution ceiling
REM Examples: -4k  -1440p  -1080p  -720p  -480p  -360p
REM No option (or -best) keeps the original best-quality behaviour.
REM ============================================================
:parse_args
if "%~1"=="" exit /b 0

if /I "%~1"=="-best" (
    set "QUALITY=best"
    set "MAXH="
    shift
    goto :parse_args
)
if /I "%~1"=="-4k" (
    set "QUALITY=4K"
    set "MAXH=2160"
    shift
    goto :parse_args
)
if /I "%~1"=="-2160p" (
    set "QUALITY=2160p"
    set "MAXH=2160"
    shift
    goto :parse_args
)
if /I "%~1"=="-1440p" (
    set "QUALITY=1440p"
    set "MAXH=1440"
    shift
    goto :parse_args
)
if /I "%~1"=="-1080p" (
    set "QUALITY=1080p"
    set "MAXH=1080"
    shift
    goto :parse_args
)
if /I "%~1"=="-720p" (
    set "QUALITY=720p"
    set "MAXH=720"
    shift
    goto :parse_args
)
if /I "%~1"=="-480p" (
    set "QUALITY=480p"
    set "MAXH=480"
    shift
    goto :parse_args
)
if /I "%~1"=="-360p" (
    set "QUALITY=360p"
    set "MAXH=360"
    shift
    goto :parse_args
)

echo [ERROR] Unknown option: %~1
echo         Valid: -best -4k -2160p -1440p -1080p -720p -480p -360p
exit /b 1

REM ============================================================
:wrap_up

echo.
echo Renaming description files to .txt...
set "RENAMED=0"
for %%F in (*.mp4.description) do (
    set "STEM=%%~nF"
    set "STEM=!STEM:~0,-4!"
    if not exist "!STEM!.txt" (
        ren "%%F" "!STEM!.txt"
        set /a RENAMED+=1
    )
)
echo Renamed !RENAMED! description file^(s^).

echo.
echo ========================================================
echo   RUN SUMMARY
echo ========================================================
echo   Total in playlist : !TOTAL!
echo   Already had       : !SKIPPED!
echo   Downloaded now    : !GOT!
echo   Unavailable       : !UNAVAILABLE!
echo   Other failures    : !FAILED!
echo ========================================================

if !UNAVAILABLE! GTR 0 (
    echo.
    echo !RED!============================================================!RESET!
    echo !RED!  UNAVAILABLE / MISSING VIDEOS : !UNAVAILABLE!!RESET!
    echo !RED!  Details: !FAILLOG!!RESET!
    echo !RED!============================================================!RESET!
)

if !FAILED! GTR 0 (
    echo.
    echo !YELLOW!========================================================!RESET!
    echo !YELLOW!  OTHER DOWNLOAD FAILURES: !FAILED!!RESET!
    echo !YELLOW!========================================================!RESET!
    for /f "usebackq tokens=*" %%U in ("!FAILLOG!") do (
        echo %%U | findstr /L /B /C:"[FAILED]" >nul
        if not errorlevel 1 echo !YELLOW!  %%U!RESET!
    )
)

set /a PROBLEMS=!UNAVAILABLE!+!FAILED!
if !PROBLEMS! GTR 0 (
    echo.
    echo Full problem list written to: !FAILLOG!
)

:bail
echo.
pause
endlocal
