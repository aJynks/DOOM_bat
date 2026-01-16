I've (with help from calude.ai) modified the omgifol python library "drawmaps" script to output the maps with classic doom colours for the linework and on a transparent PNG.... also there is an option to draw each coloured line type on a separate PNG... 

This command will draw all maps, 1024 size and output in layers, remove layers to just output as normal. You will need "pillow" and "omgifol" for it to work... you can install them with : 
pip install omg Pillow


Command Examples
python drawmaps2.py "wadName.wad" "MAP*" 1024 PNG layers
python drawmaps2.py "wadName.wad" "MAP05" 2048 PNG