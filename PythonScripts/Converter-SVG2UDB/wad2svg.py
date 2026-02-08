#!/usr/bin/env python3
"""
WAD to SVG Converter
Extracts Doom maps at 1:1 scale (1 Doom unit = 1 SVG point)
"""

import struct
import argparse
from typing import List, Optional


class WADReader:
    """Read and parse Doom WAD files"""

    def __init__(self, wad_path: str):
        self.wad_path = wad_path
        self.dir = []
        self._read_wad()

    def _read_wad(self):
        with open(self.wad_path, "rb") as f:
            wad_type = f.read(4).decode("ascii", errors="ignore")
            num_lumps = struct.unpack("<I", f.read(4))[0]
            dir_offset = struct.unpack("<I", f.read(4))[0]

            print(f"WAD Type: {wad_type}")
            print(f"Number of lumps: {num_lumps}")

            f.seek(dir_offset)
            for _ in range(num_lumps):
                offset = struct.unpack("<I", f.read(4))[0]
                size = struct.unpack("<I", f.read(4))[0]
                name = f.read(8).rstrip(b"\x00").decode("ascii", errors="ignore")
                self.dir.append({"name": name, "offset": offset, "size": size})

    def get_lump_at(self, index: int) -> Optional[bytes]:
        if index < 0 or index >= len(self.dir):
            return None
        lump = self.dir[index]
        with open(self.wad_path, "rb") as f:
            f.seek(lump["offset"])
            return f.read(lump["size"])

    def list_maps(self) -> List[str]:
        maps = []
        for e in self.dir:
            name = e["name"]
            is_doom1 = (name.startswith("E") and len(name) == 4 and name[2] == "M")
            is_doom2 = (name.startswith("MAP") and len(name) == 5)
            if is_doom1 or is_doom2:
                maps.append(name)
        return sorted(set(maps))


class DoomMap:
    """Parse and store Doom map data"""

    def __init__(self, wad: WADReader, map_name: str):
        self.wad = wad
        self.map_name = map_name.upper()
        self.vertices = []
        self.linedefs = []
        self._load_map()

    def _load_map(self):
        map_index = None
        for i, e in enumerate(self.wad.dir):
            if e["name"] == self.map_name:
                map_index = i
                break
        if map_index is None:
            raise ValueError(f"Map {self.map_name} not found in WAD")

        def find_after(expected: str, max_ahead: int = 16) -> Optional[int]:
            start = map_index + 1
            end = min(start + max_ahead, len(self.wad.dir))
            for j in range(start, end):
                if self.wad.dir[j]["name"] == expected:
                    return j
            return None

        vtx_i = find_after("VERTEXES")
        ldf_i = find_after("LINEDEFS")

        if vtx_i is not None:
            data = self.wad.get_lump_at(vtx_i)
            if data:
                count = len(data) // 4
                for i in range(count):
                    x, y = struct.unpack("<hh", data[i * 4:(i + 1) * 4])
                    self.vertices.append((x, y))
        print(f"  Loaded {len(self.vertices)} vertices")

        if ldf_i is not None:
            data = self.wad.get_lump_at(ldf_i)
            if data:
                count = len(data) // 14
                for i in range(count):
                    off = i * 14
                    v1, v2, flags, special, tag, side1, side2 = struct.unpack("<7H", data[off:off + 14])
                    self.linedefs.append({
                        "v1": v1, "v2": v2,
                        "flags": flags, "special": special, "tag": tag,
                        "side1": side1, "side2": side2
                    })
        print(f"  Loaded {len(self.linedefs)} linedefs")


