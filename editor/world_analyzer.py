"""
World Analyzer for Remnant 2 save files.

Analyzes save files to extract campaign/adventure events and their associated items.
Based on RemnantSaveGuardian's World Analyzer feature.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

# Path to game.json data file
GAME_DATA_PATH = Path(__file__).parent / 'data' / 'game.json'


class ProcessMode(Enum):
    """Mode for processing events."""

    CAMPAIGN = 'campaign'
    ADVENTURE = 'adventure'


@dataclass
class GameItem:
    """Represents an item that can drop from an event."""

    name: str
    notes: str = ''
    coop: bool = False
    tile_set: str = ''

    @property
    def display_name(self) -> str:
        """Get a human-readable display name."""
        # Extract name from path like /Items/Trinkets/Rings/HeartOfTheWolf/Ring_HeartOfTheWolf
        parts = self.name.split('/')
        if parts:
            raw_name = parts[-1]
            # Remove prefix and convert to readable
            for prefix in ('Ring_', 'Amulet_', 'Weapon_', 'Armor_', 'Trait_', 'Mod_', 'Relic_', 'MetaGem_'):
                if raw_name.startswith(prefix):
                    raw_name = raw_name[len(prefix) :]
                    break
            # Add spaces before capitals
            return re.sub(r'([a-z])([A-Z])', r'\1 \2', raw_name)
        return self.name

    @property
    def item_type(self) -> str:
        """Get the item type from the path."""
        if '/Rings/' in self.name:
            return 'Ring'
        if '/Amulets/' in self.name:
            return 'Amulet'
        if '/Weapons/' in self.name:
            if '/Melee/' in self.name:
                return 'Melee'
            if '/LongGuns/' in self.name:
                return 'Long Gun'
            if '/HandGuns/' in self.name:
                return 'Hand Gun'
            return 'Weapon'
        if '/Armor/' in self.name:
            return 'Armor'
        if '/Traits/' in self.name:
            return 'Trait'
        if '/Mods/' in self.name:
            return 'Mod'
        if '/Gems/' in self.name:
            return 'Mutator'
        if '/Relic' in self.name:
            return 'Relic'
        return 'Item'


@dataclass
class WorldEvent:
    """Represents a world event in the save file."""

    key: str
    name: str
    locations: list[str] = field(default_factory=list)
    event_type: str = ''
    tile_set: str = ''

    @property
    def world(self) -> str:
        """Get the world name."""
        if self.locations:
            return _translate_world(self.locations[0])
        return ''

    @property
    def location(self) -> str:
        """Get the full location string."""
        translated = [_translate_location(loc) for loc in self.locations]
        return ': '.join(translated)

    @property
    def display_name(self) -> str:
        """Get the display name for this event."""
        name = self.name
        if name.endswith('Story'):
            name = name[:-5]
        # Add spaces before capitals
        return re.sub(r'([a-z])([A-Z])', r'\1 \2', name)


class GameData:
    """Holds game data loaded from game.json."""

    _instance: GameData | None = None

    def __init__(self) -> None:
        self.events: dict[str, list[GameItem]] = {}
        self.sub_locations: dict[str, str] = {}
        self.injectables: dict[str, str] = {}
        self.injectable_parents: dict[str, str] = {}
        self.main_locations: list[str] = []
        self._load()

    @classmethod
    def get(cls) -> GameData:
        """Get the singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _load(self) -> None:
        """Load game data from game.json."""
        with open(GAME_DATA_PATH, encoding='utf-8') as f:
            data = json.load(f)

        # Load events
        for world_events in data.get('events', {}).values():
            for event_name, items in world_events.items():
                if items is None:
                    continue
                event_items = []
                for item in items:
                    if item.get('ignore'):
                        continue
                    game_item = GameItem(
                        name=item['name'],
                        notes=item.get('notes', ''),
                        coop=item.get('coop', False),
                        tile_set=item.get('tileSet', ''),
                    )
                    event_items.append(game_item)
                self.events[event_name] = event_items

        # Load sub-locations
        for world_locs in data.get('subLocations', {}).values():
            for key, value in world_locs.items():
                self.sub_locations[key] = value

        # Load injectables
        for world_injects in data.get('injectables', {}).values():
            for key, value in world_injects.items():
                self.injectables[key] = value

        # Load injectable parents
        for key, value in data.get('injectableParents', {}).items():
            self.injectable_parents[key] = value

        # Load main locations
        self.main_locations = data.get('mainLocations', [])

    def get_items_for_event(self, event_name: str) -> list[GameItem]:
        """Get items that can drop from an event."""
        return self.events.get(event_name, [])


# World name translations
WORLD_TRANSLATIONS = {
    'World_Jungle': 'Yaesha',
    'World_Fae': 'Losomn',
    'World_Nerud': "N'Erud",
    'World_Earth': 'Earth',
    'World_RootEarth': 'Root Earth',
    'World_Labyrinth': 'Labyrinth',
    'World_Base': 'Ward 13',
    'World_DLC1': 'Losomn',
    'World_DLC2': 'Yaesha',
    'World_DLC3': "N'Erud",
    'Campaign_Labyrinth': 'Labyrinth',
    'Campaign_Main': 'Campaign',
}


