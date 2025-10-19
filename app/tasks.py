# -*- coding: utf-8 -*-
"""
Celery任务定义 - 重构后的版本
"""

import os
import threading
from typing import Dict, Any, List
from celery import Celery

from .task_processor import TaskProcessor, TaskAbortedException
from .config_manager import ConfigManager
from .logger import get_task_logger, info, error, warning, debug

# 使用模拟的Celery应用
import uuid
import os
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
    # 获取网页域名端口号
    web_domain_port = ConfigManager().get_server()
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

        # 发送任务完成通知
        _send_task_notification(task_id, 'completed', {
            'system_name': system_name,
            'branch_name': branch_name,
            'task_id': task_id,
            'report_url': f"{web_domain_port}/report/{task_id}",
            'reports_count': len(result.reports),
            'unit_tests_count': len(result.unit_cases),
            'scenario_tests_count': len(result.scenario_cases),
            'summary': result_dict['statistics']
        })
        
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
        
        # 发送任务失败通知
        _send_task_notification(task_id, 'failed', {
            'system_name': system_name,
            'branch_name': branch_name,
            'task_id': task_id,
            'error': str(e)
        })


def _send_task_notification(task_id: str, status: str, task_data: Dict[str, Any]) -> None:
    """
    发送任务状态通知
    
    Args:
        task_id: 任务ID
        status: 任务状态 (completed, failed, aborted)
        task_data: 任务相关数据
    """
    try:
        from .utils.notification_manager import notification_manager, NotificationMessage, NotificationLevel
        from .config_manager import config_manager
        
        # 获取通知配置
        notification_config = config_manager.get_notification_config()
        
        # 检查是否有启用的通知提供者
        enabled_providers = []
        for provider, config in notification_config.items():
            if config.get('enabled', False):
                enabled_providers.append(provider)
        
        if not enabled_providers:
            info("没有启用的通知提供者，跳过发送通知")
            return
        
        # 确定通知级别和内容
        system_name = task_data.get('system_name', 'Unknown')
        branch_name = task_data.get('branch_name', 'Unknown')
        
        if status == 'completed':
            level = NotificationLevel.SUCCESS
            title = f" 代码审查任务完成 - {system_name}/{branch_name}"
            
            reports_count = task_data.get('reports_count', 0)
            unit_tests_count = task_data.get('unit_tests_count', 0)
            scenario_tests_count = task_data.get('scenario_tests_count', 0)
            
            content = f"""代码审查任务已成功完成！

📋 任务详情：
• 任务ID: {task_id}
• 系统名称: {system_name}
• 分支名称: {branch_name}

📊 生成结果：
• 审查报告: {reports_count} 个
• 单元测试: {unit_tests_count} 个
• 场景测试: {scenario_tests_count} 个

🔗 查看详情: /task/{task_id}
"""
        
        elif status == 'failed':
            level = NotificationLevel.ERROR
            title = f" 代码审查任务失败 - {system_name}/{branch_name}"
            
            error = task_data.get('error', 'Unknown error')
            
            content = f"""代码审查任务执行失败！

📋 任务详情：
• 任务ID: {task_id}
• 系统名称: {system_name}
• 分支名称: {branch_name}

❌ 失败原因：
{error}

🔗 查看详情: /task/{task_id}
"""
        
        elif status == 'aborted':
            level = NotificationLevel.WARNING
            title = f" 代码审查任务已中止 - {system_name}/{branch_name}"
            
            content = f"""代码审查任务已被用户中止。

📋 任务详情：
• 任务ID: {task_id}
• 系统名称: {system_name}
• 分支名称: {branch_name}

🔗 查看详情: /task/{task_id}
"""
        
        else:
            info(f"未知的任务状态: {status}")
            return
        
        # 创建通知消息
        message = NotificationMessage(
            title=title,
            content=content,
            level=level,
            extra_data=task_data
        )
        # 获取收件人列表（这里可以从配置中获取，或者根据系统/项目配置）
        # recipients = _get_notification_recipients(system_name, notification_config)
        recipients = notification_config.get('email', {}).get('recipients', [])
        
        if recipients:
            # 异步发送通知（在后台线程中）
            def send_notification_background():
                try:
                    results = notification_manager.send_notification_sync(
                        enabled_providers, 
                        recipients, 
                        message
                    )
                    
                    success_count = sum(1 for result in results if result.success)
                    if success_count > 0:
                        info(f"任务 {task_id} 通知发送成功: {success_count}/{len(results)}")
                    else:
                        warning(f"任务 {task_id} 通知发送失败")
                        
                except Exception as e:
                    error(f"发送任务通知异常: {e}")
            
            import threading
            thread = threading.Thread(target=send_notification_background, daemon=True)
            thread.start()
        else:
            info("没有配置收件人，跳过发送通知")
            
    except Exception as e:
        error(f"准备任务通知失败: {e}")


def _get_notification_recipients(system_name: str, notification_config: Dict[str, Any]) -> List[str]:
    """
    获取通知收件人列表
    
    Args:
        system_name: 系统名称
        notification_config: 通知配置
    
    Returns:
        收件人列表
    """
    recipients = []
    
    try:
        # 从环境变量获取默认收件人
        default_email_recipients = os.environ.get('NOTIFICATION_DEFAULT_EMAIL_RECIPIENTS', '')
        if default_email_recipients:
            recipients.extend([email.strip() for email in default_email_recipients.split(',') if email.strip()])
        
        # 可以根据系统名称配置不同的收件人
        # 这里可以扩展为从数据库或配置文件中获取特定系统的收件人
        
        # 如果没有配置收件人，使用默认收件人
        if not recipients:
            # 可以设置一个默认的管理员邮箱
            admin_email = os.environ.get('NOTIFICATION_ADMIN_EMAIL')
            if admin_email:
                recipients.append(admin_email)
    
    except Exception as e:
        error(f"获取通知收件人失败: {e}")
    
    return recipients
