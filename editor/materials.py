"""
Material quantity finding for Remnant 2 save files.

This module provides functions to find and extract material quantities
from decompressed save data.
"""

import struct

from editor.compression import decompress_save
from editor.const import PROFILE_PATH
from editor.log import log


def find_names_table(data: bytes) -> tuple[int, list[str]] | None:
    """
    Find a nested names table containing "Quantity" and "IntProperty".

    The names table starts with a count (uint32) followed by FStrings.
    We look for the "None" FString pattern which is typically the first entry.
    """
    # Look for "None" FString: [05 00 00 00][N o n e 00]
    none_pattern = struct.pack('<i', 5) + b'None\x00'

    pos = 0
    while True:
        pos = data.find(none_pattern, pos)
        if pos == -1:
            return None

        # The count should be 4 bytes before this
        count_pos = pos - 4
        if count_pos < 0:
            pos += 1
            continue

        count = struct.unpack_from('<I', data, count_pos)[0]

        # Validate count is reasonable (10-500 entries)
        if not (10 < count < 500):
            pos += 1
            continue

        # Try to read the names table
        read_pos = count_pos + 4  # Start after count
        names = []
        valid = True
        quantity_idx = None
        int_prop_idx = None

        for i in range(count):
            if read_pos + 4 > len(data):
                valid = False
                break

            str_len = struct.unpack_from('<i', data, read_pos)[0]
            if str_len <= 0 or str_len > 500:
                valid = False
                break

            read_pos += 4

            if read_pos + str_len > len(data):
                valid = False
                break

            try:
                name = data[read_pos : read_pos + str_len - 1].decode('ascii')
                names.append(name)

                if name == 'Quantity':
                    quantity_idx = i
                elif name == 'IntProperty':
                    int_prop_idx = i

            except UnicodeDecodeError:
                valid = False
                break

            read_pos += str_len

        if valid and quantity_idx is not None and int_prop_idx is not None:
            log.debug(f'Found names table at {count_pos} with {len(names)} entries')
            return count_pos, names

        pos += 1

    return None


def find_all_quantities(data: bytes, names_table_start: int, names: list[str]) -> list[tuple[int, int]]:
    """
    Find all Quantity property values in the save data.

    Returns list of (offset, value) tuples.
    """
    # Get indices
    quantity_idx = names.index('Quantity')
    int_prop_idx = names.index('IntProperty')

    # Build the property pattern
    # Property format: [uint16 name_idx][uint16 type_idx][uint32 size][uint32 index][byte noraw][value]
    prop_pattern = struct.pack('<HH', quantity_idx, int_prop_idx)

    # Search for this pattern BEFORE the names table (objects data comes before)
    search_start = 0
    search_end = names_table_start

    results = []
    pos = search_start

    while pos < search_end:
        pos = data.find(prop_pattern, pos, search_end)
        if pos == -1:
            break

        # Verify IntProperty structure
        if pos + 17 <= len(data):
            size = struct.unpack_from('<I', data, pos + 4)[0]
            idx = struct.unpack_from('<I', data, pos + 8)[0]
            noraw = data[pos + 12]
            value = struct.unpack_from('<i', data, pos + 13)[0]

            # IntProperty should have size=4, index=0, noraw=0
            if size == 4 and idx == 0 and noraw == 0 and value > 0:
                results.append((pos, value))

        pos += 1

    return results


def extract_material_name(path: str) -> str:
    """Extract a readable material name from asset path."""
    # Path like: /Game/World_Base/Items/Materials/Scraps/Material_Scraps.Material_Scraps_C
    if '/' not in path:
        return path

    # Get the last component
    name = path.rsplit('/', 1)[-1]

    # Remove _C suffix and class name duplication
    if '.' in name:
        name = name.split('.')[0]

    # Remove Material_ prefix
    if name.startswith('Material_'):
        name = name[9:]

    return name


def parse_objects_table(data: bytes, objects_table_pos: int) -> dict[int, str]:
    """
    Parse the objects table to get object index -> path mapping.

    Returns dict mapping object index to asset path for materials.
    """
    count = struct.unpack_from('<I', data, objects_table_pos)[0]
    log.debug(f'Parsing {count} objects from table at {objects_table_pos}')

    pos = objects_table_pos + 4
    objects = {}

    for i in range(count):
        if pos >= len(data) - 10:
            break

        was_loaded = data[pos]
        pos += 1

        # For wasLoaded=1 and index=0: use classPath (skip FString)
        # Otherwise: read FString
        if was_loaded == 1 and i == 0:
            path = None
        else:
            str_len = struct.unpack_from('<i', data, pos)[0]
            pos += 4

            if str_len > 0 and str_len < 500:
                try:
                    path = data[pos : pos + str_len - 1].decode('ascii')
                    pos += str_len
                except UnicodeDecodeError:
                    path = None
                    pos += str_len
            elif str_len == 0:
                path = None
            else:
                log.warning(f'Invalid str_len {str_len} at object {i}')
                break

        # For wasLoaded=0, also read FName and OuterId
        if was_loaded == 0:
            name_idx = struct.unpack_from('<H', data, pos)[0]
            pos += 2
            if name_idx & 0x8000:
                pos += 4
            pos += 4  # OuterId

        if path and '/Materials/' in path:
            objects[i] = path

    return objects


