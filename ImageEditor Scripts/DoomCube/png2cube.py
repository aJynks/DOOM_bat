#!/usr/bin/env python3

import sys
import argparse
import numpy as np
from PIL import Image
import os
import logging

logging.basicConfig(level=logging.INFO, format="%(message)s")

def load_image(path):
    try:
        img = Image.open(path).convert("RGB")
        return np.array(img)
    except Exception as e:
        logging.error(f"Failed to load image '{path}': {e}")
        sys.exit(1)

def validate_lut_dimensions(image):
    height, width, _ = image.shape
    total_pixels = width * height
    lut_size = int(round(total_pixels ** (1/3)))
    if lut_size ** 3 != total_pixels:
        logging.error("Image dimensions do not match a valid Hald CLUT. Ensure it's a square LUT (e.g. 512x512 for 64^3).")
        sys.exit(1)
    return lut_size

def generate_cube_lut(modified, lut_size, output_path, title="Generated LUT"):
    modified = modified.reshape(-1, 3).astype(np.float32) / 255.0

    try:
        with open(output_path, "w") as f:
            f.write(f"TITLE \"{title}\"\n")
            f.write(f"LUT_3D_SIZE {lut_size}\n")
            f.write("DOMAIN_MIN 0.0 0.0 0.0\n")
            f.write("DOMAIN_MAX 1.0 1.0 1.0\n")

            for b in range(lut_size):
                for g in range(lut_size):
                    for r in range(lut_size):
                        idx = r + g * lut_size + b * lut_size * lut_size
                        r_out, g_out, b_out = modified[idx]
                        f.write(f"{r_out:.6f} {g_out:.6f} {b_out:.6f}\n")
        logging.info(f"Successfully wrote .CUBE LUT to '{output_path}'")
    except Exception as e:
        logging.error(f"Failed to write LUT file: {e}")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Convert a modified Hald PNG LUT to a .CUBE LUT file.")
    parser.add_argument("modified_png", help="The color-graded Hald PNG file")
    parser.add_argument("output_cube", help="Output .CUBE file path")
    parser.add_argument("--title", default=None, help="Optional LUT title")

    args = parser.parse_args()

    # Load and validate
    modified_img = load_image(args.modified_png)
    lut_size = validate_lut_dimensions(modified_img)

    # Infer title if not given
    title = args.title or os.path.splitext(os.path.basename(args.output_cube))[0]

    # Generate LUT
    generate_cube_lut(modified_img, lut_size, args.output_cube, title)

if __name__ == "__main__":
    main()
