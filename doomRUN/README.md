# DOOM Runner (PowerShell + Batch)

G’day — aJynks here.

This is a command-line DOOM launcher I wrote for my own modding and testing workflow. I got sick of typing long engine commands every time I wanted to test a WAD, so I made this thing to do the thinking for me.

It started as a simple batch file for a couple of source ports. Then I thought, *bugger it*, and made it smarter. Now it supports multiple ports, multiple IWADs, preset mod packs (“paks”), folder auto-detection, and DoomMake projects.

This repo contains two files:

- **doom_runDoomWad.ps1** — the actual brains of the operation  
- **doom.bat** — a tiny wrapper so you can just type `doom` anywhere  

Both of these files **must** be placed in a folder that is in your system PATH.

=============================================================================

## 1) What This Is

This is a **smart command-line launcher for DOOM**.

Instead of typing stuff like:

dsda-doom.exe -iwad D:\IWADS\doom2.wad -file mymap.wad -warp 2 -skill 4

You type:

doom dsda doom2 -warp 2 -skill 4

Or even just:

doom

And it figures it out.

It’s designed for people who:
- Use multiple source ports
- Test WADs constantly
- Work with DoomMake projects
- Want sane defaults
- Want speed
- Don’t want to retype nonsense all day

=============================================================================

## 2) How It Works

When you run `doom`, the script does the following:

### Argument Parsing

Everything you type is scanned and categorized as:

- **Source port keywords** (e.g. `dsda`, `woof`, `nyan`)
- **IWAD keywords** (e.g. `doom2`, `tnt`, `plutonia`)
- **Pak keywords** (preset WAD bundles)
- **Everything else** (passed straight to the engine)

You don’t have to care about this. Just type what makes sense.

---

### Mode Detection

There are two operating modes.

#### Normal Folder Mode

Used when the current directory is **not** a DoomMake project.

Folder contents determine behavior:

- 0 WADs → runs port + IWAD only
- 1 WAD → auto-loads it
- 2+ WADs → shows an ASCII picker

Load order:

1) Pak WADs (if any)  
2) Selected or auto-detected WAD  

---

#### DoomMake Project Mode

Activated when these files exist:

- doommake.properties  
- doommake.script  
- doommake.project.properties  

In this mode:

- The project name is read automatically
- doom-loader.conf is created if missing
- The script loads:
  - ./build/<project>.wad (required)
  - ./build/dehacked.wad (optional)
- Default warp and skill values come from the config
- CLI arguments override defaults

Special token:

menu

If this appears anywhere (DoomMake mode only), all warp/skill injection is disabled.

---

### Final Command

Eventually, the script builds and runs a real engine command that looks like:

<port.exe> -iwad <iwad.wad> -file <pak wads> <selected wad> <your options>

You never need to type that yourself.

=============================================================================

## 3) How To Install

### Step 1: Put the Files Somewhere Permanent

Example:

C:\Tools\DoomRunner\
  doom.bat  
  doom_runDoomWad.ps1  

---

### Step 2: Add This Folder to PATH (REQUIRED)

This allows you to type `doom` from any directory.

Windows 10 / 11:

1. Start → Search: Environment Variables  
2. Open "Edit the system environment variables"  
3. Click "Environment Variables"  
4. Under User variables, select "Path" → Edit  
5. Click New  
6. Add the folder path (e.g. C:\Tools\DoomRunner\)  
7. Click OK on all dialogs  
8. Open a new terminal  

Verify:

where doom

---

### Step 3: Configure the Script

Open **doom_runDoomWad.ps1** and edit the blocks at the top.

#### Source Ports

Format:

"keyword" = "full path to exe"

Example:

"dsda" = "D:\Ports\dsda-doom.exe"

---

#### IWADs

Format:

"keyword" = "full path to wad"

Example:

"doom2" = "D:\IWADS\doom2.wad"

---

#### Pak Presets

Pak presets expand into multiple WADs that are always loaded first.

Format:

"pakname" = @( "path1", "path2", ... )

Example:

"pak1" = @(
  "D:\Mods\hud.wad",
  "D:\Mods\statusbar.wad"
)

---

#### Defaults

You can set default source port and IWAD near the top of the script. These are used when you just type:

doom

=============================================================================

## 4) Commands and What They Do

### Basic Syntax

doom [PORT] [IWAD] [PAK...] [OPTIONS...]

---

### Source Port Selection

doom dsda  
doom woof  
doom nyan  

Selects which engine to use.

---

### IWAD Selection

doom doom2  
doom tnt  
doom plutonia  

Selects which base game to use.

---

### Pak Presets

doom pak1  
doom dsda doom2 pak1  

Loads predefined WAD bundles before everything else.

---

### Folder Auto-Detection

doom  

If there’s exactly one WAD in the folder, it loads it.  
If there’s more than one, it asks which one.  
If there are none, it just launches the IWAD.

---

### Passing Through Engine Arguments

Anything not recognized as a keyword is passed directly to the source port.

Examples:

doom dsda doom2 -warp 2 -skill 4  
doom woof doom2 -record demo.lmp  
doom -complevel 9  

---

### DoomMake Mode

doom  

Runs the project using doom-loader.conf.

doom menu  

Disables warp/skill injection.

---

### Help

doom --help  
doom -h  
doom /?  

=============================================================================

## Troubleshooting

If `doom` is not found:
- The folder is not in PATH
- Open a new terminal

If a port or IWAD fails:
- Check paths in doom_runDoomWad.ps1

If a pak fails:
- Ensure all WAD paths exist
- Pak arrays must not be empty

=============================================================================

## License

This project is released into the **public domain** under the **Unlicense**.

You can:
- Use it
- Copy it
- Modify it
- Break it
- Fix it
- Rewrite it
- Sell it
- Bundle it
- Strip my name off it
- Claim you wrote it (I won’t cry)

No permission required. No attribution required. No warranty provided.

Do whatever you want with it.

Have fun and SLAUGHTER DEMONS.

— aJynks
