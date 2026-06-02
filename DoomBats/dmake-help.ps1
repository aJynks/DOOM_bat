# ==============================================================================
# dmake-help.ps1
# ==============================================================================

Write-Host ""
Write-Host "==============================================================================" -ForegroundColor DarkCyan
Write-Host "  DMAKE.BAT  -  doommake wrapper with optional doom.bat launch" -ForegroundColor White
Write-Host "==============================================================================" -ForegroundColor DarkCyan
Write-Host ""
Write-Host "  dmake forwards arguments to doommake. If " -NoNewline; Write-Host """--""" -ForegroundColor Yellow -NoNewline
Write-Host " is present, doom.bat is run"
Write-Host "  after doommake finishes, receiving any arguments after the " -NoNewline; Write-Host """--""" -ForegroundColor Yellow -NoNewline; Write-Host "."
Write-Host ""

Write-Host "USAGE" -ForegroundColor White
Write-Host "  dmake [doommake_args...]              - Run doommake" -ForegroundColor Gray
Write-Host "  dmake [doommake_args...] -- [args...] - Run doommake then doom.bat" -ForegroundColor Gray
Write-Host "  dmake <command> [options]             - Run a special dmake command" -ForegroundColor Gray
Write-Host ""

Write-Host "SPECIAL COMMANDS" -ForegroundColor White
Write-Host "  create    " -ForegroundColor Cyan -NoNewline; Write-Host "ProjectName [-i iwad] [-d folder]  - Create a new tweaked DoomMake project"
Write-Host "  explode   " -ForegroundColor Cyan -NoNewline; Write-Host "filename.wad [-i iwad] [-p]        - Explode a WAD into a DoomMake project"
Write-Host "  watch     " -ForegroundColor Cyan -NoNewline; Write-Host "                                   - Watch project, rebuild on file changes"
Write-Host "  texturex  " -ForegroundColor Cyan -NoNewline; Write-Host "[-make] [-fresh]                   - Export TEXTURE1 from built textures WAD"
Write-Host "  editpatch " -ForegroundColor Cyan -NoNewline; Write-Host "[-txt]                             - Open DECOHack patch editor GUI"
Write-Host "  update    " -ForegroundColor Cyan -NoNewline; Write-Host "                                   - Update DoomTools to the latest version"
Write-Host "  --targets " -ForegroundColor Cyan -NoNewline; Write-Host "                                   - Show all available doommake targets"
Write-Host "  --help    " -ForegroundColor Cyan -NoNewline; Write-Host "                                   - Show this help"
Write-Host ""

Write-Host "CREATE OPTIONS" -ForegroundColor White
Write-Host "  -i iwad    " -ForegroundColor Yellow -NoNewline; Write-Host "IWAD to use (default: doom2)"
Write-Host "             " -NoNewline; Write-Host "Options: " -ForegroundColor Gray -NoNewline; Write-Host "doom, doom2, tnt, plutonia, heretic, hexen, free1, free2" -ForegroundColor DarkGray
Write-Host "  -d folder  " -ForegroundColor Yellow -NoNewline; Write-Host "Directory to create the project in (optional)"
Write-Host ""

Write-Host "EXPLODE OPTIONS" -ForegroundColor White
Write-Host "  -i iwad    " -ForegroundColor Yellow -NoNewline; Write-Host "IWAD to use (default: doom2)"
Write-Host "             " -NoNewline; Write-Host "Options: " -ForegroundColor Gray -NoNewline; Write-Host "doom, doom2, tnt, plutonia, heretic, hexen, free1, free2" -ForegroundColor DarkGray
Write-Host "  -p         " -ForegroundColor Yellow -NoNewline; Write-Host "Use the input WAD's own PLAYPAL instead of the IWAD"
Write-Host "             " -NoNewline; Write-Host "(use for WADs with custom palettes)" -ForegroundColor DarkGray
Write-Host ""

Write-Host "TEXTUREX OPTIONS" -ForegroundColor White
Write-Host "  -make      " -ForegroundColor Yellow -NoNewline; Write-Host "After export, run doommake make"
Write-Host "  -fresh     " -ForegroundColor Yellow -NoNewline; Write-Host "After export, run doommake clean then doommake make"
Write-Host ""

Write-Host "EDITPATCH OPTIONS" -ForegroundColor White
Write-Host "  -txt       " -ForegroundColor Yellow -NoNewline; Write-Host "Open the text file viewer instead of the patch editor"
Write-Host ""

Write-Host "EXAMPLES" -ForegroundColor White
Write-Host "  dmake create MyWAD                   " -ForegroundColor Gray -NoNewline; Write-Host "- New doom2 project in current dir" -ForegroundColor DarkGray
Write-Host "  dmake create MyWAD -i doom -d MyDir  " -ForegroundColor Gray -NoNewline; Write-Host "- New doom project in MyDir folder" -ForegroundColor DarkGray
Write-Host "  dmake explode summoner.wad            " -ForegroundColor Gray -NoNewline; Write-Host "- Explode WAD using doom2 palette" -ForegroundColor DarkGray
Write-Host "  dmake explode summoner.wad -p         " -ForegroundColor Gray -NoNewline; Write-Host "- Explode WAD using its own palette" -ForegroundColor DarkGray
Write-Host "  dmake explode summoner.wad -i tnt -p  " -ForegroundColor Gray -NoNewline; Write-Host "- Explode with TNT IWAD, own palette" -ForegroundColor DarkGray
Write-Host "  dmake texturex -make                  " -ForegroundColor Gray -NoNewline; Write-Host "- Export TEXTURE1 then rebuild" -ForegroundColor DarkGray
Write-Host "  dmake -- -skill 4 -warp 1             " -ForegroundColor Gray -NoNewline; Write-Host "- Build then launch with doom.bat" -ForegroundColor DarkGray
Write-Host "  dmake make -- -skill 4 -warp 1        " -ForegroundColor Gray -NoNewline; Write-Host "- Run make then launch with doom.bat" -ForegroundColor DarkGray
Write-Host "  dmake update                          " -ForegroundColor Gray -NoNewline; Write-Host "- Update DoomTools" -ForegroundColor DarkGray
Write-Host ""