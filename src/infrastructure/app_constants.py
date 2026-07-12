"""
应用常量模块 —— 集中定义所有硬编码的数值常量

避免魔法数字散布各处，提升可维护性。
修改常量值时只需更新此文件。
"""


class AppConstant:
    """! 应用常量集合

    集中管理所有硬编码的数值常量，
    避免在代码中使用魔法数字。
    """

    ## 主窗口最小宽度（像素）
    MIN_WINDOW_WIDTH = 800
    ## 主窗口最小高度（像素）
    MIN_WINDOW_HEIGHT = 600
    ## 主窗口默认宽度（像素）
    DEFAULT_WINDOW_WIDTH = 1200
    ## 主窗口默认高度（像素）
    DEFAULT_WINDOW_HEIGHT = 800

    ## 大文件阈值（字节），10MB
    LARGE_FILE_THRESHOLD = 10 * 1024 * 1024
    ## 语法高亮禁用阈值（字节），5MB
    HIGHLIGHT_DISABLE_THRESHOLD = 5 * 1024 * 1024

    ## 最近文件列表最大条数
    MAX_RECENT_FILES = 20
    ## 未命名标签页数量上限
    MAX_UNTITLED_TABS = 99

    ## 会话自动保存间隔（毫秒）
    AUTO_SAVE_INTERVAL_MS = 30000
    ## 搜索延迟（毫秒）
    SEARCH_DELAY_MS = 150
    ## 状态栏消息默认持续时间（毫秒）
    STATUS_MESSAGE_DURATION_MS = 3000

    ## 多光标编辑最大光标数
    MAX_CURSORS = 100
    ## 编辑器内容区域水平内边距（像素）
    EDITOR_HORIZONTAL_PADDING = 16
    ## 行号区域与编辑文本间距（像素）
    LINE_NUMBER_GAP = 8

    ## 批量替换确认阈值
    BATCH_REPLACE_CONFIRM_THRESHOLD = 500
    ## 多文件搜索标签页数量警告阈值
    MULTI_FILE_SEARCH_TAB_WARNING = 20
    ## 搜索结果行截断长度
    SEARCH_RESULT_LINE_TRUNCATE = 150
    ## 最近文件路径显示截断长度
    RECENT_FILE_PATH_TRUNCATE = 80

    ## 查找结果面板最小宽度（像素）
    SEARCH_PANEL_MIN_WIDTH = 180
    ## 查找结果面板最大宽度（像素）
    SEARCH_PANEL_MAX_WIDTH = 400
    ## 欢迎页卡片最大宽度（像素）
    WELCOME_CARD_MAX_WIDTH = 700
    ## 欢迎页卡片最大高度（像素）
    WELCOME_CARD_MAX_HEIGHT = 650

    ## 编码转换文件大小上限（字节），50MB
    ENCODING_CHANGE_MAX_FILE_SIZE = 50 * 1024 * 1024

    ## IPC 连接超时（毫秒）
    IPC_TIMEOUT_MS = 3000
    ## IPC 本地服务器名称
    IPC_SERVER_NAME = "GlassEditorIPC"
    ## IPC 帧头部长度（字节），4字节大端 uint32
    IPC_HEADER_SIZE = 4

    ## 系统托盘提示文本
    TRAY_TOOLTIP = "琉璃编辑器 - GlassEditor"
