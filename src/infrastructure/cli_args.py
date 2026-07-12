"""! @brief 命令行参数数据类

定义 ParsedArgs 数据类，将 Click 解析后的命令行参数
封装为结构化对象，供 MainWindow 初始化流程使用。
"""
from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class ParsedArgs:
    """! @brief 命令行解析结果数据类

    将 Click 解析后的参数封装为结构化对象，
    供 MainWindow 初始化流程使用。

    @var files:     待打开的文件路径列表（已规范化为绝对路径）
    @var line:      跳转目标行号（None 表示不跳转）
    @var column:    跳转目标列号（None 表示不跳转）
    @var encoding:  指定的文件编码（None 表示自动检测）
    """
    files: List[str] = field(default_factory=list)
    line: Optional[int] = None
    column: Optional[int] = None
    encoding: Optional[str] = None
    ## 禁止托盘图标（CLI 覆盖）
    no_tray: bool = False
    ## 启动时最小化（仅本次启动覆盖配置）
    minimized: bool = False
