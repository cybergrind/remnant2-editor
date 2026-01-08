"""
Test scrap count reading from save files.

Uses a copy of an actual save file as a fixture.
"""

from scripts.print_scrap import find_scrap_quantity


def test_find_scrap_quantity(profile_data: bytes) -> None:
    """Test that we can find the correct scrap count."""
    scrap_count = find_scrap_quantity(profile_data)

    assert scrap_count is not None
    # Expected value from the actual save file at time of test creation
    assert scrap_count == 76073
