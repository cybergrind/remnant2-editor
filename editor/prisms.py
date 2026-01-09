"""
Prism data extraction for Remnant 2 save files.

This module provides functions to find and extract prism information
including segments, levels, and pending experience from decompressed save data.
"""

import struct
from dataclasses import dataclass

from editor.compression import decompress_save
from editor.const import PROFILE_PATH
from editor.log import log
from editor.materials import find_names_table


@dataclass
class PrismSegment:
    """A single prism segment with its name and level."""

    name: str
    level: int


@dataclass
class PrismData:
    """Complete prism data including segments and experience."""

    segments: list[PrismSegment]
    current_seed: int
    pending_experience: float

    @property
    def total_level(self) -> int:
        """Calculate total level as sum of all segment levels."""
        return sum(seg.level for seg in self.segments)


def find_prism_data(data: bytes) -> list[PrismData]:
    """
    Find all prism data in the save file.

    Args:
        data: Decompressed save data

    Returns:
        List of PrismData objects, one per prism found.
    """
    result = find_names_table(data)
    if result is None:
        log.warning('Could not find names table')
        return []

    names_start, names = result
    name_to_idx = {name: i for i, name in enumerate(names)}

    # Required property indices
    current_segments_idx = name_to_idx.get('CurrentSegments')
    struct_prop_idx = name_to_idx.get('StructProperty')
    current_seed_idx = name_to_idx.get('CurrentSeed')
    int_prop_idx = name_to_idx.get('IntProperty')
    pending_exp_idx = name_to_idx.get('PendingExperience')
    float_prop_idx = name_to_idx.get('FloatProperty')
    row_name_idx = name_to_idx.get('RowName')
    name_prop_idx = name_to_idx.get('NameProperty')
    level_idx = name_to_idx.get('Level')

    if None in (
        current_segments_idx,
        struct_prop_idx,
        current_seed_idx,
        int_prop_idx,
        pending_exp_idx,
        float_prop_idx,
        row_name_idx,
        name_prop_idx,
        level_idx,
    ):
        log.warning('Missing required property names in names table')
        return []

    prisms = []

    # Find all CurrentSeed properties (marks start of each prism's data)
    seed_pattern = struct.pack('<HH', current_seed_idx, int_prop_idx)
    pos = 0

    while pos < names_start:
        pos = data.find(seed_pattern, pos, names_start)
        if pos == -1:
            break

        # Verify it's a valid IntProperty
        size = struct.unpack_from('<I', data, pos + 4)[0]
        idx = struct.unpack_from('<I', data, pos + 8)[0]
        noraw = data[pos + 12]

        if size != 4 or idx != 0 or noraw != 0:
            pos += 1
            continue

        current_seed = struct.unpack_from('<i', data, pos + 13)[0]
        log.debug(f'Found CurrentSeed at {pos}: {current_seed}')

        # Find PendingExperience nearby (should be right after CurrentSeed)
        exp_pattern = struct.pack('<HH', pending_exp_idx, float_prop_idx)
        exp_pos = data.find(exp_pattern, pos, pos + 50)

        pending_exp = 0.0
        if exp_pos != -1:
            exp_size = struct.unpack_from('<I', data, exp_pos + 4)[0]
            exp_idx = struct.unpack_from('<I', data, exp_pos + 8)[0]
            exp_noraw = data[exp_pos + 12]

            if exp_size == 4 and exp_idx == 0 and exp_noraw == 0:
                pending_exp = struct.unpack_from('<f', data, exp_pos + 13)[0]
                log.debug(f'Found PendingExperience at {exp_pos}: {pending_exp}')

        # Find CurrentSegments before CurrentSeed
        segments_pattern = struct.pack('<HH', current_segments_idx, struct_prop_idx)
        search_start = max(0, pos - 2000)
        seg_pos = data.rfind(segments_pattern, search_start, pos)

        segments = []
        if seg_pos != -1:
            log.debug(f'Found CurrentSegments at {seg_pos}')
            segments = _parse_segments(data, seg_pos, names, name_to_idx)

        prisms.append(
            PrismData(
                segments=segments,
                current_seed=current_seed,
                pending_experience=pending_exp,
            )
        )

        pos += 1

    return prisms


