# Remnant 2 Save Editor

A Python-based save file editor for the game Remnant 2. Allows viewing and modifying save data including prism configurations, materials, and world analysis.

## Requirements

- [uv](https://github.com/astral-sh/uv) package manager

## Installation

```bash
git clone https://github.com/cybergrind/remnant2-editor.git
cd remnant2-editor
uv sync
```

## Commands

### World Analyzer

Analyze your campaign or adventure mode to see all locations, events, and possible item drops.

```bash
# Analyze campaign (default)
uv run python scripts/world_analyzer.py

# Analyze adventure mode
uv run python scripts/world_analyzer.py --adventure

# Specify a different save file
uv run python scripts/world_analyzer.py --input /path/to/save_0.sav

# Output as JSON
uv run python scripts/world_analyzer.py --json

# Hide item drops (show only locations)
uv run python scripts/world_analyzer.py --no-items
```

Example output:
```
============================================================
  N'Erud
============================================================

  [Story] IAm Legend - N'Erud
      Mod: Stasis Beam

  [SideD] Stasis Siege - Vault Of The Formless
      Ring: Metal Driver
      Hand Gun: Rupture Cannon
      Trait: Fitness

  [Miniboss] Custodian Eye - Spectrum Nexus
      Mod: Prismatic Driver
```

### Prism Editor

View and modify prism segment configurations.

```bash
# List all segments in current prisms and valid segment names
uv run python scripts/modify_prism_segment.py --list

# Replace a segment (e.g., change HealthRegen to CriticalDamage)
uv run python scripts/modify_prism_segment.py HealthRegen CriticalDamage

# Specify input/output files
uv run python scripts/modify_prism_segment.py HealthRegen CriticalDamage \
    --input /path/to/profile.sav \
    --output /path/to/profile_modified.sav
```

### Print Prism Info

Display current prism segments.

```bash
uv run python scripts/print_prisms.py
```

### Print Materials

View material quantities in your profile.

```bash
# Print scrap and corrupted shard counts
uv run python scripts/print_scrap.py

# Print all materials
uv run python scripts/print_materials.py
```

## Save File Locations

### Linux (Steam/Proton)
```
~/.steam/steam/steamapps/compatdata/1282100/pfx/drive_c/users/steamuser/Saved Games/Remnant2/Steam/<STEAM_USER_ID>/
```

### Windows
```
%USERPROFILE%\Saved Games\Remnant2\Steam\<STEAM_USER_ID>\
```

### File Types
- `profile.sav` - Player profile (materials, unlocks, prism config)
- `save_0.sav`, `save_1.sav`, etc. - World/character saves
- `.bak1`, `.bak2`, `.bak3` - Automatic backups

## Development

```bash
# Run tests
uv run pytest

# Run linting
uv run pre-commit run --all-files
```

## Credits

Based on analysis of:
- [lib.remnant2.saves](https://github.com/t1nky/lib.remnant2.saves) - C# save file library
- [RemnantSaveGuardian](https://github.com/Razzmatazzz/RemnantSaveGuardian) - Save manager with World Analyzer

## License

MIT
