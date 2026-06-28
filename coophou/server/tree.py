from dataclasses import dataclass, field
from typing import List, Any

@dataclass
class Node:
    name: str
    data: Any
    children: List['Node'] = field(default_factory=list)