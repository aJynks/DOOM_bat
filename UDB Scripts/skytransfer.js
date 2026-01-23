/// <reference path="../../udbscript.d.ts" />

`#version 5`;
`#author aJynks`;
`#name Create Sky Transfer Control Sector`;
`#description Creates a single square control sector using special 271 or 272 for the selected sectors. A separate special linedef is created for each unique sector tag, plus one extra for any untagged sectors. All untagged sectors will be given a new shared tag. Each special linedef will be set to the matching tag.`;

`#scriptoptions
skytype
{
    description = "Sky Transfer Type";
    default = 0;
    type = 11; // Enum
    enumvalues {
        0 = "271 - Transfer Sky Textures to Tagged Sectors";
        1 = "272 - Transfer Sky Textures to Tagged Sectors (Flipped)";
    }
}
`;

/*
Category: Control Geometry
Licence: CC0 1.0 (Creative Commons Zero)

This script creates a single square control sector with special 271 or 272 linedefs.
The created control sector can then be used for Boom-style sky transfers on linked sectors.

How to use:
- Select one or more sectors, linedefs, or vertices. (Best practice: Sector Select mode)
- Choose sky transfer type (271 or 272) in the script options
- Hover your mouse over a grid point where there is space to draw the new sector
- Run the script

What it does:
- Untagged sectors will be given a new, unused shared tag
- A single square control sector will be created at the mouse cursor and snapped to grid
- Each special linedef will be 32 units long
- One special linedef will be created for sectors with the new tag
- One special linedef will be created for each unique tag already present
- Each special linedef will be tagged with the sector tag it is controlling

Notes:
- All specials are part of one square sector instead of separate triangular sectors
- The square size is calculated to fit all needed special linedefs around its perimeter
*/

// Get sky transfer type from options
const skySpecial = UDB.ScriptOptions.skytype == 0 ? 271 : 272;
const skyTypeName = UDB.ScriptOptions.skytype == 0 ? "271 - Transfer Sky" : "272 - Transfer Sky (Flipped)";

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

// Force selected sectors to use F_SKY1 on the ceiling
for(let sector of sectors) {
    sector.ceilingTexture = "F_SKY1";
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

// Step 3: Get first available unused tag and tag all untagged sectors
let newTag = 0;
let allTags = [];

if(untaggedSectors.length > 0) {
    newTag = UDB.Map.getNewTag();
    
    for(let sector of untaggedSectors) {
        sector.tag = newTag;
    }
    
    allTags.push(newTag);
}

// Add existing tags to our list
allTags = allTags.concat(existingTags);

let specialCount = allTags.length;

if(specialCount == 0) {
    UDB.die('No tags to process!');
}

// Step 4: Calculate best rectangle shape
// Each special needs 32 units, we want to minimize blank sides
// Try different rectangle dimensions to find the one with least waste

function findBestRectangle(specialCount) {
    let bestWidth = 0;
    let bestHeight = 0;
    let bestWaste = Infinity;
    
    // Try different widths (in multiples of 32)
    for(let w = 1; w <= specialCount; w++) {
        for(let h = 1; h <= specialCount; h++) {
            let perimeter = (w + h) * 2; // Number of 32-unit segments around perimeter
            
            if(perimeter >= specialCount) {
                let waste = perimeter - specialCount;
                
                // Prefer more square-like shapes when waste is equal
                let squareness = Math.abs(w - h);
                let score = waste * 100 + squareness;
                
                if(score < bestWaste) {
                    bestWaste = score;
                    bestWidth = w;
                    bestHeight = h;
                }
            }
        }
    }
    
    return { width: bestWidth * 32, height: bestHeight * 32 };
}

let rect = findBestRectangle(specialCount);
let width = rect.width;
let height = rect.height;

// Step 5: Draw the rectangle at mouse position
let mousePos = UDB.Map.mousePosition;
let startPos = UDB.Map.snappedToGrid(mousePos);

let p1 = startPos;
let p2 = new UDB.Vector2D(startPos.x + width, startPos.y);
let p3 = new UDB.Vector2D(startPos.x + width, startPos.y + height);
let p4 = new UDB.Vector2D(startPos.x, startPos.y + height);

UDB.Map.drawLines([p1, p2, p3, p4, p1]);

// Get the created sector and linedefs
let controlSector = UDB.Map.getMarkedSectors()[0];
let linedefs = UDB.Map.getMarkedLinedefs();

// Set control sector properties
if(controlSector) {
    controlSector.floorHeight = 0;
    controlSector.ceilingHeight = 128;
}

// Step 6: Split linedefs into 32-unit segments and apply specials
// We need to go around the perimeter and add vertices every 32 units

// Starting from p1, go clockwise and add vertices every 32 units
let newVertices = [p1]; // Start with first corner

// Side 1: p1 to p2 (going right)
for(let i = 32; i < width; i += 32) {
    newVertices.push(new UDB.Vector2D(startPos.x + i, startPos.y));
}
newVertices.push(p2);

// Side 2: p2 to p3 (going down)
for(let i = 32; i < height; i += 32) {
    newVertices.push(new UDB.Vector2D(startPos.x + width, startPos.y + i));
}
newVertices.push(p3);

// Side 3: p3 to p4 (going left)
for(let i = 32; i < width; i += 32) {
    newVertices.push(new UDB.Vector2D(startPos.x + width - i, startPos.y + height));
}
newVertices.push(p4);

// Side 4: p4 to p1 (going up)
for(let i = 32; i < height; i += 32) {
    newVertices.push(new UDB.Vector2D(startPos.x, startPos.y + height - i));
}

// Clear the old square
UDB.Map.clearMarkeLinedefs(false);
UDB.Map.clearMarkeSectors(false);

// Draw the new square with all vertices
UDB.Map.drawLines(newVertices.concat([p1]));

// Get the new linedefs
let newLinedefs = UDB.Map.getMarkedLinedefs();
let newControlSector = UDB.Map.getMarkedSectors()[0];

// Set control sector properties
if(newControlSector) {
    newControlSector.floorHeight = 0;
    newControlSector.ceilingHeight = 128;
}

// Step 7: Apply specials to the first N linedefs
let appliedCount = 0;
for(let i = 0; i < newLinedefs.length && appliedCount < specialCount; i++) {
    let ld = newLinedefs[i];
    
    // Check if this linedef is approximately 32 units (allow small floating point errors)
    if(Math.abs(ld.length - 32) < 0.1) {
        ld.action = skySpecial;
        ld.tag = allTags[appliedCount];
        appliedCount++;
    }
}

// Report results
let totalSegments = ((width / 32) + (height / 32)) * 2;
let blankSegments = totalSegments - specialCount;

let message = 'Created control sector at ' + startPos.x + ', ' + startPos.y + '\n';
message += 'Rectangle size: ' + width + 'x' + height + '\n';
message += 'Applied ' + appliedCount + ' special linedefs (' + skyTypeName + ')\n';
message += 'Blank segments: ' + blankSegments + '\n\n';

if(newTag > 0) {
    message += 'Special 1: Tag ' + newTag + ' (newly tagged ' + untaggedSectors.length + ' sectors)\n';
}

let startNum = newTag > 0 ? 2 : 1;
for(let i = 0; i < existingTags.length; i++) {
    message += 'Special ' + (startNum + i) + ': Tag ' + existingTags[i] + '\n';
}

UDB.showMessage(message);