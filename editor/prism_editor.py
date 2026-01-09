"""Prism editing functions for Remnant 2 save files (v2).

This module uses proper structured parsing with OffsetInfo-based navigation.
No guessing, no pattern matching, no magic numbers.
"""

from pathlib import Path

from editor.log import log
from editor.model.save_file import SaveFile

# All valid prism segment names from game data
VALID_PRISM_SEGMENTS = frozenset([
    # Fusion segments (combined stats)
    'MeleeDamageMeleeSpeed',
    'DamageReductionArmorPercent',
    'MeleeCriticalEvadeSpeed',
    'HealthPercentStaminaPercent',
    'WeakspotDamageCriticalDamage',
    'HealthRegenSkillCooldown',
    'FireRateReloadSpeed',
    'RangedDamageIdealRange',
    'RangedCriticalAmmoReserves',
    'MovementSpeedEvadeSpeed',
    'ModDurationSkillDuration',
    'ModDamageModGeneration',
    'ExplosiveDamageDamageReduction',
    'WeaponSpreadSwapSpeed',
    'CastSpeedUseSpeed',
    # Base segments
    'CriticalDamage',
    'Immovable',
    'HealthPercent',
    'MeleeCriticalChance',
    'DamageReduction',
    'MeleeDamage',
    'MeleeAttackSpeed',
    'ArmorPercent',
    'EvadeSpeed',
    'StaminaPercent',
    'SkillDamage',
    'HealthRegen',
    'HealingEfficacy',
    'ConsumableSpeed',
    'FirearmChargeSpeed',
    'SharpShooter',
    'ReloadSpeed',
    'IdealRange',
    'AmmoReserves',
    'RangedFireRate',
    'WeakspotDamage',
    'RangedDamage',
    'RangedCriticalChance',
    'StatusDamage',
    'Sadistic',
    'MovementSpeed',
    'SkillCooldown',
    'ModDuration',
    'SkillDuration',
    'ModCriticalChance',
    'CriticalSituation',
    'ModGeneration',
    'ModDamage',
    'ExplosiveDamage',
    'SwapSpeed',
    'WeaponSpread',
    'Unbridled',
    'CastSpeed',
    # Mythic/Legendary segments
    'Allegiance',
    'Altruistic',
    'ArtfulDodger',
    'Bodyguard',
    'BoundlessEnergy',
    'Brutality',
    'DarkOmen',
    'DefensiveMeasures',
    'Exhausted',
    'FleetFooted',
    'FullHearted',
    'Gigantic',
    'GodTear',
    'HeavyDrinker',
    'Hyperactive',
    'Impervious',
    'InsultToInjury',
    'JackOfAllTrades',
    'LuckOfTheDevil',
    'MasterKiller',
    'Outlaw',
    'Overpowered',
    'PeakConditioning',
    'Physician',
    'PowerFantasy',
    'PowerTrip',
    'PrimeTime',
    'Reverberation',
    'SizeMatters',
    'Soulmate',
    'Spectrum',
    'SpeedDemon',
    'SteelPlating',
    'Traitor',
    'Unbreakable',
    'Vaccinated',
    'WreckingBall',
])


def list_available_segments(save_file: SaveFile) -> tuple[list[str], list[str]]:
    """List segment names available for modification.

    Returns:
        Tuple of (available_segments, all_valid_segments)
        - available_segments: Names in the file's names table that are valid prism segments
        - all_valid_segments: All valid prism segment names from game data
    """
    names_set = set(save_file.save_data.names_table)
    available = [seg for seg in VALID_PRISM_SEGMENTS if seg in names_set]
    return sorted(available), sorted(VALID_PRISM_SEGMENTS)


def modify_prism_segment(
    input_path: Path,
    output_path: Path,
    old_segment: str,
    new_segment: str,
) -> bool:
    """Modify a prism segment in a save file.

    This works by replacing the old segment name in the names table with
    the new segment name. All references to that name index will then
    point to the new name.

    Args:
        input_path: Path to input save file
        output_path: Path to write modified save file
        old_segment: Current segment name to replace
        new_segment: New segment name

    Returns:
        True if successful, False otherwise.
    """
    # Validate new segment is a valid prism segment
    if new_segment not in VALID_PRISM_SEGMENTS:
        log.error(f'"{new_segment}" is not a valid prism segment name.')
        log.error('Use --list to see valid segment names.')
        return False

    log.info(f'Loading save file: {input_path}')

    try:
        save = SaveFile.load(input_path)
    except Exception as e:
        log.error(f'Failed to load save file: {e}')
        return False

    # Check if old_segment exists in names table
    if old_segment not in save.save_data.names_table:
        log.error(f'Segment "{old_segment}" not found in names table.')
        available, _ = list_available_segments(save)
        if available:
            log.info(f'Available segments: {", ".join(available[:10])}...')
        return False

    # Replace the name
    log.info(f'Replacing "{old_segment}" with "{new_segment}"')
    if not save.replace_name(old_segment, new_segment):
        log.error(f'Failed to replace segment name')
        return False

    # Save the modified file
    try:
        save.save(output_path)
    except Exception as e:
        log.error(f'Failed to save file: {e}')
        return False

    log.info(f'Wrote modified save to: {output_path}')
    return True
