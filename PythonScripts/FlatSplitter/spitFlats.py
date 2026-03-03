#!/usr/bin/env python3
"""
Image splitter - cuts images into equal-sized tiles
"""

import sys
import os
from pathlib import Path

# Dependency check
try:
    from PIL import Image
except ImportError:
    print("Missing dependency. Install with: pip install Pillow")
    sys.exit(1)

def parse_arguments():
    """Parse command line arguments"""
    args = {
        'size': (64, 64)
    }
    
    i = 1
    while i < len(sys.argv):
        arg = sys.argv[i]
        
        if arg in ['-size', '--size']:
            if i + 1 >= len(sys.argv):
                print(f"Error: {arg} requires a value")
                sys.exit(1)
            
            size_str = sys.argv[i + 1]
            try:
                width, height = size_str.lower().split('x')
                args['size'] = (int(width), int(height))
            except (ValueError, AttributeError):
                print(f"Error: Invalid size format '{size_str}'. Use format: 32x32")
                sys.exit(1)
            i += 2
        else:
            i += 1
    
    return args

def get_image_files():
    """Get all image files in current directory"""
    image_extensions = {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.tiff', '.tif', '.webp'}
    current_dir = Path('.')
    
    image_files = []
    for file in current_dir.iterdir():
        if file.is_file() and file.suffix.lower() in image_extensions:
            image_files.append(file)
    
    return sorted(image_files)

def validate_all_filenames(image_files, tile_width, tile_height):
    """Pre-validate all filenames before processing any images"""
    filename_errors = []
    dimension_errors = []
    read_errors = []
    
    for image_path in image_files:
        try:
            img = Image.open(image_path)
            img_width, img_height = img.size
            img.close()
            
            # Check if image can be evenly divided
            if img_width % tile_width != 0 or img_height % tile_height != 0:
                dimension_errors.append(image_path.name)
                continue
            
            # Calculate tile counts
            tiles_x = img_width // tile_width
            tiles_y = img_height // tile_height
            total_tiles = tiles_x * tiles_y
            
            # Get base filename
            base_name = image_path.stem
            
            # Check each potential filename
            for i in range(1, total_tiles + 1):
                new_name = f"{base_name}{i}"
                if len(new_name) != 8:
                    filename_errors.append(image_path.name)
                    break
        
        except Exception as e:
            read_errors.append(image_path.name)
    
    return filename_errors, dimension_errors, read_errors

def split_image(image_path, tile_width, tile_height):
    """Split an image into tiles of specified size"""
    
    # Load image
    img = Image.open(image_path)
    img_width, img_height = img.size
    
    # Calculate tile counts
    tiles_x = img_width // tile_width
    tiles_y = img_height // tile_height
    
    # Get base filename without extension
    path = Path(image_path)
    base_name = path.stem
    extension = path.suffix
    
    # Create output directory
    output_dir = path.parent / "split"
    output_dir.mkdir(exist_ok=True)
    
    # Split image into tiles
    tile_num = 1
    for y in range(tiles_y):
        for x in range(tiles_x):
            # Calculate tile coordinates
            left = x * tile_width
            top = y * tile_height
            right = left + tile_width
            bottom = top + tile_height
            
            # Crop tile
            tile = img.crop((left, top, right, bottom))
            
            # Generate output filename
            output_name = f"{base_name}{tile_num}{extension}"
            output_path = output_dir / output_name
            
            # Save tile (preserving transparency)
            tile.save(output_path)
            print(f"  Created: {output_path}")
            
            tile_num += 1
    
    return True

def main():
    args = parse_arguments()
    
    # Scan current directory for image files
    image_files = get_image_files()
    
    if not image_files:
        print("Error: No image files found in current directory")
        sys.exit(1)
    
    tile_width, tile_height = args['size']
    print(f"Found {len(image_files)} image(s) in current directory")
    print(f"Tile size: {tile_width}x{tile_height}")
    print(f"\nValidating all files before processing...\n")
    
    # Pre-validate all files
    filename_errors, dimension_errors, read_errors = validate_all_filenames(image_files, tile_width, tile_height)
    
    has_errors = filename_errors or dimension_errors or read_errors
    
    if has_errors:
        print("=" * 60)
        print("VALIDATION FAILED - Cannot proceed")
        print("=" * 60)
        
        if filename_errors:
            print("Problem: Generated filenames not exactly 8 characters")
            for filename in filename_errors:
                print(f"* {filename}")
            print()
        
        if dimension_errors:
            print(f"Problem: Image cannot be evenly divided by {tile_width}x{tile_height}")
            for filename in dimension_errors:
                print(f"* {filename}")
            print()
        
        if read_errors:
            print("Problem: Could not open/read image")
            for filename in read_errors:
                print(f"* {filename}")
            print()
        
        sys.exit(1)
    
    print("✓ All validations passed!\n")
    print("=" * 60)
    print("Processing images...")
    print("=" * 60)
    print()
    
    # Process all images
    success_count = 0
    
    for image_path in image_files:
        print(f"Processing: {image_path}")
        split_image(image_path, tile_width, tile_height)
        success_count += 1
        print()
    
    print("=" * 60)
    print(f"Complete: {success_count} image(s) processed successfully")
    print("=" * 60)

if __name__ == "__main__":
    main()