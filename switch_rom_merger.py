import os
import sys
import shutil
import subprocess
import re
from pathlib import Path
from tqdm import tqdm
import struct
import hashlib
from typing import List, Dict, Tuple, Optional
import logging
import py7zr
import zipfile

# 禁用SSL证书验证
import ssl
try:
    _create_unverified_https_context = ssl._create_unverified_context
except AttributeError:
    # Legacy Python that doesn't verify HTTPS certificates by default
    pass
else:
    # Handle target environment that doesn't support HTTPS verification
    ssl._create_default_https_context = _create_unverified_https_context

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("rom_merger.log")
    ]
)
logger = logging.getLogger(__name__)

class SwitchRomMerger:
    def __init__(self):
        self.supported_extensions = {'.xci', '.xcz', '.nsp', '.nsz'}
        self.output_dir = Path('OUTPUT')
        self.output_dir.mkdir(exist_ok=True)
        self.temp_dir = Path('TEMP')
        self.temp_dir.mkdir(exist_ok=True)
        
        # 密钥和固件路径
        self.keys_file = Path('prod.keys')
        self.title_keys_file = Path('title.keys')
        self.firmware_dir = Path('Firmware')
        
        # 工具路径
        self.tools_dir = Path('tools')
        self.hactoolnet_path = self.tools_dir / "hactoolnet.exe"
        
        # 查找nsz.exe，支持在子目录中查找
        self.nsz_path = None
        if (self.tools_dir / "nsz.exe").exists():
            self.nsz_path = self.tools_dir / "nsz.exe"
        else:
            # 查找nsz子目录
            for item in self.tools_dir.glob("*"):
                if item.is_dir() and (item / "nsz.exe").exists():
                    self.nsz_path = item / "nsz.exe"
                    break
        
        # 检查必要文件
        self._check_required_files()
        
        # 检查必要的工具
        self._setup_tools()
        
    def _check_required_files(self):
        """检查必要的文件是否存在"""
        if not self.keys_file.exists():
            logger.error(f"找不到密钥文件: {self.keys_file}")
            raise FileNotFoundError(f"找不到密钥文件: {self.keys_file}")
        
        if not self.title_keys_file.exists():
            logger.warning(f"找不到标题密钥文件: {self.title_keys_file}")
        
        if not self.firmware_dir.exists() or not any(self.firmware_dir.iterdir()):
            logger.error(f"找不到固件目录或固件目录为空: {self.firmware_dir}")
            raise FileNotFoundError(f"找不到固件目录或固件目录为空: {self.firmware_dir}")
    
    def _setup_tools(self):
        """检查必要的工具"""
        # 创建tools目录
        self.tools_dir.mkdir(exist_ok=True)
        
        # 确保hactoolnet可用
        if not self.hactoolnet_path.exists():
            logger.error("找不到hactoolnet.exe，请手动下载并放置在tools目录下")
            logger.info("您可以从 https://github.com/Thealexbarney/libhac/releases 下载")
            raise FileNotFoundError("找不到hactoolnet.exe")
        else:
            logger.info(f"找到hactoolnet工具: {self.hactoolnet_path}")
        
        # 确保nsz工具可用
        if not self.nsz_path:
            logger.error("找不到nsz.exe，请手动下载并放置在tools目录下")
            logger.info("您可以从 https://github.com/nicoboss/nsz/releases 下载")
            raise FileNotFoundError("找不到nsz.exe")
        else:
            logger.info(f"找到nsz工具: {self.nsz_path}")
        
    def scan_directory(self, directory: Path) -> Dict[str, Dict]:
        """扫描目录并返回按游戏ID分组的文件列表"""
        game_files = {}
        
        logger.info(f"扫描目录: {directory}")
        all_files = list(directory.rglob('*'))
        logger.info(f"找到 {len(all_files)} 个文件，开始筛选Switch游戏文件...")
        
        for file_path in tqdm(all_files, desc="扫描文件"):
            if file_path.is_file() and file_path.suffix.lower() in self.supported_extensions:
                try:
                    # 提取游戏信息
                    game_info = self._extract_game_info(file_path)
                    if game_info:
                        game_id, is_update, is_dlc = game_info
                        
                        if game_id not in game_files:
                            game_files[game_id] = {
                                'base': None,
                                'updates': [],
                                'dlcs': []
                            }
                        
                        # 分类文件
                        if is_dlc:
                            game_files[game_id]['dlcs'].append(file_path)
                        elif is_update:
                            game_files[game_id]['updates'].append(file_path)
                        else:
                            # 基础游戏，只保留一个
                            if not game_files[game_id]['base'] or file_path.stat().st_size > game_files[game_id]['base'].stat().st_size:
                                game_files[game_id]['base'] = file_path
                except Exception as e:
                    logger.error(f"处理文件 {file_path} 时出错: {str(e)}")
        
        # 按游戏名称整理并日志输出
        for game_id, files in game_files.items():
            base_file = files['base']
            updates = files['updates']
            dlcs = files['dlcs']
            
            logger.info(f"游戏: {self._get_game_name(base_file) if base_file else game_id}")
            logger.info(f"  基础游戏: {base_file.name if base_file else '无'}")
            logger.info(f"  更新文件: {len(updates)} 个")
            logger.info(f"  DLC文件: {len(dlcs)} 个")
        
        return game_files
    
    def _extract_game_info(self, file_path: Path) -> Optional[Tuple[str, bool, bool]]:
        """
        从文件路径中提取游戏信息
        返回: (游戏ID, 是否为更新文件, 是否为DLC)
        """
        # 从文件名中提取信息
        filename = file_path.stem
        filepath_str = str(file_path)
        
        # 检查是否包含关键字来判断类型
        is_dlc = 'dlc' in filename.lower() or 'dlc' in filepath_str.lower()
        is_update = ('upd' in filename.lower() or 'update' in filename.lower() or
                    '更新' in filename.lower() or 'patch' in filename.lower() or
                    '补丁' in filename.lower() or 'v1.' in filename.lower() or 'v2.' in filename.lower())
        
        # 尝试从文件路径获取游戏名称
        # 首先检查是否在游戏名称的目录下
        try:
            # 获取文件所在的目录名
            parent_dir = file_path.parent.name
            grandparent_dir = file_path.parent.parent.name
            
            # 如果父目录包含"xci主体"、"upd"或"dlc"等关键字，使用祖父目录名作为游戏名
            if ('xci' in parent_dir.lower() or 'upd' in parent_dir.lower() or 
                'dlc' in parent_dir.lower() or 'nsp' in parent_dir.lower()):
                return grandparent_dir, is_update, is_dlc
        except:
            pass
        
        # 尝试提取ID格式的信息(格式如[XCI][HK][01001F0019804000][1.0.0])
        id_match = re.search(r'\[(?:XCI|UPD|DLC|NSP)[^\]]*\]\[(?:[^\]]*)\]\[([0-9A-F]{16})\]', filename)
        if id_match:
            game_id = id_match.group(1)
            # 如果是16位十六进制ID，使用它
            return game_id, is_update, is_dlc
        
        # 如果文件名格式符合"游戏名_版本_DLC"的格式
        name_match = re.search(r'(.+?)(?:_v?(\d+(?:\.\d+)*))?(?:_(\d+)DLC)?', filename)
        if name_match:
            game_name = name_match.group(1).strip()
            # 使用游戏名称作为ID
            return game_name, is_update, is_dlc
        
        # 如果无法提取，使用文件所在目录的名称作为ID
        try:
            return file_path.parent.name, is_update, is_dlc
        except:
            # 最后的备选方案，使用文件名
            return filename, is_update, is_dlc
    
    def _get_game_name(self, file_path: Path) -> str:
        """从文件路径中获取游戏名称"""
        if file_path:
            return file_path.stem.split('_')[0]
        return "未知游戏"
    
    def get_game_id(self, file_path: Path) -> str:
        """从文件路径中提取游戏ID"""
        game_info = self._extract_game_info(file_path)
        if game_info:
            return game_info[0]
        # 默认方法：使用文件名第一部分
        return file_path.stem.split('_')[0]
    
    def merge_files(self, game_id: str, files_dict: Dict):
        """合并同一游戏的文件"""
        try:
            base_file = files_dict['base']
            updates = files_dict['updates']
            dlcs = files_dict['dlcs']
            
            # 如果没有基础游戏文件，无法合并
            if not base_file:
                logger.warning(f"游戏 {game_id} 没有基础文件，无法合并")
                return
            
            # 创建游戏输出目录
            game_output_dir = self.output_dir / game_id
            game_output_dir.mkdir(exist_ok=True)
            
            # 使用最新版本的更新文件
            latest_update = None
            if updates:
                # 按照文件大小排序，选择最大的（通常是最新的）
                latest_update = max(updates, key=lambda f: f.stat().st_size)
            
            # 合并基础游戏和更新
            logger.info(f"开始合并游戏 {game_id}")
            
            # 输出文件名
            output_filename = f"{game_id}"
            if latest_update:
                # 尝试从更新文件名中提取版本号
                update_version = self._extract_version(latest_update)
                if update_version:
                    output_filename += f"_v{update_version}"
            
            if dlcs:
                output_filename += f"_{len(dlcs)}DLC"
            
            output_filename += ".xci"
            output_path = game_output_dir / output_filename
            
            # 使用专用工具合并文件
            self._merge_with_tools(base_file, latest_update, dlcs, output_path)
            
            logger.info(f"游戏 {game_id} 合并完成，输出文件: {output_path}")
            
        except Exception as e:
            logger.error(f"合并游戏 {game_id} 时出错: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
    
    def _extract_version(self, file_path: Path) -> Optional[str]:
        """从文件名中提取版本号"""
        match = re.search(r'v?(\d+\.\d+(\.\d+)?)', file_path.stem)
        if match:
            return match.group(1)
        return None
    
    def _merge_with_tools(self, base_file: Path, update_file: Optional[Path], dlc_files: List[Path], output_path: Path):
        """使用专用工具合并文件"""
        try:
            # 创建临时工作目录
            temp_dir = self.temp_dir / output_path.stem
            if temp_dir.exists():
                shutil.rmtree(temp_dir)
            temp_dir.mkdir(parents=True)
            
            # 提取基础游戏
            logger.info(f"正在处理基础游戏: {base_file.name}")
            base_extract_dir = temp_dir / "base"
            base_extract_dir.mkdir()
            
            # 根据文件类型解压
            if base_file.suffix.lower() in ['.xci', '.xcz']:
                self._extract_xci(base_file, base_extract_dir)
            elif base_file.suffix.lower() in ['.nsp', '.nsz']:
                self._extract_nsp(base_file, base_extract_dir)
            
            # 如果有更新，处理更新
            if update_file:
                logger.info(f"正在处理更新文件: {update_file.name}")
                update_extract_dir = temp_dir / "update"
                update_extract_dir.mkdir()
                
                # 根据文件类型解压
                if update_file.suffix.lower() in ['.xci', '.xcz']:
                    self._extract_xci(update_file, update_extract_dir)
                elif update_file.suffix.lower() in ['.nsp', '.nsz']:
                    self._extract_nsp(update_file, update_extract_dir)
                
                # 合并更新到基础游戏
                self._apply_update(base_extract_dir, update_extract_dir)
            
            # 处理DLC
            if dlc_files:
                logger.info(f"正在处理 {len(dlc_files)} 个DLC文件")
                dlc_extract_dir = temp_dir / "dlc"
                dlc_extract_dir.mkdir()
                
                for dlc_file in dlc_files:
                    logger.info(f"正在处理DLC: {dlc_file.name}")
                    # 根据文件类型解压
                    if dlc_file.suffix.lower() in ['.xci', '.xcz']:
                        self._extract_xci(dlc_file, dlc_extract_dir)
                    elif dlc_file.suffix.lower() in ['.nsp', '.nsz']:
                        self._extract_nsp(dlc_file, dlc_extract_dir)
                
                # 合并DLC到基础游戏
                self._apply_dlc(base_extract_dir, dlc_extract_dir)
            
            # 重新打包为XCI
            logger.info(f"正在将合并后的游戏打包为XCI: {output_path}")
            self._repack_as_xci(base_extract_dir, output_path)
            
            # 清理临时文件
            shutil.rmtree(temp_dir)
            logger.info(f"清理临时文件完成")
            
        except Exception as e:
            logger.error(f"使用工具合并文件时出错: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            raise
    
    def _extract_xci(self, xci_file: Path, output_dir: Path):
        """解压XCI/XCZ文件"""
        logger.info(f"解压 {xci_file} 到 {output_dir}")
        
        # 如果是XCZ文件，需要先解压为XCI
        if xci_file.suffix.lower() == '.xcz':
            temp_xci = self.temp_dir / f"{xci_file.stem}.xci"
            
            # 使用nsz工具解压XCZ
            cmd = [
                str(self.nsz_path),
                "-D", str(xci_file),
                "-o", str(self.temp_dir)
            ]
            
            logger.info(f"执行命令: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                logger.error(f"解压XCZ失败: {result.stderr}")
                raise RuntimeError(f"解压XCZ失败: {result.stderr}")
            
            xci_file = temp_xci
        
        # 使用hactoolnet解压XCI
        cmd = [
            str(self.hactoolnet_path),
            "--keyset=" + str(self.keys_file),
            "-t", "xci", "--securedir=" + str(output_dir),
            str(xci_file)
        ]
        
        logger.info(f"执行命令: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            logger.error(f"解压XCI失败: {result.stderr}")
            raise RuntimeError(f"解压XCI失败: {result.stderr}")
    
    def _extract_nsp(self, nsp_file: Path, output_dir: Path):
        """解压NSP/NSZ文件"""
        logger.info(f"解压 {nsp_file} 到 {output_dir}")
        
        # 如果是NSZ文件，需要先解压为NSP
        if nsp_file.suffix.lower() == '.nsz':
            temp_nsp = self.temp_dir / f"{nsp_file.stem}.nsp"
            
            # 使用nsz工具解压NSZ
            cmd = [
                str(self.nsz_path),
                "-D", str(nsp_file),
                "-o", str(self.temp_dir)
            ]
            
            logger.info(f"执行命令: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                logger.error(f"解压NSZ失败: {result.stderr}")
                raise RuntimeError(f"解压NSZ失败: {result.stderr}")
            
            nsp_file = temp_nsp
        
        # 使用hactoolnet解压NSP
        cmd = [
            str(self.hactoolnet_path),
            "--keyset=" + str(self.keys_file),
            "-t", "pfs0", "--outdir=" + str(output_dir),
            str(nsp_file)
        ]
        
        logger.info(f"执行命令: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            logger.error(f"解压NSP失败: {result.stderr}")
            raise RuntimeError(f"解压NSP失败: {result.stderr}")
    
    def _apply_update(self, base_dir: Path, update_dir: Path):
        """将更新应用到基础游戏"""
        logger.info(f"应用更新到基础游戏")
        
        # 合并更新文件到基础游戏目录
        for update_file in update_dir.glob('**/*'):
            if update_file.is_file():
                # 计算相对路径
                rel_path = update_file.relative_to(update_dir)
                target_path = base_dir / rel_path
                
                # 确保目标目录存在
                target_path.parent.mkdir(parents=True, exist_ok=True)
                
                # 复制更新文件到基础游戏目录
                shutil.copy2(update_file, target_path)
    
    def _apply_dlc(self, base_dir: Path, dlc_dir: Path):
        """将DLC应用到基础游戏"""
        logger.info(f"应用DLC到基础游戏")
        
        # 合并DLC文件到基础游戏目录
        for dlc_file in dlc_dir.glob('**/*'):
            if dlc_file.is_file():
                # 计算相对路径
                rel_path = dlc_file.relative_to(dlc_dir)
                target_path = base_dir / rel_path
                
                # 确保目标目录存在
                target_path.parent.mkdir(parents=True, exist_ok=True)
                
                # 复制DLC文件到基础游戏目录
                shutil.copy2(dlc_file, target_path)
    
    def _repack_as_xci(self, input_dir: Path, output_file: Path):
        """将目录重新打包为XCI文件"""
        logger.info(f"重新打包为XCI: {output_file}")
        
        # 使用hactoolnet打包为XCI
        cmd = [
            str(self.hactoolnet_path),
            "--keyset=" + str(self.keys_file),
            "-t", "xci", "--create=" + str(output_file),
            "--securedir=" + str(input_dir)
        ]
        
        logger.info(f"执行命令: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            logger.error(f"打包XCI失败: {result.stderr}")
            raise RuntimeError(f"打包XCI失败: {result.stderr}")
    
    def process_directory(self, directory: Path):
        """处理指定目录下的所有Switch游戏文件"""
        logger.info(f"开始处理目录: {directory}")
        
        # 扫描文件
        game_files = self.scan_directory(directory)
        
        # 处理每个游戏
        for game_id, files_dict in tqdm(game_files.items(), desc="合并游戏"):
            self.merge_files(game_id, files_dict)
        
        logger.info("处理完成")

def main():
    try:
        # 全局禁用SSL证书验证
        os.environ['PYTHONHTTPSVERIFY'] = '0'
        
        # 获取当前目录
        current_dir = Path.cwd()
        
        # 检查是否有特定的ROM目录
        rom_dir = current_dir / "rom"
        if rom_dir.exists() and rom_dir.is_dir():
            logger.info(f"找到ROM目录: {rom_dir}")
            target_dir = rom_dir
        else:
            logger.info(f"未找到ROM目录，使用当前目录: {current_dir}")
            target_dir = current_dir
        
        # 创建合并器实例
        merger = SwitchRomMerger()
        
        # 处理目标目录
        merger.process_directory(target_dir)
        
    except Exception as e:
        logger.error(f"发生错误: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        logger.info("程序异常终止")
        sys.exit(1)

if __name__ == "__main__":
    main() 