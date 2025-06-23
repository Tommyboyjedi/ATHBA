from enum import Enum


class EAgent(str, Enum):
    PM = "PM"
    Spec = "SpecBuilder"
    Developer = "Developer"
    Architect = "Architect"
    Tester = "Tester"
    RD = "RD"
