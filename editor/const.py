"""
Constants for Remnant 2 save file editor.
"""

from pathlib import Path


# Save file paths (Linux/Steam/Proton)
SAVE_DIR = (
    Path.home()
    / 'games/SteamLibrary/steamapps/compatdata/1282100/pfx/drive_c/users/steamuser/Saved Games/Remnant2/Steam/102469079'
)
PROFILE_PATH = SAVE_DIR / 'profile.sav'
WORLD_SAVE_PATH = SAVE_DIR / 'save_0.sav'

# Material asset path patterns
MATERIAL_SCRAPS = 'Material_Scraps'
MATERIAL_CORRUPTED_SHARD = 'Material_CorruptedShard'
