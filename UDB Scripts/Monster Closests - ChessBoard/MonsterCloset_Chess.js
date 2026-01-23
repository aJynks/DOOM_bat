`#version 4`;

`#name Monster Closet - Chess`;

`#description Creates a checkerboard-style monster closet at the mouse cursor position.`;

`#scriptoptions

monsterType
{
    description = "Monster EdNum (e.g., 3005 for Cacodemon)";
    type = 18; // Thing type picker
    default = 3005; // Cacodemon
}

thingWidth
{
    description = "Thing Width";
    type = 0; // Integer
    default = 62;
}

thingHeight
{
    description = "Thing Height";
    type = 0; // Integer
    default = 56;
}

monsterCount
{
    description = "Number of Monsters";
    type = 0; // Integer
    default = 8;
}

floorHeight
{
    description = "Monster Sector Floor Height";
    type = 0; // Integer
    default = 0;
}

teleportTag
{
    description = "Teleport Tag (0 = auto-assign next unused)";
    type = 0; // Integer
    default = 0;
}

`;

// Get the mouse position and snap to grid
let mousePos = UDB.Map.mousePosition;
let startPos = UDB.Map.snappedToGrid(mousePos);

// Get script options
let monsterType = UDB.ScriptOptions.monsterType;
let thingWidth = UDB.ScriptOptions.thingWidth;
let thingHeight = UDB.ScriptOptions.thingHeight;
let monsterCount = UDB.ScriptOptions.monsterCount;
let floorHeight = UDB.ScriptOptions.floorHeight;
let teleportTag = UDB.ScriptOptions.teleportTag;

// Round dimensions up to nearest multiple of 16
function roundTo16(value) {
    return Math.ceil(value / 16) * 16;
}

// Calculate sector dimensions (round up to expression of 16)
// Sectors should be SQUARE based on the larger dimension
let largerDimension = Math.max(thingWidth, thingHeight);
let sectorSize = roundTo16(largerDimension);
let sectorWidth = sectorSize;
let sectorHeight = sectorSize;
let ceilingHeight = floorHeight + thingHeight + 2;

// Calculate the space sector floor height (floor + 32)
let spaceFloorHeight = floorHeight + 32;

// If teleport tag is 0, find next unused tag
if (teleportTag === 0) {
    let usedTags = new Set();
    
    // Collect all used tags from sectors
    UDB.Map.getSectors().forEach(s => {
        if (s.tag > 0) usedTags.add(s.tag);
    });
    
    // Collect all used tags from linedefs
    UDB.Map.getLinedefs().forEach(ld => {
        if (ld.tag > 0) usedTags.add(ld.tag);
    });
    
    // Find next unused tag starting from 1
    teleportTag = 1;
    while (usedTags.has(teleportTag)) {
        teleportTag++;
    }
}

// Calculate checkerboard dimensions
// Find the best arrangement that minimizes wasted space
// Since we need alternating pattern, we need at least monsterCount positions
// and roughly equal number of space positions

// For a checkerboard, we need total cells = monsterCount * 2 (roughly)
// But we want to minimize total cells while fitting all monsters

function findBestGrid(monsterCount) {
    let bestCols = 0;
    let bestRows = 0;
    let bestWaste = Infinity;
    
    // Try different grid sizes
    // Start from a square-ish arrangement
    let minDimension = Math.ceil(Math.sqrt(monsterCount));
    
    for (let testCols = minDimension; testCols <= monsterCount + 2; testCols++) {
        for (let testRows = minDimension; testRows <= monsterCount + 2; testRows++) {
            // Must be even dimensions for proper checkerboard
            if (testCols % 2 !== 0) continue;
            if (testRows % 2 !== 0) continue;
            
            // Count how many monster positions are available in this grid
            let totalCells = testCols * testRows;
            let monsterPositions = Math.floor(totalCells / 2); // Half are monster positions
            
            // Must have enough positions
            if (monsterPositions < monsterCount) continue;
            
            // Calculate waste (unused cells)
            let waste = totalCells - (monsterCount * 2); // *2 because we use both monster and space cells
            
            // Prefer more square-like (cols closer to rows) when waste is equal
            let squareness = Math.abs(testCols - testRows);
            let totalWaste = waste + (squareness * 0.1); // Slight penalty for non-square
            
            if (totalWaste < bestWaste) {
                bestWaste = totalWaste;
                bestCols = testCols;
                bestRows = testRows;
            }
        }
    }
    
    return { cols: bestCols, rows: bestRows };
}

