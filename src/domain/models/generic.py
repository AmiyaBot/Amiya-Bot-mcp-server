from abc import ABC
from dataclasses import dataclass

@dataclass(frozen=True)
class Cost(ABC):
    count: int

@dataclass(frozen=True)
class MaterialCost(Cost):
    material_id: str

@dataclass(frozen=True)
class GoldCost(Cost):
    pass

def parse_cost(d: dict) -> Cost:
    ctype = d.get("type")
    count = int(d.get("count", 0) or 0)

    if ctype == "MATERIAL":
        return MaterialCost(
            material_id=str(d.get("id") or ""),
            count=count,
        )
    elif ctype == "GOLD":
        return GoldCost(count=count)
    else:
        # 兜底，防止未来加新类型直接炸
        return MaterialCost(
            material_id=str(d.get("id") or ""),
            count=count,
        )