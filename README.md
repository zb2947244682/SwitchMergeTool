# Switch游戏合并工具

这个工具可以合并Switch游戏本体（XCI/XCZ）和其各种DLC和升级补丁（NSP/NSZ），生成完整的XCI文件。

## 功能

- 递归扫描目录中的Switch游戏文件（XCI、XCZ、NSP、NSZ）
- 自动识别同一游戏的本体、DLC和补丁
- 将相关文件合并为完整的XCI格式
- 支持按游戏名称归类输出结果

## 使用前准备

1. 确保已安装Python 3.8或更高版本
2. 下载以下必要工具并放置在`tools`目录下：
   - [hactoolnet](https://github.com/Thealexbarney/libhac/releases) - 用于解包和重新打包XCI/NSP文件
   - [nsz](https://github.com/nicoboss/nsz/releases) - 用于处理NSZ/XCZ压缩文件

3. 确保以下文件/目录位于工具同级目录：
   - `prod.keys` - 产品密钥文件
   - `title.keys` - 标题密钥文件（可选）
   - `Firmware` - 固件目录，包含Switch固件文件

4. **重要**：安装Microsoft Visual C++ Build Tools
   - 访问 https://visualstudio.microsoft.com/visual-cpp-build-tools/
   - 下载并安装C++构建工具
   - 如果不安装此工具，将只能使用简化版功能（只复制基础游戏文件）

## 使用方法

1. 将你需要处理的游戏文件放在工具所在目录下的`rom`文件夹中
   - 或者直接放在工具同级目录中
   - 支持子目录，会递归搜索所有符合条件的文件

2. 文件命名格式示例：
   - 本体：`塞尔达传说：旷野之息.xci`或`塞尔达传说：旷野之息_v1.0.0.xci`
   - 补丁：`塞尔达传说：旷野之息_v1.6.0.nsp`或包含`update`/`patch`关键字
   - DLC：`塞尔达传说：旷野之息_DLC.nsp`或包含`dlc`关键字

3. 双击运行`merge_switch_roms.bat`

4. 处理完成后，合并的游戏文件会保存到`OUTPUT`目录中

## 依赖库安装问题

如果在安装Python依赖时遇到问题：

1. SSL证书验证失败：
   - 运行`install_deps_mirror.bat`使用国内镜像
   - 或参考`SSL问题解决方案.txt`中的方法

2. C++编译环境问题：
   - 错误信息：`Microsoft Visual C++ 14.0 or greater is required`
   - 解决方法参考`C编译环境问题解决方案.txt`
   - 如果不安装C++编译环境，工具会以简化模式运行（只复制基础游戏文件）

## 注意事项

- 原始文件不会被修改
- 临时文件会保存在`TEMP`目录，处理完成后会被清理
- 日志文件会保存在`rom_merger.log`，可用于排查问题
- 对于有多个版本的基础游戏文件，会选择文件大小最大的一个
- 对于多个更新文件，会选择文件大小最大的一个（通常是最新版本）

## 故障排除

1. 如果遇到"找不到hactoolnet.exe"或"找不到nsz.exe"错误：
   - 请确保已下载这些工具并放置在`tools`目录下

2. 如果遇到"找不到密钥文件"错误：
   - 请确保`prod.keys`文件位于工具同级目录

3. 如果合并过程中出现错误：
   - 检查日志文件`rom_merger.log`获取详细信息
   - 确保游戏文件完整且未损坏
   - 确保密钥文件包含正确的密钥

4. 如果依赖安装失败：
   - 参考`SSL问题解决方案.txt`和`C编译环境问题解决方案.txt` 