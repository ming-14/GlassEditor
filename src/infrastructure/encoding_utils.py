"""
编码工具模块 -- 编码转换相关的常量与工具函数

提供编码菜单分组定义、编码显示名称映射、编码转换核心逻辑。
设计依据: doc/功能.md 编码转换功能
"""

import codecs
from typing import Dict, List, Tuple, Optional

from src.infrastructure.logger import get_logger

_logger = get_logger("encoding_utils")

## 编码转换文件大小上限（50MB），超过此大小禁用编码转换
ENCODING_CHANGE_MAX_FILE_SIZE = 50 * 1024 * 1024

## 编码菜单分组定义（分组名 -> 内部编码名列表）
ENCODING_MENU_GROUPS: Dict[str, List[str]] = {
    "Unicode": [
        "utf-8", "utf-8-sig", "utf-16", "utf-16-be", "utf-16-le",
        "utf-32", "utf-32-be", "utf-32-le",
    ],
    "简体中文": ["gbk", "gb2312", "gb18030"],
    "繁体中文": ["big5", "big5hkscs"],
    "日文": ["shift-jis", "euc-jp", "iso-2022-jp"],
    "韩文": ["euc-kr", "cp949"],
    "西欧": ["iso-8859-1", "iso-8859-15", "windows-1252"],
    "其他": ["ascii", "mac-roman", "tis-620"],
}

## 内部编码名 -> 友好显示名称的映射
ENCODING_DISPLAY_NAMES: Dict[str, str] = {
    "utf-8": "UTF-8",
    "utf-8-sig": "UTF-8 with BOM",
    "utf-16": "UTF-16",
    "utf-16-be": "UTF-16 BE",
    "utf-16-le": "UTF-16 LE",
    "utf-32": "UTF-32",
    "utf-32-be": "UTF-32 BE",
    "utf-32-le": "UTF-32 LE",
    "gbk": "GBK",
    "gb2312": "GB2312",
    "gb18030": "GB18030",
    "big5": "Big5",
    "big5hkscs": "Big5-HKSCS",
    "shift-jis": "Shift-JIS",
    "euc-jp": "EUC-JP",
    "iso-2022-jp": "ISO-2022-JP",
    "euc-kr": "EUC-KR",
    "cp949": "CP949",
    "iso-8859-1": "ISO-8859-1",
    "iso-8859-15": "ISO-8859-15",
    "windows-1252": "Windows-1252",
    "ascii": "ASCII",
    "mac-roman": "MacRoman",
    "tis-620": "TIS-620",
}

## 状态栏显示名 -> 内部编码名的反向映射（用于从状态栏选择转回内部编码名）
DISPLAY_TO_INTERNAL: Dict[str, str] = {v: k for k, v in ENCODING_DISPLAY_NAMES.items()}


def get_display_name(internal_name: str) -> str:
    """! @brief 获取编码的友好显示名称

    @param internal_name 内部编码名称（如 'utf-8-sig'）
    @return 显示名称（如 'UTF-8 with BOM'），未映射时返回原名称大写
    """
    if internal_name in ENCODING_DISPLAY_NAMES:
        return ENCODING_DISPLAY_NAMES[internal_name]
    return internal_name.upper()


def get_internal_name(display_name: str) -> str:
    """! @brief 从显示名称获取内部编码名

    @param display_name 显示名称（如 'UTF-8 with BOM'）
    @return 内部编码名称（如 'utf-8-sig'），未映射时返回小写原名称
    """
    if display_name in DISPLAY_TO_INTERNAL:
        return DISPLAY_TO_INTERNAL[display_name]
    return display_name.lower()


def get_status_bar_encoding(internal_name: str) -> str:
    """! @brief 获取状态栏上应显示的编码文本

    特殊处理 UTF-8 BOM 的显示。

    @param internal_name 内部编码名称
    @return 状态栏显示文本
    """
    if internal_name == "utf-8-sig":
        return "UTF-8-BOM"
    return get_display_name(internal_name)


