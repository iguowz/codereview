# -*- coding: utf-8 -*-
"""
高级日志管理系统 - 支持文件日志、日志轮转、大小和数量限制
"""

import logging
import logging.handlers
import sys
import os
from pathlib import Path
from typing import Optional, Union
from datetime import datetime

class CodeReviewLogger:
    """代码审查系统日志管理器"""
    
    def __init__(self, 
                 name: str = 'CodeReview',
                 log_dir: Union[str, Path] = 'logs',
                 max_file_size: int = 10 * 1024 * 1024,  # 10MB
                 max_file_count: int = 5,
                 log_level: str = 'INFO',
                 enable_console: bool = True,
                 enable_file: bool = True):
        """
        初始化日志管理器
        
        Args:
            name: 日志器名称
            log_dir: 日志目录
            max_file_size: 单个日志文件最大大小（字节）
            max_file_count: 保留的日志文件最大数量
            log_level: 日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            enable_console: 是否启用控制台输出
            enable_file: 是否启用文件输出
        """
        self.name = name
        self.log_dir = Path(log_dir)
        self.max_file_size = max_file_size
        self.max_file_count = max_file_count
        self.log_level = getattr(logging, log_level.upper(), logging.INFO)
        self.enable_console = enable_console
        self.enable_file = enable_file
        
        # 创建日志目录（如果启用文件日志）
        if self.enable_file:
            self.log_dir.mkdir(exist_ok=True)
        
        # 创建日志器
        self.logger = logging.getLogger(name)
        if not self.logger.handlers:
            self._setup_logger()
    
    def _setup_logger(self):
        """设置日志器"""
        self.logger.setLevel(self.log_level)
        
        # 创建格式器
        detailed_formatter = logging.Formatter(
            '%(asctime)s | %(name)s | %(levelname)-8s | %(filename)s:%(lineno)d | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        simple_formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(message)s',
            datefmt='%H:%M:%S'
        )
        
        # 添加控制台处理器
        if self.enable_console:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(self.log_level)
            console_handler.setFormatter(simple_formatter)
            self.logger.addHandler(console_handler)
        
        # 添加文件处理器（带轮转）
        if self.enable_file:
            # 主日志文件
            log_file = self.log_dir / f'{self.name.lower()}.log'
            file_handler = logging.handlers.RotatingFileHandler(
                log_file,
                maxBytes=self.max_file_size,
                backupCount=self.max_file_count,
                encoding='utf-8'
            )
            file_handler.setLevel(self.log_level)
            file_handler.setFormatter(detailed_formatter)
            self.logger.addHandler(file_handler)
            
            # 错误日志文件
            error_log_file = self.log_dir / f'{self.name.lower()}_error.log'
            error_handler = logging.handlers.RotatingFileHandler(
                error_log_file,
                maxBytes=self.max_file_size // 2,  # 错误日志文件较小
                backupCount=self.max_file_count,
                encoding='utf-8'
            )
            error_handler.setLevel(logging.ERROR)
            error_handler.setFormatter(detailed_formatter)
            self.logger.addHandler(error_handler)
    
    def debug(self, message: str, *args, **kwargs):
        """记录调试日志"""
        self.logger.debug(message, *args, **kwargs)
    
    def info(self, message: str, *args, **kwargs):
        """记录信息日志"""
        self.logger.info(message, *args, **kwargs)
    
    def warning(self, message: str, *args, **kwargs):
        """记录警告日志"""
        self.logger.warning(message, *args, **kwargs)
    
    def error(self, message: str, *args, **kwargs):
        """记录错误日志"""
        self.logger.error(message, *args, **kwargs)
    
    def critical(self, message: str, *args, **kwargs):
        """记录严重错误日志"""
        self.logger.critical(message, *args, **kwargs)
    
    def exception(self, message: str, *args, **kwargs):
        """记录异常日志（包含堆栈跟踪）"""
        self.logger.exception(message, *args, **kwargs)
    
    def task_start(self, task_id: str, task_info: str):
        """记录任务开始"""
        self.info(f"TASK_START | {task_id} | {task_info}")
    
    def task_progress(self, task_id: str, progress_info: str):
        """记录任务进度"""
        self.info(f"TASK_PROGRESS | {task_id} | {progress_info}")
    
    def task_complete(self, task_id: str, result_summary: str):
        """记录任务完成"""
        self.info(f"TASK_COMPLETE | {task_id} | {result_summary}")
    
    def task_failed(self, task_id: str, error_info: str):
        """记录任务失败"""
        self.error(f"TASK_FAILED | {task_id} | {error_info}")
    
    def api_call(self, api_name: str, duration: float, status: str):
        """记录API调用"""
        self.info(f"API_CALL | {api_name} | {duration:.2f}s | {status}")
    
    def cleanup_old_logs(self, days: int = 30):
        """清理旧日志文件"""
        try:
            cutoff_time = datetime.now().timestamp() - (days * 24 * 3600)
            cleaned_count = 0
            
            for log_file in self.log_dir.glob('*.log*'):
                if log_file.stat().st_mtime < cutoff_time:
                    log_file.unlink()
                    cleaned_count += 1
            
            if cleaned_count > 0:
                self.info(f"清理了 {cleaned_count} 个超过 {days} 天的旧日志文件")
                
        except Exception as e:
            self.error(f"清理旧日志文件失败: {e}")
    
    def get_log_stats(self) -> dict:
        """获取日志统计信息"""
        try:
            stats = {
                'log_dir': str(self.log_dir),
                'total_files': 0,
                'total_size_mb': 0,
                'files': []
            }
            
            for log_file in self.log_dir.glob('*.log*'):
                file_size = log_file.stat().st_size
                stats['files'].append({
                    'name': log_file.name,
                    'size_mb': round(file_size / (1024 * 1024), 2),
                    'modified': datetime.fromtimestamp(log_file.stat().st_mtime).isoformat()
                })
                stats['total_size_mb'] += file_size / (1024 * 1024)
            
            stats['total_files'] = len(stats['files'])
            stats['total_size_mb'] = round(stats['total_size_mb'], 2)
            
            return stats
            
        except Exception as e:
            self.error(f"获取日志统计失败: {e}")
            return {}

