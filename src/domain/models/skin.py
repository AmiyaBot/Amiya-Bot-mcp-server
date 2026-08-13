# domain/models/skin.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict

STR_DICT = Dict[str, Any]


@dataclass(slots=True)
class Skin:
    """
    干员皮肤 / 立绘的领域模型（轻量）
    - 不负责 IO
    - 不负责 JSON 解析（解析在 data 层 OperatorImpl._init_skins 中做）

    沿用旧项目（AmiyaBot v5 operatorBuilder.skins）的字段语义，
    精英化立绘（stage0/1/2）与具名皮肤（skinN）统一用本类表示。
    """

    operator_id: str = ""
    """归属干员 ID（已做异格归属修正）"""
    operator_name: str = ""
    """归属干员名"""

    skin_id: str = ""
    """皮肤 ID（如 char_002_amiya@winter#1）"""
    skin_key: str = ""
    """立绘键：精英化立绘为 stage0/stage1/stage2，具名皮肤为 skin1/skin2..."""
    name: str = ""
    """皮肤名（skinName；精英化立绘为 初始/精英一/精英二）"""

    drawer: str = ""
    """画师（drawerList 最后一位）"""
    group: str = ""
    """系列名（skinGroupName）"""
    content: str = ""
    """皮肤台词（dialog）"""
    usage: str = ""
    """用途说明（usage，兜底为 "{name}立绘"）"""
    desc: str = ""
    """皮肤描述（description）"""
    source: str = ""
    """获取途径（obtainApproach）"""

    voice_id: str = ""
    """皮肤语音 ID（voiceId）"""
    voice_type: str = ""
    """皮肤语音类型（voiceType）"""

    is_evolve: bool = False
    """是否为精英化立绘（无独立皮肤名，不进搜索索引）"""

    # 可选：保留原始字段兜底（不建议 core 直接用它，但方便调试/兼容）
    raw: STR_DICT = field(default_factory=dict, repr=False)

    def to_dict(self) -> STR_DICT:
        """稳定的对外序列化，键名与旧项目 skins() 输出契约一致。"""
        return {
            "char_name": self.operator_name,
            "skin_id": self.skin_id,
            "skin_key": self.skin_key,
            "skin_name": self.name,
            "skin_drawer": self.drawer,
            "skin_group": self.group,
            "skin_content": self.content,
            "skin_usage": self.usage,
            "skin_desc": self.desc,
            "skin_source": self.source,
            "skin_voice": self.voice_id,
            "skin_voice_type": self.voice_type,
        }
