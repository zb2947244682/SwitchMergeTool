#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import platform
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext
from pathlib import Path
import logging
import queue
import re
from switch_rom_merger import SwitchRomMerger, logger

# 设置本地化支持中文
import locale
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

# 用于GUI和后台线程通信的队列
log_queue = queue.Queue()

# 日志处理类，将日志重定向到GUI
class QueueHandler(logging.Handler):
    def __init__(self, log_queue):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record):
        self.log_queue.put(record)

# 设置日志处理器
queue_handler = QueueHandler(log_queue)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
queue_handler.setFormatter(formatter)
logger.addHandler(queue_handler)

class SwitchRomMergerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Switch ROM 管理工具")
        self.root.geometry("800x600")
        self.root.minsize(800, 600)
        
        # 设置风格
        self.style = ttk.Style()
        self.style.configure("TButton", font=("Arial", 10))
        self.style.configure("TLabel", font=("Arial", 11))
        self.style.configure("TFrame", background="#f0f0f0")
        
        # 创建主框架
        self.main_frame = ttk.Frame(root, padding="10")
        self.main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 顶部标题
        self.title_label = ttk.Label(
            self.main_frame, 
            text="Switch ROM 管理工具", 
            font=("Arial", 16, "bold")
        )
        self.title_label.pack(pady=10)
        
        # 描述标签
        self.desc_label = ttk.Label(
            self.main_frame,
            text="本工具可以帮助您整理Switch游戏文件，包括基础游戏、更新和DLC。",
            wraplength=700
        )
        self.desc_label.pack(pady=5)
        
        # 控制区域框架
        self.control_frame = ttk.Frame(self.main_frame)
        self.control_frame.pack(fill=tk.X, pady=10)
        
        # 目录选择区域
        self.dir_frame = ttk.LabelFrame(self.control_frame, text="ROM目录设置", padding=10)
        self.dir_frame.pack(fill=tk.X, pady=5)
        
        self.dir_var = tk.StringVar(value=str(Path("rom")))
        
        self.dir_entry = ttk.Entry(self.dir_frame, textvariable=self.dir_var, width=50)
        self.dir_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        self.browse_btn = ttk.Button(self.dir_frame, text="浏览...", command=self.browse_directory)
        self.browse_btn.pack(side=tk.RIGHT)
        
        # 添加输出设置区域
        self.output_frame = ttk.LabelFrame(self.control_frame, text="输出设置", padding=10)
        self.output_frame.pack(fill=tk.X, pady=5)
        
        self.flat_output_var = tk.BooleanVar(value=False)
        self.flat_output_check = ttk.Checkbutton(
            self.output_frame,
            text="平铺输出文件（所有文件直接放在output目录下，不创建游戏子目录）",
            variable=self.flat_output_var
        )
        self.flat_output_check.pack(anchor=tk.W)
        
        # 操作按钮区域
        self.button_frame = ttk.Frame(self.control_frame)
        self.button_frame.pack(fill=tk.X, pady=10)
        
        self.scan_btn = ttk.Button(
            self.button_frame, 
            text="扫描游戏", 
            command=self.scan_games
        )
        self.scan_btn.pack(side=tk.LEFT, padx=5)
        
        self.merge_btn = ttk.Button(
            self.button_frame, 
            text="整理所有游戏", 
            command=self.merge_all_games
        )
        self.merge_btn.pack(side=tk.LEFT, padx=5)
        
        self.clear_output_btn = ttk.Button(
            self.button_frame,
            text="清空输出",
            command=self.clear_output_directory
        )
        self.clear_output_btn.pack(side=tk.LEFT, padx=5)
        
        self.clear_temp_btn = ttk.Button(
            self.button_frame,
            text="清空临时文件",
            command=self.clear_temp_directory
        )
        self.clear_temp_btn.pack(side=tk.LEFT, padx=5)

        # 第二行按钮
        self.button_frame2 = ttk.Frame(self.control_frame)
        self.button_frame2.pack(fill=tk.X, pady=5)
        
        self.open_output_btn = ttk.Button(
            self.button_frame2,
            text="打开输出目录",
            command=self.open_output_directory,
            state=tk.DISABLED  # 初始状态禁用
        )
        self.open_output_btn.pack(side=tk.LEFT, padx=5)
        
        self.open_temp_btn = ttk.Button(
            self.button_frame2,
            text="打开临时目录",
            command=self.open_temp_directory
        )
        self.open_temp_btn.pack(side=tk.LEFT, padx=5)

        # 日志显示区域
        self.log_frame = ttk.LabelFrame(self.main_frame, text="处理日志", padding=10)
        self.log_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        self.log_text = scrolledtext.ScrolledText(self.log_frame, height=15)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # 状态栏
        self.status_var = tk.StringVar(value="就绪")
        self.status_bar = ttk.Label(self.main_frame, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(fill=tk.X, side=tk.BOTTOM, pady=5)
        
        # 底部信息区域
        self.info_frame = ttk.Frame(self.main_frame)
        self.info_frame.pack(fill=tk.X, side=tk.BOTTOM, pady=5)
        
        self.info_label = ttk.Label(
            self.info_frame,
            text="提示: 本工具仅整理文件，创建真正的合并XCI需使用SAK或NSC_BUILDER工具。",
            wraplength=700,
            font=("Arial", 9)
        )
        self.info_label.pack(pady=5)
        
        # 设置日志处理定时器
        self.root.after(100, self.check_log_queue)
        
        # 检查工具和目录
        self.check_environment()
        
    def check_environment(self):
        """检查工具环境"""
        # 创建所需目录
        Path("output").mkdir(exist_ok=True)
        Path("temp").mkdir(exist_ok=True)
        Path("tools").mkdir(exist_ok=True)
        Path("rom").mkdir(exist_ok=True)
        
        # 检查工具
        tools_ok = True
        
        if not self.find_tool("hactoolnet.exe"):
            self.log_message("警告: 未找到hactoolnet.exe工具，请下载并放到tools目录")
            tools_ok = False
            
        if not self.find_tool("nsz.exe"):
            self.log_message("警告: 未找到nsz.exe工具，请下载并放到tools目录")
            tools_ok = False
            
        # 检查密钥文件
        keys_found = False
        possible_key_locations = [
            Path('prod.keys'),
            Path(os.path.expanduser('~/.switch/prod.keys')),
            Path(os.path.expanduser('~/switch/prod.keys')),
            Path('tools/keys.txt'),
        ]
        
        for key_path in possible_key_locations:
            if key_path.exists():
                keys_found = True
                self.log_message(f"找到密钥文件: {key_path}")
                break
                
        if not keys_found:
            self.log_message("警告: 未找到prod.keys密钥文件，请将其放在工具根目录下")
            
        if tools_ok and keys_found:
            self.log_message("环境检查完成：所有工具和密钥文件已找到")
        else:
            self.log_message("环境检查完成：缺少某些必要的工具或密钥文件")
            
        # 检查output目录内容，决定是否启用打开输出目录按钮
        self.update_output_button_state()
            
    def find_tool(self, tool_name):
        """查找指定的工具"""
        tools_dir = Path("tools")
        
        # 直接在tools目录中查找
        if (tools_dir / tool_name).exists():
            return True
            
        # 在子目录中查找
        for item in tools_dir.glob(f"**/{tool_name}"):
            return True
            
        return False
        
    def browse_directory(self):
        """打开文件夹选择对话框"""
        dir_path = filedialog.askdirectory(title="选择ROM目录")
        if dir_path:
            self.dir_var.set(dir_path)
            
    def log_message(self, message):
        """向日志区域添加消息"""
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        
    def check_log_queue(self):
        """检查日志队列，将日志显示到GUI"""
        try:
            while True:
                record = log_queue.get_nowait()
                msg = self.formatter_log(record)
                self.log_text.insert(tk.END, msg + "\n")
                self.log_text.see(tk.END)
                log_queue.task_done()
        except queue.Empty:
            pass
        
        # 重新安排定时器
        self.root.after(100, self.check_log_queue)
        
    def formatter_log(self, record):
        """格式化日志记录"""
        if record.levelno == logging.INFO:
            return f"{record.asctime} - {record.message}"
        else:
            return f"{record.asctime} - {record.levelname} - {record.message}"
            
    def update_status(self, message):
        """更新状态栏消息"""
        self.status_var.set(message)
        
    def scan_games(self):
        """扫描游戏文件"""
        self.update_status("正在扫描游戏文件...")
        self.log_message("开始扫描游戏文件...")
        
        rom_dir = Path(self.dir_var.get())
        if not rom_dir.exists():
            self.log_message(f"错误: 目录 {rom_dir} 不存在")
            self.update_status("扫描失败: 目录不存在")
            return
            
        # 禁用按钮，防止重复点击
        self.scan_btn.config(state=tk.DISABLED)
        self.merge_btn.config(state=tk.DISABLED)
        
        # 启动后台线程
        threading.Thread(target=self.scan_thread, args=(rom_dir,), daemon=True).start()
        
    def scan_thread(self, rom_dir):
        """后台扫描线程"""
        try:
            merger = SwitchRomMerger()
            game_files = merger.scan_directory(rom_dir)
            
            # 在GUI线程中更新状态
            self.root.after(0, lambda: self.scan_complete(game_files))
            
        except Exception as e:
            import traceback
            error_msg = f"扫描过程中出错: {str(e)}\n{traceback.format_exc()}"
            # 在GUI线程中更新状态
            self.root.after(0, lambda: self.scan_error(error_msg))
            
    def scan_complete(self, game_files):
        """扫描完成后的回调"""
        self.log_message(f"扫描完成，找到 {len(game_files)} 个游戏")
        self.update_status(f"扫描完成: 找到 {len(game_files)} 个游戏")
        
        # 启用按钮
        self.scan_btn.config(state=tk.NORMAL)
        self.merge_btn.config(state=tk.NORMAL)
        
    def scan_error(self, error_msg):
        """扫描错误的回调"""
        self.log_message(error_msg)
        self.update_status("扫描失败")
        
        # 启用按钮
        self.scan_btn.config(state=tk.NORMAL)
        self.merge_btn.config(state=tk.NORMAL)
        
    def merge_all_games(self):
        """合并所有游戏"""
        self.update_status("正在整理所有游戏文件...")
        self.log_message("开始整理所有游戏文件...")
        
        rom_dir = Path(self.dir_var.get())
        if not rom_dir.exists():
            self.log_message(f"错误: 目录 {rom_dir} 不存在")
            self.update_status("处理失败: 目录不存在")
            return
            
        # 禁用按钮，防止重复点击
        self.scan_btn.config(state=tk.DISABLED)
        self.merge_btn.config(state=tk.DISABLED)
        
        # 获取平铺输出设置
        flat_output = self.flat_output_var.get()
        if flat_output:
            self.log_message("使用平铺输出模式，所有文件将直接放在output目录下")
        
        # 启动后台线程
        threading.Thread(target=self.merge_thread, args=(rom_dir, flat_output), daemon=True).start()
        
    def merge_thread(self, rom_dir, flat_output):
        """后台合并线程"""
        try:
            merger = SwitchRomMerger(flat_output=flat_output)
            game_files = merger.scan_directory(rom_dir)
            
            # 处理所有游戏
            for game_id, files_dict in game_files.items():
                # 只处理有基础游戏文件的游戏
                if files_dict['base']:
                    merger.merge_files(game_id, files_dict)
                
            # 在GUI线程中更新状态
            self.root.after(0, lambda: self.merge_complete(len(game_files)))
            
        except Exception as e:
            import traceback
            error_msg = f"处理过程中出错: {str(e)}\n{traceback.format_exc()}"
            # 在GUI线程中更新状态
            self.root.after(0, lambda: self.merge_error(error_msg))
            
    def merge_complete(self, game_count):
        """合并完成后的回调"""
        self.log_message(f"处理完成，共处理 {game_count} 个游戏")
        
        # 自动清理临时文件
        self.log_message("自动清理临时文件...")
        self.clear_temp_files()
        
        self.update_status(f"处理完成: {game_count} 个游戏已整理")
        
        # 启用按钮
        self.scan_btn.config(state=tk.NORMAL)
        self.merge_btn.config(state=tk.NORMAL)
        
        # 启用打开输出目录按钮
        self.open_output_btn.config(state=tk.NORMAL)
        
        # 提示用户可以打开输出目录
        self.log_message("处理完成，可以点击\"打开输出目录\"按钮查看结果")
        
    def merge_error(self, error_msg):
        """合并错误的回调"""
        self.log_message(error_msg)
        
        # 尝试清理临时文件
        self.log_message("尝试清理临时文件...")
        self.clear_temp_files()
        
        self.update_status("处理失败")
        
        # 启用按钮
        self.scan_btn.config(state=tk.NORMAL)
        self.merge_btn.config(state=tk.NORMAL)
        
    def clear_temp_files(self):
        """清理临时文件"""
        try:
            temp_dir = Path("temp")
            if temp_dir.exists():
                import shutil
                file_count = 0
                
                for item in temp_dir.glob("**/*"):
                    if item.is_file():
                        file_count += 1
                
                # 删除所有文件
                shutil.rmtree(temp_dir)
                temp_dir.mkdir(exist_ok=True)
                
                self.log_message(f"临时文件清理完成，删除了 {file_count} 个文件")
        except Exception as e:
            import traceback
            self.log_message(f"清理临时文件时出错: {str(e)}")
            self.log_message(traceback.format_exc())
        
    def clear_output_directory(self):
        """清空输出目录"""
        result = tk.messagebox.askquestion(
            "确认操作", 
            "确定要清空output目录吗？这将删除所有已处理的游戏文件。", 
            icon='warning'
        )
        
        if result == 'yes':
            self.update_status("正在清空output目录...")
            self.log_message("开始清空output目录...")
            
            # 启动后台线程
            threading.Thread(target=self.clear_directory, args=("output",), daemon=True).start()
            
    def clear_temp_directory(self):
        """清空临时目录"""
        result = tk.messagebox.askquestion(
            "确认操作", 
            "确定要清空temp目录吗？", 
            icon='warning'
        )
        
        if result == 'yes':
            self.update_status("正在清空temp目录...")
            self.log_message("开始清空temp目录...")
            
            # 启动后台线程
            threading.Thread(target=self.clear_directory, args=("temp",), daemon=True).start()
            
    def clear_directory(self, dir_name):
        """清空指定目录"""
        try:
            target_dir = Path(dir_name)
            
            # 确保目录存在
            if not target_dir.exists():
                target_dir.mkdir(parents=True, exist_ok=True)
                self.root.after(0, lambda: self.clear_complete(dir_name, 0))
                return
                
            # 删除目录中的所有文件和子目录
            import shutil
            file_count = 0
            
            for item in target_dir.glob("**/*"):
                if item.is_file():
                    file_count += 1
                    
            # 删除所有文件
            shutil.rmtree(target_dir)
            target_dir.mkdir(parents=True, exist_ok=True)
            
            # 在GUI线程中更新状态
            self.root.after(0, lambda: self.clear_complete(dir_name, file_count))
            
        except Exception as e:
            import traceback
            error_msg = f"清空目录 {dir_name} 时出错: {str(e)}\n{traceback.format_exc()}"
            # 在GUI线程中更新状态
            self.root.after(0, lambda: self.log_message(error_msg))
            self.root.after(0, lambda: self.update_status(f"清空 {dir_name} 目录失败"))
            
    def clear_complete(self, dir_name, file_count):
        """清空目录完成后的回调"""
        self.log_message(f"已清空 {dir_name} 目录，删除了 {file_count} 个文件")
        self.update_status(f"已清空 {dir_name} 目录")
        
    def open_output_directory(self):
        """打开输出目录"""
        output_dir = Path("output").absolute()
        self.open_directory(output_dir)
        
    def open_temp_directory(self):
        """打开临时目录"""
        temp_dir = Path("temp").absolute()
        self.open_directory(temp_dir)
        
    def open_directory(self, directory):
        """跨平台打开目录"""
        try:
            if platform.system() == "Windows":
                os.startfile(directory)
            elif platform.system() == "Darwin":  # macOS
                subprocess.run(["open", directory], check=True)
            else:  # Linux
                subprocess.run(["xdg-open", directory], check=True)
            
            self.log_message(f"已打开目录: {directory}")
            self.update_status(f"已打开目录: {directory}")
        except Exception as e:
            self.log_message(f"打开目录失败: {str(e)}")
            self.update_status("打开目录失败")

    def update_output_button_state(self):
        """根据output目录内容更新按钮状态"""
        output_dir = Path("output")
        if output_dir.exists() and any(output_dir.iterdir()):
            self.open_output_btn.config(state=tk.NORMAL)
        else:
            self.open_output_btn.config(state=tk.DISABLED)

def main():
    # 全局设置
    os.environ['PYTHONHTTPSVERIFY'] = '0'  # 禁用SSL证书验证
    
    # 创建GUI窗口
    root = tk.Tk()
    app = SwitchRomMergerGUI(root)
    
    # 启动事件循环
    root.mainloop()

if __name__ == "__main__":
    main() 