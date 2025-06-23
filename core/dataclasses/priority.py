from enum import Enum


class Priority(Enum):
    """Priority levels for tasks."""
    low = 1
    medium = 2
    high = 3
    critical = 4

    def __str__(self):
        return self.name.capitalize()

    def lower(self):
        return self.name.lower()