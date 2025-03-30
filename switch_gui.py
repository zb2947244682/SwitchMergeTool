#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import threading
import queue
import time
import subprocess
from pathlib import Path
import locale

# 设置本地化支持中文
locale.setlocale(locale.LC_ALL, '')

class SwitchRomMergerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Switch游戏合并工具")
        self.root.geometry("800x600")
        self.root.minsize(800, 600)
        
        # 设置图标
        try:
            self.root.iconbitmap("tools/icon.ico")
        except:
            pass
        
        # 设置样式
        self.style = ttk.Style()
        self.style.configure("TFrame", background="#f0f0f0")
        self.style.configure("TButton", font=("微软雅黑", 10))
        self.style.configure("TLabel", font=("微软雅黑", 10), background="#f0f0f0")
        self.style.configure("Header.TLabel", font=("微软雅黑", 12, "bold"), background="#f0f0f0")
        
        # 创建主框架
        self.main_frame = ttk.Frame(root, padding="10")
        self.main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 创建顶部控制面板
        self.create_control_panel()
        
        # 创建日志区域
        self.create_log_area()
        
        # 创建游戏列表区域
        self.create_game_list_area()
        
        # 创建状态栏
        self.create_status_bar()
        
        # 消息队列
        self.log_queue = queue.Queue()
        self.game_list_queue = queue.Queue()
        
        # 启动线程更新UI
        self.start_gui_update_thread()
        
        # 检查必要的文件和目录
        self.check_required_files()
    
    def create_control_panel(self):
        """创建顶部控制面板"""
        control_frame = ttk.Frame(self.main_frame)
        control_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # 标题
        title_label = ttk.Label(control_frame, text="Switch游戏合并工具", style="Header.TLabel")
        title_label.pack(side=tk.LEFT, padx=5, pady=5)
        
        # 扫描按钮
        self.scan_button = ttk.Button(control_frame, text="扫描游戏", command=self.scan_games)
        self.scan_button.pack(side=tk.RIGHT, padx=5, pady=5)
        
        # 合并按钮
        self.merge_button = ttk.Button(control_frame, text="合并所有游戏", command=self.merge_games)
        self.merge_button.pack(side=tk.RIGHT, padx=5, pady=5)
        self.merge_button.config(state="disabled")
        
        # 打开输出目录按钮
        self.open_output_button = ttk.Button(control_frame, text="打开输出目录", command=self.open_output_dir)
        self.open_output_button.pack(side=tk.RIGHT, padx=5, pady=5)
    
    def create_log_area(self):
        """创建日志区域"""
        log_frame = ttk.LabelFrame(self.main_frame, text="日志信息")
        log_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 日志文本框
        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, background="black", foreground="white")
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.log_text.config(state=tk.DISABLED)
        
        # 添加右键菜单
        self.log_context_menu = tk.Menu(self.log_text, tearoff=0)
        self.log_context_menu.add_command(label="清除日志", command=self.clear_log)
        self.log_context_menu.add_command(label="复制所有文本", command=self.copy_log)
        self.log_context_menu.add_command(label="保存日志到文件", command=self.save_log)
        
        self.log_text.bind("<Button-3>", self.show_log_context_menu)
    
    def create_game_list_area(self):
        """创建游戏列表区域"""
        game_frame = ttk.LabelFrame(self.main_frame, text="已发现的游戏")
        game_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 创建Treeview用于显示游戏列表
        columns = ("游戏名称", "基础游戏", "更新文件", "DLC文件", "状态")
        self.game_tree = ttk.Treeview(game_frame, columns=columns, show="headings")
        
        # 设置列标题
        for col in columns:
            self.game_tree.heading(col, text=col)
            self.game_tree.column(col, width=100)
        
        # 设置列宽
        self.game_tree.column("游戏名称", width=150)
        self.game_tree.column("基础游戏", width=150)
        self.game_tree.column("更新文件", width=100)
        self.game_tree.column("DLC文件", width=100)
        self.game_tree.column("状态", width=100)
        
        # 创建滚动条
        scrollbar = ttk.Scrollbar(game_frame, orient=tk.VERTICAL, command=self.game_tree.yview)
        self.game_tree.configure(yscrollcommand=scrollbar.set)
        
        # 放置控件
        self.game_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 5), pady=5)
        
        # 添加右键菜单
        self.game_context_menu = tk.Menu(self.game_tree, tearoff=0)
        self.game_context_menu.add_command(label="合并所选游戏", command=self.merge_selected_game)
        self.game_context_menu.add_command(label="查看详情", command=self.view_game_details)
        
        self.game_tree.bind("<Button-3>", self.show_game_context_menu)
    
    def create_status_bar(self):
        """创建状态栏"""
        self.status_var = tk.StringVar()
        self.status_var.set("就绪")
        
        status_frame = ttk.Frame(self.root)
        status_frame.pack(fill=tk.X, side=tk.BOTTOM, padx=5, pady=2)
        
        status_label = ttk.Label(status_frame, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_label.pack(fill=tk.X)
        
        # 进度条
        self.progress_var = tk.DoubleVar()
        self.progress_var.set(0.0)
        
        self.progress_bar = ttk.Progressbar(status_frame, variable=self.progress_var, mode="determinate")
        self.progress_bar.pack(fill=tk.X, pady=(2, 0))
    
    def show_log_context_menu(self, event):
        """显示日志右键菜单"""
        self.log_context_menu.post(event.x_root, event.y_root)
    
    def show_game_context_menu(self, event):
        """显示游戏列表右键菜单"""
        selected_item = self.game_tree.selection()
        if selected_item:
            self.game_context_menu.post(event.x_root, event.y_root)
    
    def clear_log(self):
        """清除日志"""
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state=tk.DISABLED)
    
    def copy_log(self):
        """复制日志内容"""
        self.root.clipboard_clear()
        self.root.clipboard_append(self.log_text.get(1.0, tk.END))
    
    def save_log(self):
        """保存日志到文件"""
        try:
            file_path = filedialog.asksaveasfilename(
                defaultextension=".txt",
                filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")],
                title="保存日志"
            )
            if file_path:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(self.log_text.get(1.0, tk.END))
                self.add_log(f"日志已保存到: {file_path}", "success")
        except Exception as e:
            self.add_log(f"保存日志时出错: {str(e)}", "error")
    
    def add_log(self, message, level="info"):
        """添加日志消息到队列"""
        self.log_queue.put((message, level))
    
    def update_log(self):
        """更新日志区域"""
        try:
            while not self.log_queue.empty():
                message, level = self.log_queue.get_nowait()
                self.log_text.config(state=tk.NORMAL)
                
                # 添加颜色
                color = "white"  # 默认颜色
                if level == "error":
                    color = "red"
                elif level == "warning":
                    color = "yellow"
                elif level == "success":
                    color = "green"
                elif level == "info":
                    color = "white"
                
                # 添加时间戳
                timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
                self.log_text.insert(tk.END, f"[{timestamp}] ", "timestamp")
                self.log_text.insert(tk.END, f"{message}\n", level)
                
                # 设置标签颜色
                self.log_text.tag_config("timestamp", foreground="#aaaaaa")
                self.log_text.tag_config(level, foreground=color)
                
                # 滚动到底部
                self.log_text.see(tk.END)
                self.log_text.config(state=tk.DISABLED)
                
                # 更新状态栏
                self.status_var.set(message[:50] + "..." if len(message) > 50 else message)
        except Exception as e:
            print(f"更新日志时出错: {str(e)}")
    
    def update_game_list(self):
        """更新游戏列表"""
        try:
            while not self.game_list_queue.empty():
                action, data = self.game_list_queue.get_nowait()
                
                if action == "clear":
                    for item in self.game_tree.get_children():
                        self.game_tree.delete(item)
                
                elif action == "add":
                    game_id, base_file, update_count, dlc_count, status = data
                    self.game_tree.insert("", tk.END, values=(
                        game_id,
                        base_file if base_file else "无",
                        update_count,
                        dlc_count,
                        status
                    ))
                
                elif action == "update":
                    game_id, status = data
                    for item in self.game_tree.get_children():
                        if self.game_tree.item(item, "values")[0] == game_id:
                            values = self.game_tree.item(item, "values")
                            new_values = values[:-1] + (status,)
                            self.game_tree.item(item, values=new_values)
                            break
        except Exception as e:
            print(f"更新游戏列表时出错: {str(e)}")
    
    def start_gui_update_thread(self):
        """启动GUI更新线程"""
        def update_gui():
            while True:
                self.update_log()
                self.update_game_list()
                time.sleep(0.1)
        
        threading.Thread(target=update_gui, daemon=True).start()
    
    def check_required_files(self):
        """检查必要的文件和目录"""
        missing_files = []
        
        # 检查目录
        for dir_name in ["OUTPUT", "TEMP", "rom", "tools"]:
            if not os.path.exists(dir_name):
                if dir_name in ["OUTPUT", "TEMP"]:
                    self.add_log(f"创建目录: {dir_name}", "info")
                    os.makedirs(dir_name, exist_ok=True)
                else:
                    missing_files.append(dir_name)
        
        # 检查密钥文件
        if not os.path.exists("prod.keys"):
            missing_files.append("prod.keys")
        
        # 检查固件目录
        if not os.path.exists("Firmware") or not os.listdir("Firmware"):
            missing_files.append("Firmware")
        
        # 检查工具
        if not os.path.exists("tools/hactoolnet.exe"):
            missing_files.append("tools/hactoolnet.exe")
        
        # 检查NSZ工具
        nsz_exists = False
        if os.path.exists("tools/nsz.exe"):
            nsz_exists = True
        else:
            for root, dirs, files in os.walk("tools"):
                if "nsz.exe" in files:
                    nsz_exists = True
                    break
        
        if not nsz_exists:
            missing_files.append("nsz.exe")
        
        # 报告缺失的文件
        if missing_files:
            self.add_log(f"缺少以下必要文件或目录:", "warning")
            for f in missing_files:
                self.add_log(f"- {f}", "warning")
            self.add_log("请确保所有必要的文件和目录都已准备好", "warning")
        else:
            self.add_log("所有必要的文件和目录都已准备好", "success")
    
    def scan_games(self):
        """扫描游戏文件"""
        self.add_log("开始扫描游戏文件...", "info")
        self.game_list_queue.put(("clear", None))
        self.progress_var.set(0)
        
        def run_scan():
            try:
                # 禁用按钮
                self.scan_button.config(state="disabled")
                
                # 创建subprocess进程
                cmd = ["python", "switch_rom_merger.py", "--scan-only"]
                
                # 以subprocess方式运行
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,
                    universal_newlines=True
                )
                
                # 读取输出并解析
                game_count = 0
                for line in process.stdout:
                    self.add_log(line.strip())
                    
                    # 解析游戏信息
                    if "游戏:" in line:
                        game_id = line.split("游戏:")[1].strip()
                    elif "基础游戏:" in line:
                        base_file = line.split("基础游戏:")[1].strip()
                        if base_file == "无":
                            base_file = None
                    elif "更新文件:" in line:
                        update_count = line.split("更新文件:")[1].strip().split(" ")[0]
                    elif "DLC文件:" in line:
                        dlc_count = line.split("DLC文件:")[1].strip().split(" ")[0]
                        
                        # 添加到游戏列表
                        self.game_list_queue.put((
                            "add",
                            (game_id, base_file, update_count, dlc_count, "待合并")
                        ))
                        game_count += 1
                
                # 读取错误输出
                for line in process.stderr:
                    self.add_log(line.strip(), "error")
                
                # 等待进程完成
                process.wait()
                
                if process.returncode == 0:
                    self.add_log(f"扫描完成，发现 {game_count} 个游戏", "success")
                    
                    # 如果有游戏，启用合并按钮
                    if game_count > 0:
                        self.merge_button.config(state="normal")
                else:
                    self.add_log(f"扫描失败，返回码: {process.returncode}", "error")
            except Exception as e:
                self.add_log(f"扫描游戏文件时出错: {str(e)}", "error")
            finally:
                # 恢复按钮
                self.scan_button.config(state="normal")
        
        # 启动后台线程
        threading.Thread(target=run_scan, daemon=True).start()
    
    def merge_games(self):
        """合并所有游戏"""
        self.add_log("开始合并所有游戏文件...", "info")
        
        # 更新所有游戏状态为"合并中"
        for item in self.game_tree.get_children():
            game_id = self.game_tree.item(item, "values")[0]
            self.game_list_queue.put(("update", (game_id, "合并中")))
        
        def run_merge():
            try:
                # 禁用按钮
                self.merge_button.config(state="disabled")
                self.scan_button.config(state="disabled")
                
                # 创建subprocess进程
                cmd = ["python", "switch_rom_merger.py"]
                
                # 以subprocess方式运行
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,
                    universal_newlines=True
                )
                
                # 读取输出并解析
                current_game = None
                for line in process.stdout:
                    self.add_log(line.strip())
                    
                    # 解析游戏信息
                    if "开始合并游戏" in line:
                        current_game = line.split("开始合并游戏")[1].strip()
                        self.game_list_queue.put(("update", (current_game, "合并中")))
                    elif "合并成功" in line and current_game:
                        self.game_list_queue.put(("update", (current_game, "合并成功")))
                    elif "错误" in line.lower() and current_game:
                        self.game_list_queue.put(("update", (current_game, "合并失败")))
                    elif "警告" in line.lower() and current_game:
                        self.game_list_queue.put(("update", (current_game, "合并警告")))
                    elif "处理完成" in line and current_game:
                        self.game_list_queue.put(("update", (current_game, "已完成")))
                
                # 读取错误输出
                for line in process.stderr:
                    self.add_log(line.strip(), "error")
                
                # 等待进程完成
                process.wait()
                
                if process.returncode == 0:
                    self.add_log("所有游戏合并完成", "success")
                else:
                    self.add_log(f"合并失败，返回码: {process.returncode}", "error")
            except Exception as e:
                self.add_log(f"合并游戏文件时出错: {str(e)}", "error")
            finally:
                # 恢复按钮
                self.merge_button.config(state="normal")
                self.scan_button.config(state="normal")
        
        # 启动后台线程
        threading.Thread(target=run_merge, daemon=True).start()
    
    def merge_selected_game(self):
        """合并选中的游戏"""
        selected_items = self.game_tree.selection()
        if not selected_items:
            messagebox.showinfo("提示", "请先选择要合并的游戏")
            return
        
        game_ids = []
        for item in selected_items:
            game_id = self.game_tree.item(item, "values")[0]
            game_ids.append(game_id)
            self.game_list_queue.put(("update", (game_id, "合并中")))
        
        self.add_log(f"开始合并选中的 {len(game_ids)} 个游戏...", "info")
        
        def run_merge():
            try:
                # 禁用按钮
                self.merge_button.config(state="disabled")
                self.scan_button.config(state="disabled")
                
                # 为每个游戏单独创建一个进程
                for game_id in game_ids:
                    self.add_log(f"开始合并游戏: {game_id}", "info")
                    
                    # 创建subprocess进程
                    cmd = ["python", "switch_rom_merger.py", "--game-id", game_id]
                    
                    # 以subprocess方式运行
                    process = subprocess.Popen(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        bufsize=1,
                        universal_newlines=True
                    )
                    
                    # 读取输出并解析
                    for line in process.stdout:
                        self.add_log(line.strip())
                        
                        # 解析游戏信息
                        if "合并成功" in line:
                            self.game_list_queue.put(("update", (game_id, "合并成功")))
                        elif "错误" in line.lower():
                            self.game_list_queue.put(("update", (game_id, "合并失败")))
                        elif "警告" in line.lower():
                            self.game_list_queue.put(("update", (game_id, "合并警告")))
                        elif "处理完成" in line:
                            self.game_list_queue.put(("update", (game_id, "已完成")))
                    
                    # 读取错误输出
                    for line in process.stderr:
                        self.add_log(line.strip(), "error")
                    
                    # 等待进程完成
                    process.wait()
                    
                    if process.returncode == 0:
                        self.add_log(f"游戏 {game_id} 合并完成", "success")
                    else:
                        self.add_log(f"游戏 {game_id} 合并失败，返回码: {process.returncode}", "error")
                
                self.add_log("所有选中的游戏合并完成", "success")
            except Exception as e:
                self.add_log(f"合并游戏文件时出错: {str(e)}", "error")
            finally:
                # 恢复按钮
                self.merge_button.config(state="normal")
                self.scan_button.config(state="normal")
        
        # 启动后台线程
        threading.Thread(target=run_merge, daemon=True).start()
    
    def view_game_details(self):
        """查看游戏详情"""
        selected_items = self.game_tree.selection()
        if not selected_items:
            messagebox.showinfo("提示", "请先选择要查看的游戏")
            return
        
        game_id = self.game_tree.item(selected_items[0], "values")[0]
        base_file = self.game_tree.item(selected_items[0], "values")[1]
        update_count = self.game_tree.item(selected_items[0], "values")[2]
        dlc_count = self.game_tree.item(selected_items[0], "values")[3]
        status = self.game_tree.item(selected_items[0], "values")[4]
        
        # 构建详情信息
        details = f"游戏ID: {game_id}\n"
        details += f"基础游戏: {base_file}\n"
        details += f"更新文件数量: {update_count}\n"
        details += f"DLC文件数量: {dlc_count}\n"
        details += f"状态: {status}\n\n"
        
        # 查找输出目录中的文件
        output_dir = Path("OUTPUT")
        if output_dir.exists():
            details += "可能的输出文件:\n"
            for file in output_dir.glob(f"{game_id}*.xci"):
                file_size = file.stat().st_size / (1024 * 1024)  # MB
                details += f"- {file.name} ({file_size:.2f} MB)\n"
            
            if not any(output_dir.glob(f"{game_id}*.xci")):
                details += "尚未找到匹配的输出文件"
        else:
            details += "尚未生成输出文件"
        
        # 显示详情对话框
        messagebox.showinfo(f"游戏详情 - {game_id}", details)
    
    def open_output_dir(self):
        """打开输出目录"""
        output_dir = Path("OUTPUT").absolute()
        if output_dir.exists():
            if sys.platform == "win32":
                os.startfile(output_dir)
            elif sys.platform == "darwin":
                subprocess.run(["open", output_dir])
            else:
                subprocess.run(["xdg-open", output_dir])
            self.add_log(f"已打开输出目录: {output_dir}", "info")
        else:
            self.add_log(f"输出目录不存在: {output_dir}", "error")

if __name__ == "__main__":
    # 禁用SSL证书验证
    import ssl
    try:
        _create_unverified_https_context = ssl._create_unverified_context
    except AttributeError:
        pass
    else:
        ssl._create_default_https_context = _create_unverified_https_context
    
    root = tk.Tk()
    app = SwitchRomMergerGUI(root)
    root.mainloop() 