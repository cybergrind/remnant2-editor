#!/usr/bin/env python3
"""
Modify a prism segment in a Remnant 2 save file.

Usage:
    uv run python scripts/modify_prism_segment.py <old_segment> <new_segment> [--output OUTPUT]
    uv run python scripts/modify_prism_segment.py --list

Examples:
    # List available segment names
    uv run python scripts/modify_prism_segment.py --list

    # Replace HealthRegen with CriticalDamage
    uv run python scripts/modify_prism_segment.py HealthRegen CriticalDamage

    # Specify custom output path
    uv run python scripts/modify_prism_segment.py HealthRegen CriticalDamage --output /path/to/output.sav

This script uses the same approach as the dotnet/WPF interface - it modifies
the FName.name property directly, and new names are automatically added to
the names table during serialization.
"""

import argparse
from pathlib import Path

from editor.const import PROFILE_PATH
from editor.log import log
from editor.model.save_file import SaveFile
from editor.prism_editor import VALID_PRISM_SEGMENTS


def main() -> None:
    parser = argparse.ArgumentParser(description='Modify a prism segment in a save file')
    parser.add_argument('old_segment', nargs='?', help='Current segment name to replace')
    parser.add_argument('new_segment', nargs='?', help='New segment name')
    parser.add_argument(
        '--input',
        '-i',
        type=Path,
        default=PROFILE_PATH,
        help=f'Input save file (default: {PROFILE_PATH})',
    )
    parser.add_argument(
        '--output',
        '-o',
        type=Path,
        help='Output save file (default: input_modified.sav)',
    )
    parser.add_argument(
        '--list',
        '-l',
        action='store_true',
        help='List available segment names from the save file',
    )

    args = parser.parse_args()

    input_path = args.input

    if not input_path.exists():
        log.error(f'Input file not found: {input_path}')
        return

    # Load save file
    log.info(f'Reading save file: {input_path}')
    try:
        save = SaveFile.load(input_path)
    except Exception as e:
        log.error(f'Failed to load save file: {e}')
        return

    # Handle --list option
    if args.list:
        # Find all segments currently in prisms
        segments = save.find_prism_segments()
        segment_names = sorted(set(name for _, name in segments))

        if segment_names:
            log.info(f'Segments in current prisms ({len(segment_names)}):')
            for seg in segment_names:
                log.info(f'  {seg}')
        else:
            log.warning('No prism segments found in save file')

        # Show all valid segment names
        log.info('')
        log.info(f'All valid segment names ({len(VALID_PRISM_SEGMENTS)}):')
        for seg in sorted(VALID_PRISM_SEGMENTS):
            marker = ' *' if seg in segment_names else ''
            log.info(f'  {seg}{marker}')
        return

    # Require both arguments for modification
    if not args.old_segment or not args.new_segment:
        parser.error('old_segment and new_segment are required (or use --list)')

    # Validate new segment is a valid prism segment
    if args.new_segment not in VALID_PRISM_SEGMENTS:
        log.error(f'"{args.new_segment}" is not a valid prism segment name.')
        log.error('Use --list to see valid segment names.')
        return

    # Check if old_segment exists in any prism
    segments = save.find_prism_segments()
    segment_names = set(name for _, name in segments)

    if args.old_segment not in segment_names:
        log.error(f'Segment "{args.old_segment}" not found in any prism.')
        if segment_names:
            log.info(f'Available segments: {", ".join(sorted(segment_names))}')
        return

    output_path = args.output
    if output_path is None:
        # Default to same directory with _modified suffix
        output_path = input_path.parent / f'{input_path.stem}_modified{input_path.suffix}'

    log.info(f'Modifying prism segment: {args.old_segment} -> {args.new_segment}')

    # Modify the segment using the WPF-style approach (direct FName modification)
    # This matches what dotnet does - modify FName.Name directly
    count = save.modify_prism_segment(args.old_segment, args.new_segment)
    if count == 0:
        log.error('Modification failed - no segments were changed')
        return

    log.info(f'Modified {count} segment(s)')

    # Save the modified file
    try:
        save.save(output_path)
    except Exception as e:
        log.error(f'Failed to save file: {e}')
        return

    log.info('Modification complete!')
    log.info(f'Output saved to: {output_path}')


if __name__ == '__main__':
    main()
