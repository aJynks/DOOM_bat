#!/usr/bin/env python3
"""
build-singlePython-script.py - Build doompal_standalone.py from directory or tarball

Usage:
    python build-singlePython-script.py                      Build from ./doompal/ directory
    python build-singlePython-script.py -tarball             Build from doompal.tar.gz
    python build-singlePython-script.py -tarball custom.tar.gz   Build from custom tarball
"""

import sys
import tarfile
import tempfile
import shutil
from pathlib import Path


def clean_module(filepath):
    """Extract module code without docstrings or imports"""
    with open(filepath) as f:
        content = f.read()
    
    # Remove first docstring if it exists at start of file
    if content.lstrip().startswith('"""'):
        first_quote = content.find('"""')
        second_quote = content.find('"""', first_quote + 3)
        if second_quote > 0:
            content = content[second_quote + 3:]
    
    # Now remove import lines
    lines = []
    in_multiline_import = False
    
    for line in content.split('\n'):
        s = line.strip()
        
        # Start of import
        if s.startswith('import ') or s.startswith('from '):
            if '(' in line and ')' not in line:
                in_multiline_import = True
            continue
        
        # Inside multiline import
        if in_multiline_import:
            if ')' in line:
                in_multiline_import = False
            continue
        
        lines.append(line)
    
    return '\n'.join(lines)


def build_from_directory(doompal_dir, output_path):
    """Build standalone script from doompal directory"""
    
    print(f"Building standalone from directory: {doompal_dir}")
    
    if not doompal_dir.exists():
        print(f"ERROR: Directory not found: {doompal_dir}")
        return False
    
    # Ensure build directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Start building output
    output = []
    
    # Header with dependency check
    print("  Adding header and dependency check...")
    output.append('''#!/usr/bin/env python3
"""doompal - Doom palette and colormap tool (Standalone Version)"""
import sys

def check_dependencies():
    """Check if required packages are installed"""
    missing = []
    
    try:
        import PIL
    except ImportError:
        missing.append("Pillow")
    
    try:
        import numpy
    except ImportError:
        missing.append("numpy")
    
    if missing:
        print("ERROR: Missing required dependencies!", file=sys.stderr)
        print("", file=sys.stderr)
        print("Missing packages:", ", ".join(missing), file=sys.stderr)
        print("", file=sys.stderr)
        print("To install, run:", file=sys.stderr)
        print(f"  pip install {' '.join(missing)}", file=sys.stderr)
        print("", file=sys.stderr)
        print("Or install all dependencies:", file=sys.stderr)
        print("  pip install Pillow numpy", file=sys.stderr)
        sys.exit(1)

check_dependencies()

import os
import struct
from pathlib import Path
from PIL import Image
import numpy as np

__version__ = "1.0.0"

''')
    
    # Add modules
    print("  Adding modules...")
    modules = ['utils.py', 'palette.py', 'colormap.py', 'hald.py', 'cube.py', 'wad.py']
    
    for module_name in modules:
        output.append(f'\n# {"="*76}\n')
        output.append(f'# MODULE: {module_name}\n')
        output.append(f'# {"="*76}\n\n')
        output.append(clean_module(doompal_dir / 'doompal' / module_name))
    
    # Add help function
    print("  Adding help function...")
    with open(doompal_dir / 'doompal' / 'cli.py') as f:
        cli_content = f.read()
        help_start = cli_content.find('def print_compact_help():')
        help_end = cli_content.find('\n\ndef ', help_start + 1)
        
        output.append(f'\n# {"="*76}\n')
        output.append('# HELP FUNCTION\n')
        output.append(f'# {"="*76}\n\n')
        output.append(cli_content[help_start:help_end])
    
    # Add command functions
    print("  Adding commands...")
    with open(doompal_dir / 'doompal.py') as f:
        main_content = f.read()
        cmd_start = main_content.find('def cmd_cube(')
        cmd_end = main_content.find('\ndef main():')
        commands = main_content[cmd_start:cmd_end]
        
        output.append(f'\n# {"="*76}\n')
        output.append('# COMMAND FUNCTIONS\n')
        output.append(f'# {"="*76}\n\n')
        
        # Remove import statements from commands
        for line in commands.split('\n'):
            if line.strip().startswith(('import ', 'from ')):
                continue
            output.append(line + '\n')
    
    # Add main function
    print("  Adding main...")
    output.append(f'\n# {"="*76}\n')
    output.append('# MAIN ENTRY POINT\n')
    output.append(f'# {"="*76}\n\n')
    
    output.append('''class Args:
    """Simple argument container"""
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


def main():
    """Main entry point"""
    # Handle help
    if len(sys.argv) < 2 or sys.argv[1] in ['-h', '--help', '-help']:
        print_compact_help()
        return 0
    
    if sys.argv[1] in ['--version', '-v']:
        print(f"doompal version {__version__}")
        return 0
    
    # Determine command
    command = sys.argv[1]
    known_commands = ['cube', 'batch', 'playpal', 'colormap', 'colourmap', 
                      'blank', 'slade', 'extract', 'split']
    
    if command not in known_commands:
        # Auto-batch mode
        command = 'batch'
        input_filename = Path(sys.argv[1]).name.rsplit(".", 1)[0]
        cmd_args = [sys.argv[1], input_filename] + sys.argv[2:]
    else:
        # Filter out flags (args starting with -)
        cmd_args = [arg for arg in sys.argv[2:] if not arg.startswith('-')]
    
    # Build args object
    args = Args(
        input=Path(cmd_args[0]) if len(cmd_args) > 0 else None,
        output=Path(cmd_args[1]) if len(cmd_args) > 1 else None,
        slade='--slade' in sys.argv or '-slade' in sys.argv,
        blank='--blank' in sys.argv or '-blank' in sys.argv,
        all='--all' in sys.argv or '-all' in sys.argv,
        playpal='--playpal' in sys.argv or '-playpal' in sys.argv,
        boom='--boom' in sys.argv or '-boom' in sys.argv,
        boom_list='--boomlist' in sys.argv or '-boomlist' in sys.argv,
        cell=8
    )
    
    # Extract --cell value if present
    for i, arg in enumerate(sys.argv):
        if arg == '--cell' and i+1 < len(sys.argv):
            try:
                args.cell = int(sys.argv[i+1])
            except ValueError:
                pass
    
    # Route to command handler
    try:
        if command == 'cube':
            return cmd_cube(args)
        elif command == 'batch':
            return cmd_batch(args)
        elif command == 'playpal':
            return cmd_playpal(args)
        elif command in ['colormap', 'colourmap']:
            return cmd_colormap(args)
        elif command == 'blank':
            return cmd_blank(args)
        elif command == 'slade':
            return cmd_slade(args)
        elif command == 'extract':
            return cmd_extract(args)
        elif command == 'split':
            return cmd_split(args)
        else:
            print(f"ERROR: Unknown command: {command}", file=sys.stderr)
            return 1
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
''')
    
    # Write output
    final_content = ''.join(output)
    
    print(f"  Writing {output_path}...")
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(final_content)
    
    print(f"\n✓ Built standalone: {len(final_content)} characters, {final_content.count(chr(10))+1} lines")
    
    # Validate syntax
    import ast
    try:
        ast.parse(final_content)
        print("✓ Syntax valid")
        return True
    except SyntaxError as e:
        print(f"✗ Syntax error at line {e.lineno}: {e.msg}")
        return False


