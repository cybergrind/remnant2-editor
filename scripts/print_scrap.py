#!/usr/bin/env python3
"""
Print material counts (Scrap, Corrupted Shards) from a Remnant 2 save file.

Usage: uv run python scripts/print_scrap.py
"""

from editor.compression import decompress_save
from editor.const import MATERIAL_CORRUPTED_SHARD, MATERIAL_SCRAPS, PROFILE_PATH
from editor.log import log
from editor.materials import find_material_quantity


def find_scrap_quantity(data: bytes) -> int | None:
    """Find scrap (Material_Scraps) quantity."""
    return find_material_quantity(data, MATERIAL_SCRAPS)


def find_corrupted_shard_quantity(data: bytes) -> int | None:
    """Find corrupted shard (Material_CorruptedShard) quantity."""
    return find_material_quantity(data, MATERIAL_CORRUPTED_SHARD)


def main() -> None:
    log.info(f'Reading save file: {PROFILE_PATH}')

    if not PROFILE_PATH.exists():
        log.error(f'Save file not found: {PROFILE_PATH}')
        return

    # Read and decompress
    compressed_data = PROFILE_PATH.read_bytes()
    log.info(f'Compressed size: {len(compressed_data)} bytes')

    decompressed_data = decompress_save(compressed_data)
    log.info(f'Decompressed size: {len(decompressed_data)} bytes')

    # Find material quantities
    scrap_count = find_scrap_quantity(decompressed_data)
    shard_count = find_corrupted_shard_quantity(decompressed_data)

    if scrap_count is not None:
        log.info(f'Scrap count: {scrap_count}')
    else:
        log.warning('Could not find scrap count in save file')

    if shard_count is not None:
        log.info(f'Corrupted Shard count: {shard_count}')
    else:
        log.warning('Could not find corrupted shard count in save file')


if __name__ == '__main__':
    main()
