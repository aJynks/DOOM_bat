# dmod

G'day, aJynks here...

This is a small batch file I use in conjunction with [DOOMRunner](https://github.com/Youda008/DoomRunner). DoomRunner is my favourite Doom launcher, and it has a neat feature where it stores savegames and screenshots in directories based on the name of the profile you're running.

I like to have a general "look-see" profile that lets me quickly play through a WAD. But for larger WADs that I plan to spend more time with, I prefer everything to be separated. That way, I can change hotkeys, source port settings, record/play demos, and keep it all isolated from other projects I'm playing.

This setup was mainly motivated by the sheer number of configuration options and INI clutter used by [GZDoom](https://zdoom.org/downloads), though I primarily use [DSDA-Doom](https://github.com/kraflab/dsda-doom).

## What exactly does this batch file do?

- Creates a directory inside your config folder, named after the WAD/profile you specify.
- For GZDoom, it copies your "default" config files (`.ini` and `.cfg`) into the new directory.
- It also creates three subdirectories: `Demos`, `Saves`, and `Screenshots` — useful for DoomRunner’s data redirection system.

## How to use this batch file

This batch file is designed to be added to your system environment path so you can run it from any location in the terminal.

**Usage:**  
`dmod "Wad Name"`

**Parameters:**  
- `pistol` – Enables pistol start in the GZDoom config.  
- `on` – Enables freelook, crouching, and jumping in GZDoom (these are disabled by default).

**Example:**  
`dmod "Wad Name" pistol`

If your profile name has spaces, enclose it in quotes. The script will create a config directory called `Wad Name` and set up the GZDoom config to enable pistol start.

In DoomRunner, create a profile with the *exact same* name as the one used in the command. Under the **Data Directories** tab, make sure to enable the options to use preset folders for saves, demos, and screenshots.

## How to set it up

1. Install GZDoom and DSDA-Doom. (Currently, support for other engines isn’t implemented but may be added in the future.)
2. Configure each engine as you prefer.
3. Copy the default `.ini` and `.cfg` files for GZDoom, and the `.cfg` file for DSDA-Doom, into your chosen config root directory. You may wish to set them to read-only to prevent accidental changes.

These will act as template setup files — allowing each new profile to inherit a working default setup.

4. Edit the batch file and update the following paths:

```bat
set configFilePath=path\to\your\ConfigData\
set gzCFG=yourDefaultGZdoom.cfg
set gzINI=yourDefaultGZdoom.ini
set dsdaCFG=yourDefaultDSDAdoom.cfg
