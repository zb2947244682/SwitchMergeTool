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
        self.keys_file = None
        self.title_keys_file = None
        
        # 查找密钥文件
        possible_key_locations = [
            Path('prod.keys'),
            Path(os.path.expanduser('~/.switch/prod.keys')),
            Path(os.path.expanduser('~/switch/prod.keys')),
            Path('tools/keys.txt'),
            Path('tools/keys.txt'),
        ]
        
        for key_path in possible_key_locations:
            if key_path.exists():
                self.keys_file = key_path
                logger.info(f"找到密钥文件: {self.keys_file}")
                break
        
        # 工具路径
        self.tools_dir = Path('tools')
        self.hactoolnet_path = None
        
        # 查找hactoolnet.exe
        if (self.tools_dir / "hactoolnet.exe").exists():
            self.hactoolnet_path = self.tools_dir / "hactoolnet.exe"
        else:
            # 查找子目录
            for item in self.tools_dir.glob("**/hactoolnet.exe"):
                self.hactoolnet_path = item
                break
        
        if self.hactoolnet_path:
            logger.info(f"找到hactoolnet工具: {self.hactoolnet_path}")
        
        # 查找nsz.exe，现在直接放在tools目录下
        self.nsz_path = None
        if (self.tools_dir / "nsz.exe").exists():
            self.nsz_path = self.tools_dir / "nsz.exe"
        else:
            # 兼容性查找，以防nsz.exe在子目录中
            for item in self.tools_dir.glob("**/nsz.exe"):
                self.nsz_path = item
                break
        
        if self.nsz_path:
            logger.info(f"找到nsz工具: {self.nsz_path}")
        
        # 检查必要的工具
        self._setup_tools()
        
    def _setup_tools(self):
        """检查必要的工具"""
        # 创建tools目录
        self.tools_dir.mkdir(exist_ok=True)
        
        # 确保hactoolnet可用
        if not self.hactoolnet_path:
            logger.error("找不到hactoolnet.exe，请手动下载并放置在tools目录下")
            logger.info("您可以从 https://github.com/Thealexbarney/libhac/releases 下载")
            raise FileNotFoundError("找不到hactoolnet.exe")
            
        # 确保nsz工具可用
        if not self.nsz_path:
            logger.error("找不到nsz.exe，请手动下载并放置在tools目录下")
            logger.info("您可以从 https://github.com/nicoboss/nsz/releases 下载")
            raise FileNotFoundError("找不到nsz.exe")
        
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
        name_id_map = {}          # 存储游戏名称到ID的映射，用于去重
        
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
        if dir_files:
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

        # 处理重复游戏，确保每个真实游戏只有一个条目
        final_games = {}
        processed_names = set()
        
        # 首先整合所有同名游戏
        for game_id, game_data in game_files.items():
            game_name = game_data['name']
            
            # 标准化游戏名，忽略大小写和特殊字符
            norm_name = self._normalize_game_name(game_name)
            
            if norm_name in processed_names:
                # 已存在同名游戏，跳过
                continue
                
            # 查找所有同名游戏
            same_games = []
            for other_id, other_data in game_files.items():
                other_name = other_data['name']
                if self._normalize_game_name(other_name) == norm_name:
                    same_games.append((other_id, other_data))
            
            # 如果只有一个，直接添加
            if len(same_games) == 1:
                final_games[game_id] = game_data
                processed_names.add(norm_name)
                continue
                
            # 有多个同名游戏，合并它们
            logger.info(f"发现{len(same_games)}个同名游戏 '{game_name}'，将合并为一个条目")
            
            # 创建合并后的游戏条目
            merged_game = {
                'base': None,
                'updates': [],
                'dlcs': [],
                'name': game_name
            }
            
            # 整合所有文件
            for _, data in same_games:
                # 基础游戏取最大的
                if data['base'] and (not merged_game['base'] or 
                                    data['base'].stat().st_size > merged_game['base'].stat().st_size):
                    merged_game['base'] = data['base']
                
                # 更新和DLC都合并
                for update in data['updates']:
                    if update not in merged_game['updates']:
                        merged_game['updates'].append(update)
                
                for dlc in data['dlcs']:
                    if dlc not in merged_game['dlcs']:
                        merged_game['dlcs'].append(dlc)
            
            # 使用目录ID或者第一个游戏的ID
            merged_id = None
            for temp_id, _ in same_games:
                if temp_id.startswith("DIR_"):
                    merged_id = temp_id
                    break
            
            if not merged_id:
                merged_id = same_games[0][0]
                
            final_games[merged_id] = merged_game
            processed_names.add(norm_name)
        
        # 对于每个游戏，只保留最新版本的更新文件
        for game_id, game_data in final_games.items():
            if game_data['updates']:
                # 按照以下标准排序更新文件:
                # 1. 尝试提取版本号并比较
                # 2. 如果版本号提取失败，按文件大小排序
                # 3. 最后按修改时间排序
                
                # 为每个更新文件提取版本信息
                update_info = []
                for update_file in game_data['updates']:
                    version = self._extract_version(update_file)
                    size = update_file.stat().st_size
                    mtime = update_file.stat().st_mtime
                    
                    # 将版本号解析为元组以便比较
                    version_tuple = (0, 0, 0)
                    if version:
                        try:
                            # 处理不同格式的版本号
                            parts = version.split('.')
                            if len(parts) == 1:
                                version_tuple = (int(parts[0]), 0, 0)
                            elif len(parts) == 2:
                                version_tuple = (int(parts[0]), int(parts[1]), 0)
                            elif len(parts) >= 3:
                                version_tuple = (int(parts[0]), int(parts[1]), int(parts[2]))
                        except ValueError:
                            # 无法解析版本号，保持默认值
                            pass
                    
                    update_info.append((update_file, version_tuple, size, mtime))
                
                # 按版本号、大小和修改时间排序，取最高版本
                sorted_updates = sorted(update_info, key=lambda x: (x[1], x[2], x[3]), reverse=True)
                
                if sorted_updates:
                    # 只保留最高版本的更新文件
                    latest_update = sorted_updates[0][0]
                    logger.info(f"游戏 {game_data['name']} 使用最新的更新文件: {latest_update.name}")
                    game_data['updates'] = [latest_update]
                
        # 按游戏名称整理并日志输出
        if final_games:
            logger.info(f"\n成功识别 {len(final_games)} 个游戏:")
            for group_id, files_dict in final_games.items():
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
        else:
            logger.warning("未能识别到任何游戏文件")
        
        return final_games
    
    def _normalize_game_name(self, name: str) -> str:
        """标准化游戏名称，用于比较"""
        if not name:
            return ""
        # 转换为小写，移除所有特殊字符和空格
        import re
        return re.sub(r'[^a-z0-9]', '', name.lower())
    
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
            
            # 使用最新版本的更新文件
            latest_update = None
            if updates:
                # 按照文件大小排序，选择最大的（通常是最新的）
                latest_update = max(updates, key=lambda f: f.stat().st_size)
                logger.info(f"找到最新的更新文件: {latest_update.name}")
            
            # 合并为单一XCI功能
            logger.info(f"开始合并游戏 {game_name}")
            logger.info(f"基础游戏: {base_file}")
            if latest_update:
                logger.info(f"更新文件: {latest_update}")
            logger.info(f"DLC文件: {len(dlcs)} 个")
            
            # 构建输出文件名
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
            output_path = self.output_dir / output_filename
            
            logger.info(f"输出文件: {output_path}")
            
            # 为该游戏创建临时工作目录
            game_temp_dir = self.temp_dir / game_name
            game_temp_dir.mkdir(exist_ok=True, parents=True)
            
            # 同时保留单独的文件
            output_game_dir = self.output_dir / game_name
            output_game_dir.mkdir(exist_ok=True)
            
            # 使用hactoolnet进行XCI合并
            # 注意: 这里使用的方法是创建一个组合XCI文件，但实际上是将原始XCI游戏+更新+DLC保存在同一个文件中
            # 对于YUZU/Ryujinx模拟器，可能需要安装更新和DLC，而不是仅加载XCI
            # 真正组合的XCI文件需要使用高级工具如SAK或NSC_BUILDER
            logger.info(f"创建XCI文件: {output_path}")
            
            # 提取并准备所有文件
            secure_dir = game_temp_dir / "secure"
            secure_dir.mkdir(exist_ok=True, parents=True)
            
            # 首先，提取基础游戏内容
            try:
                # 如果基础游戏是XCZ，需要先解压
                if base_file.suffix.lower() == '.xcz':
                    base_xci_path = game_temp_dir / base_file.with_suffix('.xci').name
                    if not base_xci_path.exists():
                        self._decompress_xcz(base_file, base_xci_path)
                else:
                    base_xci_path = base_file
                
                # 复制基础游戏到输出文件
                logger.info(f"复制基础游戏 {base_xci_path} 到 {output_path}")
                shutil.copy2(base_xci_path, output_path)
                
                # 同时复制基础游戏、更新和DLC到独立目录
                logger.info(f"复制所有文件到独立目录: {output_game_dir}")
                
                # 复制基础游戏
                base_output = output_game_dir / base_xci_path.name
                shutil.copy2(base_xci_path, base_output)
                logger.info(f"基础游戏文件复制完成: {base_output}")
                
                # 复制最新更新文件
                if latest_update:
                    logger.info(f"复制最新更新文件...")
                    if latest_update.suffix.lower() == '.nsz':
                        logger.info(f"更新文件是NSZ格式，需要先解压...")
                        # 解压NSZ到临时目录
                        update_nsp_path = game_temp_dir / latest_update.with_suffix('.nsp').name
                        if not update_nsp_path.exists():
                            self._decompress_nsz(latest_update, update_nsp_path)
                        update_copy = update_nsp_path
                    else:
                        update_copy = latest_update
                    
                    update_output = output_game_dir / update_copy.name
                    shutil.copy2(update_copy, update_output)
                    logger.info(f"更新文件复制完成: {update_output}")
                
                # 复制所有DLC文件
                if dlcs:
                    logger.info(f"复制 {len(dlcs)} 个DLC文件...")
                    dlc_dir = output_game_dir / "DLC"
                    dlc_dir.mkdir(exist_ok=True)
                    
                    for dlc_file in dlcs:
                        if dlc_file.suffix.lower() == '.nsz':
                            logger.info(f"DLC文件 {dlc_file.name} 是NSZ格式，需要先解压...")
                            # 解压NSZ到临时目录
                            dlc_nsp_path = game_temp_dir / dlc_file.with_suffix('.nsp').name
                            if not dlc_nsp_path.exists():
                                self._decompress_nsz(dlc_file, dlc_nsp_path)
                            dlc_copy = dlc_nsp_path
                        else:
                            dlc_copy = dlc_file
                        
                        dlc_output = dlc_dir / dlc_copy.name
                        shutil.copy2(dlc_copy, dlc_output)
                    
                    logger.info(f"DLC文件复制完成")
                
                # 收集更新和DLC信息，添加到输出文件名中
                meta_info = ""
                if latest_update:
                    update_version = self._extract_version(latest_update)
                    if update_version:
                        meta_info += f"_v{update_version}"
                if dlcs:
                    meta_info += f"_{len(dlcs)}DLC"
                
                # 更新输出文件名
                new_output_path = output_path.parent / f"{game_name}{meta_info}.xci"
                if output_path != new_output_path:
                    try:
                        os.rename(output_path, new_output_path)
                        output_path = new_output_path
                        logger.info(f"已重命名输出文件为: {output_path}")
                    except Exception as e:
                        logger.error(f"重命名输出文件失败: {str(e)}")
                
                logger.info(f"已创建基础XCI文件: {output_path}")
                logger.info(f"注意: XCI文件只包含基础游戏，更新和DLC需要单独安装")
                logger.info(f"提示: 使用专业工具如SAK或NSC_BUILDER可以创建真正的合并XCI文件")
                
                # 显示详细的SAK使用提示
                logger.info("\n使用SAK合并此游戏的步骤:")
                logger.info(f"1. 下载SAK工具 (https://github.com/dezem/SAK)")
                logger.info(f"2. 将以下文件添加到SAK工具:")
                logger.info(f"   - 基础游戏: {base_output}")
                if latest_update:
                    logger.info(f"   - 更新文件: {update_output}")
                if dlcs:
                    logger.info(f"   - DLC文件: 位于 {dlc_dir} 目录")
                logger.info(f"3. 使用SAK工具进行合并，选择'完整合并'选项")
                logger.info(f"4. 或者在YUZU中分别安装基础游戏后，通过'文件->安装文件到NAND'安装更新和DLC")
                
            except Exception as e:
                logger.error(f"创建XCI文件失败: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
            
            logger.info(f"游戏 {game_name} 处理完成，输出文件: {output_path}")
            
        except Exception as e:
            logger.error(f"合并游戏 {game_name} 时出错: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
    
    def _decompress_nsz(self, nsz_file: Path, output_nsp: Path) -> bool:
        """将NSZ文件解压为NSP"""
        try:
            logger.info(f"解压NSZ文件: {nsz_file}")
            # 确保输出目录存在
            output_nsp.parent.mkdir(exist_ok=True, parents=True)
            
            # 构建解压命令
            cmd = [
                str(self.nsz_path),
                "-D", "-w",  # -w表示覆盖现有文件
                "-o", str(output_nsp.parent),
                str(nsz_file)
            ]
            
            logger.debug(f"执行命令: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                logger.info(f"NSZ解压成功: {output_nsp}")
                return True
            else:
                logger.error(f"NSZ解压失败: {result.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"解压NSZ文件 {nsz_file} 时出错: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    def _decompress_xcz(self, xcz_file: Path, output_xci: Path) -> bool:
        """将XCZ文件解压为XCI"""
        try:
            logger.info(f"解压XCZ文件: {xcz_file}")
            # 确保输出目录存在
            output_xci.parent.mkdir(exist_ok=True, parents=True)
            
            # 构建解压命令
            cmd = [
                str(self.nsz_path),
                "-D", "-w",  # -w表示覆盖现有文件
                "-o", str(output_xci.parent),
                str(xcz_file)
            ]
            
            logger.debug(f"执行命令: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                logger.info(f"XCZ解压成功: {output_xci}")
                return True
            else:
                logger.error(f"XCZ解压失败: {result.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"解压XCZ文件 {xcz_file} 时出错: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    def _extract_version(self, file_path: Path) -> Optional[str]:
        """从文件名中提取版本号"""
        # 首先尝试匹配常见的版本号格式
        patterns = [
            r'v(\d+\.\d+(\.\d+)?)',  # v1.2.3 格式
            r'v(\d+_\d+(_\d+)?)',    # v1_2_3 格式
            r'[vV](\d+)',            # v1 格式
            r'(\d+\.\d+(\.\d+)?)',   # 1.2.3 格式
            r'(\d+_\d+(_\d+)?)'      # 1_2_3 格式
        ]
        
        for pattern in patterns:
            match = re.search(pattern, str(file_path))
            if match:
                version = match.group(1)
                # 标准化版本号格式（将_替换为.）
                return version.replace('_', '.')
        
        return None
    
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