def is_encoding_available(encoding_name: str) -> bool:
    """! @brief 检查编码是否在当前 Python 环境中可用

    @param encoding_name 内部编码名称
    @return True 表示可用
    """
    try:
        codecs.lookup(encoding_name)
        return True
    except LookupError:
        return False


def try_encode_content(
    content: str,
    target_encoding: str,
) -> Tuple[bytes, Optional[str], Optional[List[Tuple[int, str]]]]:
    """! @brief 尝试将文本内容编码为目标编码

    @param content Unicode 文本内容
    @param target_encoding 目标编码名称
    @return (编码后的字节流, 错误消息, 无法编码的字符列表)
            成功时错误消息和字符列表均为 None；
            失败时字节流为空，错误消息非 None，字符列表包含前5个无法编码的字符及其位置
    """
    try:
        encoded = content.encode(target_encoding)
        return encoded, None, None
    except UnicodeEncodeError as e:
        _logger.warning(
            f"编码转换失败: 无法用 {target_encoding} 编码全部内容",
            error=str(e),
        )
        bad_chars = _find_unencodable_chars(content, target_encoding)
        err_msg = _build_encode_error_message(target_encoding, bad_chars)
        return b"", err_msg, bad_chars


def _find_unencodable_chars(
    content: str,
    target_encoding: str,
    max_count: int = 5,
) -> List[Tuple[int, str]]:
    """! @brief 查找文本中无法用目标编码表示的字符

    使用二分法逐字符检测，仅返回前 max_count 个。

    @param content 文本内容
    @param target_encoding 目标编码
    @param max_count 最大返回数量
    @return [(字符位置, 字符), ...] 列表
    """
    bad_chars: List[Tuple[int, str]] = []
    for i, ch in enumerate(content):
        try:
            ch.encode(target_encoding)
        except UnicodeEncodeError:
            bad_chars.append((i, ch))
            if len(bad_chars) >= max_count:
                break
    return bad_chars


def _build_encode_error_message(
    target_encoding: str,
    bad_chars: Optional[List[Tuple[int, str]]],
) -> str:
    """! @brief 构建编码错误的用户友好错误消息

    @param target_encoding 目标编码名称
    @param bad_chars 无法编码的字符列表
    @return 错误消息字符串
    """
    display = get_display_name(target_encoding)
    if not bad_chars:
        return f"无法转换到 {display}，部分字符无法编码。"

    char_details = []
    for pos, ch in bad_chars:
        char_details.append(f"位置 {pos}: '{ch}' (U+{ord(ch):04X})")
    details_str = "\n".join(char_details)

    return (
        f"无法转换到 {display}，以下字符无法编码：\n{details_str}\n\n"
        f"建议：使用 GB18030 等更宽编码，或修改文本内容。"
    )


def get_all_available_encodings() -> Dict[str, List[str]]:
    """! @brief 获取所有可用编码的分组字典（过滤掉不可用的编码）

    @return {分组名: [可用内部编码名列表]}
    """
    result: Dict[str, List[str]] = {}
    for group, encodings in ENCODING_MENU_GROUPS.items():
        available = [e for e in encodings if is_encoding_available(e)]
        if available:
            result[group] = available
    return result


def force_encode_content(
    content: str,
    target_encoding: str,
) -> Tuple[bytes, int]:
    """! @brief 强制将文本内容编码为目标编码，清除无法编码的字符

    使用 errors='ignore' 策略，跳过所有无法用目标编码表示的字符。
    返回编码后的字节流和被清除的字符数量。

    @param content Unicode 文本内容
    @param target_encoding 目标编码名称
    @return (编码后的字节流, 被清除的字符数量)
    """
    removed_count = 0
    filtered_chars: List[str] = []
    for ch in content:
        try:
            ch.encode(target_encoding)
            filtered_chars.append(ch)
        except UnicodeEncodeError:
            removed_count += 1

    filtered_content = "".join(filtered_chars)
    encoded = filtered_content.encode(target_encoding)

    _logger.info(
        f"强制编码: {target_encoding}, 清除 {removed_count} 个无法编码的字符",
    )
    return encoded, removed_count
