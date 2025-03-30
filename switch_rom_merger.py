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
        
    def extract_title_id(self, filename: str) -> Optional[str]:
        """从文件名中提取Title ID"""
        # 常见的Title ID格式模式：[01XXXXXXXXXXXXXX] 或 01XXXXXXXXXXXXXX
        patterns = [
            r'\[([0-9A-Fa-f]{16})\]',  # [0100000000000XXX]
            r'(?<!\[)([0-9A-Fa-f]{16})(?!\])'  # 0100000000000XXX 但不在括号内
        ]
        
        for pattern in patterns:
            match = re.search(pattern, filename)
            if match:
                return match.group(1).upper()
        return None
    
    def extract_base_title_id(self, title_id: str) -> str:
        """提取基础游戏的Title ID（去除DLC和更新的特定部分）"""
        # 通常主游戏ID格式为: 01XXXXXXXXXXX000
        # DLC ID格式为:      01XXXXXXXXXXX00X (X > 0)
        # 更新ID格式为:      01XXXXXXXXXXX800
        if not title_id or len(title_id) != 16:
            return title_id
            
        # 取前13位 + "000" 作为基础游戏ID
        base_id = title_id[:13] + "000"
        return base_id
    
    def is_dlc_file(self, file_path: Path) -> bool:
        """判断文件是否为DLC"""
        file_str = str(file_path).lower()
        filename = file_path.name.lower()
        
        # 检查文件名中是否包含DLC相关关键字
        if 'dlc' in filename or 'dlc' in file_str:
            return True
        
        # 检查TitleID是否是DLC格式（通常以00X结尾，X > 0）
        title_id = self.extract_title_id(file_str)
        if title_id and len(title_id) == 16:
            # 通常DLC的ID是以非零数字结尾的00X格式
            if title_id[13:15] == '00' and title_id[15] != '0':
                return True
        
        return False
    
    def is_update_file(self, file_path: Path) -> bool:
        """判断文件是否为更新文件"""
        file_str = str(file_path).lower()
        filename = file_path.name.lower()
        
        # 检查文件名中是否包含更新相关关键字
        if ('upd' in filename or 'update' in filename or
           '更新' in filename or 'patch' in filename or
           '补丁' in filename or 'v1.' in filename or 'v2.' in filename):
            return True
        
        # 检查TitleID是否是更新格式（通常以800结尾）
        title_id = self.extract_title_id(file_str)
        if title_id and len(title_id) == 16:
            # 通常更新的ID是以800结尾
            if title_id[13:] == '800':
                return True
        
        return False
    
    def scan_directory(self, directory: Path) -> Dict[str, Dict]:
        """扫描目录并返回按游戏Title ID/名称分组的文件列表"""
        game_files = {}           # 存储最终整合后的游戏信息
        raw_files = {}            # 存储原始按Title ID分组的文件信息
        title_id_map = {}         # 存储TitleID到游戏名称的映射
        base_id_map = {}          # 存储基础ID到完整ID的映射
        dir_files = {}            # 按目录分组的文件
        
        logger.info(f"扫描目录: {directory}")
        
        # 只处理特定类型的文件
        all_files = []
        for ext in self.supported_extensions:
            all_files.extend(list(directory.rglob(f"*{ext}")))
        
        logger.info(f"找到 {len(all_files)} 个Switch游戏文件...")
        
        # 首先按目录分组
        for file_path in all_files:
            rel_path = file_path.relative_to(directory)
            if len(rel_path.parts) > 0:
                top_dir = rel_path.parts[0]
                if top_dir not in dir_files:
                    dir_files[top_dir] = []
                dir_files[top_dir].append(file_path)
        
        # 记录找到的目录
        logger.info(f"找到以下游戏目录:")
        for dir_name, files in dir_files.items():
            logger.info(f"  - {dir_name}: {len(files)}个文件")
        
        # 第一遍扫描：提取所有文件的Title ID并分类
        for file_path in tqdm(all_files, desc="识别游戏文件"):
            try:
                file_str = str(file_path)
                filename = file_path.name
                
                # 尝试提取Title ID
                title_id = self.extract_title_id(file_str)
                
                # 判断文件类型
                is_dlc = self.is_dlc_file(file_path)
                is_update = self.is_update_file(file_path)
                
                # 获取父目录名
                rel_path = file_path.relative_to(directory)
                parent_dir = rel_path.parts[0] if len(rel_path.parts) > 0 else ""
                
                # 如果有Title ID
                if title_id:
                    # 提取游戏名称
                    # 先尝试从目录名提取游戏名称
                    game_name = None
                    if parent_dir:
                        game_name = parent_dir
                    
                    # 如果从目录没找到合适的，尝试从文件名提取
                    if not game_name or game_name == title_id:
                        # 从文件名中提取游戏名称，移除版本号、括号内容等
                        game_name = re.sub(r'\[.*?\]', '', filename)  # 移除方括号内容
                        game_name = re.sub(r'\(.*?\)', '', game_name)  # 移除圆括号内容
                        game_name = re.sub(r'v\d+(\.\d+)*', '', game_name)  # 移除版本号
                        game_name = game_name.replace(title_id, '')  # 移除Title ID
                        game_name = game_name.strip('_.- ')  # 移除前后的特殊字符
                    
                    # 如果游戏名称为空，使用Title ID作为名称
                    if not game_name or len(game_name) < 2:
                        game_name = f"Game_{title_id}"
                    
                    # 将Title ID映射到游戏名称
                    title_id_map[title_id] = game_name
                    
                    # 计算基础游戏ID
                    base_title_id = self.extract_base_title_id(title_id)
                    if base_title_id not in base_id_map:
                        base_id_map[base_title_id] = []
                    if title_id not in base_id_map[base_title_id]:
                        base_id_map[base_title_id].append(title_id)
                    
                    # 创建或更新原始文件条目
                    if title_id not in raw_files:
                        raw_files[title_id] = {
                            'base': None,
                            'updates': [],
                            'dlcs': [],
                            'name': game_name,
                            'base_id': base_title_id,
                            'dir': parent_dir
                        }
                    
                    # 归类文件
                    if is_dlc:
                        raw_files[title_id]['dlcs'].append(file_path)
                    elif is_update:
                        raw_files[title_id]['updates'].append(file_path)
                    else:
                        # 基础游戏，选择最大的文件
                        if not raw_files[title_id]['base'] or file_path.stat().st_size > raw_files[title_id]['base'].stat().st_size:
                            raw_files[title_id]['base'] = file_path
                    
                else:
                    # 没有Title ID的情况下，尝试从文件名和目录名提取信息
                    if parent_dir:
                        # 用顶级目录作为游戏名
                        game_name = parent_dir
                        
                        # 创建一个假的ID用于分组
                        fake_id = f"DIR_{game_name}"
                        
                        if fake_id not in raw_files:
                            raw_files[fake_id] = {
                                'base': None,
                                'updates': [],
                                'dlcs': [],
                                'name': game_name,
                                'base_id': fake_id,
                                'dir': parent_dir
                            }
                        
                        # 根据文件名归类
                        if is_dlc:
                            raw_files[fake_id]['dlcs'].append(file_path)
                        elif is_update:
                            raw_files[fake_id]['updates'].append(file_path)
                        else:
                            # 基础游戏，选择最大的文件
                            if not raw_files[fake_id]['base'] or file_path.stat().st_size > raw_files[fake_id]['base'].stat().st_size:
                                raw_files[fake_id]['base'] = file_path
                        
                        # 添加到映射
                        if fake_id not in base_id_map:
                            base_id_map[fake_id] = [fake_id]
                
            except Exception as e:
                logger.error(f"处理文件 {file_path} 时出错: {str(e)}")
        
        # 特殊处理：合并同名目录下的文件
        dir_groups = {}  # 目录名到文件ID的映射
        for title_id, info in raw_files.items():
            dir_name = info['dir']
            if dir_name and not dir_name.startswith('.'):
                if dir_name not in dir_groups:
                    dir_groups[dir_name] = []
                dir_groups[dir_name].append(title_id)
        
        # 为每个目录组创建合并条目
        for dir_name, title_ids in dir_groups.items():
            if len(title_ids) > 1:  # 只处理有多个文件的目录
                # 创建目录组ID
                dir_group_id = f"DIR_{dir_name}"
                
                # 创建新条目
                game_files[dir_group_id] = {
                    'base': None,
                    'updates': [],
                    'dlcs': [],
                    'name': dir_name
                }
                
                # 合并该目录下所有文件
                for title_id in title_ids:
                    if raw_files[title_id]['base']:
                        # 如果当前没有基础游戏或找到更大的，更新它
                        if not game_files[dir_group_id]['base'] or (
                            raw_files[title_id]['base'].stat().st_size > 
                            game_files[dir_group_id]['base'].stat().st_size):
                            game_files[dir_group_id]['base'] = raw_files[title_id]['base']
                    
                    # 添加更新和DLC
                    game_files[dir_group_id]['updates'].extend(raw_files[title_id]['updates'])
                    game_files[dir_group_id]['dlcs'].extend(raw_files[title_id]['dlcs'])
            else:
                # 单个文件的目录，直接复制
                title_id = title_ids[0]
                game_files[title_id] = {
                    'base': raw_files[title_id]['base'],
                    'updates': raw_files[title_id]['updates'],
                    'dlcs': raw_files[title_id]['dlcs'],
                    'name': raw_files[title_id]['name']
                }
        
        # 然后处理按TitleID分组的文件
        for base_id, related_ids in base_id_map.items():
            # 跳过已处理的目录组
            if base_id.startswith("DIR_") or base_id in game_files:
                continue
                
            # 找出最可能的主游戏ID
            main_game_id = None
            base_file = None
            main_game_name = None
            
            # 首先检查是否有 "000" 结尾的主游戏ID
            for title_id in related_ids:
                if title_id.endswith("000") and raw_files[title_id]['base']:
                    main_game_id = title_id
                    base_file = raw_files[title_id]['base']
                    main_game_name = raw_files[title_id]['name']
                    break
            
            # 如果没找到主游戏，选择拥有base文件的第一个ID
            if not main_game_id:
                for title_id in related_ids:
                    if raw_files[title_id]['base']:
                        main_game_id = title_id
                        base_file = raw_files[title_id]['base']
                        main_game_name = raw_files[title_id]['name']
                        break
            
            # 如果还是没找到，选择第一个ID
            if not main_game_id and related_ids:
                main_game_id = related_ids[0]
                main_game_name = raw_files[main_game_id]['name']
            
            # 如果找到了主游戏ID，整合所有相关文件
            if main_game_id:
                # 创建新的游戏条目
                game_files[base_id] = {
                    'base': base_file,
                    'updates': [],
                    'dlcs': [],
                    'name': main_game_name
                }
                
                # 整合所有相关ID的文件
                for title_id in related_ids:
                    if raw_files[title_id]['updates']:
                        game_files[base_id]['updates'].extend(raw_files[title_id]['updates'])
                    if raw_files[title_id]['dlcs']:
                        game_files[base_id]['dlcs'].extend(raw_files[title_id]['dlcs'])
                    # 如果当前没有base文件但这个ID有，使用它
                    if not game_files[base_id]['base'] and raw_files[title_id]['base']:
                        game_files[base_id]['base'] = raw_files[title_id]['base']

        # 按游戏名称整理并日志输出
        logger.info(f"\n成功识别 {len(game_files)} 个游戏:")
        for group_id, files_dict in game_files.items():
            base_file = files_dict['base']
            updates = files_dict['updates']
            dlcs = files_dict['dlcs']
            game_name = files_dict['name']
            
            logger.info(f"游戏: {game_name} (ID: {group_id})")
            logger.info(f"  基础游戏: {base_file.name if base_file else '无'}")
            logger.info(f"  更新文件: {len(updates)} 个")
            logger.info(f"  DLC文件: {len(dlcs)} 个")
            
            # 详细记录更新和DLC文件
            if updates:
                logger.debug(f"  更新文件列表:")
                for upd in updates:
                    logger.debug(f"    - {upd}")
            
            if dlcs:
                logger.debug(f"  DLC文件列表:")
                for dlc in dlcs:
                    logger.debug(f"    - {dlc}")
        
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
    
    def merge_files(self, title_id: str, files_dict: Dict):
        """合并同一游戏的文件"""
        try:
            base_file = files_dict['base']
            updates = files_dict['updates']
            dlcs = files_dict['dlcs']
            game_name = files_dict['name']
            
            # 如果没有基础游戏文件，无法合并
            if not base_file:
                logger.warning(f"游戏 {game_name} 没有基础文件，无法合并")
                return
            
            # 使用OUTPUT目录
            game_output_dir = self.output_dir
            game_output_dir.mkdir(exist_ok=True)
            
            # 使用最新版本的更新文件
            latest_update = None
            if updates:
                # 按照文件大小排序，选择最大的（通常是最新的）
                latest_update = max(updates, key=lambda f: f.stat().st_size)
                logger.info(f"找到最新的更新文件: {latest_update.name}")
            
            # 合并基础游戏和更新
            logger.info(f"开始合并游戏 {game_name}")
            logger.info(f"基础游戏: {base_file}")
            if latest_update:
                logger.info(f"更新文件: {latest_update}")
            logger.info(f"DLC文件: {len(dlcs)} 个")
            
            # 输出文件名
            output_filename = f"{game_name}"
            if latest_update:
                # 尝试从更新文件名中提取版本号
                update_version = self._extract_version(latest_update)
                if update_version:
                    output_filename += f"_v{update_version}"
                else:
                    output_filename += "_更新版"
            
            if dlcs:
                output_filename += f"_{len(dlcs)}DLC"
            
            # 清理文件名称中的特殊字符
            output_filename = re.sub(r'[\\/:*?"<>|]', '', output_filename)
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
            
            logger.info(f"游戏 {game_name} 处理完成，输出文件: {output_path}")
            
        except Exception as e:
            logger.error(f"合并游戏 {game_name} 时出错: {str(e)}")
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
        
        # 移除没有基础游戏的条目（除非显式指定了游戏ID）
        if not args.game_id:
            for game_id in list(game_files.keys()):
                if not game_files[game_id]['base']:
                    logger.warning(f"游戏 {game_id} 没有基础游戏文件，将被跳过")
                    del game_files[game_id]
        
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
            # 查找匹配的游戏（支持部分匹配）
            matching_games = []
            search_term = args.game_id.lower()
            
            for group_id, files_dict in game_files.items():
                game_name = files_dict['name'].lower()
                
                if search_term in group_id.lower() or search_term in game_name:
                    matching_games.append((group_id, files_dict))
            
            if matching_games:
                logger.info(f"找到 {len(matching_games)} 个匹配的游戏:")
                for i, (group_id, files_dict) in enumerate(matching_games):
                    logger.info(f"{i+1}. {files_dict['name']} (ID: {group_id})")
                
                # 如果只有一个匹配，直接处理
                if len(matching_games) == 1:
                    group_id, files_dict = matching_games[0]
                    logger.info(f"处理游戏: {files_dict['name']}")
                    merger.merge_files(group_id, files_dict)
                else:
                    # 如果有多个匹配，提示用户选择
                    logger.info(f"找到多个匹配的游戏，请使用更精确的游戏ID")
                    logger.info(f"示例: python switch_rom_merger.py --game-id \"完整游戏名称\"")
            else:
                logger.error(f"找不到匹配的游戏: {args.game_id}")
        else:
            # 处理所有游戏
            for group_id, files_dict in tqdm(game_files.items(), desc="合并游戏"):
                # 只处理有基础游戏文件的游戏
                if files_dict['base']:
                    merger.merge_files(group_id, files_dict)
                else:
                    logger.warning(f"跳过没有基础游戏文件的游戏: {files_dict['name']}")
        
        logger.info("处理完成")
        
    except Exception as e:
        logger.error(f"发生错误: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        logger.info("程序异常终止")
        sys.exit(1)

if __name__ == "__main__":
    main() 