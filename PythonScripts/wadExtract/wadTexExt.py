#!/usr/bin/env python3
"""
WAD Texture Extractor
Extracts textures, patches, and flats used by a specific map from a Doom WAD file.

Usage:
    python wad_texture_extractor.py mapfile.wad -map MAP01 -iwad doom2.wad [-list|-lump|-png]
"""

import struct
import sys
import argparse
from pathlib import Path
from typing import List, Set, Tuple, Dict, Optional
from dataclasses import dataclass


@dataclass
class WadHeader:
    """WAD file header"""
    identification: str  # IWAD or PWAD
    numlumps: int
    infotableofs: int


@dataclass
class LumpInfo:
    """WAD lump directory entry"""
    filepos: int
    size: int
    name: str


@dataclass
class Patch:
    """Texture patch definition"""
    originx: int
    originy: int
    patch_num: int
    stepdir: int
    colormap: int


@dataclass
class TextureDefinition:
    """Texture definition from TEXTURE1/TEXTURE2"""
    name: str
    width: int
    height: int
    patches: List[Patch]


class WadReader:
    """Reads and parses Doom WAD files"""
    
    def __init__(self, filepath: str):
        self.filepath = filepath
        self.file = None
        self.header = None
        self.lumps: List[LumpInfo] = []
        self.lump_dict: Dict[str, LumpInfo] = {}
        
    def __enter__(self):
        self.file = open(self.filepath, 'rb')
        self._read_header()
        self._read_directory()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.file:
            self.file.close()
    
    def _read_header(self):
        """Read WAD header"""
        self.file.seek(0)
        data = self.file.read(12)
        
        identification = data[0:4].decode('ascii')
        numlumps = struct.unpack('<I', data[4:8])[0]
        infotableofs = struct.unpack('<I', data[8:12])[0]
        
        self.header = WadHeader(identification, numlumps, infotableofs)
    
    def _read_directory(self):
        """Read WAD directory/lump table"""
        self.file.seek(self.header.infotableofs)
        
        for i in range(self.header.numlumps):
            data = self.file.read(16)
            filepos = struct.unpack('<I', data[0:4])[0]
            size = struct.unpack('<I', data[4:8])[0]
            name = data[8:16].rstrip(b'\x00').decode('ascii', errors='ignore')
            
            lump = LumpInfo(filepos, size, name)
            self.lumps.append(lump)
            self.lump_dict[name.upper()] = lump
    
    def find_lump(self, name: str) -> Optional[LumpInfo]:
        """Find a lump by name"""
        return self.lump_dict.get(name.upper())
    
    def read_lump(self, lump: LumpInfo) -> bytes:
        """Read lump data"""
        if lump.size == 0:
            return b''
        self.file.seek(lump.filepos)
        return self.file.read(lump.size)
    
    def find_map_index(self, mapname: str) -> int:
        """Find the index of a map marker lump"""
        mapname = mapname.upper()
        for i, lump in enumerate(self.lumps):
            if lump.name == mapname:
                return i
        return -1
    
    def read_lump_by_name(self, name: str) -> Optional[bytes]:
        """Read lump data by name"""
        lump = self.find_lump(name)
        if lump:
            return self.read_lump(lump)
        return None


