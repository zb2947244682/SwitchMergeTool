import os
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk
from pathlib import Path
import logging
import queue
import time

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

# 环境变量也设置一下
os.environ['PYTHONHTTPSVERIFY'] = '0'

# 导入主脚本
import switch_rom_merger

# 设置日志
log_queue = queue.Queue()
gui_logger = logging.getLogger("GUI")
gui_logger.setLevel(logging.INFO)

# 自定义日志处理器，将日志消息放入队列
class QueueHandler(logging.Handler):
    def __init__(self, log_queue):
        super().__init__()
        self.log_queue = log_queue
        
    def emit(self, record):
        self.log_queue.put(record)

# 添加队列处理器到日志系统
queue_handler = QueueHandler(log_queue)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
queue_handler.setFormatter(formatter)
gui_logger.addHandler(queue_handler)
logging.getLogger().addHandler(queue_handler)

class RedirectText:
    def __init__(self, text_widget):
        self.text_widget = text_widget
        self.buffer = ""

    def write(self, string):
        self.buffer += string
        self.text_widget.insert(tk.END, string)
        self.text_widget.see(tk.END)
        self.text_widget.update()

    def flush(self):
        pass

class SwitchRomMergerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Switch游戏合并工具")
        self.root.geometry("800x600")
        self.root.minsize(700, 500)
        
        # 设置图标
        try:
            if os.path.exists("icon.ico"):
                self.root.iconbitmap("icon.ico")
        except Exception:
            pass
        
        # 设置界面
        self.setup_ui()
        
        # 工作线程
        self.worker_thread = None
        self.stop_event = threading.Event()
        
        # 保存扫描到的游戏
        self.games = {}
        
        # 日志刷新计时器
        self.root.after(100, self.update_log_display)
        
        # 状态变量
        self.running = False
        self.merger = None
        
        # 重定向标准输出
        self.text_redirect = RedirectText(self.log_text)
        sys.stdout = self.text_redirect
        sys.stderr = self.text_redirect
        
        # 状态栏
        self.status_var = tk.StringVar(value="就绪")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(fill=tk.X, side=tk.BOTTOM, pady=5)
    
    def setup_ui(self):
        # 创建主框架
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 控制面板
        control_frame = ttk.LabelFrame(main_frame, text="控制面板", padding="10")
        control_frame.pack(fill=tk.X, pady=5)
        
        # 输入目录
        input_frame = ttk.Frame(control_frame)
        input_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(input_frame, text="游戏文件目录:").pack(side=tk.LEFT, padx=5)
        self.input_dir_var = tk.StringVar(value=os.path.join(os.getcwd(), "rom"))
        ttk.Entry(input_frame, textvariable=self.input_dir_var, width=50).pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        ttk.Button(input_frame, text="浏览", command=self.browse_input_dir).pack(side=tk.LEFT, padx=5)
        
        # 模式选择
        mode_frame = ttk.Frame(control_frame)
        mode_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(mode_frame, text="扫描模式:").pack(side=tk.LEFT, padx=5)
        self.scan_mode_var = tk.StringVar(value="all")
        ttk.Radiobutton(mode_frame, text="所有游戏", variable=self.scan_mode_var, value="all").pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(mode_frame, text="仅扫描", variable=self.scan_mode_var, value="scan_only").pack(side=tk.LEFT, padx=5)
        
        # 游戏ID输入
        game_id_frame = ttk.Frame(control_frame)
        game_id_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(game_id_frame, text="游戏名称(可选):").pack(side=tk.LEFT, padx=5)
        self.game_id_var = tk.StringVar()
        ttk.Entry(game_id_frame, textvariable=self.game_id_var, width=40).pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        ttk.Label(game_id_frame, text="(输入游戏名称的一部分以筛选)").pack(side=tk.LEFT, padx=5)
        
        # 合并说明
        note_frame = ttk.LabelFrame(main_frame, text="合并说明", padding="10")
        note_frame.pack(fill=tk.X, pady=5)
        
        note_text = "本工具会将游戏整理到OUTPUT目录，并生成以下文件:\n" \
                    "1. 基础XCI文件 - 包含基础游戏，但不含更新和DLC\n" \
                    "2. 分类目录 - 包含基础游戏、最新更新和所有DLC文件\n\n" \
                    "注意: 如需创建完整合并的XCI(包含更新和DLC)，请使用:\n" \
                    "- SAK (Switch Army Knife)\n" \
                    "- NSC_BUILDER\n" \
                    "这些工具可以将我们整理好的文件进行真正的合并。\n\n" \
                    "在YUZU中使用时，您可以:\n" \
                    "1. 直接加载基础XCI文件(不含更新/DLC)\n" \
                    "2. 加载基础XCI后，通过'文件->安装文件到NAND'安装更新和DLC"
        
        note_label = ttk.Label(note_frame, text=note_text, justify=tk.LEFT, wraplength=780)
        note_label.pack(fill=tk.X, pady=5)
        
        # 按钮
        button_frame = ttk.Frame(control_frame)
        button_frame.pack(fill=tk.X, pady=5)
        
        self.start_button = ttk.Button(button_frame, text="开始处理", command=self.start_processing)
        self.start_button.pack(side=tk.LEFT, padx=5)
        
        self.stop_button = ttk.Button(button_frame, text="停止", command=self.stop_processing, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=5)
        
        # 日志区域
        log_frame = ttk.LabelFrame(main_frame, text="处理日志", padding="10")
        log_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, width=80, height=20)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # 状态栏
        self.status_var = tk.StringVar(value="就绪")
        status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(fill=tk.X, side=tk.BOTTOM, pady=5)
    
    def browse_input_dir(self):
        directory = filedialog.askdirectory(initialdir=self.input_dir_var.get())
        if directory:
            self.input_dir_var.set(directory)
    
    def update_log_display(self):
        """更新日志显示"""
        # 处理队列中的所有日志消息
        while True:
            try:
                record = log_queue.get_nowait()
                self.display_log(record)
                log_queue.task_done()
            except queue.Empty:
                break
        
        # 继续轮询
        self.root.after(100, self.update_log_display)
    
    def display_log(self, record):
        """显示日志消息"""
        self.log_text.config(state=tk.NORMAL)
        
        # 根据日志级别设置颜色
        tag = None
        if record.levelno >= logging.ERROR:
            tag = "error"
            self.log_text.tag_config("error", foreground="red")
        elif record.levelno >= logging.WARNING:
            tag = "warning"
            self.log_text.tag_config("warning", foreground="orange")
        elif record.levelno >= logging.INFO:
            tag = "info"
            self.log_text.tag_config("info", foreground="blue")
        
        # 添加日志消息
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        formatted_message = formatter.format(record)
        self.log_text.insert(tk.END, formatted_message + "\n", tag)
        
        # 滚动到底部
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)
    
    def start_processing(self):
        if self.running:
            return
            
        # 获取输入
        input_dir = self.input_dir_var.get()
        scan_mode = self.scan_mode_var.get()
        game_id = self.game_id_var.get()
        
        if not os.path.exists(input_dir):
            messagebox.showerror("错误", f"目录不存在: {input_dir}")
            return
            
        # 更新UI状态
        self.running = True
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        self.status_var.set("正在处理...")
        self.log_text.delete(1.0, tk.END)
        
        # 启动处理线程
        self.process_thread = threading.Thread(
            target=self.processing_thread,
            args=(input_dir, scan_mode == "scan_only", game_id)
        )
        self.process_thread.daemon = True
        self.process_thread.start()
        
        # 启动状态更新
        self.root.after(100, self.update_status)
    
    def processing_thread(self, input_dir, scan_only, game_id):
        try:
            gui_logger.info(f"开始处理目录: {input_dir}")
            gui_logger.info(f"模式: {'仅扫描' if scan_only else '完整处理'}")
            if game_id:
                gui_logger.info(f"指定游戏名称: {game_id}")
                
            # 创建合并器
            self.merger = switch_rom_merger.SwitchRomMerger()
            
            # 扫描文件
            input_path = Path(input_dir)
            game_files = self.merger.scan_directory(input_path)
            
            # 如果只需要扫描，直接返回
            if scan_only:
                gui_logger.info("仅扫描模式，不执行合并")
                return
                
            # 如果指定了游戏ID，只处理该游戏
            if game_id:
                # 查找匹配的游戏（支持部分匹配）
                matching_games = []
                search_term = game_id.lower()
                
                for group_id, files_dict in game_files.items():
                    game_name = files_dict['name'].lower()
                    
                    if search_term in group_id.lower() or search_term in game_name:
                        matching_games.append((group_id, files_dict))
                
                if matching_games:
                    gui_logger.info(f"找到 {len(matching_games)} 个匹配的游戏:")
                    for i, (group_id, files_dict) in enumerate(matching_games):
                        gui_logger.info(f"{i+1}. {files_dict['name']} (ID: {group_id})")
                    
                    # 如果只有一个匹配，直接处理
                    if len(matching_games) == 1:
                        group_id, files_dict = matching_games[0]
                        gui_logger.info(f"处理游戏: {files_dict['name']}")
                        self.merger.merge_files(group_id, files_dict)
                    else:
                        # 如果有多个匹配，提示用户选择
                        gui_logger.info(f"找到多个匹配的游戏，请使用更精确的游戏名称")
                else:
                    gui_logger.error(f"找不到匹配的游戏: {game_id}")
            else:
                # 处理所有游戏
                for group_id, files_dict in game_files.items():
                    # 只处理有基础游戏文件的游戏
                    if files_dict['base']:
                        try:
                            self.merger.merge_files(group_id, files_dict)
                        except Exception as e:
                            gui_logger.error(f"处理游戏 {files_dict['name']} 时出错: {str(e)}")
                    else:
                        gui_logger.warning(f"跳过没有基础游戏文件的游戏: {files_dict['name']}")
            
            gui_logger.info("处理完成")
            
        except Exception as e:
            gui_logger.error(f"处理过程中出错: {str(e)}")
            import traceback
            gui_logger.error(traceback.format_exc())
            
            # 在主线程中显示错误消息
            self.root.after(0, lambda: messagebox.showerror("错误", f"处理过程中出现错误:\n{str(e)}"))
        
        finally:
            self.running = False
            
    def stop_processing(self):
        if not self.running:
            return
            
        gui_logger.info("正在停止处理...")
        self.running = False
        
    def update_status(self):
        if not self.running:
            self.start_button.config(state=tk.NORMAL)
            self.stop_button.config(state=tk.DISABLED)
            self.status_var.set("处理完成" if not self.running else "已停止")
        else:
            self.root.after(100, self.update_status)
    
    def setup_environment(self):
        """运行环境设置脚本"""
        if os.path.exists("install_full_deps.bat"):
            os.system("start install_full_deps.bat")
        else:
            os.system("start setup.bat")
    
    def open_output_dir(self):
        """打开输出目录"""
        output_dir = Path("OUTPUT")
        if not output_dir.exists():
            output_dir.mkdir(exist_ok=True)
        
        # 打开资源管理器
        os.startfile(output_dir)

def main():
    # 全局禁用SSL证书验证
    os.environ['PYTHONHTTPSVERIFY'] = '0'
    
    root = tk.Tk()
    app = SwitchRomMergerGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main() 