#!/usr/bin/env python3
"""
SVG to JSON Geometry Converter for UDB Scripts
Converts Affinity Designer SVG exports to JSON data that UDB scripts can import
"""

import sys
import json
import os
import argparse
import math
import re
from xml.etree import ElementTree as ET
from typing import List, Tuple, Dict

def cubic_bezier_point(t: float, p0: Tuple[float, float], p1: Tuple[float, float], 
                       p2: Tuple[float, float], p3: Tuple[float, float]) -> Tuple[float, float]:
    """Calculate point on cubic Bézier curve at parameter t (0 to 1)"""
    mt = 1 - t
    mt2 = mt * mt
    mt3 = mt2 * mt
    t2 = t * t
    t3 = t2 * t
    
    x = mt3 * p0[0] + 3 * mt2 * t * p1[0] + 3 * mt * t2 * p2[0] + t3 * p3[0]
    y = mt3 * p0[1] + 3 * mt2 * t * p1[1] + 3 * mt * t2 * p2[1] + t3 * p3[1]
    
    return (x, y)

def quadratic_bezier_point(t: float, p0: Tuple[float, float], p1: Tuple[float, float], 
                           p2: Tuple[float, float]) -> Tuple[float, float]:
    """Calculate point on quadratic Bézier curve at parameter t (0 to 1)"""
    mt = 1 - t
    mt2 = mt * mt
    t2 = t * t
    
    x = mt2 * p0[0] + 2 * mt * t * p1[0] + t2 * p2[0]
    y = mt2 * p0[1] + 2 * mt * t * p1[1] + t2 * p2[1]
    
    return (x, y)

def perpendicular_distance(point: Tuple[float, float], line_start: Tuple[float, float], 
                          line_end: Tuple[float, float]) -> float:
    """Calculate perpendicular distance from point to line segment"""
    x0, y0 = point
    x1, y1 = line_start
    x2, y2 = line_end
    
    dx = x2 - x1
    dy = y2 - y1
    
    if dx == 0 and dy == 0:
        return math.sqrt((x0 - x1)**2 + (y0 - y1)**2)
    
    t = max(0, min(1, ((x0 - x1) * dx + (y0 - y1) * dy) / (dx * dx + dy * dy)))
    
    proj_x = x1 + t * dx
    proj_y = y1 + t * dy
    
    return math.sqrt((x0 - proj_x)**2 + (y0 - proj_y)**2)

def rdp_simplify(points: List[Tuple[float, float]], epsilon: float) -> List[Tuple[float, float]]:
    """
    Ramer-Douglas-Peucker algorithm for curve simplification.
    Reduces number of points while maintaining curve shape within epsilon tolerance.
    """
    if len(points) < 3:
        return points
    
    # Find point with maximum distance from line between first and last
    dmax = 0
    index = 0
    end = len(points) - 1
    
    for i in range(1, end):
        d = perpendicular_distance(points[i], points[0], points[end])
        if d > dmax:
            index = i
            dmax = d
    
    # If max distance is greater than epsilon, recursively simplify
    if dmax > epsilon:
        # Recursive call on both segments
        rec_results1 = rdp_simplify(points[:index + 1], epsilon)
        rec_results2 = rdp_simplify(points[index:], epsilon)
        
        # Combine results (removing duplicate middle point)
        result = rec_results1[:-1] + rec_results2
    else:
        # If max distance is less than epsilon, just keep endpoints
        result = [points[0], points[end]]
    
    return result

