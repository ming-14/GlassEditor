"""
编码检测模块 -- 自动检测文件编码

设计依据: doc/架构设计.md 2.4节 EncodingDetector
"""

from typing import Tuple, Optional

import chardet

from src.infrastructure.logger import get_logger

_logger = get_logger("encoding_detector")


class EncodingDetector:
    """
    文件编码自动检测器

    检测策略:
    1. 先检查BOM标记(快速且可靠)
    2. 使用chardet检测(必需依赖)
    3. 置信度低于0.5时回退到utf-8
    """

    # BOM标记映射
    _BOM_MAP = {
        b"\xef\xbb\xbf": "utf-8-sig",
        b"\xff\xfe": "utf-16-le",
        b"\xfe\xff": "utf-16-be",
        b"\xff\xfe\x00\x00": "utf-32-le",
        b"\x00\x00\xfe\xff": "utf-32-be",
    }

    @classmethod
    def detect(cls, data: bytes) -> Tuple[str, float]:
        """
        检测编码

        @param data: 文件二进制内容(前2KB左右即可)
        @return: (编码名称, 置信度 0.0~1.0)
        """
        if not data:
            return "utf-8", 1.0

        # 1. 检查BOM
        bom_encoding = cls._check_bom(data)
        if bom_encoding:
            return bom_encoding, 1.0

        # 2. 使用chardet检测
        result = chardet.detect(data[:2048])
        encoding = result.get("encoding")
        confidence = result.get("confidence", 0.0)

        if encoding and confidence >= 0.5:
            return cls._normalize(encoding.lower()), confidence

        # 3. 置信度不足, 回退utf-8
        _logger.debug(
            "chardet置信度不足, 回退utf-8",
            detected=encoding, confidence=confidence,
        )
        return "utf-8", confidence

    @classmethod
    def detect_from_file(cls, file_path: str, sample_size: int = 2048) -> Tuple[str, float]:
        """
        从文件路径检测编码(读取前sample_size字节)

        @param file_path: 文件路径
        @param sample_size: 采样字节数
        @return: (编码名称, 置信度)
        """
        try:
            with open(file_path, "rb") as f:
                data = f.read(sample_size)
            return cls.detect(data)
        except (OSError, UnicodeDecodeError):
            return "utf-8", 0.0

    @classmethod
    def _check_bom(cls, data: bytes) -> Optional[str]:
        """检查BOM标记"""
        for bom, enc in cls._BOM_MAP.items():
            if data.startswith(bom):
                return enc
        return None

    @staticmethod
    def _normalize(encoding: str) -> str:
        """标准化编码名称"""
        encoding = encoding.lower().replace("_", "-").replace(" ", "-")
        aliases = {
            "utf8": "utf-8",
            "utf-8-sig": "utf-8",
            "ascii": "utf-8",
            "iso-8859-1": "latin-1",
            "cp936": "gbk",
            "ms936": "gbk",
            "windows-1252": "cp1252",
        }
        return aliases.get(encoding, encoding)
