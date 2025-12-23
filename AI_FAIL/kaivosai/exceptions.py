"""Custom exception classes for KaivosAI.

Provides specific exception types for different error scenarios,
enabling better error handling and more informative error messages.

Exception Hierarchy:
    GameError (base)
    ├── MapError - Map/world operations
    ├── DatabaseError - Database operations
    ├── CommandError - CLI command parsing/execution
    ├── RobotError - Robot operations
    └── ValidationError - Input validation
"""


class GameError(Exception):
    """Base exception for all KaivosAI game errors.
    
    All custom exceptions in the game inherit from this class,
    allowing broad exception catching when needed.
    
    Args:
        message: Error description
        details: Optional additional context (dict, str, etc.)
    
    Attributes:
        message: Error description string
        details: Additional error context
    """
    
    def __init__(self, message: str, details=None):
        self.message = message
        self.details = details
        super().__init__(self.message)
    
    def __str__(self):
        if self.details:
            return f"{self.message} (Details: {self.details})"
        return self.message


class MapError(GameError):
    """Exception for map-related operations.
    
    Raised when:
    - Object not found at position
    - Invalid position coordinates
    - Collision detection fails
    - Pathfinding errors
    
    Example:
        >>> raise MapError("Position (5,5) out of bounds", details={"pos": (5,5)})
    """
    pass


class DatabaseError(GameError):
    """Exception for database operations.
    
    Raised when:
    - Connection failures
    - Query execution errors
    - Data integrity violations
    - Migration failures
    
    Example:
        >>> raise DatabaseError("Failed to persist object", details={"id": 42})
    """
    pass


class CommandError(GameError):
    """Exception for CLI command processing.
    
    Raised when:
    - Invalid command syntax
    - Missing required parameters
    - Parameter parsing failures
    - Command execution errors
    
    Example:
        >>> raise CommandError("Invalid robot ID", details={"input": "abc"})
    """
    pass


class RobotError(GameError):
    """Exception for robot operations.
    
    Raised when:
    - Robot not found
    - Invalid robot state
    - Program execution errors
    - Movement/pathfinding failures
    
    Example:
        >>> raise RobotError("Robot inventory full", details={"capacity": 5})
    """
    pass


class ValidationError(GameError):
    """Exception for input validation failures.
    
    Raised when:
    - Invalid coordinates
    - Out of range values
    - Type mismatches
    - Constraint violations
    
    Example:
        >>> raise ValidationError("Coordinate out of range", details={"x": -1})
    """
    pass