class SVGToJSON:
    def __init__(self, svg_path: str, curve_segments: int = 32, simplify_tolerance: float = 0.5):
        self.svg_path = svg_path
        self.curve_segments = curve_segments  # Initial sampling resolution
        self.simplify_tolerance = simplify_tolerance  # RDP simplification tolerance
        self.shapes = []
        self.document_height = 0
        
    def parse_svg(self):
        """Parse the SVG file and extract geometry"""
        tree = ET.parse(self.svg_path)
        root = tree.getroot()
        
        # Get document height for Y-axis flip
        # Try width/height first, fall back to viewBox if they're percentages
        height_attr = root.get('height', '4096px')
        
        if '%' in height_attr or height_attr == '':
            # Use viewBox instead
            viewbox = root.get('viewBox', '0 0 4096 4096')
            parts = viewbox.split()
            if len(parts) == 4:
                self.document_height = float(parts[3])
            else:
                self.document_height = 4096.0
        else:
            # Parse pixel value
            self.document_height = float(height_attr.replace('px', '').replace('pt', ''))
        
        print(f"Parsing SVG: {self.svg_path}")
        print(f"Document size: {self.document_height}px x {self.document_height}px")
        print(f"Y-axis will be flipped for Doom coordinates\n")
        
        # Process all elements using iter() to handle namespaces properly
        rect_count = 0
        path_count = 0
        poly_count = 0
        circle_count = 0
        ellipse_count = 0
        
        for elem in root.iter():
            tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
            
            if tag == 'rect':
                self._process_rect(elem, rect_count)
                rect_count += 1
            elif tag == 'path':
                self._process_path(elem, path_count)
                path_count += 1
            elif tag == 'polygon':
                self._process_polygon(elem, poly_count)
                poly_count += 1
            elif tag == 'circle':
                self._process_circle(elem, circle_count)
                circle_count += 1
            elif tag == 'ellipse':
                self._process_ellipse(elem, ellipse_count)
                ellipse_count += 1
            
        print(f"\nExtracted {len(self.shapes)} shapes")
        
    def _flip_y(self, y: float) -> float:
        """Flip Y coordinate from SVG (top-left origin) to Doom (bottom-left origin)"""
        return self.document_height - y
    
    def _process_rect(self, rect, idx):
        """Convert SVG rect to vertex list"""
        x = float(rect.get('x', 0))
        y = float(rect.get('y', 0))
        width = float(rect.get('width', 0))
        height = float(rect.get('height', 0))
        
        # Create 4 vertices (clockwise from top-left)
        vertices = [
            [round(x), round(self._flip_y(y))],                      # top-left
            [round(x + width), round(self._flip_y(y))],              # top-right
            [round(x + width), round(self._flip_y(y + height))],     # bottom-right
            [round(x), round(self._flip_y(y + height))]              # bottom-left
        ]
        
        self.shapes.append({
            'type': 'rect',
            'name': f'rect_{idx}',
            'vertices': vertices,
            'closed': True
        })
        
        print(f"  Rectangle {idx}: {len(vertices)} vertices")
        
    def _process_path(self, path, idx):
        """Convert SVG path to vertex list, approximating curves as line segments"""
        d = path.get('d', '')
        if not d:
            print(f"  ⚠ Path {idx}: No 'd' attribute - SKIPPING")
            return
        
        # Check if path is closed
        is_closed = 'Z' in d or 'z' in d
        
        # Also check style attribute for fill:none (indicates open path)
        style = path.get('style', '')
        if 'fill:none' in style or 'fill: none' in style:
            is_closed = False
        
        print(f"  Processing path {idx}... ({'closed' if is_closed else 'OPEN'})")
        
        # Check for curve commands
        has_curves = any(cmd in d for cmd in ['C', 'c', 'Q', 'q'])
        
        if has_curves:
            print(f"    Converting curves to {self.curve_segments} segments per curve")
            vertices_raw = self._parse_path_with_curves(d)
            
            # Step 1: Snap to integer grid and remove duplicates
            vertices_snapped = []
            prev_point = None
            for v in vertices_raw:
                point = (round(v[0]), round(v[1]))
                if point != prev_point:  # Remove consecutive duplicates
                    vertices_snapped.append(point)
                    prev_point = point
            
            print(f"    Snapped to grid: {len(vertices_raw)} -> {len(vertices_snapped)} unique vertices")
            
            # Step 2: Apply RDP simplification to remove collinear/redundant points
            if self.simplify_tolerance > 0 and len(vertices_snapped) > 2:
                points_float = [(float(p[0]), float(p[1])) for p in vertices_snapped]
                simplified = rdp_simplify(points_float, self.simplify_tolerance)
                vertices = [[int(p[0]), int(p[1])] for p in simplified]
                print(f"    Simplified: {len(vertices_snapped)} -> {len(vertices)} vertices (tolerance: {self.simplify_tolerance})")
            else:
                vertices = [[v[0], v[1]] for v in vertices_snapped]
            
            if len(vertices) >= 2:  # Open paths only need 2 vertices minimum
                self.shapes.append({
                    'type': 'path',
                    'name': f'path_{idx}',
                    'vertices': vertices,
                    'closed': is_closed
                })
                print(f"    ✓ Path {idx}: {len(vertices)} vertices ({'closed shape' if is_closed else 'open line'})")
            else:
                print(f"    ⚠ Not enough vertices ({len(vertices)})")
            return
        
        # No curves - parse as straight lines
        d_spaced = re.sub(r'([MLZmlz])', r' \1 ', d)
        d_spaced = d_spaced.replace(',', ' ')
        commands = d_spaced.split()
        
        vertices = []
        current_pos = None
        i = 0
        
        while i < len(commands):
            cmd = commands[i]
            
            if cmd == 'M' or cmd == 'm':
                if i + 2 < len(commands):
                    try:
                        x = float(commands[i+1])
                        y = float(commands[i+2])
                        if cmd == 'm' and current_pos:
                            x += current_pos[0]
                            y += current_pos[1]
                        current_pos = (x, y)
                        vertices.append([round(x), round(self._flip_y(y))])
                    except ValueError:
                        pass
                i += 3
                
            elif cmd == 'L' or cmd == 'l':
                if i + 2 < len(commands):
                    try:
                        x = float(commands[i+1])
                        y = float(commands[i+2])
                        if cmd == 'l' and current_pos:
                            x += current_pos[0]
                            y += current_pos[1]
                        current_pos = (x, y)
                        vertices.append([round(x), round(self._flip_y(y))])
                    except ValueError:
                        pass
                i += 3
                
            elif cmd == 'Z' or cmd == 'z':
                i += 1
                break
                
            else:
                i += 1
        
        if len(vertices) >= 2:  # Open paths need at least 2 vertices
            min_verts = 3 if is_closed else 2
            if len(vertices) >= min_verts:
                self.shapes.append({
                    'type': 'path',
                    'name': f'path_{idx}',
                    'vertices': vertices,
                    'closed': is_closed
                })
                print(f"    ✓ Path {idx}: {len(vertices)} vertices ({'closed shape' if is_closed else 'open line'})")
            else:
                print(f"    ⚠ Not enough vertices ({len(vertices)})")
        else:
            print(f"    ⚠ Not enough vertices ({len(vertices)})")
    
    def _parse_path_with_curves(self, d: str) -> List[List[int]]:
        """Parse SVG path with curves, converting to line segments"""
        # Tokenize the path
        d_clean = d.replace(',', ' ')
        d_clean = re.sub(r'([MLCQZmlcqz])', r' \1 ', d_clean)
        tokens = [t for t in d_clean.split() if t]
        
        vertices = []
        current_pos = (0.0, 0.0)
        i = 0
        
        while i < len(tokens):
            cmd = tokens[i]
            
            if cmd == 'M':  # Absolute move
                x, y = float(tokens[i+1]), float(tokens[i+2])
                current_pos = (x, y)
                vertices.append([round(x), round(self._flip_y(y))])
                i += 3
                
            elif cmd == 'm':  # Relative move
                dx, dy = float(tokens[i+1]), float(tokens[i+2])
                current_pos = (current_pos[0] + dx, current_pos[1] + dy)
                vertices.append([round(current_pos[0]), round(self._flip_y(current_pos[1]))])
                i += 3
                
            elif cmd == 'L':  # Absolute line
                x, y = float(tokens[i+1]), float(tokens[i+2])
                current_pos = (x, y)
                vertices.append([round(x), round(self._flip_y(y))])
                i += 3
                
            elif cmd == 'l':  # Relative line
                dx, dy = float(tokens[i+1]), float(tokens[i+2])
                current_pos = (current_pos[0] + dx, current_pos[1] + dy)
                vertices.append([round(current_pos[0]), round(self._flip_y(current_pos[1]))])
                i += 3
                
            elif cmd == 'C':  # Absolute cubic Bézier
                p0 = current_pos
                p1 = (float(tokens[i+1]), float(tokens[i+2]))
                p2 = (float(tokens[i+3]), float(tokens[i+4]))
                p3 = (float(tokens[i+5]), float(tokens[i+6]))
                
                # Approximate curve with line segments
                for j in range(1, self.curve_segments + 1):
                    t = j / self.curve_segments
                    pt = cubic_bezier_point(t, p0, p1, p2, p3)
                    vertices.append([round(pt[0]), round(self._flip_y(pt[1]))])
                
                current_pos = p3
                i += 7
                
            elif cmd == 'c':  # Relative cubic Bézier
                p0 = current_pos
                p1 = (current_pos[0] + float(tokens[i+1]), current_pos[1] + float(tokens[i+2]))
                p2 = (current_pos[0] + float(tokens[i+3]), current_pos[1] + float(tokens[i+4]))
                p3 = (current_pos[0] + float(tokens[i+5]), current_pos[1] + float(tokens[i+6]))
                
                for j in range(1, self.curve_segments + 1):
                    t = j / self.curve_segments
                    pt = cubic_bezier_point(t, p0, p1, p2, p3)
                    vertices.append([round(pt[0]), round(self._flip_y(pt[1]))])
                
                current_pos = p3
                i += 7
                
            elif cmd == 'Q':  # Absolute quadratic Bézier
                p0 = current_pos
                p1 = (float(tokens[i+1]), float(tokens[i+2]))
                p2 = (float(tokens[i+3]), float(tokens[i+4]))
                
                for j in range(1, self.curve_segments + 1):
                    t = j / self.curve_segments
                    pt = quadratic_bezier_point(t, p0, p1, p2)
                    vertices.append([round(pt[0]), round(self._flip_y(pt[1]))])
                
                current_pos = p2
                i += 5
                
            elif cmd == 'q':  # Relative quadratic Bézier
                p0 = current_pos
                p1 = (current_pos[0] + float(tokens[i+1]), current_pos[1] + float(tokens[i+2]))
                p2 = (current_pos[0] + float(tokens[i+3]), current_pos[1] + float(tokens[i+4]))
                
                for j in range(1, self.curve_segments + 1):
                    t = j / self.curve_segments
                    pt = quadratic_bezier_point(t, p0, p1, p2)
                    vertices.append([round(pt[0]), round(self._flip_y(pt[1]))])
                
                current_pos = p2
                i += 5
                
            elif cmd in ['Z', 'z']:  # Close path
                i += 1
                break
                
            else:
                i += 1
        
        return vertices
    
    def _process_polygon(self, polygon, idx):
        """Convert SVG polygon to vertex list"""
        points = polygon.get('points', '')
        if not points:
            return
            
        # Parse points attribute
        coords = [float(x) for x in points.replace(',', ' ').split()]
        vertices = []
        
        for i in range(0, len(coords), 2):
            x = coords[i]
            y = coords[i+1]
            vertices.append([round(x), round(self._flip_y(y))])
        
        if len(vertices) >= 3:
            self.shapes.append({
                'type': 'polygon',
                'name': f'polygon_{idx}',
                'vertices': vertices,
                'closed': True
            })
            print(f"  Polygon {idx}: {len(vertices)} vertices")
    
    def _process_circle(self, circle, idx):
        """Store SVG circle as parametric data for runtime curve generation"""
        cx = float(circle.get('cx', 0))
        cy = float(circle.get('cy', 0))
        r = float(circle.get('r', 0))
        
        if r == 0:
            return
        
        print(f"  Circle {idx}: center ({cx}, {cy}), radius {r}")
        
        self.shapes.append({
            'type': 'circle',
            'name': f'circle_{idx}',
            'cx': round(cx),
            'cy': round(self._flip_y(cy)),
            'r': round(r),
            'closed': True
        })
    
    def _process_ellipse(self, ellipse, idx):
        """Store SVG ellipse as parametric data for runtime curve generation"""
        cx = float(ellipse.get('cx', 0))
        cy = float(ellipse.get('cy', 0))
        rx = float(ellipse.get('rx', 0))
        ry = float(ellipse.get('ry', 0))
        
        if rx == 0 or ry == 0:
            return
        
        print(f"  Ellipse {idx}: center ({cx}, {cy}), radii ({rx}, {ry})")
        
        self.shapes.append({
            'type': 'ellipse',
            'name': f'ellipse_{idx}',
            'cx': round(cx),
            'cy': round(self._flip_y(cy)),
            'rx': round(rx),
            'ry': round(ry),
            'closed': True
        })
    
    def write_udb_script(self, output_path: str, script_name: str):
        """Write UDB script with embedded geometry data"""
        
        # Build JavaScript array of shapes
        shapes_js = "const shapes = " + json.dumps(self.shapes, indent=2) + ";\n\n"
        
        script_content = f'''/// <reference path="../udbscript.d.ts" />

`#version 5`;
`#name svg2UDB - {script_name}`;
`#description Imports geometry from embedded SVG data`;

`#scriptoptions

floor_height
{{
    description = "Floor height";
    type = 0; // integer
    default = 0;
}}

ceiling_height
{{
    description = "Ceiling height";
    type = 0; // integer
    default = 128;
}}

floor_texture
{{
    description = "Floor texture";
    type = 7; // flat
    default = "FLOOR0_1";
}}

ceiling_texture
{{
    description = "Ceiling texture";
    type = 7; // flat
    default = "CEIL1_1";
}}

light_level
{{
    description = "Light level (0-255)";
    type = 0; // integer
    default = 160;
}}

curve_segments
{{
    description = "Curve resolution (segments for circles/curves)";
    type = 0; // integer
    default = 64;
}}
`;

// Embedded geometry data from SVG
{shapes_js}

// Main import function
function importGeometry() {{
    
    UDB.showMessage('Importing ' + shapes.length + ' shapes from SVG');
    
    // Get options
    const floorHeight = UDB.ScriptOptions.floor_height;
    const ceilingHeight = UDB.ScriptOptions.ceiling_height;
    const floorTex = UDB.ScriptOptions.floor_texture;
    const ceilingTex = UDB.ScriptOptions.ceiling_texture;
    const lightLevel = UDB.ScriptOptions.light_level;
    const curveSegments = UDB.ScriptOptions.curve_segments;
    
    // Helper function to generate circle/ellipse vertices
    function generateCurveVertices(shape, segments) {{
        const vertices = [];
        
        if (shape.type === 'circle') {{
            for (let i = 0; i < segments; i++) {{
                const angle = 2 * Math.PI * i / segments;
                const x = shape.cx + shape.r * Math.cos(angle);
                const y = shape.cy + shape.r * Math.sin(angle);
                vertices.push([Math.round(x), Math.round(y)]);
            }}
        }} else if (shape.type === 'ellipse') {{
            for (let i = 0; i < segments; i++) {{
                const angle = 2 * Math.PI * i / segments;
                const x = shape.cx + shape.rx * Math.cos(angle);
                const y = shape.cy + shape.ry * Math.sin(angle);
                vertices.push([Math.round(x), Math.round(y)]);
            }}
        }}
        
        return vertices;
    }}
    
    // Process each shape
    for (const shape of shapes) {{
        // Get vertices - either pre-calculated or generate from parametric data
        let shapeVertices;
        if (shape.vertices) {{
            shapeVertices = shape.vertices;
        }} else if (shape.type === 'circle' || shape.type === 'ellipse') {{
            shapeVertices = generateCurveVertices(shape, curveSegments);
        }} else {{
            continue;
        }}
        
        if (shapeVertices.length < 2) {{
            continue;
        }}
        
        // Handle open lines differently from closed shapes
        if (!shape.closed) {{
            // Open line - create linedefs without sectors
            for (let i = 0; i < shapeVertices.length - 1; i++) {{
                const v1 = UDB.Map.createVertex([shapeVertices[i][0], shapeVertices[i][1]]);
                const v2 = UDB.Map.createVertex([shapeVertices[i+1][0], shapeVertices[i+1][1]]);
                
                // Create linedef without sector (decoration line)
                const ld = UDB.Map.drawLines([
                    [shapeVertices[i][0], shapeVertices[i][1]],
                    [shapeVertices[i+1][0], shapeVertices[i+1][1]]
                ]);
            }}
            continue;
        }}
        
        // Closed shape - prepare vertices for drawLines
        if (shapeVertices.length < 3) {{
            continue;
        }}
        
        const drawData = [];
        for (const [x, y] of shapeVertices) {{
            drawData.push([x, y]);
        }}
        
        // Close the path by adding first vertex at end if not already closed
        const first = shapeVertices[0];
        const last = shapeVertices[shapeVertices.length - 1];
        if (first[0] !== last[0] || first[1] !== last[1]) {{
            drawData.push([first[0], first[1]]);
        }}
        
        // Draw the shape
        const success = UDB.Map.drawLines(drawData);
        
        if (!success) {{
            UDB.showMessage('Failed to draw shape: ' + shape.name);
            continue;
        }}
    }}
    
    // Get all marked linedefs and sidedefs (created by drawLines)
    const markedLinedefs = UDB.Map.getMarkedLinedefs(true);
    const markedSectors = UDB.Map.getMarkedSectors(true);
    
    // Apply textures and properties to new geometry
    for (const linedef of markedLinedefs) {{
        // Use applySidedFlags() to automatically set blocking and two-sided flags
        linedef.applySidedFlags();
        
        // NO WALL TEXTURES - let user assign manually in UDB
        // This allows for proper handling of inner/outer sectors
    }}
    
    for (const sector of markedSectors) {{
        sector.floorHeight = floorHeight;
        sector.ceilingHeight = ceilingHeight;
        sector.floorTexture = floorTex;
        sector.ceilingTexture = ceilingTex;
        sector.lightLevel = lightLevel;
    }}
    
    UDB.showMessage('Import complete!\\n\\n' +
        'Linedefs: ' + markedLinedefs.length + '\\n' +
        'Sectors: ' + markedSectors.length + '\\n' +
        'Shapes: ' + shapes.length + '\\n\\n' +
        'Remember to:\\n' +
        '- Add a player start (Thing type 1)\\n' +
        '- Build nodes (F9 or F5)\\n' +
        '- Test your map!');
}}

// Run the import
importGeometry();
'''
        
        with open(output_path, 'w') as f:
            f.write(script_content)
        
        print(f"\n✓ UDB script written: {output_path}")
        print(f"  {len(self.shapes)} shapes embedded in script")
        print(f"  Script name: svg2UDB - {script_name}")
        print(f"\nTo use:")
        print(f"  1. Copy to UDB's Scripts folder")
        print(f"  2. In UDB: Tools → Run Script → svg2UDB - {script_name}")
        print(f"  3. Configure options and click OK")
        print(f"\nNote: 'Curve resolution' in UDB only affects circles/ellipses.")
        print(f"      Bézier curves use --curve-segments at Python conversion time.")

