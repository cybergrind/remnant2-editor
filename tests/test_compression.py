"""
Test compression and CRC32 functions.
"""

import struct

from editor.compression import calculate_crc32, update_crc32, verify_crc32


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