class TaskLogger(CodeReviewLogger):
    """任务专用日志器"""
    
    def __init__(self, task_id: str, **kwargs):
        self.task_id = task_id
        super().__init__(name=f'Task-{task_id[:8]}', **kwargs)
    
    def log_llm_call(self, task_id: str, call_type: str, duration: float, status: str, tokens: int = None):
        """记录LLM调用日志"""
        tokens_str = f" | {tokens} tokens" if tokens else ""
        self.info(f"LLM_CALL | {call_type} | {status} | {duration:.2f}s{tokens_str}")
    
    def task_start(self):
        """记录任务开始"""
        self.info(f"TASK_START | {self.task_id}")
    
    def task_progress(self, task_id: str, message: str):
        """记录任务进度"""
        self.info(f"TASK_PROGRESS | {message}")
    
    def task_complete(self, task_id: str, message: str = None):
        """记录任务完成"""
        msg = f" | {message}" if message else ""
        self.info(f"TASK_COMPLETE | {self.task_id}{msg}")
    
    def task_failed(self, task_id: str, error: str):
        """记录任务失败"""
        self.error(f"TASK_FAILED | {self.task_id} | {error}")
    
    def log_file_processing(self, task_id: str, filename: str, status: str):
        """记录文件处理状态"""
        self.info(f"FILE_PROCESS | {filename} | {status}")

# 全局日志配置
DEFAULT_LOG_CONFIG = {
    'log_dir': 'logs',
    'max_file_size': 10 * 1024 * 1024,  # 10MB
    'max_file_count': 5,
    'log_level': 'INFO',
    'enable_console': True,
    'enable_file': True
}

# 全局日志器实例
_global_logger = None

def get_logger(name: Optional[str] = None, **kwargs) -> CodeReviewLogger:
    """获取日志器实例"""
    global _global_logger
    
    if name:
        # 创建命名日志器
        config = DEFAULT_LOG_CONFIG.copy()
        config.update(kwargs)
        return CodeReviewLogger(name, **config)
    
    if _global_logger is None:
        # 创建全局日志器
        config = DEFAULT_LOG_CONFIG.copy()
        config.update(kwargs)
        _global_logger = CodeReviewLogger(**config)
    
    return _global_logger

def get_task_logger(task_id: str, **kwargs) -> TaskLogger:
    """获取任务专用日志器"""
    config = DEFAULT_LOG_CONFIG.copy()
    config.update(kwargs)
    return TaskLogger(task_id, **config)

# 兼容性别名
logger = get_logger()

# 便捷函数
def debug(message: str, *args, **kwargs):
    logger.debug(message, *args, **kwargs)

def info(message: str, *args, **kwargs):
    logger.info(message, *args, **kwargs)

def warning(message: str, *args, **kwargs):
    logger.warning(message, *args, **kwargs)

def error(message: str, *args, **kwargs):
    logger.error(message, *args, **kwargs)

def critical(message: str, *args, **kwargs):
    logger.critical(message, *args, **kwargs)

def exception(message: str, *args, **kwargs):
    logger.exception(message, *args, **kwargs)

def cleanup_old_logs(days: int = 30):
    """清理旧日志文件"""
    global_logger = get_logger()
    global_logger.cleanup_old_logs(days)

def get_log_stats() -> dict:
    """获取日志统计信息"""
    global_logger = get_logger()
    return global_logger.get_log_stats()
