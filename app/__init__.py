# -*- coding: utf-8 -*-
from flask import Flask, render_template
from flask_cors import CORS
from celery import Celery
import os
from dotenv import load_dotenv

def create_celery(app):
    # 检查是否启用Redis
    use_redis = os.environ.get('USE_REDIS', 'false').lower() == 'true'
    
    if use_redis:
        celery = Celery(
            app.import_name,
            backend=app.config['CELERY_RESULT_BACKEND'],
            broker=app.config['CELERY_BROKER_URL']
        )
        celery.conf.update(app.config)
        
        class ContextTask(celery.Task):
            def __call__(self, *args, **kwargs):
                with app.app_context():
                    return self.run(*args, **kwargs)
        
        celery.Task = ContextTask
        return celery
    else:
        # 如果不使用Redis，返回None
        return None

def create_app():
    # 加载 .env 环境变量
    load_dotenv()
    app = Flask(__name__, 
                template_folder='../templates',
                static_folder='../static')
    
    # 配置
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key')
    
    # Redis配置 - 可配置使用
    use_redis = os.environ.get('USE_REDIS', 'false').lower() == 'true'
    if use_redis:
        app.config['CELERY_BROKER_URL'] = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')
        app.config['CELERY_RESULT_BACKEND'] = os.environ.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')
    else:
        app.config['CELERY_BROKER_URL'] = None
        app.config['CELERY_RESULT_BACKEND'] = None
    
    # 启用CORS
    CORS(app)
    
    # 注册路由
    from app.routes import bp
    app.register_blueprint(bp)
    
    # 添加主页路由
    @app.route('/')
    def index():
        return render_template('index.html')
    
    # 初始化Celery（如果启用）
    app.celery = create_celery(app)
    
    return app
