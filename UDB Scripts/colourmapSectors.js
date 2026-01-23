/// <reference path="../../udbscript.d.ts" />

`#version 5`;
`#author aJynks`;
`#name Create ColourMap Control Sectors`;
`#description Creates diagonal triangle control sectors using special 242 for the selected sectors. A separate control sector is created for each unique sector tag, plus one extra for any untagged sectors. All untagged sectors will be given a new shared tag. Each triangle’s 242 linedef will be set to the matching tag, and the control sector will copy the floor and ceiling heights from the sector it controls.`
/*
`#category Control Geometry`;
`#copyright CC0 (Creative Commons Zero)`;

`#help
This script creates diagonal triangle control sectors with a special 242 linedef.
The created control sectors can then have colourmaps applied to the 242 linedef
and act as Boom-style colourmap swaps on linked sectors.

How to use:
- Select one or more sectors, linedefs, or vertices. (Best Practise : Sectors Select Mode)
- Hover your mouse over a grid point where there is space to draw the new sectors.
- Run the script.

What it does:
- Untagged sectors will be given a new, unused shared tag.
- All control sectors will be created at the mouse cursor and snapped to your grid.
- One control sector will be created for the sectors with the new tag.
- One control sector will be created for each unique tag already present.
- Each control sector will match the floor and ceiling height of the sector whose tag it controls.
- Each control sector will have a diagonal 242 linedef, tagged with the sector tag it is controlling.

Notes:
- The triangles are placed at the mouse cursor.
- Existing geometry is not modified.

Limitations / To do:
- If sectors with different floor or ceiling heights share the same tag, there is
  currently no way to handle this correctly. I may look into this in the future.`
*/

// Step 1: Get selected sectors intelligently
let sectors = [];

let selectedSectors = UDB.Map.getSelectedSectors();
if(selectedSectors.length > 0) {
    sectors = selectedSectors;
}
else {
    let selectedLinedefs = UDB.Map.getSelectedLinedefs();
    if(selectedLinedefs.length > 0) {
        for(let ld of selectedLinedefs) {
            if(ld.front && ld.front.sector && !sectors.includes(ld.front.sector)) {
                sectors.push(ld.front.sector);
            }
            if(ld.back && ld.back.sector && !sectors.includes(ld.back.sector)) {
                sectors.push(ld.back.sector);
            }
        }
    }
    else {
        let selectedVertices = UDB.Map.getSelectedVertices();
        if(selectedVertices.length > 0) {
            for(let vertex of selectedVertices) {
                let linedefs = vertex.getLinedefs();
                for(let ld of linedefs) {
                    if(ld.front && ld.front.sector && !sectors.includes(ld.front.sector)) {
                        sectors.push(ld.front.sector);
                    }
                    if(ld.back && ld.back.sector && !sectors.includes(ld.back.sector)) {
                        sectors.push(ld.back.sector);
                    }
                }
            }
        }
    }
}

if(sectors.length == 0) {
    UDB.die('No sectors found! Please select sectors, linedefs, or vertices.');
}

// Step 2: Collect unique existing tags and find untagged sectors
let existingTags = [];
let untaggedSectors = [];

for(let sector of sectors) {
    if(sector.tag == 0) {
        untaggedSectors.push(sector);
    }
    else {
        if(!existingTags.includes(sector.tag)) {
            existingTags.push(sector.tag);
        }
    }
}

let tagCount = existingTags.length;

// Step 3: Get first available unused tag and tag all untagged sectors
let newTag = 0;

if(untaggedSectors.length > 0) {
    newTag = UDB.Map.getNewTag();
    
    for(let sector of untaggedSectors) {
        sector.tag = newTag;
    }
}

// Step 3.5: Build tag → height lookup
let tagToHeights = new Map();

for(let s of sectors) {
    if(!tagToHeights.has(s.tag)) {
        tagToHeights.set(s.tag, {
            floor: s.floorHeight,
            ceil: s.ceilingHeight
        });
    }
}

// Step 4: Draw triangles
let mousePos = UDB.Map.mousePosition;
let startPos = UDB.Map.snappedToGrid(mousePos);

// Helper function to draw a triangle and return its hypotenuse + sector
function drawTriangle(basePos) {
    // Clear previous marks (important!)
    UDB.Map.clearMarkeLinedefs(false);
    UDB.Map.clearMarkeSectors(false);

    let p1 = basePos;
    let p2 = new UDB.Vector2D(basePos.x + 32, basePos.y);
    let p3 = new UDB.Vector2D(basePos.x, basePos.y + 32);
    
    UDB.Map.drawLines([
        p1,
        p2,
        p3,
        p1
    ]);
    
    // Get newly created sector
    let newSectors = UDB.Map.getMarkedSectors();
    let controlSector = (newSectors && newSectors.length > 0) ? newSectors[0] : null;
    
    // Find the hypotenuse (longest line)
    let linedefs = UDB.Map.getMarkedLinedefs();
    let hypotenuse = null;
    let maxLength = 0;
    
    for(let ld of linedefs) {
        if(ld.length > maxLength) {
            maxLength = ld.length;
            hypotenuse = ld;
        }
    }
    
    // Clear marks for next triangle
    UDB.Map.clearMarkeLinedefs(false);
    UDB.Map.clearMarkeSectors(false);
    
    return { hypotenuse, controlSector };
}

let triangleCount = 0;

// Draw first triangle for the new tag (if there were untagged sectors)
if(newTag > 0) {
    let pos = new UDB.Vector2D(startPos.x + (triangleCount * 64), startPos.y);
    let result = drawTriangle(pos);
    
    if(result.hypotenuse) {
        result.hypotenuse.action = 242;
        result.hypotenuse.tag = newTag;
    }

    if(result.controlSector) {
        let h = tagToHeights.get(newTag);
        if(h) {
            result.controlSector.floorHeight = h.floor;
            result.controlSector.ceilingHeight = h.ceil;
        }
    }
    
    triangleCount++;
}

// Draw triangles for each existing tag
for(let i = 0; i < existingTags.length; i++) {
    let tag = existingTags[i];
    let pos = new UDB.Vector2D(startPos.x + (triangleCount * 64), startPos.y);
    let result = drawTriangle(pos);
    
    if(result.hypotenuse) {
        result.hypotenuse.action = 242;
        result.hypotenuse.tag = tag;
    }

    if(result.controlSector) {
        let h = tagToHeights.get(tag);
        if(h) {
            result.controlSector.floorHeight = h.floor;
            result.controlSector.ceilingHeight = h.ceil;
        }
    }
    
    triangleCount++;
}

// Report results
let message = 'Drew ' + triangleCount + ' control triangles at ' + startPos.x + ', ' + startPos.y + '\n';
if(newTag > 0) {
    message += 'Triangle 1: Special 242, tag ' + newTag + ' (newly tagged ' + untaggedSectors.length + ' sectors)\n';
}
for(let i = 0; i < existingTags.length; i++) {
    let triangleNum = newTag > 0 ? i + 2 : i + 1;
    message += 'Triangle ' + triangleNum + ': Special 242, tag ' + existingTags[i] + '\n';
}
message += '\nFound ' + tagCount + ' unique existing tags total';

UDB.showMessage(message);
