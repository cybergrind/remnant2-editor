"""
Constants for Remnant 2 save file editor.
"""

from editor.steam_storage import get_game, get_steam_user_id

# Remnant 2 Steam app ID
REMNANT2_APP_ID = 1282100

# Save file paths (Linux/Steam/Proton)
STEAM_USER_ID = get_steam_user_id()
GAME_DIR = get_game(REMNANT2_APP_ID)
SAVE_DIR = GAME_DIR / 'pfx/drive_c/users/steamuser/Saved Games/Remnant2/Steam' / STEAM_USER_ID
PROFILE_PATH = SAVE_DIR / 'profile.sav'
WORLD_SAVE_PATH = SAVE_DIR / 'save_0.sav'

# Material asset path patterns
MATERIAL_SCRAPS = 'Material_Scraps'
MATERIAL_CORRUPTED_SHARD = 'Material_CorruptedShard'
