import os
from PIL import Image

# Always use the folder this script is in
INPUT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(INPUT_DIR, "stcfn_sizes.txt")


def lump_to_char(name):
    try:
        num = int(name[-3:])
        return chr(num)
    except:
        return "?"


def main():
    files = sorted(
        f for f in os.listdir(INPUT_DIR)
        if f.upper().startswith("STCFN")
    )

    with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
        for f in files:
            path = os.path.join(INPUT_DIR, f)

            try:
                with Image.open(path) as img:
                    width, height = img.size
            except:
                continue  # skip non-images

            char = lump_to_char(f)

            out.write(f"{f} {char} {width}x{height}\n")

    print(f"Done. Output: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()