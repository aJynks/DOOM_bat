=============================================================================
RUN Doom

G’day — aJynks here...

This is a batch file I made to help me quickly test my own WADs for my hobby project in various engines. I originally intended it to work only with kexDoom, DSDA-Doom, and GZDoom. But while I was writing it I thought, bugger it, and made it support several other engines too.

This batch file calls a PowerShell script. I almost got it working entirely in batch, but it was just easier to handle in PowerShell. It should just work, but you may need to enable PowerShell script execution outside of PowerShell (see Execution Policies).

=============================================================================
What exactly does this batch file do?

It launches Doom and allows you to select a source port via command line.
It also automatically loads a WAD file if it is the only .wad file in the current directory.

=============================================================================
How to use this batch file

This batch file is designed to be placed somewhere in your system’s environment path, so you can run it from anywhere in the command line.

Usage:
  doom [SourcePort] [IWAD] [other arguments...]

Parameters:
- SourcePortName : e.g. cherry to launch Cherry Doom
- IWADName       : e.g. tnt or doom2 to specify which IWAD to use
- Additional arguments : any valid arguments accepted by the source port
                         (e.g. -file, -warp, -skill, -nomonsters, etc.)

Examples:
  doom
    Loads Doom with the default source port and IWAD.
    If there is exactly one WAD file in the current directory, it will be auto-loaded.

  doom tnt -warp 1 -skill 4
    Loads the IWAD TNT.WAD using the default source port, and warps to map 1 on skill level 4.

  doom helion -warp 1 -skill 4
    Uses Helion as the source port, default IWAD, and warps to map 1, skill level 4.

  doom crispy doom
    Launches Crispy Doom with doom.wad.
    If there is only one WAD in the directory, it will be auto-loaded.

Note:
  It will only auto-load a .wad file if it is the ONLY one in the directory
  where the script is executed.
  If more than one .wad file is present, you must manually specify it using
  -file filename.wad (no path required).

=============================================================================
How to set it up

1. Place both the .bat and .ps1 files in a directory that is included in your system’s PATH.
2. Open doom_runDoomWad.ps1 in a text editor.
3. Edit the $sourcePort_exes and $iwad_paths variables to match the locations of your engines and IWADs.
   The keys you assign (e.g., "dsda", "crispy", "gz") become the commands you type in the doom call.
4. Set your default source port by changing:
     $defaultPort = $sourcePort_exes["dsda"]
   to something like:
     $defaultPort = $sourcePort_exes["kex"]

=============================================================================
How to set Defaults

Edit the "Default values" section inside doom_runDoomWad.ps1.

To use KEX as your default source port:
  $defaultPort = $sourcePort_exes["kex"]

Just replace "kex" with the name of the source port you want as default.

=============================================================================

That’s it!

Have fun and SLAUGHTER DEMONS
-- aJynks
