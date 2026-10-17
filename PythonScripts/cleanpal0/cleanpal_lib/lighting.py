"""Doom software-renderer lighting: which COLORMAP row a pixel uses.

Integer maths copied from vanilla r_main.c (R_InitLightTables /
R_ExecuteSetViewSize) at the 320x200 reference resolution, full screen,
high detail. Ports with lighting options or other resolutions can differ.
"""

LIGHTLEVELS = 16
LIGHTSEGSHIFT = 4
NUMCOLORMAPS = 32
MAXLIGHTSCALE = 48
LIGHTSCALESHIFT = 12
MAXLIGHTZ = 128
LIGHTZSHIFT = 20
DISTMAP = 2
FRACBITS = 16
SCREENWIDTH = 320
VIEWWIDTH = 320
CENTERXFRAC = (SCREENWIDTH // 2) << FRACBITS     # projection

WALL_ORIENTATIONS = ["Diagonal / other", "East-West (darker)", "North-South (brighter)"]
SURFACES = ["Wall / sprite", "Floor / ceiling"]


def _clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def _startmap(lightnum):
    return ((LIGHTLEVELS - 1 - lightnum) * 2) * NUMCOLORMAPS // LIGHTLEVELS


def light_num(light, extralight=0, fake=0):
    """Sector light 0..255 -> light band 0..15 (with fake contrast -1/+1)."""
    return _clamp((int(light) >> LIGHTSEGSHIFT) + extralight + fake, 0, LIGHTLEVELS - 1)


def wall_row(light, dist, orientation=0, extralight=0):
    """COLORMAP row for a wall / sprite pixel at `dist` map units.
    orientation: 0 = other, 1 = east-west line (-1 band), 2 = north-south (+1)."""
    fake = {1: -1, 2: 1}.get(orientation, 0)
    ln = light_num(light, extralight, fake)
    dist = max(int(dist), 1)
    scale = CENTERXFRAC // dist                      # rw_scale, fixed point
    j = _clamp(scale >> LIGHTSCALESHIFT, 0, MAXLIGHTSCALE - 1)
    level = _startmap(ln) - j * SCREENWIDTH // VIEWWIDTH // DISTMAP
    return _clamp(level, 0, NUMCOLORMAPS - 1)


def flat_row(light, dist, extralight=0):
    """COLORMAP row for a floor / ceiling pixel at `dist` map units."""
    ln = light_num(light, extralight)
    j = _clamp((max(int(dist), 0) << FRACBITS) >> LIGHTZSHIFT, 0, MAXLIGHTZ - 1)
    scale = ((CENTERXFRAC << FRACBITS) // ((j + 1) << LIGHTZSHIFT)) >> LIGHTSCALESHIFT
    level = _startmap(ln) - scale // DISTMAP
    return _clamp(level, 0, NUMCOLORMAPS - 1)


def surface_row(surface, light, dist, orientation=0):
    if surface == SURFACES[1]:
        return flat_row(light, dist)
    return wall_row(light, dist, orientation)
