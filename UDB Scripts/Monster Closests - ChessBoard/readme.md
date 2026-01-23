# Monster Closet Scripts for Ultimate Doom Builder

A pair of UDBScript tools for creating efficient, teleporter-based monster closets in MBF21 format Doom maps.

# Credits

Chess-Closest idea taken from DragonFly's Monster Closet Tutorial.
https://www.youtube.com/watch?v=mZTfm0sewaY (9:51 - Monster Spawning Closets)

DragonFly Credits : an_Mutt for teaching him the method.


## Overview

These scripts automate the creation of "monster closets" - hidden sectors that store monsters ready to teleport into your map. The classic checkerboard pattern allows monsters to activate when the player makes noise, then teleport in via linedef action 97.

## Scripts

### 1. Monster Closet Creator (`MonsterCloset_Chess.js`)

Creates an optimized checkerboard-style monster closet at your cursor position.

#### Features
- **Automatic grid optimization** - Calculates the most efficient square-like arrangement for your monster count
- **Smart dimension handling** - Rounds to 16-unit increments, uses square sectors based on largest dimension
- **Checkerboard pattern** - Alternates monster sectors (CEIL3_3) with raised-floor space sectors (CEIL4_1)
- **Random monster angles** - Each monster faces a random cardinal direction (0°, 90°, 180°, 270°)
- **Auto-sector joining** - Automatically joins all monster sectors together and all space sectors together
- **Teleport line setup** - Configures all boundary lines with action 97 (WR Teleport)
- **Auto-tag assignment** - Can automatically find and assign the next unused tag number
- **Landscape orientation** - Always creates wider-than-tall layouts for efficient space usage

#### Script Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| Monster EdNum | Thing Type | 3005 | The monster type to place (uses thing picker) |
| Thing Width | Integer | 62 | Width of the monster |
| Thing Height | Integer | 56 | Height of the monster |
| Number of Monsters | Integer | 8 | How many monsters to place in the closet |
| Monster Sector Floor Height | Integer | 0 | Floor height for monster sectors |
| Teleport Tag | Integer | 0 | Tag for teleport destination (0 = auto-assign next unused) |

#### Script Default Properties
- Floor: User-specified height (default 0)
- Ceiling: Floor height + Thing Height + 2
- Textures: CEIL3_3 (floor and ceiling)

- Floor: Monster floor height + 32 (raised to prevent premature monster movement)
- Ceiling: Same as monster sectors
- Textures: CEIL4_1 (floor and ceiling)

#### Usage

1. Bind Script to a hotkey Slot, with a bound Hotkey 
2. Position your cursor where you want the closet to spawn. Ensure there is room!
3. Configure the script options in the UDB Scripts docker
4. The closet is created from the top left courner, at your cursor position (snapped to grid)

**Note**: The closet is created but not yet functional. You still need to:
- Create a teleport destination sector with the matching tag
- Place a teleport destination thing (type 14) in that sector
- Connect the closet to a noise-triggering sector in your map
- Add a trigger to lower the space sector floors (activating the teleports)

---

### 2. Monster Closet - Create Bounds (`MonsterCloset_Chess-SoundBox.js`)

Creates a bounding sector around selected monster closets and sets external lines of each closet to be impassable. For use as a sound activation sector.

#### Features
- **Automatic bounds detection** - Calculates bounding box from selected sectors
- **Configurable buffer** - Adds buffer space around closets (default 64 units)
- **Multi-closet support** - Can wrap multiple separate closets in one operation
- **External line flagging** - Automatically sets outer lines to impassable + block monsters
- **Property inheritance** - Copies floor/ceiling heights from selected sectors

#### Script Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| Buffer size | Integer | 64 | Space between closet edge and bounding box |


#### Usage

1. Create one or more monster closets using the first script
2. Arrange your closest neatly together, with some space between each closet. 32 or 64 units is nice standard distance.
3. Select all the closet sectors via Sector Mode (Sector Mode must be the active selection set when running the script)
4. Run this script (I recommend via a hotkey, like before)
5. A bounding box is created with properly flagged external lines

---

## Closet is not active yet

### Set Teleport Destinations
1. You need to create sectors, that contain a single teleport destination for each unique teleport tag you wish to use.
2. These tags need to match the tag ids on the telport linedefs (these are set during creation by the script)

### Set Sound Box
3. You then need to join the bouncding box sector to your "alert sector" to propgare the sound there to wake them up.
4. Simply select your map sector then the bounding box sector and press "j" to join them. Now any sound made by the player in that joined sector will wake up the monsters.
5. Make sure you select you MAP sector, and then the bounding box sector, as the first selected secotr will be used to set flats, floor and cieling hight for the join3d sectors.

### Set Monster Release
6. Each "checker" that dose not contain monsters in each individual monster box is 32units high. 
7. Give them a tag
8. Use that tag to trigger a "align floor to lowest ajacent floor" type special. 
9. Any type will do, as long as the end result is that raised floor is now the same hight as the floor of the sector containing the monster.

## In game Functionality
1. Player makes a sound in the audioBox sector.
2. Monsters wake up.
3. The monster box floors are lowered
4. The monsters are released
5. The monsters teleport.

