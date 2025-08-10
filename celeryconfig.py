# Celery配置
import os

# 检查是否启用Redis
use_redis = os.environ.get('USE_REDIS', 'false').lower() == 'true'

if use_redis:
    # Redis配置
    broker_url = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')
    result_backend = os.environ.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')
    
    # Redis特定配置
    broker_connection_retry_on_startup = True
    broker_connection_retry = True
    result_expires = 3600  # 结果过期时间：1小时
else:
    # 不使用Redis时，这些配置不会被使用（因为使用MockCelery）
    # 但保留配置结构以避免导入错误
    broker_url = None
    result_backend = None

task_serializer = 'json'
result_serializer = 'json'
accept_content = ['json']
timezone = 'Asia/Shanghai'
enable_utc = True

task_routes = {
    'app.tasks.review_code_task': {'queue': 'code_review'}
}

task_default_queue = 'default'
task_default_exchange = 'default'
task_default_routing_key = 'default'