def build_from_tarball(tarball_path, output_path):
    """Build standalone script from tarball"""
    
    print(f"Building standalone from tarball: {tarball_path}")
    
    if not tarball_path.exists():
        print(f"ERROR: Tarball not found: {tarball_path}")
        return False
    
    # Create temp directory
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        
        # Extract tarball
        print("  Extracting tarball...")
        with tarfile.open(tarball_path, 'r:gz') as tar:
            tar.extractall(tmpdir)
        
        # Find the doompal directory
        doompal_dir = tmpdir / 'doompal'
        if not doompal_dir.exists():
            print("ERROR: doompal directory not found in tarball!")
            return False
        
        # Build from extracted directory
        return build_from_directory(tmpdir, output_path)


def show_help():
    """Show help message"""
    print("""
========================================
build-singlePython-script.py - Build doompal_standalone.py
========================================

Usage:
  python build-singlePython-script.py                Build from ./doompal/ directory (default)
  python build-singlePython-script.py -tarball       Build from doompal.tar.gz
  python build-singlePython-script.py -tarball <file>  Build from custom tarball
  python build-singlePython-script.py -h             Show this help

Modes:
  Directory mode (default)
    - Reads from ./doompal/ directory
    - Faster, no extraction needed
    - Use during development

  Tarball mode
    - Reads from doompal.tar.gz (or custom file)
    - Extracts to temp directory
    - Use for distribution builds

Output:
  ./build/doompal_standalone.py - Single-file Python script

Examples:
  python build-singlePython-script.py                # From ./doompal/
  python build-singlePython-script.py -tarball       # From doompal.tar.gz
  python build-singlePython-script.py -tarball v1.0.tar.gz  # From v1.0.tar.gz
""")


def main():
    """Main entry point"""
    
    output = Path('build/doompal_standalone.py')
    
    # Parse arguments
    if len(sys.argv) > 1:
        if sys.argv[1] in ['-h', '--help', '-help']:
            show_help()
            return 0
        elif sys.argv[1] == '-tarball':
            # Tarball mode
            if len(sys.argv) > 2:
                # Custom tarball filename
                tarball = Path(sys.argv[2])
            else:
                # Default tarball
                tarball = Path('doompal.tar.gz')
            
            if not tarball.exists():
                print(f"ERROR: {tarball} not found!")
                return 1
            
            success = build_from_tarball(tarball, output)
        else:
            print(f"ERROR: Unknown option: {sys.argv[1]}")
            print("Use -h for help")
            return 1
    else:
        # Default: directory mode
        doompal_dir = Path('.')
        
        # Check if doompal directory exists
        if not (doompal_dir / 'doompal').exists():
            print("ERROR: ./doompal/ directory not found!")
            print("\nAre you in the right directory?")
            print("Expected structure:")
            print("  ./doompal/")
            print("  ./doompal.py")
            print("\nOr use: python build-singlePython-script.py -tarball")
            return 1
        
        success = build_from_directory(doompal_dir, output)
    
    if success:
        print(f"\n✓ Success! Created {output}")
        return 0
    else:
        print("\n✗ Build failed!")
        return 1


if __name__ == '__main__':
    sys.exit(main())