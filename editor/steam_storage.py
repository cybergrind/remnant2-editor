"""
Steam storage discovery module for Linux.

Provides APIs to discover Steam library locations and installed games.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


def parse_vdf(content: str) -> dict:
    """Parse Valve Data Format (VDF) content into a dictionary.

    VDF is a simple key-value format used by Steam:
        "key"   "value"
        "key"
        {
            "nested"    "value"
        }
    """
    result = {}
    stack = [result]
    lines = content.split('\n')

    # Pattern for key-value pairs: "key"   "value"
    kv_pattern = re.compile(r'^\s*"([^"]+)"\s+"([^"]*)"')
    # Pattern for key only (start of block): "key"
    key_pattern = re.compile(r'^\s*"([^"]+)"\s*$')

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Try key-value pair first
        kv_match = kv_pattern.match(line)
        if kv_match:
            key, value = kv_match.groups()
            stack[-1][key] = value
            continue

        # Try key only (start of nested block)
        key_match = key_pattern.match(line)
        if key_match:
            key = key_match.group(1)
            new_dict = {}
            stack[-1][key] = new_dict
            stack.append(new_dict)
            continue

        # Opening brace (already handled by key detection, but may appear on next line)
        if line == '{':
            continue

        # Closing brace
        if line == '}':
            if len(stack) > 1:
                stack.pop()

    return result


def _normalize_name(name: str) -> str:
    """Normalize name for fuzzy matching: lowercase, keep only alphanumerics.

    Examples:
        'Remnant II' -> 'remnantii'
        'Remnant 2'  -> 'remnant2'
        'The Witcher 3: Wild Hunt' -> 'thewitcher3wildhunt'
    """
    return re.sub(r'[^a-z0-9]', '', name.lower())


@dataclass
class SteamLibrary:
    """Represents a Steam library folder."""

    path: Path
    content_id: str
    total_size: int

    @property
    def steamapps_path(self) -> Path:
        """Path to steamapps directory."""
        return self.path / 'steamapps'

    @property
    def compatdata_path(self) -> Path:
        """Path to compatdata directory (Proton prefixes)."""
        return self.steamapps_path / 'compatdata'


@dataclass
class GameInfo:
    """Game information with Path-like behavior for compatdata access.

    Supports the `/` operator to construct paths relative to the game's
    compatdata directory:

        game = get_game(1282100)  # Remnant 2
        save_path = game / 'pfx/drive_c/users/steamuser/Saved Games'
    """

    app_id: int
    name: str
    install_dir: str
    size_on_disk: int
    library: SteamLibrary

    @property
    def game_path(self) -> Path:
        """Path to game installation directory."""
        return self.library.steamapps_path / 'common' / self.install_dir

    @property
    def compatdata_path(self) -> Path:
        """Path to Proton prefix directory."""
        return self.library.compatdata_path / str(self.app_id)

    def __truediv__(self, other: str | Path) -> Path:
        """Enable path joining with `/` operator relative to compatdata.

        Example:
            game / 'pfx/drive_c/users/steamuser/Saved Games'
        """
        return self.compatdata_path / other

    def __repr__(self) -> str:
        return f"GameInfo(app_id={self.app_id}, name={self.name!r}, path={self.compatdata_path})"


def get_steam_root() -> Path | None:
    """Find Steam installation root directory.

    Checks common Linux locations:
    - ~/.steam/steam (symlink to actual location)
    - ~/.local/share/Steam
    """
    # Try ~/.steam/steam first (common symlink)
    steam_symlink = Path.home() / '.steam' / 'steam'
    if steam_symlink.exists():
        return steam_symlink.resolve()

    # Try ~/.local/share/Steam
    local_steam = Path.home() / '.local' / 'share' / 'Steam'
    if local_steam.exists():
        return local_steam

    return None


def list_libraries() -> list[SteamLibrary]:
    """List all Steam library folders.

    Reads libraryfolders.vdf from the Steam installation.
    """
    steam_root = get_steam_root()
    if not steam_root:
        return []

    vdf_path = steam_root / 'steamapps' / 'libraryfolders.vdf'
    if not vdf_path.exists():
        return []

    content = vdf_path.read_text(encoding='utf-8')
    data = parse_vdf(content)

    libraries = []
    library_folders = data.get('libraryfolders', {})

    for key, info in library_folders.items():
        if not key.isdigit():
            continue
        if not isinstance(info, dict):
            continue

        path = info.get('path')
        if not path:
            continue

        library = SteamLibrary(
            path=Path(path),
            content_id=info.get('contentid', ''),
            total_size=int(info.get('totalsize', 0)),
        )
        libraries.append(library)

    return libraries


def list_games() -> list[GameInfo]:
    """List all installed games across all Steam libraries."""
    games = []

    for library in list_libraries():
        steamapps = library.steamapps_path
        if not steamapps.exists():
            continue

        # Find all appmanifest files
        for manifest_path in steamapps.glob('appmanifest_*.acf'):
            try:
                content = manifest_path.read_text(encoding='utf-8')
                data = parse_vdf(content)
                app_state = data.get('AppState', {})

                app_id = app_state.get('appid')
                name = app_state.get('name')
                install_dir = app_state.get('installdir')

                if not all([app_id, name, install_dir]):
                    continue

                game = GameInfo(
                    app_id=int(app_id),
                    name=name,
                    install_dir=install_dir,
                    size_on_disk=int(app_state.get('SizeOnDisk', 0)),
                    library=library,
                )
                games.append(game)
            except (ValueError, OSError):
                continue

    return games


def get_game(app_id: int) -> GameInfo:
    """Get game information by Steam app ID.

    Raises:
        LookupError: If game is not found in any Steam library.
    """
    for game in list_games():
        if game.app_id == app_id:
            return game
    raise LookupError(f'Game with app_id={app_id} not found in any Steam library')


def find_game(name: str) -> GameInfo:
    """Find game by fuzzy name matching.

    Normalizes names (lowercase, alphanumeric only) and checks if
    the search term is contained in the game name.

    Examples:
        find_game('Remnant 2')   # matches 'Remnant II'
        find_game('remnant')     # matches 'Remnant II'
        find_game('remnant2')    # matches 'Remnant II'
        find_game('REMNANTII')   # matches 'Remnant II'

    Raises:
        LookupError: If no matching game is found.
    """
    search_norm = _normalize_name(name)
    if not search_norm:
        raise LookupError(f'Invalid search name: {name!r}')

    for game in list_games():
        game_norm = _normalize_name(game.name)
        if search_norm in game_norm or game_norm in search_norm:
            return game

    raise LookupError(f'Game matching {name!r} not found in any Steam library')


def get_steam_user_id() -> str:
    """Get the current Steam user ID.

    Looks for numeric directory names (Steam user IDs) in the
    Steam userdata directory (~/.steam/steam/userdata/).

    Returns:
        Steam user ID string.

    Raises:
        LookupError: If no Steam user ID is found.
    """
    steam_root = get_steam_root()
    if steam_root is None:
        raise LookupError('Steam installation not found')

    userdata_path = steam_root / 'userdata'
    if not userdata_path.exists():
        raise LookupError(f'Steam userdata directory not found: {userdata_path}')

    # Look for numeric directory names (Steam user IDs)
    for entry in userdata_path.iterdir():
        if entry.is_dir() and entry.name.isdigit():
            return entry.name

    raise LookupError(f'No Steam user ID found in {userdata_path}')
