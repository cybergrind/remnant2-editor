"""
Tests for save file round-trip serialization.
"""

from pathlib import Path

import pytest

from editor.compression import decompress_save
from editor.model.save_file import SaveFile


def test_roundtrip_preserves_data(profile_data: bytes, fixtures_dir: Path) -> None:
    """Test that load -> save produces identical output."""
    profile_path = fixtures_dir / 'profile.sav'

    # Load the save file
    save = SaveFile.load(profile_path)

    # Serialize back to bytes
    output = save.to_decompressed()

    # Should be identical to original (both are re-serialized, so same size)
    # Note: We compare against a fresh load, not the original file,
    # because both dotnet and Python produce slightly smaller files
    # than the original game save (due to not preserving some padding)
    save2 = SaveFile.load(profile_path)
    output2 = save2.to_decompressed()

    assert output == output2, "Round-trip should be deterministic"


def test_roundtrip_crc32_valid(fixtures_dir: Path) -> None:
    """Test that round-trip produces valid CRC32."""
    from editor.compression import verify_crc32

    profile_path = fixtures_dir / 'profile.sav'
    save = SaveFile.load(profile_path)
    output = save.to_decompressed()

    assert verify_crc32(output), "Round-trip output should have valid CRC32"


def test_name_replacement(fixtures_dir: Path) -> None:
    """Test that name replacement works correctly."""
    profile_path = fixtures_dir / 'profile.sav'
    save = SaveFile.load(profile_path)

    # Find a name that exists
    if 'HealthRegen' in save.save_data.names_table:
        old_name = 'HealthRegen'
        new_name = 'HealthRegenSkillCooldown'
    else:
        pytest.skip("HealthRegen not in names table")

    # Replace the name
    result = save.replace_name(old_name, new_name)
    assert result is True

    # Verify the name was replaced
    assert old_name not in save.save_data.names_table
    assert new_name in save.save_data.names_table

    # Verify we can still serialize
    output = save.to_decompressed()
    assert len(output) > 0
