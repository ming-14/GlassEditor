"""对话框模块

本模块对话框均继承 qfluentwidgets 的 MessageBoxBase，其基类 MaskDialogBase 在构造时
即读取 parent.width()/height()，故 parent 不可为 None；离屏/测试场景须传宿主窗口。
"""
