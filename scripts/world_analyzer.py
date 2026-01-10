#!/usr/bin/env python3
"""
World Analyzer - Analyze Remnant 2 save files for locations and items.

Usage:
    uv run python scripts/world_analyzer.py [--input INPUT] [--adventure]

Examples:
    # Analyze campaign from default profile
    uv run python scripts/world_analyzer.py

    # Analyze adventure mode
    uv run python scripts/world_analyzer.py --adventure

    # Analyze specific save file
    uv run python scripts/world_analyzer.py --input /path/to/save.sav
"""

from __future__ import annotations

import argparse
from pathlib import Path

from editor.compression import decompress_save
from editor.const import WORLD_SAVE_PATH
from editor.log import log
from editor.world_analyzer import (
    ProcessMode,
    WorldEvent,
    analyze_save,
    get_event_items,
)


def format_table(events: list[WorldEvent], show_items: bool = True) -> str:
    """Format events as a table."""
    lines = []

    # Group events by world
    events_by_world: dict[str, list[WorldEvent]] = {}
    for event in events:
        world = event.world
        if world not in events_by_world:
            events_by_world[world] = []
        events_by_world[world].append(event)

    for world, world_events in events_by_world.items():
        lines.append(f'\n{"=" * 60}')
        lines.append(f'  {world}')
        lines.append(f'{"=" * 60}')

        for event in world_events:
            # Format location
            location = event.location
            if location.startswith(world + ': '):
                location = location[len(world) + 2 :]

            # Event header
            event_line = f'\n  [{event.event_type}] {event.display_name}'
            if location:
                event_line += f' - {location}'
            lines.append(event_line)

            # Items
            if show_items:
                items = get_event_items(event)
                if items:
                    for item in items:
                        item_line = f'      {item.item_type}: {item.display_name}'
                        if item.coop:
                            item_line += ' (co-op)'
                        lines.append(item_line)
                        if item.notes:
                            # Wrap notes
                            notes = item.notes
                            if len(notes) > 50:
                                notes = notes[:47] + '...'
                            lines.append(f'        Note: {notes}')

    return '\n'.join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Analyze Remnant 2 save files for locations and items'
    )
    parser.add_argument(
        '--input',
        '-i',
        type=Path,
        default=WORLD_SAVE_PATH,
        help=f'Input save file (default: {WORLD_SAVE_PATH})',
    )
    parser.add_argument(
        '--adventure',
        '-a',
        action='store_true',
        help='Analyze adventure mode instead of campaign',
    )
    parser.add_argument(
        '--no-items',
        action='store_true',
        help='Hide item drops',
    )
    parser.add_argument(
        '--json',
        action='store_true',
        help='Output as JSON',
    )

    args = parser.parse_args()

    input_path = args.input
    if not input_path.exists():
        log.error(f'Input file not found: {input_path}')
        return

    mode = ProcessMode.ADVENTURE if args.adventure else ProcessMode.CAMPAIGN

    log.info(f'Analyzing {mode.value} from: {input_path}')

    # Read and decompress save file
    try:
        data = input_path.read_bytes()
        decompressed = decompress_save(data)
        # Convert to text for regex parsing
        save_text = decompressed.decode('latin-1')
    except Exception as e:
        log.error(f'Failed to read save file: {e}')
        return

    # Analyze
    events = analyze_save(save_text, mode)

    if not events:
        log.warning(f'No events found for {mode.value}')
        return

    log.info(f'Found {len(events)} events')

    if args.json:
        import json

        output = []
        for event in events:
            items = get_event_items(event)
            output.append(
                {
                    'name': event.display_name,
                    'type': event.event_type,
                    'location': event.location,
                    'items': [
                        {
                            'name': item.display_name,
                            'type': item.item_type,
                            'coop': item.coop,
                            'notes': item.notes,
                        }
                        for item in items
                    ],
                }
            )
        print(json.dumps(output, indent=2))
    else:
        table = format_table(events, show_items=not args.no_items)
        print(table)


if __name__ == '__main__':
    main()
