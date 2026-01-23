`#version 4`;

`#name Monster Closet - Chess - SoundBox`;

`#description Creates a bounding sector around selected sectors with a 64-unit buffer. Sets external lines to impassable and block monsters.`;

`#scriptoptions

bufferSize
{
    description = "Buffer size around selected sectors";
    type = 0; // Integer
    default = 64;
}

`;

// Get selected sectors
let selectedSectors = UDB.Map.getSelectedSectors();

if (selectedSectors.length === 0) {
    UDB.showMessage("Please select the monster closet sectors first!");
    UDB.die();
}

let bufferSize = UDB.ScriptOptions.bufferSize;

// Find the bounding box of all selected sectors
let minX = Infinity;
let minY = Infinity;
let maxX = -Infinity;
let maxY = -Infinity;

// Go through all vertices of selected sectors to find bounds
for (let sector of selectedSectors) {
    let sidedefs = sector.getSidedefs();
    for (let sidedef of sidedefs) {
        let linedef = sidedef.line;
        
        // Check start vertex
        if (linedef.start.position.x < minX) minX = linedef.start.position.x;
        if (linedef.start.position.y < minY) minY = linedef.start.position.y;
        if (linedef.start.position.x > maxX) maxX = linedef.start.position.x;
        if (linedef.start.position.y > maxY) maxY = linedef.start.position.y;
        
        // Check end vertex
        if (linedef.end.position.x < minX) minX = linedef.end.position.x;
        if (linedef.end.position.y < minY) minY = linedef.end.position.y;
        if (linedef.end.position.x > maxX) maxX = linedef.end.position.x;
        if (linedef.end.position.y > maxY) maxY = linedef.end.position.y;
    }
}

// Add buffer to the bounding box
minX -= bufferSize;
minY -= bufferSize;
maxX += bufferSize;
maxY += bufferSize;

// Draw the bounding box
let boundingBox = [
    [minX, minY],
    [maxX, minY],
    [maxX, maxY],
    [minX, maxY],
    [minX, minY]
];

UDB.Map.drawLines(boundingBox);

// Get the newly created sector (it will be marked)
let newSectors = UDB.Map.getMarkedSectors();
if (newSectors.length > 0) {
    let boundingSector = newSectors[0];
    
    // Set some properties for the bounding sector
    boundingSector.floorTexture = "CEIL4_1";
    boundingSector.ceilingTexture = "CEIL4_1";
    
    // Copy floor/ceiling heights from one of the selected sectors
    if (selectedSectors.length > 0) {
        boundingSector.floorHeight = selectedSectors[0].floorHeight;
        boundingSector.ceilingHeight = selectedSectors[0].ceilingHeight;
    }
}

// Now find and mark all "external" linedefs (outer edges of the original closets)
// External linedefs are those that:
// 1. Belong to the selected sectors
// 2. Have only one side facing a selected sector (the other side is the new bounding sector or void)

let externalLinedefs = [];

for (let sector of selectedSectors) {
    let sidedefs = sector.getSidedefs();
    
    for (let sidedef of sidedefs) {
        let linedef = sidedef.line;
        
        // Check if this is an external line
        // A line is external if one side is our selected sector and the other side is NOT a selected sector
        let frontIsSelected = linedef.front && selectedSectors.includes(linedef.front.sector);
        let backIsSelected = linedef.back && selectedSectors.includes(linedef.back.sector);
        
        // External line: one side selected, other side not selected (or doesn't exist)
        if ((frontIsSelected && !backIsSelected) || (backIsSelected && !frontIsSelected)) {
            if (!externalLinedefs.includes(linedef)) {
                externalLinedefs.push(linedef);
            }
        }
    }
}

// Set flags on external linedefs
for (let linedef of externalLinedefs) {
    // Set impassable flag (flag 1)
    linedef.flags["1"] = true;
    
    // Set block monsters flag (flag 2)
    linedef.flags["2"] = true;
}

let width = Math.round(maxX - minX);
let height = Math.round(maxY - minY);

UDB.showMessage(`Created bounding box: ${width} x ${height}\nSet ${externalLinedefs.length} lines to impassable + block monsters`);