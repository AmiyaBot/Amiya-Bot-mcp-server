from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict


class Transformer(ABC):
    """
    抽象的“转换器”基类：把一种输入转换为另一种输出。
    这里先做最小抽象：输入/输出是 bytes 或 str，由实现自行约定。
    """

    input_mime: str | None = None
    output_mime: str | None = None

    @abstractmethod
    async def transform(self, *, input: Any, cfg: Dict[str, Any] | None = None) -> Any:
        """
        执行转换。

        Args:
            input: 输入对象（由具体 transformer 约定类型，比如 HTMLToPNGTransformer 要求 str）
            cfg: 可选配置（viewport、等待策略等）

        Returns:
            输出对象（由具体 transformer 约定类型，比如 HTMLToPNGTransformer 输出 bytes）
        """
        raise NotImplementedError