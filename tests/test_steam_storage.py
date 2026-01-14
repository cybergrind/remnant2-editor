"""Tests for Steam storage discovery module."""

import pytest

from editor.steam_storage import (
    GameInfo,
    SteamLibrary,
    _normalize_name,
    get_steam_user_id,
    parse_vdf,
)
from pathlib import Path


class TestParseVdf:
    """Tests for VDF parser."""

    def test_simple_key_value(self):
        content = '"key"\t\t"value"'
        result = parse_vdf(content)
        assert result == {"key": "value"}

    def test_nested_structure(self):
        content = '''
"root"
{
    "child"     "value"
}
'''
        result = parse_vdf(content)
        assert result == {"root": {"child": "value"}}

    def test_multiple_keys(self):
        content = '''
"key1"      "value1"
"key2"      "value2"
'''
        result = parse_vdf(content)
        assert result == {"key1": "value1", "key2": "value2"}

    def test_deeply_nested(self):
        content = '''
"level1"
{
    "level2"
    {
        "level3"    "deep_value"
    }
}
'''
        result = parse_vdf(content)
        assert result == {"level1": {"level2": {"level3": "deep_value"}}}

    def test_libraryfolders_structure(self):
        """Test parsing a realistic libraryfolders.vdf structure."""
        content = '''
"libraryfolders"
{
    "0"
    {
        "path"      "/home/user/.local/share/Steam"
        "contentid"     "1234567890"
        "totalsize"     "0"
        "apps"
        {
            "228980"        "0"
            "1282100"       "92793797879"
        }
    }
}
'''
        result = parse_vdf(content)
        assert "libraryfolders" in result
        assert "0" in result["libraryfolders"]
        lib = result["libraryfolders"]["0"]
        assert lib["path"] == "/home/user/.local/share/Steam"
        assert lib["contentid"] == "1234567890"
        assert lib["apps"]["1282100"] == "92793797879"

    def test_appmanifest_structure(self):
        """Test parsing a realistic appmanifest.acf structure."""
        content = '''
"AppState"
{
    "appid"     "1282100"
    "name"      "Remnant II"
    "installdir"        "Remnant2"
    "SizeOnDisk"        "92793797879"
}
'''
        result = parse_vdf(content)
        assert "AppState" in result
        app = result["AppState"]
        assert app["appid"] == "1282100"
        assert app["name"] == "Remnant II"
        assert app["installdir"] == "Remnant2"

    def test_empty_content(self):
        result = parse_vdf("")
        assert result == {}

    def test_empty_value(self):
        content = '"key"       ""'
        result = parse_vdf(content)
        assert result == {"key": ""}


class TestNormalizeName:
    """Tests for name normalization."""

    def test_lowercase(self):
        assert _normalize_name("REMNANT") == "remnant"

    def test_removes_spaces(self):
        assert _normalize_name("Dark Souls") == "darksouls"

    def test_removes_special_chars(self):
        assert _normalize_name("The Witcher 3: Wild Hunt") == "thewitcher3wildhunt"

    def test_keeps_numbers(self):
        assert _normalize_name("Fallout 4") == "fallout4"

    def test_roman_numerals_preserved(self):
        # Roman numerals are NOT converted (by design)
        assert _normalize_name("Remnant II") == "remnantii"
        assert _normalize_name("Civilization VI") == "civilizationvi"
        assert _normalize_name("Final Fantasy VII") == "finalfantasyvii"

    def test_words_with_roman_substrings_unchanged(self):
        # Words containing roman numeral letters should not be mangled
        assert _normalize_name("Vixens") == "vixens"
        assert _normalize_name("Divinity") == "divinity"
        assert _normalize_name("Survive") == "survive"

    def test_empty_string(self):
        assert _normalize_name("") == ""

    def test_only_special_chars(self):
        assert _normalize_name("!@#$%") == ""


class TestSteamLibrary:
    """Tests for SteamLibrary dataclass."""

    def test_steamapps_path(self):
        lib = SteamLibrary(
            path=Path("/home/user/SteamLibrary"),
            content_id="123",
            total_size=1000,
        )
        assert lib.steamapps_path == Path("/home/user/SteamLibrary/steamapps")

    def test_compatdata_path(self):
        lib = SteamLibrary(
            path=Path("/home/user/SteamLibrary"),
            content_id="123",
            total_size=1000,
        )
        assert lib.compatdata_path == Path("/home/user/SteamLibrary/steamapps/compatdata")


class TestGameInfo:
    """Tests for GameInfo class."""

    @pytest.fixture
    def library(self):
        return SteamLibrary(
            path=Path("/home/user/SteamLibrary"),
            content_id="123",
            total_size=1000,
        )

    @pytest.fixture
    def game(self, library):
        return GameInfo(
            app_id=1282100,
            name="Remnant II",
            install_dir="Remnant2",
            size_on_disk=92793797879,
            library=library,
        )

    def test_game_path(self, game):
        expected = Path("/home/user/SteamLibrary/steamapps/common/Remnant2")
        assert game.game_path == expected

    def test_compatdata_path(self, game):
        expected = Path("/home/user/SteamLibrary/steamapps/compatdata/1282100")
        assert game.compatdata_path == expected

    def test_truediv_operator_string(self, game):
        result = game / "pfx/drive_c"
        expected = Path("/home/user/SteamLibrary/steamapps/compatdata/1282100/pfx/drive_c")
        assert result == expected

    def test_truediv_operator_path(self, game):
        result = game / Path("pfx/drive_c")
        expected = Path("/home/user/SteamLibrary/steamapps/compatdata/1282100/pfx/drive_c")
        assert result == expected

    def test_truediv_operator_long_path(self, game):
        result = game / "pfx/drive_c/users/steamuser/Saved Games/Remnant2"
        expected = Path(
            "/home/user/SteamLibrary/steamapps/compatdata/1282100"
            "/pfx/drive_c/users/steamuser/Saved Games/Remnant2"
        )
        assert result == expected

    def test_repr(self, game):
        repr_str = repr(game)
        assert "1282100" in repr_str
        assert "Remnant II" in repr_str


class TestGetSteamUserId:
    """Tests for get_steam_user_id function."""

    def test_returns_numeric_string(self):
        # On a system with Steam installed, should return a numeric user ID
        user_id = get_steam_user_id()
        assert user_id.isdigit()