def find_objects_table_position(data: bytes) -> int | None:
    """
    Find the start of the objects table in the nested blob.

    The objects table starts with count followed by object entries.
    First object typically has path starting with /Game/Characters/Player.
    """
    # Search for the pattern that indicates objects table start
    pattern = b'/Game/Characters/Player/Base/Character_Master_Player'

    pos = data.find(pattern)
    if pos == -1:
        return None

    # Structure: [count: uint32][wasLoaded: byte][str_len: int32][str data...]
    # str_len is at pos - 4, wasLoaded at pos - 5, count at pos - 9

    # Verify the structure
    str_len = struct.unpack_from('<i', data, pos - 4)[0]
    was_loaded = data[pos - 5]
    count = struct.unpack_from('<I', data, pos - 9)[0]

    log.debug(f'Objects table detection: str_len={str_len}, wasLoaded={was_loaded}, count={count}')

    # Validate
    if str_len > 0 and str_len < 200 and was_loaded in [0, 1] and 500 < count < 2000:
        count_pos = pos - 9
        log.debug(f'Found objects table at {count_pos} with {count} objects')
        return count_pos

    return None


def find_materials(data: bytes) -> dict[str, int]:
    """
    Find all materials and their quantities in the save.

    Args:
        data: Decompressed save data

    Returns:
        Dict mapping material name to quantity.
    """
    result = find_names_table(data)
    if result is None:
        log.warning('Could not find names table')
        return {}

    names_table_start, names = result

    # Find and parse objects table
    objects_table_pos = find_objects_table_position(data)
    if objects_table_pos is None:
        log.warning('Could not find objects table')
        return {}

    material_objects = parse_objects_table(data, objects_table_pos)
    log.debug(f'Found {len(material_objects)} material objects')

    # Get all quantities
    quantities = find_all_quantities(data, names_table_start, names)
    log.debug(f'Found {len(quantities)} quantity properties')

    # Build mapping from object index to quantity
    # The object index appears ~17 bytes before its Quantity property
    materials = {}

    for obj_idx, material_path in material_objects.items():
        name = extract_material_name(material_path)

        # Search for this object index in the property data area
        # Object index is stored as uint32
        obj_bytes = struct.pack('<I', obj_idx)

        # Search in property data area (before objects table)
        search_end = objects_table_pos
        pos = 70000  # Start of nested blob data approximately

        while pos < search_end:
            pos = data.find(obj_bytes, pos, search_end)
            if pos == -1:
                break

            # Check if there's a Quantity property nearby (within ~25 bytes after)
            # The structure is: [ItemBP obj_idx][8 zero bytes][InstanceData obj_idx][8 bytes][Quantity]
            # So distance from ItemBP to Quantity is typically ~17 bytes
            for qty_pos, qty_value in quantities:
                distance = qty_pos - pos
                if 12 < distance < 25:  # Tighter range to avoid false matches
                    log.debug(f'{name}: obj_idx={obj_idx} at {pos}, qty={qty_value} at {qty_pos}')
                    materials[name] = qty_value
                    break
            else:
                pos += 1
                continue
            break  # Found it, stop searching for this material

    return materials


def find_material_quantity(data: bytes, material_name: str) -> int | None:
    """
    Find the quantity of a specific material by its name.

    Args:
        data: Decompressed save data
        material_name: Part of the material path to match (e.g., 'Material_Scraps')

    Returns:
        The quantity value, or None if not found.
    """
    # Find names table
    result = find_names_table(data)
    if result is None:
        return None

    names_table_start, names = result

    # Find objects table
    objects_table_pos = find_objects_table_position(data)
    if objects_table_pos is None:
        return None

    # Parse objects to find the target material
    material_objects = parse_objects_table(data, objects_table_pos)

    # Find the object index for our material
    target_obj_idx = None
    for obj_idx, path in material_objects.items():
        if material_name in path:
            target_obj_idx = obj_idx
            log.debug(f'Found {material_name} at object index {obj_idx}')
            break

    if target_obj_idx is None:
        log.debug(f'Material {material_name} not found in objects table')
        return None

    # Get all quantities
    quantities = find_all_quantities(data, names_table_start, names)
    if not quantities:
        return None

    # Search for this object index in property data and find nearby Quantity
    obj_bytes = struct.pack('<I', target_obj_idx)
    search_end = objects_table_pos
    pos = 70000

    while pos < search_end:
        pos = data.find(obj_bytes, pos, search_end)
        if pos == -1:
            break

        # Check for nearby Quantity (within ~25 bytes after)
        for qty_pos, qty_value in quantities:
            distance = qty_pos - pos
            if 12 < distance < 25:
                log.debug(f'Found quantity {qty_value} for {material_name}')
                return qty_value

        pos += 1

    return None


def main() -> None:
    """Print all materials and quantities from the default save file."""
    log.info(f'Reading save file: {PROFILE_PATH}')

    if not PROFILE_PATH.exists():
        log.error(f'Save file not found: {PROFILE_PATH}')
        return

    # Read and decompress
    compressed_data = PROFILE_PATH.read_bytes()
    log.info(f'Compressed size: {len(compressed_data)} bytes')

    decompressed_data = decompress_save(compressed_data)
    log.info(f'Decompressed size: {len(decompressed_data)} bytes')

    # Find all materials
    materials = find_materials(decompressed_data)

    if not materials:
        log.warning('No materials found in save file')
        return

    log.info(f'Found {len(materials)} materials:')

    # Sort by name and print
    for name in sorted(materials.keys()):
        qty = materials[name]
        log.info(f'  {name}: {qty}')


if __name__ == '__main__':
    main()
