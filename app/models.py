from dataclasses import dataclass, field
from typing import List

@dataclass
class Variant:
    color: str = ""
    size: str = ""
    status: str = "unknown"

@dataclass
class Product:
    site: str = ""
    url: str = ""
    name: str = ""
    price: str = ""
    image_url: str = ""
    variants: List[Variant] = field(default_factory=list)
