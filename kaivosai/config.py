"""Game configuration constants for KaivosAI.

Centralized definitions for all magic numbers and configuration values
used throughout the game. Modify these to adjust game balance and behavior.

Sections:
    - Map and World: Dimensions, terrain generation
    - Game Timing: Production/consumption intervals
    - Transfer System: Material movement rates
    - Message System: Message expiry and limits
    - Display: Terminal UI dimensions and limits
"""

# ============================================================================
# MAP AND WORLD CONFIGURATION
# ============================================================================

MAP_WIDTH = 30
"""Game world width in cells."""

MAP_HEIGHT = 30
"""Game world height in cells."""

ROCK_DENSITY = 0.03
"""Probability of rock cluster formation during terrain generation (0.0-1.0)."""

ROCK_CLUSTER_SIZE = 4
"""Average number of rocks per cluster in terrain generation."""

# ============================================================================
# GAME TIMING
# ============================================================================

PRODUCTION_INTERVAL = 10
"""Mines produce 1 material every N seconds (default 10s)."""

CONSUMPTION_INTERVAL = 10
"""Bases consume 1 material every N seconds (default 10s)."""

TRANSFER_RATE = 1
"""Materials per second during robot loading/unloading (1 material/s)."""

# ============================================================================
# MESSAGE SYSTEM
# ============================================================================

MESSAGE_EXPIRY = 3600
"""Message lifespan in seconds (default 3600s = 1 hour)."""

MAX_MESSAGE_LENGTH = 8
"""Maximum characters in a RoboBASIC SEND message."""

MESSAGE_INBOX_LIMIT = 100
"""Maximum messages stored in robot inbox (optional: prevents memory issues)."""

# ============================================================================
# DISPLAY AND UI
# ============================================================================

DISPLAY_WIDTH = 120
"""Maximum terminal width for map display in characters."""

DISPLAY_HEIGHT = 60
"""Maximum terminal height for map display in characters."""

REFRESH_INTERVAL = 0.5
"""UI refresh rate in seconds (0.5s = 2 refreshes/second)."""

MAP_MARGIN = 2
"""Cell margin around objects when auto-centering map view."""

CLOCK_FORMAT_WEEK_LENGTH = 7
"""Days per week in game clock (7 = 1 week every 604800 seconds)."""

# ============================================================================
# ROBOT SYSTEM
# ============================================================================

DEFAULT_ROBOT_CAPACITY = 5
"""Default material capacity for new robots."""

DEFAULT_MINE_CAPACITY = 10
"""Default material capacity for new mines."""

DEFAULT_STORAGE_CAPACITY = 20
"""Default material capacity for storage buildings."""

# ============================================================================
# ROBOBRAIN EXECUTION
# ============================================================================

ROBOBRAIN_LINE_MAX_LENGTH = 20
"""Maximum characters per RoboBASIC program line."""

ROBOBRAIN_LABEL_MAX_LENGTH = 10
"""Maximum characters for a RoboBASIC label name."""

ROBOBRAIN_EXECUTION_RATE = 1.0
"""Seconds per program line execution (1 line/second)."""

# ============================================================================
# DATABASE
# ============================================================================

DATABASE_TIMEOUT = 10.0
"""SQLite connection timeout in seconds."""

DATABASE_DIRECTORY = "databases"
"""Directory where game.db is stored."""

DATABASE_FILE = "game.db"
"""Default database filename."""
