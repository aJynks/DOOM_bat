# ==============================================================================
# dmake-targethelp.ps1
# ==============================================================================
# Prints a formatted, colour-coded list of all doommake targets.
# Called by dmake.bat when --targets is passed.
# ==============================================================================

Write-Host ""
Write-Host ""
Write-Host "DMAKE-ONLY commands:" -ForegroundColor White
Write-Host "  dmake --targets            - Show this target list" -ForegroundColor Cyan
Write-Host "  dmake create ProjectName   - Create a new tweaked DoomMake project" -ForegroundColor Cyan
Write-Host "  dmake explode file.wad     - Explode a WAD into a DoomMake project" -ForegroundColor Cyan
Write-Host "  dmake watch                - Watch project and rebuild on file changes" -ForegroundColor Cyan
Write-Host "  dmake texturex             - Export TEXTURE1 from built textures WAD" -ForegroundColor Cyan
Write-Host "  dmake editpatch            - Open DECOHack patch editor GUI" -ForegroundColor Cyan
Write-Host "  dmake update               - Update DoomTools to the latest version" -ForegroundColor Cyan

Write-Host "DEFAULT targets:" -ForegroundColor White
Write-Host "  doommake all               - Build all project components (no release WAD)" -ForegroundColor Gray
Write-Host "  doommake assets            - Convert and merge assets WAD" -ForegroundColor Gray
Write-Host "  doommake clean             - Delete the build directory" -ForegroundColor Gray
Write-Host "  doommake convert           - Convert graphics, sprites, sounds and palettes" -ForegroundColor Gray
Write-Host "  doommake converttextures   - Convert texture flats and patches to Doom format" -ForegroundColor Gray
Write-Host "  doommake editor            - Rebuild the editor WAD" -ForegroundColor Gray
Write-Host "  doommake init              - Initialise the build directory" -ForegroundColor Gray
Write-Host "  doommake make              - Full build and create release WAD (no zip)" -ForegroundColor Gray
Write-Host "  doommake maps              - Merge the maps WAD" -ForegroundColor Gray
Write-Host "  doommake maptextures       - Export a WAD of only textures used in maps" -ForegroundColor Gray
Write-Host "  doommake patch             - Compile the DeHackEd patch and show budget" -ForegroundColor Gray
Write-Host "  doommake rebuildpalettes   - Rebuild primary palettes and colormaps" -ForegroundColor Gray
Write-Host "  doommake rebuildtextures   - Rebuild texture listings in src/textures" -ForegroundColor Gray
Write-Host "  doommake textures          - Convert and merge textures WAD" -ForegroundColor Gray
Write-Host ""
Write-Host "TWEAK targets:" -ForegroundColor White
Write-Host "  doommake deco              - Compile DECOHack and build a DEHACKED-only WAD" -ForegroundColor Yellow
Write-Host "  doommake fresh             - Clean build dir then do a full rebuild" -ForegroundColor Yellow
Write-Host "  doommake nopatch           - Full build and release WAD without DECOHack/DeHackEd" -ForegroundColor Yellow
Write-Host "  doommake playpal           - Convert palettes and colormaps into a palette-only WAD" -ForegroundColor Yellow
Write-Host "  doommake release           - Full build, create release WAD and zip for distribution" -ForegroundColor Yellow
Write-Host "  doommake texall            - Build texture WAD with ALL textures (for UDB)" -ForegroundColor Yellow
Write-Host "  doommake texrestricted     - Build texture WAD with only project textures (for UDB)" -ForegroundColor Yellow
Write-Host ""