class MapParser:
    """Parse Doom map data to find used textures and flats"""
    
    def __init__(self, wad: WadReader, mapname: str):
        self.wad = wad
        self.mapname = mapname.upper()
        self.textures: Set[str] = set()
        self.flats: Set[str] = set()
    
    def parse(self) -> Tuple[Set[str], Set[str]]:
        """Parse map and return (textures, flats) used"""
        map_index = self.wad.find_map_index(self.mapname)
        if map_index == -1:
            raise ValueError(f"Map {self.mapname} not found in WAD")
        
        # Check if UDMF format
        if map_index + 1 < len(self.wad.lumps) and self.wad.lumps[map_index + 1].name == 'TEXTMAP':
            self._parse_udmf(map_index)
        else:
            self._parse_doom_format(map_index)
        
        return self.textures, self.flats
    
    def _parse_doom_format(self, map_index: int):
        """Parse traditional Doom format map"""
        sidedefs_lump = None
        sectors_lump = None
        
        for i in range(map_index + 1, min(map_index + 12, len(self.wad.lumps))):
            lump = self.wad.lumps[i]
            if lump.name == 'SIDEDEFS':
                sidedefs_lump = lump
            elif lump.name == 'SECTORS':
                sectors_lump = lump
            elif lump.name in ['THINGS', 'LINEDEFS', 'VERTEXES', 'SEGS', 'SSECTORS', 'NODES', 'REJECT', 'BLOCKMAP']:
                continue
            else:
                break
        
        if sidedefs_lump:
            self._parse_sidedefs(sidedefs_lump)
        
        if sectors_lump:
            self._parse_sectors(sectors_lump)
    
    def _parse_sidedefs(self, lump: LumpInfo):
        """Parse SIDEDEFS to extract wall textures"""
        data = self.wad.read_lump(lump)
        num_sidedefs = len(data) // 30
        
        for i in range(num_sidedefs):
            offset = i * 30
            sidedef = data[offset:offset + 30]
            
            upper_tex = sidedef[4:12].rstrip(b'\x00').decode('ascii', errors='ignore')
            lower_tex = sidedef[12:20].rstrip(b'\x00').decode('ascii', errors='ignore')
            middle_tex = sidedef[20:28].rstrip(b'\x00').decode('ascii', errors='ignore')
            
            for tex in [upper_tex, lower_tex, middle_tex]:
                if tex and tex != '-':
                    self.textures.add(tex.upper())
    
    def _parse_sectors(self, lump: LumpInfo):
        """Parse SECTORS to extract flats"""
        data = self.wad.read_lump(lump)
        num_sectors = len(data) // 26
        
        for i in range(num_sectors):
            offset = i * 26
            sector = data[offset:offset + 26]
            
            floor_flat = sector[4:12].rstrip(b'\x00').decode('ascii', errors='ignore')
            ceiling_flat = sector[12:20].rstrip(b'\x00').decode('ascii', errors='ignore')
            
            if floor_flat:
                self.flats.add(floor_flat.upper())
            if ceiling_flat:
                self.flats.add(ceiling_flat.upper())
    
    def _parse_udmf(self, map_index: int):
        """Parse UDMF format map"""
        textmap_lump = self.wad.lumps[map_index + 1]
        data = self.wad.read_lump(textmap_lump)
        text = data.decode('ascii', errors='ignore')
        
        lines = text.split('\n')
        in_sidedef = False
        in_sector = False
        
        for line in lines:
            line = line.strip()
            
            if line == 'sidedef':
                in_sidedef = True
                in_sector = False
            elif line == 'sector':
                in_sector = True
                in_sidedef = False
            elif line == '}':
                in_sidedef = False
                in_sector = False
            elif in_sidedef:
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip(' ";')
                    
                    if key in ['texturetop', 'texturemiddle', 'texturebottom'] and value != '-':
                        self.textures.add(value.upper())
            elif in_sector:
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip(' ";')
                    
                    if key in ['texturefloor', 'textureceiling']:
                        self.flats.add(value.upper())


class TextureManager:
    """Manages texture definitions from TEXTURE1/TEXTURE2"""
    
    def __init__(self, wad: WadReader):
        self.wad = wad
        self.textures: Dict[str, TextureDefinition] = {}
        self.pnames: List[str] = []
        self._load_pnames()
        self._load_textures()
    
    def _load_pnames(self):
        """Load PNAMES lump"""
        pnames_data = self.wad.read_lump_by_name('PNAMES')
        if not pnames_data:
            return
        
        num_patches = struct.unpack('<I', pnames_data[0:4])[0]
        
        for i in range(num_patches):
            offset = 4 + (i * 8)
            name = pnames_data[offset:offset + 8].rstrip(b'\x00').decode('ascii', errors='ignore')
            self.pnames.append(name.upper())
    
    def _load_textures(self):
        """Load TEXTURE1 and TEXTURE2 lumps"""
        for texture_lump_name in ['TEXTURE1', 'TEXTURE2']:
            texture_data = self.wad.read_lump_by_name(texture_lump_name)
            if not texture_data:
                continue
            
            num_textures = struct.unpack('<I', texture_data[0:4])[0]
            
            for i in range(num_textures):
                offset_pos = 4 + (i * 4)
                texture_offset = struct.unpack('<I', texture_data[offset_pos:offset_pos + 4])[0]
                
                tex_data = texture_data[texture_offset:]
                
                name = tex_data[0:8].rstrip(b'\x00').decode('ascii', errors='ignore').upper()
                width = struct.unpack('<H', tex_data[12:14])[0]
                height = struct.unpack('<H', tex_data[14:16])[0]
                patch_count = struct.unpack('<H', tex_data[20:22])[0]
                
                patches = []
                for p in range(patch_count):
                    patch_offset = 22 + (p * 10)
                    originx = struct.unpack('<h', tex_data[patch_offset:patch_offset + 2])[0]
                    originy = struct.unpack('<h', tex_data[patch_offset + 2:patch_offset + 4])[0]
                    patch_num = struct.unpack('<H', tex_data[patch_offset + 4:patch_offset + 6])[0]
                    stepdir = struct.unpack('<H', tex_data[patch_offset + 6:patch_offset + 8])[0]
                    colormap = struct.unpack('<H', tex_data[patch_offset + 8:patch_offset + 10])[0]
                    
                    patches.append(Patch(originx, originy, patch_num, stepdir, colormap))
                
                texture_def = TextureDefinition(name, width, height, patches)
                self.textures[name] = texture_def
    
    def get_texture(self, name: str) -> Optional[TextureDefinition]:
        """Get texture definition by name"""
        return self.textures.get(name.upper())
    
    def get_patches_for_texture(self, name: str) -> List[str]:
        """Get list of patch names used by a texture"""
        texture = self.get_texture(name)
        if not texture:
            return []
        
        patch_names = []
        for patch in texture.patches:
            if 0 <= patch.patch_num < len(self.pnames):
                patch_names.append(self.pnames[patch.patch_num])
        
        return patch_names


