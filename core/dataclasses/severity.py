from dataclasses import dataclass


@dataclass
class Severity:
    name: str
    order: int

    class Meta:
        ordering = ('order', 'name')

    def __str__(self):
        return self.name
