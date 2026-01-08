"""
Test compression and CRC32 functions.
"""

import struct
from pathlib import Path

from editor.compression import (
    calculate_crc32,
    compress_save,
    decompress_save,
    update_crc32,
    verify_crc32,
)


def test_verify_crc32_valid(profile_data: bytes) -> None:
    """Test that the fixture file has a valid CRC32."""
    assert verify_crc32(profile_data) is True


def test_calculate_crc32_matches_stored(profile_data: bytes) -> None:
    """Test that calculated CRC32 matches the stored value."""
    stored_crc = struct.unpack_from('<I', profile_data, 0)[0]
    calculated_crc = calculate_crc32(profile_data)

    assert calculated_crc == stored_crc


def test_verify_crc32_invalid(profile_data: bytes) -> None:
    """Test that modified data fails CRC32 verification."""
    # Modify a byte in the data (not in the CRC header)
    modified = bytearray(profile_data)
    modified[100] ^= 0xFF  # Flip all bits at position 100

    assert verify_crc32(modified) is False


def test_update_crc32(profile_data: bytes) -> None:
    """Test that update_crc32 correctly fixes the checksum after modification."""
    modified = bytearray(profile_data)

    # Modify some data
    modified[100] ^= 0xFF

    # CRC should now be invalid
    assert verify_crc32(modified) is False

    # Update the CRC
    update_crc32(modified)

    # CRC should now be valid
    assert verify_crc32(modified) is True


def test_compress_decompress_roundtrip(profile_data: bytes) -> None:
    """Test that compress -> decompress produces the original data."""
    # Compress the decompressed data
    compressed = compress_save(profile_data)

    # Decompress it again
    decompressed = decompress_save(compressed)

    # Should match the original
    assert decompressed == profile_data


def test_compress_decompress_roundtrip_from_file(fixtures_dir: Path) -> None:
    """Test full roundtrip: file -> decompress -> compress -> decompress."""
    profile_path = fixtures_dir / 'profile.sav'
    if not profile_path.exists():
        import pytest

        pytest.skip('profile.sav fixture not found')

    # Read original compressed file
    original_compressed = profile_path.read_bytes()

    # Decompress
    decompressed = decompress_save(original_compressed)

    # Compress again
    recompressed = compress_save(decompressed)

    # Decompress the recompressed data
    decompressed_again = decompress_save(recompressed)

    # The decompressed data should match
    assert decompressed_again == decompressed


def test_compress_modified_data(profile_data: bytes) -> None:
    """Test that modified data can be compressed and decompressed correctly."""
    # Modify the data
    modified = bytearray(profile_data)
    modified[100] ^= 0xFF

    # Update CRC
    update_crc32(modified)
    assert verify_crc32(modified) is True

    # Compress
    compressed = compress_save(bytes(modified))

    # Decompress
    decompressed = decompress_save(compressed)

    # Should match the modified data
    assert decompressed == bytes(modified)
