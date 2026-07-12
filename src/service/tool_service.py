"""
辅助工具服务模块 —— 字数统计、哈希计算、排序、大小写转换等

设计依据: doc/架构设计.md 2.3节 ToolService, doc/功能设计.md 2.6节
"""

import hashlib
from typing import Dict

from src.infrastructure.logger import get_logger


class ToolService:
    """
    辅助工具服务 —— 提供纯文本操作的实用工具

    所有方法均为纯文本操作，无UI依赖，方便单元测试。
    """

    def __init__(self):
        """构造函数"""
        self._logger = get_logger("ToolService")

    @staticmethod
    def count_stats(text: str) -> Dict[str, int]:
        """
        统计文本的字数信息

        @param text: 输入文本
        @return: 统计结果字典:
                 - chars_with_spaces: 字符数（含空白）
                 - chars_without_spaces: 字符数（不含空白）
                 - words: 单词数（按字母数字序列分隔）
                 - lines: 行数
        """
        if not text:
            return {
                "chars_with_spaces": 0,
                "chars_without_spaces": 0,
                "words": 0,
                "lines": 0,
            }

        # 行数：按换行符分割
        lines = text.splitlines()
        line_count = len(lines)
        if text.endswith("\n") or text.endswith("\r"):
            line_count += 1

        # 字符数（含空格）
        chars_with_spaces = len(text)

        # 字符数（不含空白字符）
        chars_without_spaces = sum(1 for ch in text if not ch.isspace())

        # 单词数：按非字母数字字符分割，过滤空串
        import re
        words = re.findall(r'\w+', text)
        word_count = len(words)

        return {
            "chars_with_spaces": chars_with_spaces,
            "chars_without_spaces": chars_without_spaces,
            "words": word_count,
            "lines": line_count,
        }

    @staticmethod
    def compute_hash(text: str, algorithm: str = "md5") -> str:
        """
        计算文本的哈希值

        @param text: 输入文本
        @param algorithm: 哈希算法，支持 'md5', 'sha1', 'sha256'
        @return: 十六进制哈希字符串，算法不支持时返回空字符串
        """
        algorithm = algorithm.lower()
        if algorithm == "md5":
            h = hashlib.md5()
        elif algorithm == "sha1":
            h = hashlib.sha1()
        elif algorithm == "sha256":
            h = hashlib.sha256()
        else:
            return ""

        h.update(text.encode("utf-8"))
        return h.hexdigest()

    @staticmethod
    def sort_lines(
        text: str,
        reverse: bool = False,
        numeric: bool = False,
        unique: bool = False,
    ) -> str:
        """
        对文本按行排序

        @param text: 输入文本
        @param reverse: 是否降序排列
        @param numeric: 是否按数值排序
        @param unique: 是否去重
        @return: 排序后的文本
        """
        if not text:
            return ""

        lines = text.splitlines()

        # 保留最后一行是否以换行符结尾
        ends_with_newline = text.endswith("\n") or text.endswith("\r")

        if unique:
            # 使用字典保持首现顺序后再排序
            seen: set = set()
            unique_lines = []
            for line in lines:
                if line not in seen:
                    seen.add(line)
                    unique_lines.append(line)
            lines = unique_lines

        if numeric:
            # 尝试按数值排序
            def numeric_key(s: str):
                s = s.strip()
                try:
                    return float(s)
                except ValueError:
                    return float("inf") if not reverse else float("-inf")

            lines.sort(key=numeric_key, reverse=reverse)
        else:
            lines.sort(reverse=reverse)

        return "\n".join(lines) + ("\n" if ends_with_newline and lines else "")

    @staticmethod
    def convert_case(text: str, mode: str) -> str:
        """
        转换文本大小写

        @param text: 输入文本
        @param mode: 转换模式:
                     - 'upper': 全大写
                     - 'lower': 全小写
                     - 'title': 首字母大写（每个单词）
                     - 'swap': 大小写互换
        @return: 转换后的文本
        """
        mode = mode.lower()
        if mode == "upper":
            return text.upper()
        elif mode == "lower":
            return text.lower()
        elif mode == "title":
            return text.title()
        elif mode == "swap":
            return text.swapcase()
        return text