def _translate_world(world: str) -> str:
    """Translate internal world name to display name."""
    return WORLD_TRANSLATIONS.get(world, world)


def _translate_location(location: str) -> str:
    """Translate internal location name to display name."""
    game_data = GameData.get()
    if location in game_data.sub_locations:
        return game_data.sub_locations[location]
    return _translate_world(location)


def _extract_events_text(save_text: str, mode: ProcessMode) -> str:
    """Extract the relevant portion of save text for a mode."""
    campaign_start_marker = '/Game/World_Base/Quests/Quest_Ward13/Quest_Ward13.Quest_Ward13_C'
    campaign_end_marker = '/Game/Campaign_Main/Quest_Campaign_Main.Quest_Campaign_Main_C'

    campaign_end = save_text.find(campaign_end_marker)

    if mode == ProcessMode.CAMPAIGN:
        campaign_start = save_text.find(campaign_start_marker)
        if campaign_start == -1 or campaign_end == -1:
            return ''
        # Find the last occurrence of campaign start before campaign end
        events_text = save_text[:campaign_end]
        last_start = events_text.rfind(campaign_start_marker)
        if last_start != -1:
            return events_text[last_start:]
        return ''

    # Adventure mode
    adventure_pattern = r'/Game/World_(?:\w+)/Quests/Quest_AdventureMode/Quest_AdventureMode_\w+\.Quest_AdventureMode_\w+_C'
    match = re.search(adventure_pattern, save_text)
    if match:
        adventure_end = match.start()
        adventure_start = campaign_end if campaign_end != -1 else 0
        if adventure_start > adventure_end:
            adventure_start = 0
        return save_text[adventure_start:adventure_end]

    return ''


def _parse_events(events_text: str, mode: ProcessMode) -> list[WorldEvent]:
    """Parse events from the events text."""
    if not events_text:
        return []

    events: list[WorldEvent] = []
    seen_events: set[str] = set()

    # Event types to skip
    skip_event_types = {'Global', 'Earth', 'AdventureMode'}

    # Event names to skip
    skip_event_names = {'AdventureMode', 'Campaign_Main'}

    # Match quest events
    pattern = r'/Game/(?P<world>(?:World|Campaign)_\w+)/Quests/(?:Quest_)?(?P<eventType>[a-zA-Z0-9]+)_(?P<eventName>\w+)/(?P<details>\w+)\.\w+'

    for match in re.finditer(pattern, events_text):
        world = match.group('world')
        event_type = match.group('eventType')
        event_name = match.group('eventName')
        details = match.group('details')

        # Skip certain patterns
        if 'EventTree' in match.group(0):
            continue
        if details.endswith('_C'):
            continue
        if event_type in skip_event_types:
            continue
        if event_name in skip_event_names:
            continue
        if 'Template' in match.group(0) or 'TileInfo' in match.group(0):
            continue

        # Create unique key
        event_key = f'{world}:{event_type}:{event_name}'
        if event_key in seen_events:
            continue
        seen_events.add(event_key)

        # Process event name
        name = event_name
        if '_Spawntable' in name:
            name = name.replace('_Spawntable', '')

        # Handle item prefixes
        if any(name.startswith(prefix) for prefix in ('Ring', 'Amulet', 'Trait')):
            event_type = 'Item'

        # Handle story events
        if event_type == 'Story' and 'Quest_Event' not in match.group(0):
            name = f'{name}Story'

        # Handle injectables
        if 'Injectable' in event_type or 'Abberation' in event_type:
            name_parts = name.split('_')
            name = name_parts[-1] if name_parts[-1] != 'DLC' else name_parts[-2]

        # Get sub-location
        game_data = GameData.get()
        locations = [world]
        if event_name in game_data.sub_locations:
            locations.append(game_data.sub_locations[event_name])

        event = WorldEvent(
            key=match.group(0),
            name=name,
            locations=locations,
            event_type=event_type,
        )

        events.append(event)

    return events


def analyze_save(save_text: str, mode: ProcessMode = ProcessMode.CAMPAIGN) -> list[WorldEvent]:
    """
    Analyze a save file and extract world events.

    Args:
        save_text: The decompressed save file as text
        mode: Campaign or Adventure mode

    Returns:
        List of world events found in the save
    """
    events_text = _extract_events_text(save_text, mode)
    return _parse_events(events_text, mode)


def get_event_items(event: WorldEvent) -> list[GameItem]:
    """Get items that can drop from an event."""
    game_data = GameData.get()
    return game_data.get_items_for_event(event.name)


def iter_events_with_items(events: list[WorldEvent]) -> Iterator[tuple[WorldEvent, list[GameItem]]]:
    """Iterate over events with their possible items."""
    for event in events:
        items = get_event_items(event)
        yield event, items
