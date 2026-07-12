## `main_window.py` 微架构拆分方案

### 核心思路

按 **单一职责** 原则，将当前 MainWindow 中松耦合的 UI 子组件和独立行为模块提取为 `src/ui/` 下的独立类。MainWindow 保留为纯粹的**编排器**（orchestrator），负责初始化、信号连接、生命周期管理。

---

### 拆分后的模块结构

#### 1. `welcome_page.py`（新建，~220 行）

**提取内容**：
- `_create_welcome_page()` → 提取为 `WelcomePage(QWidget)` 类
- `_show_welcome_page()` → `WelcomePage.show()`
- `_welcome_tab_exists()` → 合并入 WelcomePage
- `_hide_welcome_page()` → 合并入 WelcomePage
- `_update_welcome_visibility()` → 保留在 MainWindow（涉及 TabManager 交互）
- `_update_welcome_theme_buttons()` → WelcomePage 实例方法
- `_closing_welcome` 相关逻辑 → 保留在 MainWindow

**依赖注入**：接收 `theme_service, action_manager`（或通过信号回调）
**信号**：`theme_changed_requested(str)`, `new_file_requested()`, `open_file_requested()`

#### 2. `menu_manager.py`（新建，~500 行）

**提取内容**：
- `_create_menu_bar()` → `MenuBarManager.create_menu_bar()`
- 所有 `_show_*_menu()`（文件/编辑/视图/工具/语法/帮助）→ MenuBarManager 方法
- 所有 `_populate_*()`（编码/最近文件/行操作/大小写/主题/缩放/行操作子菜单）→ MenuBarManager 方法
- `_create_delete_action()`, `_create_sort_dedup_action()` → MenuBarManager 工厂方法
- `_show_language_picker_dialog()` → 保持为 MenuBarManager 方法
- `_on_syntax_auto_detect_toggled()` → MenuBarManager 方法
- `_apply_language_to_tab()` → 提取到 `syntax_service.py` 或保留在 MenuBarManager

**依赖注入**：`action_manager, tab_manager, file_service, theme_service, config_service, signal_bus, status_bar_widget`
**信号**：菜单按钮需发射信号让 MainWindow 处理（如 `open_recent_file(str)`）

#### 3. `search_result_panel.py`（新建，~280 行）

**提取内容**：
- `_create_search_result_panel()` → `SearchResultPanel(QWidget)` 类
- `_show_search_result_panel()` → 实例方法
- `_hide_search_result_panel()` → 实例方法
- `_perform_multi_file_search()` → SearchResultPanel 方法
- `_on_search_result_double_clicked()` → SearchResultPanel 方法
- `_find_in_files()` → SearchResultPanel 方法（或保留公共入口）
- `_on_search_panel_search()` → SearchResultPanel 方法
- 所有相关成员变量（`_search_result_panel`, `_search_result_input`, `_search_result_btn`, `_search_result_status`, `_search_result_tree`）→ SearchResultPanel 属性

**依赖注入**：`tab_manager, signal_bus, parent`
**信号**：`navigate_to_match(tab_index, line_num, search_text)` → MainWindow 处理标签切换和光标定位

#### 4. `split_view_manager.py`（新建，~100 行）

**提取内容**：
- `_toggle_split()` → `SplitViewManager` 方法
- `_open_split_view()` → SplitViewManager 方法
- `_close_split_view()` → SplitViewManager 方法
- `_set_focus_side()` → SplitViewManager 方法
- 分屏相关状态变量（`_split_active`, `_split_orientation`, `_split_editor`, `_focus_side`, `_panel_tab_index`, `_syncing_tab`）→ SplitViewManager 属性

**依赖注入**：`tab_manager, signal_bus, tab_widget, main_splitter, splitter`

#### 5. `syntax_helper.py`（新建，~100 行）

**提取内容**：
- `_apply_language_to_tab()` 中与高亮器创建和主题应用的纯逻辑
- 从 MenuManager 和 MainWindow 中抽离"清旧高亮器→创建新高亮器→应用配色→rehighlight"的重复模式

**设计**：无状态工具类/模块级函数，纯逻辑不涉及 UI

---

### 保留在 MainWindow 中的内容（约 1500 行）

| 模块 | 说明 |
|------|------|
| `__init__` | 服务/控制器/UI 编排，保持构造顺序不变 |
| `closeEvent` + `_save_full_session` | 关闭生命周期 |
| `_exec_tristate_dialog` | UI 工具方法 |
| `init_ui` | 组合子组件（更新调用方式） |
| `init_editor_interface` | EditorTabWidget 创建、splitter 布局、状态栏/搜索栏添加 |
| `init_command_bar` | CommandBar 创建 |
| `_populate_menus_and_toolbar` | 简化，委托 MenuManager |
| `_add_command_bar_actions` | 保留 |
| `connect_signals` | 简化，添加与子组件信号的连接 |
| `_bind_editor_signals` | 保留 |
| 所有 `_on_*` 信号槽 | 核心事件处理（tab/文件/搜索/编码/主题/配置变更） |
| 编辑操作（`_on_delete*` 等） | 保留 |
| `_load_config_and_theme` | 保留 |
| `_restore_session` | 保留 |
| `_process_cli_args` + `_apply_cursor_position` | 保留 |
| `_on_open_recent_file` 等 | 保留（委托 MenuManager 发射信号） |
| 右键上下文菜单 | `eventFilter` + `_show_editor_context_menu` |
| 拖拽 | `dragEnterEvent`, `dropEvent`, `_open_dropped_file` |
| 文件外部修改 | `_on_file_externally_modified`, `_reload_file` |
| 全屏 | `toggle_fullscreen`, `changeEvent` |
| 打印/导出PDF | `_on_print`, `_export_pdf` |
| 公共接口方法 | `export_pdf`, `confirm_close_unsaved_tab`, 等 |

---

### 依赖关系

```
main_window.py
├── menu_manager.py          (构造器注入：action_mgr, tab_mgr, services, signal_bus)
├── welcome_page.py          (构造器注入：theme_service, action_manager)
├── search_result_panel.py   (构造器注入：tab_manager, signal_bus)
├── split_view_manager.py    (构造器注入：tab_manager, signal_bus, tab_widget, splitter)
└── syntax_helper.py         (模块级函数，无状态)
```

MainWindow 与子组件之间通过 **Qt 信号** 通信：
- `welcome_page.new_file_requested` → `MainWindow._on_new_tab_requested`
- `welcome_page.open_file_requested` → `MainWindow._action_manager.open_file()`
- `welcome_page.theme_changed_requested` → `MainWindow._on_theme_change`
- `menu_manager.open_recent_file_requested` → `MainWindow._on_open_recent_file`
- `menu_manager.encoding_changed_requested` → `MainWindow._on_encoding_changed`
- `search_result_panel.navigate_to_match` → `MainWindow._on_search_result_navigate`
- `split_view_manager.status_message` → `MainWindow._on_status_message`
