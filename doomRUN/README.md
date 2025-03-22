# RUN Doom

G'day aJynks here....

This is a bat file I made to help me quickly test my own wads for my hobby project in various engines. I had planned to only have it work on [kexDoom](https://www.gog.com/en/game/doom_doom_ii), [dsda-DOOM](https://github.com/kraflab/dsda-doom)] and [gzDOOM](https://zdoom.org/downloads)]. When I was writing it I thought, fuck it, and made it for a number of other engines as well.

This bat file calls a powershell script. I almost got it running in a bat file, but it was just easier to do in powershell. It should just work, but you may need to enable powerscipt to be called outside of powershell.


## What exactly dose this bat file do?

This will simply load doom and allow you to select a port via command line. It will also automatically load any a wad file if it is the single file in the directory.

## How to use this bat file

This bat file is designed to be used in your enviroment path so you can run it form anywhere.

**usage :** doom (runs doom useing the default sourceport)
**prams :** SourcePortName (writting "cherry" for example will load Cherry Doom
**prams :** iWADname (typing a iwad will load that iwad)
**prams :** it will also acept any additional commands that the source port uses. -file, -warp, -skill etc etc. Liturally all of them

**examples :** 
* doom (loads doom with the default source port and default iwad, if there is a single wad file in the dir you run it from this will also be loaded.
* doom tnt -warp 1 -skill 4 (loads the iwad TNT, in the default source port, with the war and skill prams)
* doom helion -warp 1 -skill 4 (load defailt iwad in helion source port, with warp and skill prams)
* doom crispy doom (loads crispy source port, loads doom.wad and if it finds a single wad file it will load it)

Remeber it will only auto load a wad file if it is THE ONLY wad file found at the locaiton you run the script. If there is more than 1 wad file, you will still need to manually type -file filename.wad (no path needed)

## How to set it up

* Place both the batfile and the powerscript in a direcotry that is added to your enviroment path so it can be run from any directory.
* open doom_runDoomWad.ps1 in a text editor. 
* Edit the paths so they point to the various source ports and iwads. The names of these are also the commands to run them!
* Do not forget to also set the default sourceport for the variable $defaultPort

That is it!!

Have fun and SLAUGHTER DEMONS
--aJynks