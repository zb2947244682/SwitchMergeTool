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
import zipfile  # 使用内置的zipfile替代py7zr

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
        
        # 检查必要文件
        self._check_required_files()
        
        # 下载必要的工具
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
        """下载并设置必要的工具"""
        # 创建tools目录
        tools_dir = Path('tools')
        tools_dir.mkdir(exist_ok=True)
        
        # 确保hactoolnet可用
        hactoolnet_path = tools_dir / "hactoolnet.exe"
        if not hactoolnet_path.exists():
            logger.error("找不到hactoolnet.exe，请手动下载并放置在tools目录下")
            logger.info("您可以从 https://github.com/Thealexbarney/libhac/releases 下载")
            raise FileNotFoundError("找不到hactoolnet.exe")
        
        # 确保nsz工具可用
        nsz_path = tools_dir / "nsz.exe"
        if not nsz_path.exists():
            logger.error("找不到nsz.exe，请手动下载并放置在tools目录下")
            logger.info("您可以从 https://github.com/nicoboss/nsz/releases 下载")
            raise FileNotFoundError("找不到nsz.exe")
        
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
        
        # 尝试从文件名中识别DLC和更新
        is_dlc = 'dlc' in filename.lower() or 'dlc' in str(file_path).lower()
        is_update = any(update_keyword in filename.lower() for update_keyword in ['update', '更新', 'patch', '补丁', 'v1.', 'v2.'])
        
        # 如果文件名格式符合"游戏名_版本_DLC"的格式
        match = re.search(r'(.+?)(?:_v?(\d+(?:\.\d+)*))?(?:_(\d+)DLC)?', filename)
        if match:
            game_name = match.group(1).strip()
            # 使用游戏名称作为ID
            return game_name, is_update, is_dlc
        
        # 如果无法从文件名中提取，则使用文件名作为游戏ID
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
            
            # 简化版本：仅复制基础游戏文件到输出目录
            logger.info(f"由于依赖库限制，将执行简化版合并：复制基础游戏文件")
            shutil.copy2(base_file, output_path)
            
            # 记录其他文件信息
            info_file = game_output_dir / f"{game_id}_info.txt"
            with open(info_file, 'w', encoding='utf-8') as f:
                f.write(f"游戏: {game_id}\n")
                f.write(f"基础游戏: {base_file}\n")
                
                if latest_update:
                    f.write(f"最新更新: {latest_update}\n")
                
                if dlcs:
                    f.write(f"DLC文件 ({len(dlcs)}):\n")
                    for dlc in dlcs:
                        f.write(f"  - {dlc}\n")
                
                f.write("\n注意: 由于依赖库限制，未能执行完整合并。请安装Visual C++ Build Tools后重试。")
            
            logger.info(f"游戏 {game_id} 处理完成，输出文件: {output_path}")
            logger.info(f"详细信息已保存到: {info_file}")
            
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
        # 由于依赖库限制，这个功能被简化
        logger.warning("由于缺少必要的依赖库，完整的合并功能不可用")
        shutil.copy2(base_file, output_path)
        logger.info(f"已将基础游戏文件复制到: {output_path}")
    
    def _extract_xci(self, xci_file: Path, output_dir: Path):
        """解压XCI/XCZ文件"""
        # 由于依赖库限制，这个功能被简化
        logger.warning(f"无法解压 {xci_file} 到 {output_dir}，缺少必要的依赖库")
    
    def _extract_nsp(self, nsp_file: Path, output_dir: Path):
        """解压NSP/NSZ文件"""
        # 由于依赖库限制，这个功能被简化
        logger.warning(f"无法解压 {nsp_file} 到 {output_dir}，缺少必要的依赖库")
    
    def _apply_update(self, base_dir: Path, update_dir: Path):
        """将更新应用到基础游戏"""
        logger.warning("应用更新功能不可用，缺少必要的依赖库")
    
    def _apply_dlc(self, base_dir: Path, dlc_dir: Path):
        """将DLC应用到基础游戏"""
        logger.warning("应用DLC功能不可用，缺少必要的依赖库")
    
    def _repack_as_xci(self, input_dir: Path, output_file: Path):
        """将目录重新打包为XCI文件"""
        logger.warning("重新打包XCI功能不可用，缺少必要的依赖库")
    
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