class DoomGraphic:
    """Doom picture format parser"""
    
    def __init__(self, data: bytes):
        self.data = data
        self.width = 0
        self.height = 0
        self.left_offset = 0
        self.top_offset = 0
        self.pixels = None
        self._parse()
    
    def _parse(self):
        """Parse Doom picture format"""
        if len(self.data) < 8:
            return
        
        self.width = struct.unpack('<H', self.data[0:2])[0]
        self.height = struct.unpack('<H', self.data[2:4])[0]
        self.left_offset = struct.unpack('<h', self.data[4:6])[0]
        self.top_offset = struct.unpack('<h', self.data[6:8])[0]
        
        self.pixels = [[-1 for _ in range(self.height)] for _ in range(self.width)]
        
        column_pointers = []
        for x in range(self.width):
            ptr = struct.unpack('<I', self.data[8 + x * 4:8 + x * 4 + 4])[0]
            column_pointers.append(ptr)
        
        for x in range(self.width):
            offset = column_pointers[x]
            
            while True:
                if offset >= len(self.data):
                    break
                
                row_start = self.data[offset]
                if row_start == 255:
                    break
                
                offset += 1
                pixel_count = self.data[offset]
                offset += 1
                offset += 1
                
                for i in range(pixel_count):
                    if offset >= len(self.data):
                        break
                    y = row_start + i
                    if y < self.height:
                        self.pixels[x][y] = self.data[offset]
                    offset += 1
                
                offset += 1
    
    def to_rgba(self, palette: List[Tuple[int, int, int]]) -> bytes:
        """Convert to RGBA bytes using provided palette"""
        rgba_data = bytearray()
        
        for y in range(self.height):
            for x in range(self.width):
                palette_index = self.pixels[x][y]
                
                if palette_index == -1:
                    rgba_data.extend([0, 0, 0, 0])
                else:
                    r, g, b = palette[palette_index]
                    rgba_data.extend([r, g, b, 255])
        
        return bytes(rgba_data)


class FlatGraphic:
    """Doom flat format (raw 64x64 pixels)"""
    
    def __init__(self, data: bytes):
        self.data = data
        self.width = 64
        self.height = 64
    
    def to_rgba(self, palette: List[Tuple[int, int, int]]) -> bytes:
        """Convert to RGBA bytes using provided palette"""
        rgba_data = bytearray()
        
        for i in range(self.width * self.height):
            if i < len(self.data):
                palette_index = self.data[i]
                r, g, b = palette[palette_index]
                rgba_data.extend([r, g, b, 255])
            else:
                rgba_data.extend([0, 0, 0, 255])
        
        return bytes(rgba_data)


def load_palette(wad: WadReader) -> List[Tuple[int, int, int]]:
    """Load PLAYPAL from WAD"""
    playpal_data = wad.read_lump_by_name('PLAYPAL')
    if not playpal_data or len(playpal_data) < 768:
        raise ValueError("PLAYPAL not found or invalid")
    
    palette = []
    for i in range(256):
        offset = i * 3
        r = playpal_data[offset]
        g = playpal_data[offset + 1]
        b = playpal_data[offset + 2]
        palette.append((r, g, b))
    
    return palette


