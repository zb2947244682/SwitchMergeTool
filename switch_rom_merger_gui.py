import os
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
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

class SwitchRomMergerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Switch游戏合并工具")
        self.root.geometry("800x600")
        self.root.minsize(700, 500)
        
        # 设置界面
        self.setup_ui()
        
        # 工作线程
        self.worker_thread = None
        self.stop_event = threading.Event()
        
        # 日志刷新计时器
        self.root.after(100, self.update_log_display)
    
    def setup_ui(self):
        # 创建主框架
        main_frame = tk.Frame(self.root, padx=10, pady=10)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 顶部框架 - 选择目录
        top_frame = tk.Frame(main_frame)
        top_frame.pack(fill=tk.X, pady=(0, 10))
        
        tk.Label(top_frame, text="ROM目录:").pack(side=tk.LEFT, padx=(0, 5))
        
        self.dir_var = tk.StringVar(value=str(Path.cwd() / "rom"))
        dir_entry = tk.Entry(top_frame, textvariable=self.dir_var, width=50)
        dir_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        browse_button = tk.Button(top_frame, text="浏览...", command=self.browse_directory)
        browse_button.pack(side=tk.LEFT)
        
        # 中间框架 - 日志显示
        mid_frame = tk.Frame(main_frame)
        mid_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        tk.Label(mid_frame, text="处理日志:").pack(anchor=tk.W)
        
        self.log_text = scrolledtext.ScrolledText(mid_frame, height=20, wrap=tk.WORD)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        self.log_text.config(state=tk.DISABLED)
        
        # 底部框架 - 按钮
        bottom_frame = tk.Frame(main_frame)
        bottom_frame.pack(fill=tk.X)
        
        self.start_button = tk.Button(bottom_frame, text="开始处理", command=self.start_processing, width=15)
        self.start_button.pack(side=tk.LEFT, padx=(0, 5))
        
        self.setup_button = tk.Button(bottom_frame, text="环境设置", command=self.setup_environment, width=15)
        self.setup_button.pack(side=tk.LEFT, padx=(0, 5))
        
        self.output_button = tk.Button(bottom_frame, text="打开输出目录", command=self.open_output_dir, width=15)
        self.output_button.pack(side=tk.LEFT, padx=(0, 5))
        
        self.exit_button = tk.Button(bottom_frame, text="退出", command=self.root.quit, width=15)
        self.exit_button.pack(side=tk.RIGHT)
    
    def browse_directory(self):
        """打开目录选择对话框"""
        directory = filedialog.askdirectory(initialdir=self.dir_var.get())
        if directory:
            self.dir_var.set(directory)
    
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
        """开始处理"""
        if self.worker_thread and self.worker_thread.is_alive():
            messagebox.showinfo("处理中", "已有处理任务正在进行中")
            return
        
        directory = Path(self.dir_var.get())
        if not directory.exists():
            messagebox.showerror("错误", f"目录不存在: {directory}")
            return
        
        # 清空日志显示
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state=tk.DISABLED)
        
        # 禁用开始按钮
        self.start_button.config(state=tk.DISABLED, text="处理中...")
        
        # 重置停止事件
        self.stop_event.clear()
        
        # 创建并启动工作线程
        self.worker_thread = threading.Thread(
            target=self.processing_thread, 
            args=(directory,),
            daemon=True
        )
        self.worker_thread.start()
    
    def processing_thread(self, directory):
        """处理线程"""
        try:
            gui_logger.info(f"开始处理目录: {directory}")
            
            # 创建合并器实例
            merger = switch_rom_merger.SwitchRomMerger()
            
            # 处理目录
            merger.process_directory(directory)
            
            gui_logger.info("处理完成")
            
            # 在主线程中显示完成消息
            self.root.after(0, lambda: messagebox.showinfo("完成", "游戏文件处理完成!\n输出文件保存在OUTPUT目录中。"))
            
        except Exception as e:
            gui_logger.error(f"处理过程中出现错误: {str(e)}")
            import traceback
            gui_logger.error(traceback.format_exc())
            
            # 在主线程中显示错误消息
            self.root.after(0, lambda: messagebox.showerror("错误", f"处理过程中出现错误:\n{str(e)}"))
        
        finally:
            # 恢复开始按钮状态
            self.root.after(0, lambda: self.start_button.config(state=tk.NORMAL, text="开始处理"))
    
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