#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import shutil
import subprocess
import re
import argparse
import platform
import glob
import locale
from pathlib import Path
from tqdm import tqdm
import struct
import hashlib
from typing import List, Dict, Tuple, Optional
import logging
import py7zr
import zipfile

# 设置本地化支持中文
locale.setlocale(locale.LC_ALL, '')

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
        logging.FileHandler('rom_merger.log', encoding='utf-8')
    ]
)
logger = logging.getLogger('SwitchRomMerger')

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
        
        # 只处理特定类型的文件
        all_files = []
        for ext in self.supported_extensions:
            all_files.extend(list(directory.rglob(f"*{ext}")))
        
        logger.info(f"找到 {len(all_files)} 个Switch游戏文件...")
        
        for file_path in tqdm(all_files, desc="扫描文件"):
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
        # 从文件名和路径中提取信息
        filename = file_path.stem
        filepath_str = str(file_path)
        
        # 检查是否包含关键字来判断类型
        is_dlc = 'dlc' in filename.lower() or 'dlc' in filepath_str.lower()
        is_update = ('upd' in filename.lower() or 'update' in filename.lower() or
                    '更新' in filename.lower() or 'patch' in filename.lower() or
                    '补丁' in filename.lower() or 'v1.' in filename.lower() or 'v2.' in filename.lower())
        
        # 推断游戏ID
        game_id = None
        
        # 1. 尝试使用父目录名称作为ID
        try:
            parent_dir = file_path.parent.name
            if parent_dir and not parent_dir.startswith('.'):
                game_id = parent_dir
        except:
            pass
        
        # 2. 尝试从文件名中提取游戏名称
        if not game_id:
            game_id = filename.split('_')[0] if '_' in filename else filename
            
            # 清除文件名中的版本号和其他标记
            game_id = re.sub(r'[\[\(].*?[\]\)]', '', game_id)  # 移除方括号和圆括号内的内容
            game_id = re.sub(r'v\d+(\.\d+)*', '', game_id)     # 移除版本号
            game_id = game_id.strip()
            
        # 如果还是没有游戏ID，使用文件名
        if not game_id:
            game_id = filename
            
        # 清理游戏ID
        game_id = game_id.strip()
        
        return game_id, is_update, is_dlc
    
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
            
            # 使用OUTPUT目录，不再为每个游戏创建子目录
            game_output_dir = self.output_dir
            
            # 使用最新版本的更新文件
            latest_update = None
            if updates:
                # 按照文件大小排序，选择最大的（通常是最新的）
                latest_update = max(updates, key=lambda f: f.stat().st_size)
                logger.info(f"找到最新的更新文件: {latest_update.name}")
            
            # 合并基础游戏和更新
            logger.info(f"开始合并游戏 {game_id}")
            logger.info(f"基础游戏: {base_file}")
            if latest_update:
                logger.info(f"更新文件: {latest_update}")
            logger.info(f"DLC文件: {len(dlcs)} 个")
            
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
            
            logger.info(f"输出文件: {output_path}")
            
            # 直接复制模式标志，当合并失败时会设置为True
            direct_copy_mode = False
            
            # 开始合并前先创建备份输出目录
            backup_dir = self.temp_dir / "backup"
            backup_dir.mkdir(exist_ok=True)
            
            # 复制基础游戏文件到备份目录
            backup_base = backup_dir / base_file.name
            logger.info(f"备份基础游戏文件: {backup_base}")
            try:
                shutil.copy2(base_file, backup_base)
            except Exception as e:
                logger.error(f"备份基础游戏文件失败: {str(e)}")
            
            # 尝试使用专用工具合并文件
            try:
                # 设置超时时间，避免程序卡死
                import threading
                import time
                
                # 创建一个事件用于通知合并完成
                merge_done = threading.Event()
                merge_success = [False]  # 使用列表，使其能在线程中被修改
                
                # 定义合并线程
                def merge_thread():
                    try:
                        self._merge_with_tools(base_file, latest_update, dlcs, output_path)
                        merge_success[0] = True
                    except Exception as e:
                        logger.error(f"合并线程中出错: {str(e)}")
                    finally:
                        merge_done.set()
                
                # 启动合并线程
                thread = threading.Thread(target=merge_thread)
                thread.daemon = True
                thread.start()
                
                # 等待合并完成，最多等待30分钟
                timeout = 30 * 60  # 30分钟
                start_time = time.time()
                
                logger.info(f"开始合并，最多等待 {timeout/60} 分钟...")
                
                while not merge_done.is_set() and (time.time() - start_time) < timeout:
                    time.sleep(5)
                    elapsed = time.time() - start_time
                    logger.info(f"合并进行中... 已经过 {elapsed/60:.1f} 分钟")
                
                if not merge_done.is_set():
                    logger.error(f"合并超时，已等待 {timeout/60} 分钟，切换到直接复制模式")
                    direct_copy_mode = True
                elif not merge_success[0]:
                    logger.error("合并失败，切换到直接复制模式")
                    direct_copy_mode = True
                else:
                    logger.info("合并成功！")
            except Exception as e:
                logger.error(f"启动合并线程时出错: {str(e)}")
                direct_copy_mode = True
            
            # 如果需要直接复制模式
            if direct_copy_mode:
                logger.info("使用直接复制模式")
                
                # 如果输出文件已经存在，检查是否有效
                if output_path.exists() and output_path.stat().st_size > 1024 * 1024:
                    logger.info(f"输出文件已存在且大小合理: {output_path.stat().st_size / (1024*1024):.2f} MB")
                else:
                    # 复制基础游戏文件到输出目录
                    logger.info(f"复制基础游戏文件到输出目录: {output_path}")
                    try:
                        shutil.copy2(base_file, output_path)
                        logger.info(f"复制基础游戏文件成功: {output_path}")
                    except Exception as e:
                        logger.error(f"复制基础游戏文件失败: {str(e)}")
                        
                        # 尝试从备份目录复制
                        if backup_base.exists():
                            logger.info(f"尝试从备份目录复制: {backup_base}")
                            try:
                                shutil.copy2(backup_base, output_path)
                                logger.info(f"从备份目录复制成功")
                            except Exception as e2:
                                logger.error(f"从备份目录复制失败: {str(e2)}")
            
            logger.info(f"游戏 {game_id} 处理完成，输出文件: {output_path}")
            
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
            logger.info(f"这是XCZ文件，需要先解压为XCI: {temp_xci}")
            
            # 使用nsz工具解压XCZ
            cmd = [
                str(self.nsz_path),
                "-D", str(xci_file),
                "-o", str(self.temp_dir)
            ]
            
            logger.info(f"执行命令: {' '.join(cmd)}")
            
            try:
                # 使用subprocess.Popen来实时输出进度
                process = subprocess.Popen(
                    cmd, 
                    stdout=subprocess.PIPE, 
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,
                    universal_newlines=True
                )
                
                # 实时输出进度
                for line in process.stdout:
                    logger.info(f"NSZ输出: {line.strip()}")
                
                # 等待进程完成
                process.wait()
                
                if process.returncode != 0:
                    error = process.stderr.read()
                    logger.error(f"解压XCZ失败，返回码: {process.returncode}, 错误: {error}")
                    raise RuntimeError(f"解压XCZ失败: {error}")
                
                # 检查解压后的文件是否存在
                if not temp_xci.exists():
                    # 尝试查找其他可能的输出文件
                    potential_files = list(self.temp_dir.glob(f"{xci_file.stem}*.xci"))
                    if potential_files:
                        temp_xci = potential_files[0]
                        logger.info(f"找到可能的XCI文件: {temp_xci}")
                    else:
                        logger.error(f"解压后未找到XCI文件: {temp_xci}")
                        # 列出临时目录中的所有文件
                        all_files = list(self.temp_dir.glob("*"))
                        logger.info(f"临时目录中的文件: {[f.name for f in all_files]}")
                        raise FileNotFoundError(f"解压后未找到XCI文件: {temp_xci}")
            except Exception as e:
                logger.error(f"执行NSZ命令时出错: {str(e)}")
                # 尝试直接复制XCZ文件作为备选方案
                logger.info(f"尝试直接复制基础游戏文件...")
                shutil.copy2(xci_file, output_dir / xci_file.name)
                return
            
            xci_file = temp_xci
        
        # 使用hactoolnet解压XCI
        cmd = [
            str(self.hactoolnet_path),
            "--keyset=" + str(self.keys_file),
            "-t", "xci", "--securedir=" + str(output_dir),
            str(xci_file)
        ]
        
        logger.info(f"执行命令: {' '.join(cmd)}")
        
        try:
            # 使用subprocess.Popen来实时输出进度
            process = subprocess.Popen(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            # 实时输出进度
            for line in process.stdout:
                logger.info(f"hactoolnet输出: {line.strip()}")
            
            # 等待进程完成
            process.wait()
            
            if process.returncode != 0:
                error = process.stderr.read()
                logger.error(f"解压XCI失败，返回码: {process.returncode}, 错误: {error}")
                # 尝试直接复制XCI文件作为备选方案
                logger.info(f"尝试直接复制基础游戏文件...")
                shutil.copy2(xci_file, output_dir / xci_file.name)
                return
            
            # 检查解压后的目录是否有文件
            output_files = list(output_dir.glob("*"))
            if not output_files:
                logger.warning(f"解压XCI后目录为空: {output_dir}")
                # 尝试直接复制XCI文件作为备选方案
                logger.info(f"尝试直接复制基础游戏文件...")
                shutil.copy2(xci_file, output_dir / xci_file.name)
            else:
                logger.info(f"解压XCI成功，输出目录中的文件: {[f.name for f in output_files]}")
        except Exception as e:
            logger.error(f"执行hactoolnet命令时出错: {str(e)}")
            # 尝试直接复制XCI文件作为备选方案
            logger.info(f"尝试直接复制基础游戏文件...")
            shutil.copy2(xci_file, output_dir / xci_file.name)
    
    def _extract_nsp(self, nsp_file: Path, output_dir: Path):
        """解压NSP/NSZ文件"""
        logger.info(f"解压 {nsp_file} 到 {output_dir}")
        
        # 如果是NSZ文件，需要先解压为NSP
        if nsp_file.suffix.lower() == '.nsz':
            temp_nsp = self.temp_dir / f"{nsp_file.stem}.nsp"
            logger.info(f"这是NSZ文件，需要先解压为NSP: {temp_nsp}")
            
            # 使用nsz工具解压NSZ
            cmd = [
                str(self.nsz_path),
                "-D", str(nsp_file),
                "-o", str(self.temp_dir)
            ]
            
            logger.info(f"执行命令: {' '.join(cmd)}")
            
            try:
                # 使用subprocess.Popen来实时输出进度
                process = subprocess.Popen(
                    cmd, 
                    stdout=subprocess.PIPE, 
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,
                    universal_newlines=True
                )
                
                # 实时输出进度
                for line in process.stdout:
                    logger.info(f"NSZ输出: {line.strip()}")
                
                # 等待进程完成
                process.wait()
                
                if process.returncode != 0:
                    error = process.stderr.read()
                    logger.error(f"解压NSZ失败，返回码: {process.returncode}, 错误: {error}")
                    raise RuntimeError(f"解压NSZ失败: {error}")
                
                # 检查解压后的文件是否存在
                if not temp_nsp.exists():
                    # 尝试查找其他可能的输出文件
                    potential_files = list(self.temp_dir.glob(f"{nsp_file.stem}*.nsp"))
                    if potential_files:
                        temp_nsp = potential_files[0]
                        logger.info(f"找到可能的NSP文件: {temp_nsp}")
                    else:
                        logger.error(f"解压后未找到NSP文件: {temp_nsp}")
                        # 列出临时目录中的所有文件
                        all_files = list(self.temp_dir.glob("*"))
                        logger.info(f"临时目录中的文件: {[f.name for f in all_files]}")
                        raise FileNotFoundError(f"解压后未找到NSP文件: {temp_nsp}")
            except Exception as e:
                logger.error(f"执行NSZ命令时出错: {str(e)}")
                # 尝试直接复制NSZ文件作为备选方案
                logger.info(f"尝试直接复制DLC/更新文件...")
                shutil.copy2(nsp_file, output_dir / nsp_file.name)
                return
            
            nsp_file = temp_nsp
        
        # 使用hactoolnet解压NSP
        cmd = [
            str(self.hactoolnet_path),
            "--keyset=" + str(self.keys_file),
            "-t", "pfs0", "--outdir=" + str(output_dir),
            str(nsp_file)
        ]
        
        logger.info(f"执行命令: {' '.join(cmd)}")
        
        try:
            # 使用subprocess.Popen来实时输出进度
            process = subprocess.Popen(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            # 实时输出进度
            for line in process.stdout:
                logger.info(f"hactoolnet输出: {line.strip()}")
            
            # 等待进程完成
            process.wait()
            
            if process.returncode != 0:
                error = process.stderr.read()
                logger.error(f"解压NSP失败，返回码: {process.returncode}, 错误: {error}")
                # 尝试直接复制NSP文件作为备选方案
                logger.info(f"尝试直接复制DLC/更新文件...")
                shutil.copy2(nsp_file, output_dir / nsp_file.name)
                return
            
            # 检查解压后的目录是否有文件
            output_files = list(output_dir.glob("*"))
            if not output_files:
                logger.warning(f"解压NSP后目录为空: {output_dir}")
                # 尝试直接复制NSP文件作为备选方案
                logger.info(f"尝试直接复制DLC/更新文件...")
                shutil.copy2(nsp_file, output_dir / nsp_file.name)
            else:
                logger.info(f"解压NSP成功，输出目录中的文件: {[f.name for f in output_files]}")
        except Exception as e:
            logger.error(f"执行hactoolnet命令时出错: {str(e)}")
            # 尝试直接复制NSP文件作为备选方案
            logger.info(f"尝试直接复制DLC/更新文件...")
            shutil.copy2(nsp_file, output_dir / nsp_file.name)
    
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
        
        # 检查输入目录是否为空
        input_files = list(input_dir.glob("**/*"))
        if not input_files:
            logger.error(f"输入目录为空，无法打包XCI: {input_dir}")
            logger.info(f"尝试直接复制最初的主体游戏文件作为输出...")
            
            # 查找同名的XCI文件作为备选
            base_files = list(self.temp_dir.glob("**/*.xci"))
            if base_files:
                # 使用最大的文件（很可能是主游戏）
                biggest_file = max(base_files, key=lambda f: f.stat().st_size)
                logger.info(f"找到备选XCI文件: {biggest_file}")
                shutil.copy2(biggest_file, output_file)
                return
            else:
                logger.error(f"未找到备选XCI文件，无法创建输出")
                return
        
        # 计算输入文件的总大小
        total_size = sum(f.stat().st_size for f in input_files if f.is_file())
        logger.info(f"输入文件总大小: {total_size / (1024 * 1024):.2f} MB")
        
        # 使用hactoolnet打包为XCI
        cmd = [
            str(self.hactoolnet_path),
            "--keyset=" + str(self.keys_file),
            "-t", "xci", "--create=" + str(output_file),
            "--securedir=" + str(input_dir)
        ]
        
        logger.info(f"执行命令: {' '.join(cmd)}")
        
        try:
            # 使用subprocess.Popen来实时输出进度
            process = subprocess.Popen(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            # 实时输出进度
            for line in process.stdout:
                logger.info(f"hactoolnet打包输出: {line.strip()}")
            
            # 等待进程完成
            process.wait()
            
            if process.returncode != 0:
                error = process.stderr.read()
                logger.error(f"打包XCI失败，返回码: {process.returncode}, 错误: {error}")
                
                # 尝试使用备选方案：直接复制主游戏文件
                logger.info(f"尝试直接复制最初的主体游戏文件作为输出...")
                
                # 查找同名的XCI文件作为备选
                base_files = list(self.temp_dir.glob("**/*.xci"))
                if base_files:
                    # 使用最大的文件（很可能是主游戏）
                    biggest_file = max(base_files, key=lambda f: f.stat().st_size)
                    logger.info(f"找到备选XCI文件: {biggest_file}")
                    shutil.copy2(biggest_file, output_file)
                else:
                    logger.error(f"未找到备选XCI文件，无法创建输出")
                return
            
            # 检查输出文件是否存在和大小是否合理
            if output_file.exists():
                output_size = output_file.stat().st_size
                logger.info(f"打包XCI成功，输出文件大小: {output_size / (1024 * 1024):.2f} MB")
                
                # 简单检查文件大小是否合理
                if output_size < 1024 * 1024:  # 小于1MB
                    logger.warning(f"输出文件大小异常小: {output_size / (1024 * 1024):.2f} MB")
            else:
                logger.error(f"打包完成但输出文件不存在: {output_file}")
                
                # 尝试使用备选方案
                logger.info(f"尝试直接复制主体游戏文件作为输出...")
                base_files = list(self.temp_dir.glob("**/*.xci"))
                if base_files:
                    biggest_file = max(base_files, key=lambda f: f.stat().st_size)
                    logger.info(f"找到备选XCI文件: {biggest_file}")
                    shutil.copy2(biggest_file, output_file)
        except Exception as e:
            logger.error(f"执行hactoolnet打包命令时出错: {str(e)}")
            
            # 尝试使用备选方案
            logger.info(f"尝试直接复制主体游戏文件作为输出...")
            base_files = list(self.temp_dir.glob("**/*.xci"))
            if base_files:
                biggest_file = max(base_files, key=lambda f: f.stat().st_size)
                logger.info(f"找到备选XCI文件: {biggest_file}")
                shutil.copy2(biggest_file, output_file)
    
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
        
        # 解析命令行参数
        parser = argparse.ArgumentParser(description='Switch游戏合并工具')
        parser.add_argument('--scan-only', action='store_true', help='仅扫描游戏文件，不执行合并')
        parser.add_argument('--game-id', type=str, help='仅处理指定ID的游戏')
        args = parser.parse_args()
        
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
        
        # 扫描游戏文件
        game_files = merger.scan_directory(target_dir)
        
        # 如果只需要扫描，直接返回
        if args.scan_only:
            logger.info("仅扫描模式，不执行合并")
            return
        
        # 如果指定了游戏ID，只处理该游戏
        if args.game_id:
            game_id = args.game_id
            if game_id in game_files:
                logger.info(f"仅处理游戏: {game_id}")
                merger.merge_files(game_id, game_files[game_id])
            else:
                logger.error(f"找不到指定的游戏ID: {game_id}")
                return
        else:
            # 处理所有游戏
            for game_id, files_dict in tqdm(game_files.items(), desc="合并游戏"):
                merger.merge_files(game_id, files_dict)
        
        logger.info("处理完成")
        
    except Exception as e:
        logger.error(f"发生错误: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        logger.info("程序异常终止")
        sys.exit(1)

if __name__ == "__main__":
    main() 