def save_as_png(rgba_data: bytes, width: int, height: int, filepath: Path):
    """Save RGBA data as PNG using PIL"""
    try:
        from PIL import Image
    except ImportError:
        print("Error: PIL (Pillow) is required for PNG export. Install with: pip install Pillow")
        sys.exit(1)
    
    img = Image.frombytes('RGBA', (width, height), rgba_data)
    img.save(filepath)


def composite_texture(texture_def: TextureDefinition, patch_graphics: Dict[str, DoomGraphic], 
                     pnames: List[str], palette: List[Tuple[int, int, int]]) -> bytes:
    """Composite a texture from multiple patches"""
    rgba_data = bytearray([0, 0, 0, 0] * texture_def.width * texture_def.height)
    
    for patch in texture_def.patches:
        if patch.patch_num >= len(pnames):
            continue
        
        patch_name = pnames[patch.patch_num]
        if patch_name not in patch_graphics:
            continue
        
        graphic = patch_graphics[patch_name]
        
        if not graphic.pixels:
            continue
        
        for px in range(graphic.width):
            for py in range(graphic.height):
                tx = patch.originx + px
                ty = patch.originy + py
                
                if 0 <= tx < texture_def.width and 0 <= ty < texture_def.height:
                    palette_index = graphic.pixels[px][py]
                    
                    if palette_index != -1:
                        offset = (ty * texture_def.width + tx) * 4
                        r, g, b = palette[palette_index]
                        rgba_data[offset] = r
                        rgba_data[offset + 1] = g
                        rgba_data[offset + 2] = b
                        rgba_data[offset + 3] = 255
    
    return bytes(rgba_data)


