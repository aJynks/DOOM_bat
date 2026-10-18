"""In-app help text."""

from ..constants import VERSION


# ============================================================ GUI
HELP_TEXT = """\
cleanpal v%s - Doom PLAYPAL / COLORMAP editor

MODES  (Mode dropdown, top bar)
  PLAYPAL    the palette tools (Cull / Move / Reorder / Paint), view, export.
  COLORMAP   the light tables: the palette grid shrinks to a selector, a
             fade view appears under it and the side panel shows the
             COLORMAP tools. Selection and history are shared by both.

IWAD  (IWAD button, top bar - always needed)
  The IWAD (doom2.wad, doom.wad, ...) supplies textures and patches for the
  Palettised preview, and the fallback PLAYPAL / COLORMAP. On first start
  cleanpal asks for it, offering one found beside the loaded file or in
  DOOMWADDIR / DOOMWADPATH (the folders dsda-doom searches).

LOADING
  Open a WAD (PLAYPAL lump - and its COLORMAP lump, kept for compare /
  import; the IWAD's COLORMAP is used when the file has none), SLADE
  playpal.pal / pal0.pal, SLADE pal0.png, DoomTools playpal.png, a
  .cleanpal project, or a COLORMAP image. pal0 (the first 256 colours,
  or row / line 0 of an image) is shown as a SLADE style 16x16 grid,
  index 0 top-left.

TOOLS  (PLAYPAL - side panel: Cull / Move / Reorder / Paint)
  Each tool is a window; only one is open at a time and its button lights
  up (the grid border takes its colour). With no tool open the grid shows
  the current snapshot with no markers - select, step through history,
  export, save.
    Cull     matching (exact / similar), Align, manual delete, Snapshot.
             Culling ONLY runs while this window is open.
    Move     drag colours to new slots.
    Reorder  sort colours into ramps.
    Paint    palette ramps and solid fills.
  Move, Reorder and Paint need a clean snapshot. Culling keeps the FIRST
  colour of each group, so changing the palette with culls pending would
  change which colours get kept. Switching from Cull with marks on the grid
  says so and offers "Take snapshot and continue" or Cancel.
  While Move / Reorder / Paint is open: culling is paused, Align is
  ignored (slots = indices), Back / Ctrl+Z only steps through that
  session's entries, and Export / Collapse are paused.
  Closing Cull with marks pending asks: Take snapshot / Close without
  applying (the marks come back when you reopen Cull) / Cancel.
  Switching to COLORMAP mode closes the open tool; COLORMAP always works
  on the current snapshot (no culling there).

CULL TOOLS - MATCHING, runs in order
  1. Remove exact colours
     Entries with exactly the same RGB value. The first occurrence (lowest
     index) is kept, later copies are removed.            Marker: X

  2. Remove similar colours  (needs stage 1)
     Only looks at what stage 1 left. Pairs within the tolerance are
     joined into clusters, and clustering is TRANSITIVE: if A~B and B~C,
     then A, B and C are one cluster even if A and C are further apart.
     The lowest index of each cluster is kept.           Marker: O

     CIEDE2000      (default) modern perceptual distance, built for judging
                    small differences. Corrects dE76's over-reaction to
                    saturated colours and its blue-purple distortion.
                    ~1 is just noticeable. Default 1.5.
     CIE Lab dE76   older perceptual distance. Cautious with vivid
                    colours. Default 2.0.
     Weighted RGB   channel-weighted RGB distance (0.299/0.587/0.114).
                    Blue barely counts. Default 1.1.

  Tolerance
     Drag the slider, click anywhere on its bar to jump there, use the
     mouse wheel over it (+/-0.05), or type in the box (applies as you
     type).
     In the box: Up/Down = +/-0.05, Shift+Up/Down = +/-0.5,
     mouse wheel = +/-0.05. Values above the slider range can be typed.

  Align
     Removes the removed entries and packs the kept colours toward index 0
     in their original order. The empty tail shows as a checkerboard.

TEXT FIELDS
  Every text / number box has a right-click menu: Cut, Copy, Paste,
  Delete, Select all. Ctrl+A selects the whole box while typing.

VIEW
  Mouse wheel      zoom toward the cursor
  Middle drag      pan
  Fit / F / double middle-click   reset to auto-fit
  The grid auto-fits as the window resizes until you zoom or pan.

SELECTION
  Click             select one colour
  Click-drag        box-select every colour inside
  Shift + click/drag   add to the selection
  Ctrl + click/drag    toggle colours in / out
  Ctrl+A            select all
  Esc / Clear       clear the selection
  Cull scope (under Remove similar):
    Whole palette          similar matching works on every colour
    Selected colours only  only the selection is culled; colours can only
                           merge with each other, unselected colours are
                           never touched. Nothing selected = nothing culled.
  In the Cull tools, selecting on the grid switches the scope to Selected
  colours only. Selecting is easiest with Align off - the grid reflows as
  culling changes.

REORDER TOOLS  (Reorder button -> Reorder tools window)
  Reorders the working palette into ramps (needs a clean snapshot - see
  TOOLS). You can select colours in the grid (with Preview off) to reorder
  just those.

  In the window pick a method, set its options, then:
    Preview   shows the result live on the grid (button turns blue). Changing
              any option re-sorts at once. While it is on, the selection is
              locked.
    Apply     keeps it and adds a "Reorder ..." history entry. Works with or
              without Preview. The window stays open, so you can select the
              next colour family and reorder that too.
    Cancel    (or Esc, or the Preview button again) restores the palette.

  Apply to:
    Whole palette        every colour is sorted; empty slots go to the end.
    Selected (gathered)  the selected colours are sorted and pulled together
                         into ONE block that starts at the first selected
                         slot. The other colours keep their order and shift
                         along to close the gaps. Select all the reds anywhere
                         in the palette and they end up as one red section.
                         The selection stays on the moved block afterwards.
    Opens on Selected if 2+ colours are selected, else Whole palette.
    Selecting in the grid while the window is open switches it to Selected;
    clearing the selection switches it back to Whole palette.

  Methods that find ramps:
    Curved ramps    (default, best on Doom's PLAYPAL) every colour links to
                    its nearest darker neighbour, cheapest links first, each
                    colour taking at most one lighter and one darker link.
                    Max step   longest allowed link (OKLab distance x100)
                    Max bend   how sharply a ramp may change direction - keep
                               it high for white -> colour -> black ramps
                    Hue/chroma weight  how much more a hue / colourfulness
                               change costs than a lightness change
    Line ramps      repeatedly takes the longest gap-free run of colours lying
                    on one straight line in RGB (ramps made by linear RGB
                    blending), removes it and repeats.
                    Line tolerance  distance from the line (RGB units)
                    Max gap         largest gap between neighbours on a line
    Shade families  colours with the same R:G:B ratio, i.e. one colour scaled
                    toward black. Ratio tolerance x100.
    Hue bands       greys first, then groups split at gaps in hue. Simple
                    baseline. Max band width in degrees.
  Shared options for those four:
    Order colours by   order inside each ramp (default OKLab lightness)
    Lightest / Darkest first
    Ramp order         Greys first then hue / Original position /
                       Largest first / By key (each ramp's highest value)
    Outliers           colours in ramps smaller than Min ramp size:
                       Join nearest ramp (if one is close, else left single),
                       Collect at end, or Leave single
    Min ramp size      smaller groups count as outliers

  Plain orderings (no ramps):
    Stepped hue     Alan Zucconi's hue x lightness buckets, alternating
                    direction. Smooth looking grid, not strict ramps.
    Gradient path   one nearest-colour chain through everything (OKLab),
                    tidied with 2-opt. Good on a selection.
    Single key      plain sort by the Order colours by key.
    Reverse         reverses the palette or the selection.

  No sort is perfect - try a few and compare. Sorting a selection (one
  colour family at a time) gives the most control.
  Method, options and direction are saved with the settings and presets.

  Ramp test (command line, no GUI):
    cleanpal --ramptest <palette> [folder]
  Shuffles the palette three times, runs every method with its defaults and
  reports how many of the palette's own ramps (runs of close colours in its
  current order) come back as neighbours. Writes <name>_ramptest.png with
  every result side by side.

PAINT TOOLS  (Paint button -> Paint tools window)
  Needs a clean snapshot (see TOOLS). Palette colours can only be changed
  here: the ramp, Fill, single cells, and scratch colours dragged onto the
  grid.

  Paint session - edits stay pending until you Snapshot
    Ramp Apply, Fill selected, single-cell picker edits and scratch drops
    change the working palette at once but add NO history entry. Change
    the selection between edits as much as you like.
    Snapshot   records everything since the last snapshot as ONE entry
               ("Painted: 3 ramps, 2 fills, 5 cells - ...")
    Revert     throws away everything since the last snapshot (or since
               Paint opened); the selection is kept
    Hide selection outline  hides the cyan selection, the ramp-target
               dashes and the picked-cell box (selection stays active)
    Closing with pending edits asks Snapshot / Discard / Cancel. History
    (Back / the list) is locked while edits are pending.

  Filters...  (Paint session row) - classic filters on the selection
    Pick a filter on the left, set its options (slider or number box).
    The strip shows the selected colours before (top) / after (bottom);
    blank cells are skipped. Preview shows it live on the grid - you can
    change the selection while previewing and it re-runs. Apply writes it
    (a pending paint edit - Snapshot records it). Reset = filter defaults.
    Cancel / Esc restores. Each filter remembers its settings.
      Levels                 input black / gamma / white, output range;
                             RGB or one channel
      Brightness / Contrast  Perceptual (OKLab) or Classic (RGB); pivot =
                             mid grey or selection average
      Hue / Saturation / Lightness   OKLCH (perceptual) or HSL (classic)
      Colorise               one hue, keeps lightness; hue / saturation or
                             the Paint fill colour; strength
      Black & white          Doom / Rec.601, Rec.709, OKLab L or a custom
                             channel mix
      Invert                 RGB, or lightness only (keeps the hue)
      Gradient map           lightness -> the Paint window's current ramp
                             (recolour a family, keep its shading)
      Even out ramp          even lightness steps, hue + chroma kept
      Temperature / Tint     warm / cool, green / magenta
      Posterise              N levels per channel, or lightness only

  Double-click a cell   colour picker on that one cell - changes apply
    live. The selection is left as it was. A white dashed box marks the
    cell. Double-click another cell to move the picker; picking a ramp
    node or the fill swatch moves it back. Blank cells work too.

  Fill
    Swatch / hex box / Picker... set the fill colour; From selection takes
    the first selected colour. Fill selected writes it into every selected
    cell.

  Ramp
  Select the cells to fill in the main grid - blank (empty) cells and
  normal colours can all be selected. The ramp fills them in INDEX ORDER,
  one step per cell; scattered cells work too.

  Gradient bar
    Start and end nodes are fixed at the ends.
    Click the bar        add a node there (it takes the colour shown, so the
                         ramp doesn't jump)
    Drag a node          move it            Right-click / Del   remove it
    Double-click a node  open the colour picker on it
    Node row: swatch (click = picker), hex box, position %%, Delete node.
    Right-click the swatch or hex box to copy / paste the node colour.
  Blend
    OKLab            (default) even-looking steps, no muddy middle
    RGB              plain RGB mixing, like most paint programs / Doom's ramps
    OKLCH (hue path) goes round the hue wheel - the most vivid in-betweens
  Ease     Linear / Ease in / Ease out / Ease in-out, Strength 1 - 6
  Ease applies to: Whole ramp, or Each segment (every node-to-node stretch
           eases on its own). With whole-ramp easing the nodes are drawn
           where their colour actually lands on the bar.
  Reverse              flips the ramp
  Use selection ends   start / end take the first / last selected cells'
                       colours (extend or smooth an existing ramp)
  Steps strip          the actual colours that will be written, with hover
                       info. Dot = same RGB as an earlier step; corner
                       triangle = already in the palette elsewhere (Remove
                       exact would flag it).
  Preview / Apply / Cancel: Apply writes the ramp (a pending paint edit -
  Snapshot records it). Esc cancels a preview.
  Load ramp... / Save ramp... store nodes, blend and easing as .json.
  The ramp is remembered between sessions and saved in projects.

COLOUR PICKER  (popup - Picker... / double-click a node / swatch)
  Non-modal: edits apply live to the node, the steps and the grid preview.
  Clicking another ramp node switches the picker to that node.
  Modes (dropdown) - all edit the same colour, switching never changes it:
    RGB Sliders        R / G / B sliders + full spectrum box (hue across,
                       white - colour - black down)
    HSL Sliders        H / S / L sliders + hue x lightness box drawn at the
                       current saturation
    HSL Colour Wheel   hue ring + saturation / lightness triangle
  Hue and saturation are remembered through greys, black and white, so
  dropping saturation to 0 and back keeps your hue.
  Fields: R G B (0-255), H (0-360) S L (0-100), R# G# B#, and # hex.
  The # box takes EBEBEB, #EBEBEB, #ebe or 235,235,235; Ctrl+C / Ctrl+V.
  Right-click any field or the swatch: Cut / Copy / Paste / Select all, plus
  Copy colour as hex, Copy colour as R,G,B and Paste colour (applies a
  copied colour in any of those forms to the whole colour).
  Precision:  Shift + drag = fine (quarter speed)   Ctrl + drag = lock to
              one axis   arrow keys nudge the last-used control by 1
              (Shift = 10)   mouse wheel on sliders / fields = 1 (Shift 10)
  Swatch: left = new, right = colour when the node was picked - click the
  right half to revert.
  Eyedropper: click anywhere on screen (any program); a magnifier shows the
  exact pixel. Esc / right-click cancels.
  Recent: last 16 colours used. On top keeps the window above others.

SCRATCH PALETTE  (Scratch palette... button)
  Temporary swatches in named sets (New / Rename / Delete).
  Add:   + Picker (current picker colour), + Selected (selected grid
         cells), Eyedropper, Ctrl+V (hex lines), or drag cells from the
         main grid onto it (a selected group drags as a group).
  Use:   click a swatch          -> picker / active ramp node
         drag onto a grid cell   -> writes it into the palette (Paint)
         drag onto the ramp bar  -> recolours that node (or adds one)
         drag onto the picker    -> sets the picker
         Fill selected           -> writes it into every selected cell
                                    (Paint tools must be open)
         Palette writes become "Set colour ..." history entries.
  Manage: drag to reorder, Shift / Ctrl click to multi-select, Del
         removes, Ctrl+C copies as hex. Right-click a swatch: Copy hex,
         Copy R,G,B, Paste colour(s) here, Send to picker, Remove. A dot marks swatches whose
         colour is already in the palette; hover shows where.
  Import: hex text, GIMP .gpl, JASC .pal or raw .pal (as a new set).
  Export: .gpl or hex .txt. Sets are kept between sessions and in projects.

PLAYPALS  (Tools panel -> Playpals... - a reference window, opens alongside any tool)
  Browse other palettes and copy colours out of them.
  Add...       load pal0s: WAD PLAYPAL, SLADE .pal / pal0.png, DoomTools
               playpal.png, a .cleanpal project (its current entry). Pick
               several at once. The IWAD's PLAYPAL is always listed first.
               The list is remembered.
  Remove / Clear   take palettes off the list (the IWAD stays).
  Single / Tile    one big palette, or C x R at once. Up / Down (or the
               wheel) = next palette; in Tile the active one is outlined.
  Mark colours already in my palette   white corner = exists in yours;
               hover also says "also in working palette at #n".
  Select like the main grid (click / drag / Shift / Ctrl / Ctrl+A), then:
    Copy (Ctrl+C)        to the shared clipboard (index order, no gaps)
    Paste into Paint     copy + paste over at the main grid's first
    Insert into Paint    selected cell / copy + insert paste
    Ctrl+V / Ctrl+Shift+V in this window insert / paste over the clipboard.
    Drag one colour onto a main-grid cell to set it (Paint tools).
  Pasting outside the Paint tools offers to open them (with the usual
  clean-snapshot check). Pastes are pending Paint edits until Snapshot.

CLIPBOARD  (side panel buttons + Paint / Move windows; Ctrl+C works anywhere)
  Ctrl+C  copy     the selected colours, index order, blank cells skipped -
                   one gap-free block. Also put on the system clipboard as
                   hex (Scratch palette's Ctrl+V can take it).
  Ctrl+X  cut      Paint: copy, then the cells become empty.
                   Move: take them out; the rest closes up, free slots go
                   to the end.
  Ctrl+Shift+V  paste over   Paint only: write the block over the cells
                   starting at the first selected cell (or the cell under
                   the mouse). A popup says so if it would run past 255.
  Ctrl+V  insert paste   Paint and Move: the block goes in front of
                   the target colour. Colours from there are pushed right
                   into the empty slots after it; if those run out, the
                   nearest empty slots before it are used (colours between
                   shift left) - so cut + insert paste = move. A popup
                   says "No room to insert" if the palette doesn't have
                   enough empty slots.
  Pasted colours become the selection. If the system clipboard holds a hex
  list copied elsewhere since your last Ctrl+C, that list is pasted instead.
  Paint: cuts / pastes are pending edits (Snapshot records them). Move: each
  is one undo step (Ctrl+Z), recorded by Apply.

MANUAL DELETE  (Cull tools)
  Delete / Backspace / the "Delete / restore selected" button
                    marks the selected colours as deleted   Marker: bar -
                    Do it again on deleted colours to restore them.
  Deleted colours are left out of exact / similar matching completely, are
  baked by Snapshot and are left out of exports. In the Align view they
  vanish, so switch Align off to reach them again.

MOVE TOOLS  (Move button or M key - needs a clean snapshot)
  Select first, then drag: dragging a SELECTED colour moves the
  selection; dragging from an unselected colour (or outside the grid)
  draws a selection box as usual (Shift adds, Ctrl toggles). To move one
  colour: click it, then drag it.
  A dropped colour lands on the slot and the colours in between shift
  along. Alt + drag (or "Swap instead of insert") swaps two single colours
  instead. A multi-colour selection moves as a block, in order, with its
  gaps closed up.
  Undo move / Ctrl+Z   undoes moves one at a time
  Apply                records the moves as one "Moved colours" entry
                       (the window stays open)
  Revert               back to how it was at the last Apply / opening
  Closing with unapplied moves asks Apply / Discard / Cancel. History
  can't be stepped while moves are unapplied.

PALETTISED PREVIEW
  Opens a separate window.
  Open folder...  every PNG in the folder and its subfolders - Type: Loose.
  Open WAD...     Type: All / Patches / Sprites / Flats / Graphics, plus
                  TEXTURE1 and TEXTURE2 when present:
    TEXTURE1 / TEXTURE2  every texture the lump defines, composited from
        its patches. Each lump comes from the WAD if it has one, else from
        the IWAD. The WAD's lists use the WAD's PNAMES (else the IWAD's);
        IWAD lists use the IWAD's. Patches are looked up by name in the WAD
        first, then the IWAD. Missing patches leave a transparent gap and
        are named in the info line (red name in Grid view).
    All  this WAD's own graphics plus the textures it defines itself.
  Doom-format graphics are decoded with the WAD's PLAYPAL, else the IWAD's,
  else the loaded palette. Type / name filters narrow the list.
  Up / Down (or PgUp / PgDn, or the arrow buttons) cycles through them.
  The image is shown converted to the CURRENT result palette (the colours
  an export would write right now) and updates live as you edit.
  Space flips Palettised / Original. Wheel zoom, middle-drag pan, F fit.
  Single / Grid: Grid shows columns x rows images per page (default 4x4,
  1-16 each). All images share one pixel scale so relative sizes are true;
  each cell is the size of the page's largest image. Up / Down moves a
  page and refits; zoom and pan freely in between. Names show on the
  cells when large enough (Names tick box or N key hides them); hover
  shows details; double-click an image to open it in Single view.
  Dither: Floyd-Steinberg on / off. Matching is nearest RGB.
  Source images and WADs are only read, never modified.

  Apply COLORMAP lighting (tick box under the image):
    Shows the images the way Doom's software renderer lights them, through
    the CURRENT COLORMAP (generated + your hand edits; it updates live).
    Sector light 0-255 and Distance (16-2048 map units) pick the COLORMAP
    row with vanilla's own light-table maths (320x200 reference, full
    screen); the info line shows the row used.
    Wall / sprite or Floor / ceiling (they use different distance tables).
    Diagonal / East-West (one band darker) / North-South (one band
    brighter) - Doom's fake contrast on axis-aligned walls.
    Corridor (single view): the image as a wall receding in perspective
    from 48 to 2048 units - every row the engine would use, in one picture.
    Invulnerability shows row 32 (only offered when COLORMAP mode's "Show
    invulnerability + dark rows" is ticked).
    Space compares with loaded COLORMAP: Space then flips between the
    current palette + COLORMAP and the loaded PLAYPAL + COLORMAP at the
    same light and distance (instead of Palettised / Original).
    Ports with lighting options, other resolutions or GL renderers can
    differ from the vanilla maths.

SNAPSHOTS - work like export + reload
  Snapshot   (Cull tools) takes the current result exactly as an export
             would (culling applied, packed toward 0 if Align is ticked) and makes
             it the working palette. Everything after that works on the new
             palette as if you had exported it and loaded it again.
  History    every entry is a complete palette. Click one to load it.
             Back / Ctrl+Z loads the previous entry.
  Remove     deletes the current entry and loads the one before it.
             #0 Original can't be removed.
  Collapse   keeps only the current entry and makes it the new #0 (asks
             first - the other entries are gone for good).
  A snapshot taken after stepping back discards the later entries.
  History lives in the session unless you save a project. Closing with
  changes that are neither exported nor saved as a project asks first.
  Loading a palette starts a fresh history.

COLORMAP MODE
  The COLORMAP is 34 rows x 256: rows 0-31 light levels (0 = full bright),
  row 32 invulnerability, row 33 dark. Every cell names a palette index -
  lighting can only ever pick colours already in the palette.
  The working COLORMAP is GENERATED from the current palette and updates
  with every palette change; your hand edits sit on top of it.

  Generation (COLORMAP panel)
    Matching   Perceptual (OKLab) keeps hue better in the darks; Classic
               (RGB) is exactly Freedoom's / id's generator.
    Fade curve 1 = linear like Doom; above 1 stays bright longer, below 1
               darkens sooner.
    Fade toward  black by default; a tint gives coloured darkness.
    Invulnerability  Inverse grey (Doom's formula), From loaded COLORMAP
               (matched by colour), or None (copy row 0). Hidden unless
               "Show invulnerability + dark rows" is ticked.
    Show invulnerability + dark rows  off by default: the fade strips show
               rows 0-31 only and the matrix 32 rows. Exports always write
               all 34 rows (row 32 inverse grey, row 33 dark).
    Auto-fill smoothly between hand-set steps: a colour with some hand-set
               steps fades along a smooth path through them instead of the
               plain fade - pin rows 12 and 24 and the rest follows.
  Open COLORMAP...   a WAD's COLORMAP lump, a raw .lmp, or a 256 x 32-34
               image (pixels = palette colours). It is kept for the
               preview compare and Import as hand edits (cells that differ
               from the generated ones become hand edits, matched by colour).
  Export...    COLORMAP lump (.lmp) or 256x34 image (.png), for exactly the
               palette an export writes now (removals packed or emptied the
               same way, hand edits remapped).

  Fade view (under the grid)
    Drag the bar between the palette grid and the fade view to resize them
    (remembered). On that bar:  ▲ Palette  minimises the palette grid so
    the fade view gets the full height;  ▼ Fades  shrinks the fade view
    to just the bar so the grid gets the room. Click the same button again,
    or double-click the bar, to restore the previous split.
    Fades: one strip per selected colour, light rows 0-31 left to right
    (numbered along the top), bright to dark. With "Show invulnerability
    + dark rows" ticked an extra column marked I shows the invulnerability
    row - view-only here (set it with the Invulnerability dropdown).
    Matrix: the whole COLORMAP, 256 columns x 32 light rows (+ the I row
    when shown). Row 33, the unused all-black row, is never displayed
    (exports still write it).
    Markers (H): untick to see raw colours only - no hand-set triangles /
    squares, no "target gone" marks, no diagnostic outlines. Hover still
    tells you everything. Highlight problem steps (Diagnostics panel)
    switches the diagnostic outlines alone while Markers is on.
    Right-click a palette cell = brush colour (yellow dashed outline).
    Paint   click / drag cells to set them to the brush
    Erase   back to auto        Pick   take a cell's colour as the brush
    Ctrl + paint / erase = that step for every selected colour.
    All COLORMAP tools (Paint / Erase / Pick, Clear hand edits, Import as
    hand edits, the bulk tools, diagnostics, Create fade colours) work on
    light rows 0-31 only; the invulnerability row and row 33 are left alone.
    Corner triangle = hand-set; red slash = hand-set target was removed /
    deleted (auto used meanwhile). Wheel scrolls long selections.
    Each stroke is one history entry (Back undoes; the selection stays).

  Ramp tool on fades (Ramp tool in the fade view toolbar)
    Build fades with the Ramp tool. Choose strips first (Fades view):
      click an index number   = the whole strip (rows 0-31)
      click a cell            = that strip from that row to 31
      Ctrl + click            = add another strip with ITS OWN start row
                                (e.g. 112 whole, 113 from 20, 114 from 30);
                                Ctrl + click a chosen index removes it
      Shift + click an index  = whole strips from the last one to this one
    Gold outline = reference strip (the last one clicked), cyan = others;
    rows before each start are dimmed and left alone.
    "Ramp tool..." opens the Ramp tool in fade mode:
      start node = LOCKED: the colour the fade continues from (the colour
        itself for a whole strip, or what the row before the start shows);
      end node = row 31; add nodes, blends and easing as usual.
      RELATIVE: nodes are stored as changes from the start (lightness and
        colourfulness ratios, hue turn), so every strip gets the same shape
        of fade from its own colour, spread over its own rows.
      Steps: top = smooth ramp, bottom = palette colour it snaps to (the
        COLORMAP can only use palette colours); red underline = poor snap.
      Add missing colours (budget): new palette colours (empty slots) that
        fix the worst snaps across all strips.
      Preview / Apply / Cancel: Apply writes each strip's range as hand-set
        steps (one history entry).

    Full bright / Normal      never darken (or undo that)
    Clear hand edits          the selection back to auto
    Fade down through the selection itself: treats the selection as a
      ramp (by Lightness or Index); each colour steps down through the
      others N steps per light level, then Black or Auto past the end.
    Store selection as targets + Limit to targets: the selected colours'
      fades may only use the stored colours (plus the fade colour) - stops
      reds drifting into muddy browns. Remove limit undoes it.
    Fade curve Set / Clear    a curve for just these colours
    Copy fade shape / Paste shape to selected: copies one colour's fade as
      a relative shape (offsets from its own colour) onto others.

  Create fade colours
    Works out which NEW dark colours would most improve the fades (whole
    palette or selected), up to the budget. Steps are weighted by how much
    the colour is used in the Palettised preview's images when it is open.
    The proposals window shows each colour, what it serves and the error
    before / after; untick any, then Add to palette - they go into empty
    slots (cull + snapshot first to make room) and the COLORMAP starts
    using them at once.

  Diagnostics
    Early crush (red)  falls to near black too soon
    Hue drift (orange) lands on a different hue than it should
    Big jump (yellow)  a much bigger brightness step than the ideal fade
    Far from ideal (purple)
    Click a colour in the list to select it and see its fade.

  Hand edits follow their colours through moves, sorts, Align packing and
  snapshots. Edits pointing at a culled colour follow the colour it merged
  into; otherwise they go back to auto (the snapshot status line says how
  many). Changing a colour (ramp, set colour) resets its own fade.

PROJECTS
  Save project / Save project as...  write a .cleanpal file (JSON):
    every history entry and which one is loaded, deleted marks, the
    selection, matching / sort / export / COLORMAP settings, every entry's
    COLORMAP hand edits, the loaded COLORMAP, the mode, the ramp, scratch
    sets, recent colours and picker mode. Palettes are stored inside, so the
    project still opens if the source WAD / PNG moves.
  Load project... (or Open..., or cleanpal mywork.cleanpal) restores it exactly. Its scratch
    sets are merged into yours (same name = project's version wins).
  A project save counts as saved for the close warning.
  Hover info and analysis PNGs refer to the working palette's indices.

HOVER
  Shows index, RGB and Lab. Hovering a removed entry outlines the colour
  it collapses into; hovering a kept entry outlines what it absorbed.

EXPORT - writes what the grid currently shows
  With the Cull tools open: the culled result (packed if Align is on).
  With no tool open: the palette as it is. Paused in Move / Reorder / Paint.
  DoomTools playpal.png        256x14, Doom pain / item / radsuit tints
  DoomTools blank playpal.png  256x14, pal0 copied to every row
  SLADE pal0.png               128x128 grid, 8x8 cells
  SLADE pal0.pal               768 byte raw palette
  SLADE playpal.pal            14 x 768 bytes, tinted
  Analysis PNGs                original cleanpal0 outputs, into a folder:
     -identical-  stage 1 removals at their original slots
     -similar-    stage 2 removals at their original slots
     -aligned-    kept colours packed from slot 0
     Split        also one -keepNNN file per set / cluster

  Removed / empty slots are TRANSPARENT in PNGs and GREEN (0,255,0) in
  .pal files. Green stays untinted in every palette so it reads as a
  placeholder. You are warned if a kept colour is exactly (0,255,0).

  Filename token: (DE2000-1.5) / (CIE-2.0) / (RGB-1.1) with similar on,
  (EXACT) for
  exact only, (NONE) with no matching.

SETTINGS
  Everything is remembered when you close: matching tick boxes, metric,
  each metric's tolerance, Align, sort method and options, export format,
  split, window size /
  position and the last folder. Stored in
  %%APPDATA%%\\cleanpal\\cleanpal_settings.json. You are told if saving fails.

PRESETS
  Save preset...  writes the matching, sort + export setup to a .json file:
                  tick boxes, metric, every metric's tolerance, Align,
                  sort method and options, export format and split (no
                  window size or folders).
  Load preset...  applies one immediately. The preset's name shows in
                  the title bar.
  Default folder: %%APPDATA%%\\cleanpal\\presets
""" % VERSION
