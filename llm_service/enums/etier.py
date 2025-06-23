from enum import Enum


class ETier(str, Enum):
    STANDARD = "standard"
    HEAVY = "heavy"
    MEGA = "mega"
