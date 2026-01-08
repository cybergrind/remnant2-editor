"""
Test prism data extraction from save files.
"""

from editor.prisms import find_prism_data


def test_find_prism_data(profile_data: bytes) -> None:
    """Test that we can find prism data in the fixture."""
    prisms = find_prism_data(profile_data)

    assert len(prisms) >= 1, 'Should find at least one prism'

    prism = prisms[0]

    # Check that we have segments
    assert len(prism.segments) > 0, 'Prism should have segments'

    # Check that total level is sum of segment levels
    expected_total = sum(seg.level for seg in prism.segments)
    assert prism.total_level == expected_total

    # Check that pending experience is a reasonable value
    assert prism.pending_experience >= 0


def test_prism_segment_names(profile_data: bytes) -> None:
    """Test that segment names are valid."""
    prisms = find_prism_data(profile_data)

    assert len(prisms) >= 1

    prism = prisms[0]

    # Known segment names from the C# reference
    known_segments = {
        'CriticalDamage',
        'WeakspotDamage',
        'RangedDamage',
        'MeleeDamage',
        'ModDamage',
        'SkillDamage',
        'ExplosiveDamage',
        'StatusDamage',
        'RangedCriticalChance',
        'MeleeCriticalChance',
        'ModCriticalChance',
        'SkillCriticalChance',
        'RangedFireRate',
        'FirearmChargeSpeed',
        'MeleeAttackSpeed',
        'HealthPercent',
        'HealthFlat',
        'HealthRegen',
        'HealingEfficacy',
        'GreyHealthRate',
        'StaminaPercent',
        'StaminaFlat',
        'DamageReduction',
        'ArmorPercent',
        'ArmorFlat',
        'ShieldPercent',
        'ShieldDuration',
        'EvadeSpeed',
        'EvadeDistance',
        'ReviveSpeed',
        'MovementSpeed',
        'WeaponSpread',
        'IdealRange',
        'ReloadSpeed',
        'SwapSpeed',
        'AmmoReserves',
        'ProjectileSpeed',
        'HeatReduction',
        'CastSpeed',
        'ModGeneration',
        'ModDuration',
        'SkillCooldown',
        'SkillDuration',
        'ConsumableSpeed',
        'ConsumableDuration',
    }

    for seg in prism.segments:
        # Segment name should be known or a fusion/legendary type
        # (fusion names are combinations like "WeakspotDamageCriticalDamage")
        is_known = seg.name in known_segments
        is_fusion = any(known in seg.name for known in known_segments)
        assert is_known or is_fusion, f'Unknown segment name: {seg.name}'
