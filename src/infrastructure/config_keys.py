"""
配置键名常量模块 —— 集中定义所有配置项的键名

避免魔法字符串散布各处，提升配置可维护性。
修改配置键名时只需更新此文件。
"""


class ConfigKey:
    """! 配置键名常量集合

    集中管理所有配置项的键名字符串，
    避免在代码中使用魔法字符串。
    """

    ## 编辑器字体大小
    FONT_SIZE = "font_size"
    ## 编辑器字体族
    FONT_FAMILY = "font_family"
    ## 主题名称
    THEME = "theme"
    ## 是否显示行号
    SHOW_LINE_NUMBERS = "show_line_numbers"
    ## 是否自动换行
    WORD_WRAP = "word_wrap"
    ## 是否自动缩进
    AUTO_INDENT = "auto_indent"
    ## 是否自动补全括号
    BRACKET_COMPLETION = "bracket_completion"
    ## Tab 宽度（空格数）
    TAB_WIDTH = "tab_width"
    ## 是否减少动画效果
    REDUCE_ANIMATION = "reduce_animation"
    ## 是否首次启动
    FIRST_RUN = "first_run"
    ## 编辑器配色方案
    EDITOR_COLORS = "editor_colors"

    ## 关闭窗口时最小化到系统托盘
    CLOSE_TO_TRAY = "close_to_tray"
    ## 启动时最小化到系统托盘
    START_MINIMIZED_TO_TRAY = "start_minimized_to_tray"
