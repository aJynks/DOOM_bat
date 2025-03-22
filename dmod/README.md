# dmod

G'day aJynks here....

This is a small batfile I use in conjunction with [DOOMRUNNER](https://github.com/Youda008/DoomRunner)]. Basically Doomrunner is my favriout doom launcher and it has a cool feature that will store savegames and screen shots in directories based on the name of the name of the profile you are running.

I like to have a kind of "looksee" profile that allows me to simply play a wad quickly, but for larger wads that I intend of spending a lot of time in I like to have everythign seperated. I can change htkeys, the settings in the source port, record and play demos and nothing I do touches my other wads I am playing.

This was mainly done due to the massive ammount of options and ini stuff used by [gzDOOM](https://zdoom.org/downloads)]. Even though I mainly use [dsda-DOOM](https://github.com/kraflab/dsda-doom)].

## What exactly dose this bat file do?

It creates a directory in your condif dir, based on the command you enter. It then copies your "default" configs into that dir for use with Doomrunner. In teh case of gzDoom it also copies in a CFG file and edits that file so the copied ini file is pointing to the new CFG file. 

## How to use this bat file

This bat file is designed to be used in your enviroment path so you can run it form anywhere.

**usage :** dmod "Wad Name"
**prams :** pistol will add pistol starts to GZDoom config
**prams :** on will enable mouse look, crouch and jump in gzDoom (these are all turned off by default)

**example :** dmod "Wad Name" pistol

use quotes if you have a space in your Profil Name. This will create a config dir for called "Wad Name" and edit the gz cfg file to make it psitol start.

In doomrunner simply create a profile with the exact same wad name. Make sure in the "data directories" tab you have ticked the options to use preset dirs.

## How to set it up

Install gzDoom, and dsda-Doom (at the momment I have not added support for other engines but that may come). Load them up and set them up as you wish. Then copy the ini and cfg file for gzDoom and the cfg file for dsda-Doom and place them in the root of your config dir. I like to set them to read only as well to make sure they stay put.

These will be your default setup files, alowing any new profile to basically be ready to go form launch.

Now edit the bat file.
* set configFilePath = "path/to/configDir/"
* set gzCFG=filenameOfDefault_gzDoom.cfg
* set gzINI=filenameOfDefault_gzDoom.ini
* set dsdaCFG=filenameOfDefault_dsda-Doom.cfg

Have fun and SLAUGHTER DEMONS
--aJynks