def _parse_segments(data: bytes, seg_pos: int, names: list[str], name_to_idx: dict[str, int]) -> list[PrismSegment]:
    """
    Parse the CurrentSegments StructProperty.

    The segments are stored as an array of structs, each containing:
    - RowName (NameProperty): segment name like "CriticalDamage"
    - Level (IntProperty): segment level value
    - None terminator (2 bytes: 00 00)

    Args:
        data: Decompressed save data
        seg_pos: Position of CurrentSegments property
        names: Names table
        name_to_idx: Name to index mapping

    Returns:
        List of PrismSegment objects
    """
    segments = []

    # Read property header
    size = struct.unpack_from('<I', data, seg_pos + 4)[0]

    # Get required indices
    row_name_idx = name_to_idx['RowName']
    name_prop_idx = name_to_idx['NameProperty']
    level_idx = name_to_idx['Level']
    int_prop_idx = name_to_idx['IntProperty']

    # Skip header (12 bytes) + noraw (1) + struct type FName (2) + GUID padding (16)
    # Total: 31 bytes to first segment
    pos = seg_pos + 31
    end_pos = seg_pos + 12 + size

    while pos < end_pos:
        # Check for RowName property
        name_idx = struct.unpack_from('<H', data, pos)[0]
        type_idx = struct.unpack_from('<H', data, pos + 2)[0]

        if name_idx == 0:  # None terminator (2 bytes)
            pos += 2
            continue

        if name_idx != row_name_idx or type_idx != name_prop_idx:
            pos += 1
            continue

        # Parse RowName property
        # Format: [name:2][type:2][size:4][index:4][noraw:1][value:size]
        prop_size = struct.unpack_from('<I', data, pos + 4)[0]
        value_idx = struct.unpack_from('<H', data, pos + 13)[0]

        if value_idx >= len(names):
            pos += 1
            continue

        segment_name = names[value_idx]
        pos += 13 + prop_size  # Move past RowName property

        # Parse Level property
        name_idx = struct.unpack_from('<H', data, pos)[0]
        type_idx = struct.unpack_from('<H', data, pos + 2)[0]

        level = 0
        if name_idx == level_idx and type_idx == int_prop_idx:
            level = struct.unpack_from('<i', data, pos + 13)[0]
            pos += 13 + 4  # Move past Level property

        segments.append(PrismSegment(name=segment_name, level=level))
        log.debug(f'  Segment: {segment_name} = {level}')

    return segments


def main() -> None:
    """Print all prism data from the default save file."""
    log.info(f'Reading save file: {PROFILE_PATH}')

    if not PROFILE_PATH.exists():
        log.error(f'Save file not found: {PROFILE_PATH}')
        return

    # Read and decompress
    compressed_data = PROFILE_PATH.read_bytes()
    decompressed_data = decompress_save(compressed_data)
    log.info(f'Decompressed size: {len(decompressed_data)} bytes')

    # Find all prisms
    prisms = find_prism_data(decompressed_data)

    if not prisms:
        log.warning('No prisms found in save file')
        return

    log.info(f'Found {len(prisms)} prism(s):')

    for i, prism in enumerate(prisms):
        log.info(f'Prism {i + 1}:')
        log.info(f'  Total Level: {prism.total_level}')
        log.info(f'  Pending Experience: {prism.pending_experience:.0f}')
        log.info(f'  Current Seed: {prism.current_seed}')

        if prism.segments:
            log.info(f'  Segments ({len(prism.segments)}):')
            for seg in prism.segments:
                if seg.level > 0:
                    log.info(f'    {seg.name}: {seg.level}')


if __name__ == '__main__':
    main()
