# 交换机巡检工具 v1.2.1

基于 PySide6 的交换机巡检工具，支持华为、新华三和思科设备，采用“左侧工具导航 + 右侧工具面板”的壳结构，工具由 `config/tools.yaml` 注册表驱动。

## 运行

```powershell
cd network-box
python scripts\gui_app.py
```

## 巡检模板

- 华为 VRP：`config/HW-command.yaml`
- 新华三 Comware：`config/H3C-command.yaml`
- 思科 IOS：`config/Cisco-command.yaml`

新华三不同型号和 Comware 版本可能不支持个别 `display` 子命令；不支持时仅该条命令失败，不影响同一设备的其他巡检命令。

## 厂商识别

设备管理页的设备类型可选择“自动识别”。完成连接测试后，程序会通过 Netmiko 和版本命令识别华为、新华三或思科，并将识别结果写回设备列表。SSH 和 Telnet 均支持自动识别。

## 自定义巡检命令

程序首次运行时会在 EXE 同目录创建 `config` 文件夹，并将内置 YAML 模板复制进去。修改 `HW-command.yaml`、`H3C-command.yaml` 或 `Cisco-command.yaml` 后，在巡检执行页点击“重新加载配置”即可刷新命令列表。已有外部 YAML 不会被程序覆盖。

## 目录结构

```text
network-box/
  config/
    tools.yaml          # 工具注册表
    HW-command.yaml     # 华为 VRP 巡检命令模板
    H3C-command.yaml    # 新华三 Comware 巡检命令模板
    Cisco-command.yaml  # 思科 IOS 巡检命令模板
  core/
    registry.py         # 注册表加载与面板实例化
    executor_async.py   # SSH/Telnet 批量巡检线程
    config_backup_worker.py # 华为/新华三/思科设备配置保存线程
    snmp_worker.py      # SNMP 测试线程
    cmd_worker.py       # CMD 命令执行线程
    config_loader.py    # YAML 配置加载
  ui/
    toolbox_window.py   # 工具箱主窗口（壳）
    device_manager.py   # 设备管理
    config_compare_panel.py # 配置导入、导出与比较
    snmp_panel.py       # SNMP 测试
    inspection_panel.py # 批量巡检
    result_panel.py     # 结果查看
    cmd_panel.py        # CMD 命令面板（Ping/Tracert）
  scripts/
    gui_app.py          # 程序入口
```

## 如何添加新工具

1. 在 `ui/` 下新建一个继承 `QWidget` 的面板类。
2. 在 `config/tools.yaml` 的对应分类下增加一条记录：

```yaml
- id: my_tool
  name: 我的工具
  description: 工具说明
  panel: ui.my_tool:MyToolPanel
```

重启程序后，新工具会自动出现在左侧导航中。
