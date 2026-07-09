from dataclasses import dataclass

@dataclass
class Bid:
    id: str
    code: str
    value: float
