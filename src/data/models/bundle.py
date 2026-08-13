from dataclasses import dataclass, field
from typing import Any, Dict, Mapping

from src.domain.models.operator import Operator
from src.domain.models.skin import Skin
from src.helpers.bundle import *

@dataclass(frozen=True, slots=True)
class DataBundle:
    version: str

    # domain models
    operators: Dict[str, Operator]
    """Domain Model: 干员字典，key 为 operator_id"""
    tokens: Dict[str, Any]
    """Domain Model: 召唤物字典，key 为 token_id"""

    # indices
    operator_name_to_id: Dict[str, str]
    """干员中文名/英文代号 -> operator_id 的映射"""
    operator_index_to_id: Dict[str, str]
    """干员index_name -> operator_id 的映射"""
    token_name_to_id: Dict[str, str]
    """召唤物中文名/英文名 -> token_id 的映射（供统一搜索使用）"""

    skins: Dict[str, Skin]
    """皮肤字典，key 为 skin_id（含精英化立绘与具名皮肤）"""
    skin_name_to_id: Dict[str, str]
    """具名皮肤名 -> skin_id 的映射（供统一搜索使用，精英化立绘不收录）"""

    tables: Dict[str, Dict[str,Any]]
    """保留一些表，方便详情方法内部使用（避免再读磁盘）"""