def map_to_svg(
    doom_map,
    out_file: str,
    canvas_size: int = 4096,
    line_width: float = 1.0,
    background: Optional[str] = None,
    stroke: str = "black",
):
    """
    Export at 1:1 scale with absolute Doom coordinates.
    (0,0) in Doom = (canvas_size/2, canvas_size/2) in SVG
    """
    verts = doom_map.vertices
    if not verts:
        raise ValueError("No vertices")

    xs = [v[0] for v in verts]
    ys = [v[1] for v in verts]

    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    map_width = max_x - min_x
    map_height = max_y - min_y

    print(f"  Map: ({min_x}, {min_y}) to ({max_x}, {max_y})")
    print(f"  Size: {map_width} × {map_height} units")

    # Doom (0,0) maps to center of canvas (2048, 2048 in 4096×4096)
    canvas_center = canvas_size / 2

    with open(out_file, "w", encoding="utf-8") as f:
        f.write(
            f'<?xml version="1.0" encoding="UTF-8" standalone="no"?>'
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'width="{canvas_size}px" height="{canvas_size}px">\n'
        )
        f.write(f'<!-- Map: {doom_map.map_name} | 1:1 scale | Doom (0,0) = SVG ({canvas_center},{canvas_center}) -->\n\n')

        if background:
            f.write(f'<rect width="{canvas_size}" height="{canvas_size}" fill="{background}"/>\n\n')

        for ld in doom_map.linedefs:
            if ld["v1"] >= len(verts) or ld["v2"] >= len(verts):
                continue

            v1, v2 = verts[ld["v1"]], verts[ld["v2"]]

            # Absolute coordinates: Doom (x,y) -> SVG (canvas_center + x, canvas_center - y)
            x1 = canvas_center + v1[0]
            y1 = canvas_center - v1[1]  # Flip Y
            x2 = canvas_center + v2[0]
            y2 = canvas_center - v2[1]  # Flip Y

            f.write(
                f'<line x1="{x1:.1f}" y1="{y1:.1f}" '
                f'x2="{x2:.1f}" y2="{y2:.1f}" '
                f'stroke="{stroke}" stroke-width="{line_width}"/>\n'
            )

        f.write("</svg>\n")

    print(f"  ✓ {out_file}")
    print(f"  Doom (0,0) = SVG ({canvas_center},{canvas_center})")


def mapnum_to_name(n: int) -> str:
    if n < 1 or n > 99:
        raise ValueError("Map 1-99 only")
    return f"MAP{n:02d}"


def main():
    parser = argparse.ArgumentParser(description="WAD to SVG (1:1 scale)")
    parser.add_argument("wad", help="WAD file")
    parser.add_argument("output", help="Output prefix")
    parser.add_argument("--all", action="store_true", help="Export all maps")
    parser.add_argument("-map", "--map", dest="mapnum", type=int, default=1,
                        help="Map number (default: 1)")
    parser.add_argument("--canvas", type=int, default=4096, help="Canvas size (default: 4096)")
    parser.add_argument("--line-width", type=float, default=1.0, help="Line width (default: 1)")
    parser.add_argument("--no-bg", action="store_true", help="No background")
    parser.add_argument("--bg", type=str, default="white", help="Background color (default: white)")
    parser.add_argument("--stroke", type=str, default="black", help="Line color (default: black)")
    parser.add_argument("--list", action="store_true", help="List maps")

    args = parser.parse_args()

    wad = WADReader(args.wad)

    if args.list:
        maps = wad.list_maps()
        print("Maps:" if maps else "No maps")
        for m in maps:
            print(" ", m)
        return

    background = None if args.no_bg else args.bg
    maps_in_wad = wad.list_maps()

    if args.all:
        if not maps_in_wad:
            raise SystemExit("No maps")
        for map_name in maps_in_wad:
            out_file = f"{args.output}_{map_name.lower()}.svg"
            print(f"\n{map_name}:")
            doom_map = DoomMap(wad, map_name)
            map_to_svg(doom_map, out_file, args.canvas, args.line_width, background, args.stroke)
    else:
        map_name = mapnum_to_name(args.mapnum)
        if map_name not in set(maps_in_wad):
            raise SystemExit(f"{map_name} not found. Use --list")

        out_file = f"{args.output}_{map_name.lower()}.svg"
        print(f"\n{map_name}:")
        doom_map = DoomMap(wad, map_name)
        map_to_svg(doom_map, out_file, args.canvas, args.line_width, background, args.stroke)

    print("\n✓ Done")


if __name__ == "__main__":
    main()