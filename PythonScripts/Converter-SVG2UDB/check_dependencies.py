#!/usr/bin/env python3
"""
Dependency checker for svg2udb.py
Run this to verify all required packages are installed
"""

import sys

print("Checking Python dependencies for svg2udb.py...")
print("=" * 60)

# All modules used by svg2udb.py
required_modules = {
    'sys': 'Core Python',
    'json': 'Core Python', 
    'os': 'Core Python',
    'argparse': 'Core Python',
    'math': 'Core Python',
    're': 'Core Python',
    'xml.etree.ElementTree': 'Core Python',
    'typing': 'Core Python (3.5+)'
}

all_ok = True

for module, source in required_modules.items():
    try:
        # Import the module
        module_base = module.split('.')[0]
        __import__(module_base)
        print(f"✓ {module:30} ({source})")
    except ImportError:
        print(f"✗ {module:30} MISSING!")
        all_ok = False

print("=" * 60)

if all_ok:
    print("\n✓ ALL DEPENDENCIES INSTALLED!")
    print("\nYou can run svg2udb.py without issues.")
    print("\nExample usage:")
    print('  py svg2udb.py --center yourfile.svg output')
else:
    print("\n✗ SOME DEPENDENCIES MISSING")
    print("\nYou're using an outdated Python version.")
    print("Please upgrade to Python 3.5 or higher.")

sys.exit(0 if all_ok else 1)