let gridSize = findBestGrid(monsterCount);
let cols = gridSize.cols;
let rows = gridSize.rows;

// If the grid is taller than it is wide, swap dimensions to make it landscape
if (rows > cols) {
    let temp = cols;
    cols = rows;
    rows = temp;
}

// Clear any existing marks
UDB.Map.clearAllMarks();

// Arrays to store sectors by type
let monsterSectorsList = [];
let spaceSectorsList = [];

// Track which cells have monsters in checkerboard pattern
let monstersPlaced = 0;

// Create the entire checkerboard grid
for (let row = 0; row < rows; row++) {
    for (let col = 0; col < cols; col++) {
        // Calculate position for this cell
        let cellX = startPos.x + (col * sectorWidth);
        let cellY = startPos.y - (row * sectorHeight);
        
        // Create the sector
        let sector = createSectorBox(cellX, cellY, sectorWidth, sectorHeight);
        
        if (sector !== null) {
            // Checkerboard pattern: monster on even positions (row + col) % 2 == 0
            let isMonsterPosition = (row + col) % 2 === 0;
            
            if (isMonsterPosition && monstersPlaced < monsterCount) {
                // Monster sector
                sector.ceilingTexture = "CEIL3_3";
                sector.floorTexture = "CEIL3_3";
                sector.ceilingHeight = ceilingHeight;
                sector.floorHeight = floorHeight;
                monsterSectorsList.push(sector);
                
                // Create the monster thing in the center with random angle
                let monsterPos = new UDB.Vector2D(
                    cellX + sectorWidth / 2,
                    cellY - sectorHeight / 2
                );
                let randomAngles = [0, 90, 180, 270];
                let randomAngle = randomAngles[Math.floor(Math.random() * 4)];
                let thing = UDB.Map.createThing(monsterPos, monsterType);
                thing.angle = randomAngle;
                
                monstersPlaced++;
            } else {
                // Space sector (raised floor)
                sector.ceilingTexture = "CEIL4_1";
                sector.floorTexture = "CEIL4_1";
                sector.ceilingHeight = ceilingHeight;
                sector.floorHeight = spaceFloorHeight; // Half the total room height
                spaceSectorsList.push(sector);
            }
        }
    }
}

// Join all monster sectors together
if (monsterSectorsList.length > 1) {
    UDB.Map.joinSectors(monsterSectorsList);
}

// Join all space sectors together
if (spaceSectorsList.length > 1) {
    UDB.Map.joinSectors(spaceSectorsList);
}

// Now find and configure all two-sided linedefs in the closet
let allLinedefs = UDB.Map.getLinedefs();
let closetLinedefs = [];

for (let ld of allLinedefs) {
    // Only process two-sided lines
    if (ld.back !== null && ld.front !== null) {
        // Check if this linedef is part of our closet
        let frontIsMonster = monsterSectorsList.some(s => ld.front.sector === s);
        let backIsMonster = monsterSectorsList.some(s => ld.back.sector === s);
        let frontIsSpace = spaceSectorsList.some(s => ld.front.sector === s);
        let backIsSpace = spaceSectorsList.some(s => ld.back.sector === s);
        
        // If one side is monster and other is space, this is part of our closet
        if ((frontIsMonster && backIsSpace) || (frontIsSpace && backIsMonster)) {
            closetLinedefs.push(ld);
        }
    }
}

// Apply teleport action and tag to all closet linedefs
for (let ld of closetLinedefs) {
    ld.action = 97; // WR Teleport (repeatable)
    ld.tag = teleportTag;
}

// Calculate total closet dimensions
let totalWidth = cols * sectorSize;
let totalHeight = rows * sectorSize;

// Build the output message
let message = `Monsters        : ${monsterCount}\n`;
message += `Teleport Tag    : ${teleportTag}\n`;
message += `Monster Closet  : ${totalWidth} x ${totalHeight}`;

UDB.showMessage(message);


/**
 * Helper function to create a rectangular sector
 */
function createSectorBox(x, y, width, height) {
    // Draw a rectangle
    // Note: y coordinates go down, so we subtract height
    let coords = [
        [x, y],
        [x + width, y],
        [x + width, y - height],
        [x, y - height],
        [x, y] // Close the rectangle
    ];
    
    UDB.Map.drawLines(coords);
    
    // Get the newly created sector (will be marked)
    let markedSectors = UDB.Map.getMarkedSectors();
    
    if (markedSectors.length > 0) {
        // Clear the mark for the next iteration
        markedSectors[0].marked = false;
        return markedSectors[0];
    }
    
    return null;
}