def main():
    parser = argparse.ArgumentParser(
        description='Convert SVG to UDB script with embedded geometry data',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  py svg2udb.py mymap.svg output
  py svg2udb.py -d "C:\\UDB\\Scripts" mymap.svg output
  py svg2udb.py mymap.svg output -d "C:\\UDB\\Scripts"
  py svg2udb.py --absolute mymap.svg output  (use absolute coordinates)
  
The -d parameter can be placed anywhere in the command.
Output filename will automatically have .js appended.
Centering is ON by default (Affinity center -> Doom 0,0).
Use --absolute to disable centering.
        '''
    )
    
    parser.add_argument('input', help='Input SVG file')
    parser.add_argument('output', help='Output script name (without .js extension)')
    parser.add_argument('-d', '--directory', 
                        help='Directory to save the script (default: current directory)',
                        default='.')
    parser.add_argument('--absolute', action='store_true',
                        help='Use absolute SVG coordinates (disable auto-centering)')
    parser.add_argument('--curve-segments', type=int, default=2048,
                        help='Initial curve sampling resolution (default: 2048). High values recommended since grid snapping removes duplicates.')
    parser.add_argument('--simplify', type=float, default=1.5,
                        help='Curve simplification tolerance (default: 1.5). Lower = more accurate but more vertices. 0 = no simplification.')
    
    args = parser.parse_args()
    
    # Center by default unless --absolute is specified
    args.center = not args.absolute
    
    # Build output path with svg2UDB prefix
    output_base = f"svg2UDB - {args.output}"
    output_filename = output_base if output_base.endswith('.js') else output_base + '.js'
    output_path = os.path.join(args.directory, output_filename)
    
    # Extract script name from output filename (without .js)
    script_name = args.output
    
    # Create directory if it doesn't exist
    os.makedirs(args.directory, exist_ok=True)
    
    print("=" * 60)
    print("SVG to UDB Script Converter")
    print("=" * 60)
    print(f"Input:       {args.input}")
    print(f"Output:      {output_path}")
    print(f"Script name: svg2UDB - {script_name}")
    if args.absolute:
        print(f"Centering:   NO (using absolute SVG coordinates)")
    else:
        print(f"Centering:   YES (Affinity center -> Doom 0,0) [default]")
    if args.directory != '.':
        print(f"Directory:   {args.directory}")
    print()
    
    try:
        converter = SVGToJSON(args.input, curve_segments=args.curve_segments, simplify_tolerance=args.simplify)
        converter.parse_svg()
        
        # Apply centering offset if requested
        if args.center:
            # Affinity center is at (2048, 2048) for 4096x4096 document
            center_x = converter.document_height / 2
            center_y = converter.document_height / 2
            
            print(f"Applying center offset: -{center_x}, -{center_y}")
            
            for shape in converter.shapes:
                if 'vertices' in shape:
                    # Shape with pre-calculated vertices
                    for vertex in shape['vertices']:
                        vertex[0] -= int(center_x)
                        vertex[1] -= int(center_y)
                elif shape['type'] in ['circle', 'ellipse']:
                    # Parametric shape - offset center
                    shape['cx'] -= int(center_x)
                    shape['cy'] -= int(center_y)
        
        converter.write_udb_script(output_path, script_name)
        
        print("\n" + "=" * 60)
        print("Conversion complete!")
        print(f"Script location: {output_path}")
        print("Run it in UDB: Tools → Run Script")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n✗ Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    main()