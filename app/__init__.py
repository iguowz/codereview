# -*- coding: utf-8 -*-
from flask import Flask, render_template
from flask_cors import CORS
from celery import Celery
import os
from dotenv import load_dotenv

def create_celery(app):
    # 使用MockCelery，不需要Redis
    return None

def create_app():
    # 加载 .env 环境变量
    load_dotenv()
    app = Flask(__name__, 
                template_folder='../templates',
                static_folder='../static')
    
    # 配置
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key')
    
    # 使用MockCelery模式，不需要Redis配置
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

    # 添加报告页面路由
    @app.route('/report/<task_id>')
    def report(task_id=None):
        return render_template('index.html')
    
    # MockCelery模式，不需要初始化Celery
    app.celery = None
    
    return app
