# -*- coding: utf-8 -*-
"""
Celery任务定义 - 重构后的版本
"""

import os
import threading
from typing import Dict
from celery import Celery

from .task_processor import TaskProcessor, TaskAbortedException
from .config_manager import ConfigManager
from .logger import get_task_logger, info, error, warning

# 检查是否启用Redis
use_redis = os.environ.get('USE_REDIS', 'false').lower() == 'true'

if use_redis:
    # 创建Celery实例
    celery_app = Celery('tasks')
    celery_app.config_from_object('celeryconfig')
else:
    # 如果不使用Redis，创建一个模拟的Celery应用
    import uuid
    from collections import defaultdict
    
    class MockTaskResult:
        """模拟Celery任务结果"""
        def __init__(self, task_id: str):
            self.id = task_id
            self.task_id = task_id
            self._status = 'PENDING'
            self._result = None
            self._traceback = None
        
        @property
        def status(self):
            return self._status
        
        @property
        def state(self):
            return self._status
        
        @property
        def result(self):
            return self._result
        
        def ready(self):
            return self._status in ['SUCCESS', 'FAILURE', 'REVOKED']
        
        def successful(self):
            return self._status == 'SUCCESS'
        
        def failed(self):
            return self._status == 'FAILURE'
        
        def get(self, timeout=None):
            if self._status == 'SUCCESS':
                return self._result
            elif self._status == 'FAILURE':
                raise Exception(self._result)
            else:
                raise Exception(f"Task {self.task_id} is in {self._status} state")
    
    class MockCelery:
        """模拟Celery应用"""
        
        def __init__(self):
            self._tasks = {}
            self._task_registry = defaultdict(dict)
        
        def task(self, func):
            """装饰器：模拟Celery任务"""
            task_name = f"{func.__module__}.{func.__name__}"
            
            def wrapper(*args, **kwargs):
                # 直接执行任务函数
                result = func(*args, **kwargs)
                return result
            
            # 添加delay方法以模拟Celery任务（在后台线程中执行）
            def delay(*args, **kwargs):
                task_id = str(uuid.uuid4())
                task_result = MockTaskResult(task_id)
                self._tasks[task_id] = task_result
                
                def run_task():
                    try:
                        info(f"MockCelery开始执行后台任务: {func.__name__} (ID: {task_id})")
                        task_result._status = 'STARTED'
                        
                        # 执行实际任务
                        result = func(*args, **kwargs)
                        
                        task_result._status = 'SUCCESS'
                        task_result._result = result
                        info(f"MockCelery后台任务执行完成: {func.__name__} (ID: {task_id})")
                        
                    except Exception as e:
                        task_result._status = 'FAILURE'
                        task_result._result = str(e)
                        task_result._traceback = e
                        error(f"MockCelery后台任务执行失败: {func.__name__} (ID: {task_id}) - {e}")
                        import traceback
                        traceback.print_exc()
                
                # 在后台线程中执行任务
                thread = threading.Thread(target=run_task, name=f"MockCelery-{func.__name__}-{task_id[:8]}")
                thread.daemon = True
                thread.start()
                info(f"MockCelery已启动后台线程: {thread.name}")
                
                return task_result
            
            def apply_async(*args, **kwargs):
                """异步执行任务（与delay相同）"""
                return delay(*args, **kwargs)
            
            wrapper.delay = delay
            wrapper.apply_async = apply_async
            wrapper.name = task_name
            self._task_registry[task_name] = wrapper
            
            return wrapper
        
        def AsyncResult(self, task_id):
            """获取任务结果"""
            return self._tasks.get(task_id, MockTaskResult(task_id))
    
    celery_app = MockCelery()


@celery_app.task
def review_code_task(system_name: str, branch_name: str, task_id: str):
    """
    代码审查任务 - 重构后的版本
    
    Args:
        system_name: 系统名称
        branch_name: 分支名称
        task_id: 任务ID
    """
    from .task_processor import TaskStatusManager
    
    processor = TaskProcessor()
    status_manager = TaskStatusManager()
    
    try:
        # 更新任务状态为进行中
        task_logger = get_task_logger(task_id)
        task_logger.task_progress(task_id, "开始更新任务状态为processing")
        status_manager.update_task_status(task_id, 'processing')
        task_logger.task_progress(task_id, "任务状态已更新为processing")
        
        # 处理任务
        task_logger.task_progress(task_id, "开始处理任务")
        result = processor.process_task(system_name, branch_name, task_id)
        task_logger.task_progress(task_id, "任务处理完成，开始转换结果")
        
        # 转换结果格式
        result_dict = processor.convert_result_to_dict(result)
        task_logger.task_progress(task_id, "结果转换完成")
        
        # 打印统计信息
        task_logger.task_complete(task_id, f"报告: {len(result.reports)}, 单元测试: {len(result.unit_cases)}, 场景测试: {len(result.scenario_cases)}")
        
        # 更新任务状态为完成前，最后检查一次是否被中止
        try:
            processor._check_task_abort(task_id)
        except TaskAbortedException as e:
            # 如果在最后关头发现任务被中止，不要设置为completed
            task_logger.task_progress(task_id, f"任务在完成前被中止: {str(e)}")
            info(f"任务 {task_id} 在完成前被发现已中止")
            return  # 不设置为completed，保持aborted状态
        
        # 更新任务状态为完成
        task_logger.task_progress(task_id, "开始更新任务状态为completed")
        status_manager.update_task_status(task_id, 'completed', result_dict)
        task_logger.task_complete(task_id, "任务状态已更新为completed")
        
    except TaskAbortedException as e:
        # 任务被用户中止
        task_logger = get_task_logger(task_id)
        task_logger.task_progress(task_id, f"任务被用户中止: {str(e)}")
        info(f"任务 {task_id} 被用户中止，停止执行")
        # 注意：任务状态已经在中止API中更新为aborted，这里不需要再次更新
        
    except Exception as e:
        # 更新任务状态为失败
        task_logger = get_task_logger(task_id)
        task_logger.task_failed(task_id, str(e))
        import traceback
        traceback.print_exc()
        status_manager.update_task_status(task_id, 'failed', {'error': str(e)})