def main():
    parser = argparse.ArgumentParser(description='Extract textures, patches, and flats from Doom WAD')
    parser.add_argument('wadfile', help='Path to WAD file')
    parser.add_argument('-map', required=True, help='Map name (e.g., MAP01, E1M1)')
    parser.add_argument('-iwad', required=True, help='Path to IWAD file (e.g., doom2.wad)')
    parser.add_argument('-list', action='store_true', help='List resources only')
    parser.add_argument('-lump', action='store_true', help='Extract as raw lumps')
    parser.add_argument('-png', action='store_true', help='Extract as PNG files')
    
    args = parser.parse_args()
    
    if not args.list and not args.lump and not args.png:
        args.png = True
    
    print(f"Loading {args.wadfile}...")
    with WadReader(args.wadfile) as wad:
        print(f"Loading IWAD {args.iwad}...")
        with WadReader(args.iwad) as iwad:
            iwad_name = Path(args.iwad).stem.lower()
            
            print(f"Parsing map {args.map}...")
            map_parser = MapParser(wad, args.map)
            textures_used, flats_used = map_parser.parse()
            
            print(f"Found {len(textures_used)} textures and {len(flats_used)} flats")
            
            print("Loading texture definitions...")
            pwad_textures = TextureManager(wad)
            iwad_textures = TextureManager(iwad)
            
            patches_needed = set()
            texture_patches = {}
            
            for texture_name in textures_used:
                patches = pwad_textures.get_patches_for_texture(texture_name)
                if not patches:
                    patches = iwad_textures.get_patches_for_texture(texture_name)
                
                if patches:
                    texture_patches[texture_name] = patches
                    patches_needed.update(patches)
            
            print(f"Found {len(patches_needed)} patches needed")
            
            if args.list:
                print("\n=== FLATS ===")
                for flat in sorted(flats_used):
                    source = "PWAD" if wad.find_lump(flat) else "IWAD"
                    print(f"  {flat} ({source})")
                
                print("\n=== PATCHES ===")
                for patch in sorted(patches_needed):
                    source = "PWAD" if wad.find_lump(patch) else "IWAD"
                    print(f"  {patch} ({source})")
                
                print("\n=== TEXTURES ===")
                for texture in sorted(textures_used):
                    patches = texture_patches.get(texture, [])
                    patch_count = len(patches)
                    source = "PWAD" if pwad_textures.get_texture(texture) else "IWAD"
                    print(f"  {texture} ({patch_count} patches, {source})")
            
            else:
                palette = None
                try:
                    palette = load_palette(wad)
                    print("Using PLAYPAL from PWAD")
                except:
                    palette = load_palette(iwad)
                    print("Using PLAYPAL from IWAD")
                
                base_dir = Path('.')
                flats_dir = base_dir / 'flats'
                patches_dir = base_dir / 'patches'
                composite_dir = base_dir / 'composite'
                
                flats_dir.mkdir(exist_ok=True)
                patches_dir.mkdir(exist_ok=True)
                composite_dir.mkdir(exist_ok=True)
                
                print("\nExtracting flats...")
                for flat_name in flats_used:
                    lump = wad.find_lump(flat_name)
                    source_wad = wad
                    output_dir = flats_dir
                    
                    if not lump:
                        lump = iwad.find_lump(flat_name)
                        source_wad = iwad
                        iwad_dir = flats_dir / iwad_name
                        iwad_dir.mkdir(exist_ok=True)
                        output_dir = iwad_dir
                    
                    if not lump:
                        print(f"  Warning: Flat {flat_name} not found")
                        continue
                    
                    data = source_wad.read_lump(lump)
                    
                    if args.lump:
                        output_file = output_dir / f"{flat_name}.lmp"
                        output_file.write_bytes(data)
                        print(f"  {flat_name} -> {output_file}")
                    elif args.png:
                        flat = FlatGraphic(data)
                        rgba_data = flat.to_rgba(palette)
                        output_file = output_dir / f"{flat_name}.png"
                        save_as_png(rgba_data, flat.width, flat.height, output_file)
                        print(f"  {flat_name} -> {output_file}")
                
                print("\nExtracting patches...")
                for patch_name in patches_needed:
                    lump = wad.find_lump(patch_name)
                    source_wad = wad
                    output_dir = patches_dir
                    
                    if not lump:
                        lump = iwad.find_lump(patch_name)
                        source_wad = iwad
                        iwad_dir = patches_dir / iwad_name
                        iwad_dir.mkdir(exist_ok=True)
                        output_dir = iwad_dir
                    
                    if not lump:
                        print(f"  Warning: Patch {patch_name} not found")
                        continue
                    
                    data = source_wad.read_lump(lump)
                    
                    if args.lump:
                        output_file = output_dir / f"{patch_name}.lmp"
                        output_file.write_bytes(data)
                        print(f"  {patch_name} -> {output_file}")
                    elif args.png:
                        graphic = DoomGraphic(data)
                        if graphic.pixels:
                            rgba_data = graphic.to_rgba(palette)
                            output_file = output_dir / f"{patch_name}.png"
                            save_as_png(rgba_data, graphic.width, graphic.height, output_file)
                            print(f"  {patch_name} -> {output_file}")
                
                if args.png:
                    print("\nCreating composite textures...")
                    for texture_name in textures_used:
                        patches = texture_patches.get(texture_name, [])
                        
                        if len(patches) <= 1:
                            continue
                        
                        texture_def = pwad_textures.get_texture(texture_name)
                        source_wad = wad
                        output_dir = composite_dir
                        pnames = pwad_textures.pnames
                        
                        if not texture_def:
                            texture_def = iwad_textures.get_texture(texture_name)
                            source_wad = iwad
                            iwad_dir = composite_dir / iwad_name
                            iwad_dir.mkdir(exist_ok=True)
                            output_dir = iwad_dir
                            pnames = iwad_textures.pnames
                        
                        if not texture_def:
                            print(f"  Warning: Texture definition for {texture_name} not found")
                            continue
                        
                        patch_graphics = {}
                        for patch in texture_def.patches:
                            if patch.patch_num < len(pnames):
                                pname = pnames[patch.patch_num]
                                
                                lump = wad.find_lump(pname)
                                if lump:
                                    data = wad.read_lump(lump)
                                else:
                                    lump = iwad.find_lump(pname)
                                    if lump:
                                        data = iwad.read_lump(lump)
                                    else:
                                        continue
                                
                                graphic = DoomGraphic(data)
                                patch_graphics[pname] = graphic
                        
                        rgba_data = composite_texture(texture_def, patch_graphics, pnames, palette)
                        
                        output_file = output_dir / f"{texture_name}.png"
                        save_as_png(rgba_data, texture_def.width, texture_def.height, output_file)
                        print(f"  {texture_name} ({len(patches)} patches) -> {output_file}")
                
                print("\nDone!")


if __name__ == '__main__':
    main()