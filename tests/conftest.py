"""
Pytest configuration and shared fixtures.
"""

from pathlib import Path

import pytest

from editor.compression import decompress_save


FIXTURES_DIR = Path(__file__).parent / 'fixtures'


@pytest.fixture()
def fixtures_dir() -> Path:
    """Return the path to the test fixtures directory."""
    return FIXTURES_DIR


@pytest.fixture()
def profile_data(fixtures_dir: Path) -> bytes:
    """Load and decompress the profile.sav fixture."""
    profile_path = fixtures_dir / 'profile.sav'
    if not profile_path.exists():
        pytest.skip('profile.sav fixture not found')

    compressed = profile_path.read_bytes()
    return decompress_save(compressed)
