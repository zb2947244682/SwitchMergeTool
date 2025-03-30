# Switch ROM 管理工具

这是一个用于管理任天堂Switch游戏ROM的工具，可以自动整理游戏文件、更新和DLC，使它们组织得更有条理。

## 主要功能

- 自动扫描识别Switch游戏文件(XCI, XCZ, NSP, NSZ)
- 将相同游戏的各个部分(基础游戏、更新、DLC)归类到一起
- 解压缩NSZ和XCZ格式为NSP和XCI格式
- 创建合理的目录结构方便管理和使用
- 提供GUI界面方便操作

## 目录结构

处理后的游戏文件将按以下结构整理:

```
output/
  └── 游戏名称/
      ├── 游戏名称.xci           # 基础游戏XCI文件
      ├── UPDATE/                # 更新文件目录
      │   ├── update1.nsp
      │   └── update2.nsp
      └── DLC/                   # DLC文件目录
          ├── dlc1.nsp
          └── dlc2.nsp
```

## 使用方法

### 命令行使用

1. 运行`start.bat`一键整理游戏文件
2. 运行`python switch_rom_merger.py --scan-only`仅扫描游戏文件
3. 运行`python switch_rom_merger.py --game-id "游戏名称"`处理特定游戏

### GUI界面使用

1. 运行`start_gui.bat`启动图形界面
2. 选择要处理的选项并按照提示操作

## 安装环境

本工具需要Python 3.6或更高版本以及以下依赖库:

- tqdm
- py7zr
- pillow (GUI界面需要)
- tkinter (GUI界面需要)

安装依赖:

1. 运行`install_deps.bat`安装依赖
2. 如需使用国内镜像源，运行`install_deps_mirror.bat`

## 必要的外部工具

本工具需要以下外部工具才能正常工作:

1. **hactoolnet** - 用于处理XCI和NSP文件
2. **nsz** - 用于解压缩NSZ和XCZ文件

这些工具需要放在`tools`目录下。

## 密钥文件

处理Switch游戏文件需要正确的密钥文件(`prod.keys`)，可以放置在以下位置之一:

- 工具根目录
- `~/.switch/prod.keys`
- `~/switch/prod.keys`
- `tools/keys.txt`

## 创建完整合并的XCI文件

虽然本工具可以整理游戏文件，但创建真正包含更新和DLC的完整XCI需要使用专门的工具:

### 使用SAK工具合并

1. 下载SAK工具：https://github.com/dezem/SAK
2. 将整理好的基础游戏、更新和DLC文件添加到SAK
3. 使用SAK的"完整合并"选项创建包含更新和DLC的单一XCI文件

### 使用NSC_BUILDER合并

1. 下载NSC_BUILDER汉化版：https://github.com/zdm65477730/NSC_BUILDER/releases
2. 将基础游戏、更新和DLC文件放在同一文件夹中
3. 使用"多文件处理"功能(输入2)
4. 将文件夹拖入窗口
5. 选择"重新打包列表为XCI"选项

## 问题排查

1. **找不到工具**: 确保hactoolnet.exe和nsz.exe已正确放置在tools目录中
2. **密钥错误**: 确保prod.keys文件包含正确的密钥并放在支持的位置
3. **解压错误**: 检查ROM文件是否完整，尝试单独使用nsz工具解压
4. **YUZU无法识别合并的XCI**: 请使用SAK或NSC_BUILDER创建真正的合并XCI

## 注意事项

- 本工具不提供任何游戏ROM文件
- 仅用于个人备份使用，请遵守当地法律法规
- 不支持在线更新，需手动更新工具

## 许可证

本工具使用MIT许可证。 