"""WAD file reading and lump extraction"""

import struct
from pathlib import Path


class WADFile:
    """Simple WAD file reader for extracting lumps"""
    
    def __init__(self, path):
        """
        Open a WAD file and read its directory.
        
        Args:
            path: Path to .wad file
        """
        self.path = Path(path)
        self.lumps = {}
        
        with open(self.path, "rb") as f:
            # Read WAD header
            magic = f.read(4)
            if magic not in (b"IWAD", b"PWAD"):
                raise ValueError(f"Not a valid WAD file: {path}")
            
            numlumps, diroffset = struct.unpack("<II", f.read(8))
            
            # Read directory
            f.seek(diroffset)
            for _ in range(numlumps):
                filepos, size = struct.unpack("<II", f.read(8))
                name = f.read(8).rstrip(b'\x00').decode('ascii', errors='ignore')
                self.lumps[name.upper()] = (filepos, size)
    
    def has_lump(self, name):
        """Check if lump exists in WAD"""
        return name.upper() in self.lumps
    
    def read_lump(self, name):
        """
        Read lump data from WAD.
        
        Args:
            name: Lump name (case-insensitive)
            
        Returns:
            bytes object containing lump data
            
        Raises:
            KeyError: If lump not found
        """
        name = name.upper()
        if name not in self.lumps:
            raise KeyError(f"Lump '{name}' not found in WAD")
        
        filepos, size = self.lumps[name]
        
        with open(self.path, "rb") as f:
            f.seek(filepos)
            return f.read(size)
    
    def list_lumps(self):
        """Get list of all lump names"""
        return list(self.lumps.keys())
    
    def find_boom_colormaps(self):
        """
        Find all Boom colormaps (between C_START and C_END markers).
        
        Returns:
            List of colormap lump names
        """
        lumps = self.list_lumps()
        
        # Find C_START and C_END
        try:
            start_idx = lumps.index("C_START")
            end_idx = lumps.index("C_END")
        except ValueError:
            return []  # No Boom colormaps
        
        # Return lumps between markers
        return lumps[start_idx + 1:end_idx]


def extract_playpal(wad_path):
    """
    Extract PLAYPAL lump from WAD.
    
    Args:
        wad_path: Path to WAD file
        
    Returns:
        bytes object (10752 bytes) or None if not found
    """
    wad = WADFile(wad_path)
    
    if not wad.has_lump("PLAYPAL"):
        return None
    
    return wad.read_lump("PLAYPAL")


def extract_colormap(wad_path, lump_name="COLORMAP"):
    """
    Extract COLORMAP (or Boom colormap) lump from WAD.
    
    Args:
        wad_path: Path to WAD file
        lump_name: Name of colormap lump (default "COLORMAP")
        
    Returns:
        bytes object (8704 bytes) or None if not found
    """
    wad = WADFile(wad_path)
    
    if not wad.has_lump(lump_name):
        return None
    
    return wad.read_lump(lump_name)


def read_wad_lump(wad_path, lump_name):
    """
    Read a lump from WAD file (backward compatibility wrapper).
    
    Args:
        wad_path: Path to WAD file
        lump_name: Lump name
        
    Returns:
        bytes object or None if not found
    """
    wad = WADFile(wad_path)
    
    if not wad.has_lump(lump_name):
        return None
    
    return wad.read_lump(lump_name)


def find_boom_colormaps(wad_path):
    """
    Find all Boom colormaps in WAD (backward compatibility wrapper).
    
    Returns:
        List of tuples (name, filepos, size)
    """
    wad = WADFile(wad_path)
    colormap_names = wad.find_boom_colormaps()
    
    # Return with filepos and size info
    result = []
    for name in colormap_names:
        if name in wad.lumps:
            filepos, size = wad.lumps[name]
            result.append((name, filepos, size))
    
    return result
