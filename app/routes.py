# -*- coding: utf-8 -*-
from flask import Blueprint, request, jsonify
from app.tasks import review_code_task
from app.config_manager import config_manager
from app.logger import info, warning, error
from datetime import datetime
import yaml
import os
import uuid
import requests

bp = Blueprint('api', __name__, url_prefix='/api')

@bp.route('/branches/<system_name>', methods=['GET'])
def get_branches(system_name):
    """获取指定系统的可用分支列表"""
    try:
        from app.utils.git_api import GitAPIClient
        git_client = GitAPIClient()
        
        # 获取系统配置
        system_config = None
        for system in config_manager.get_all_systems():
            if system['name'] == system_name:
                system_config = system
                break
        
        if not system_config:
            return jsonify({'error': f'System {system_name} not found'}), 404
        
        # 获取默认分支和常用分支
        default_branch = 'main'  # GitHub默认分支
        common_branches = ['main', 'master', 'develop', 'dev', 'staging', 'release']
        
        # 尝试从GitHub API获取实际分支列表
        try:
            auth_headers = git_client._get_auth_headers(system_config)
            provider = system_config.get('git_provider')
            
            if provider == 'github':
                # 获取第一个项目的分支列表
                if system_config.get('projects'):
                    project = system_config['projects'][0]
                    owner = project.get('owner')
                    repo = project.get('repo')
                    
                    if owner and repo:
                        url = f"https://api.github.com/repos/{owner}/{repo}/branches"
                        response = requests.get(url, headers=auth_headers, timeout=10)
                        
                        if response.status_code == 200:
                            branches = response.json()
                            branch_names = [branch['name'] for branch in branches[:20]]  # 限制前20个分支
                            
                            return jsonify({
                                'system_name': system_name,
                                'branches': branch_names,
                                'default_branch': default_branch,
                                'common_branches': common_branches,
                                'source': 'github_api'
                            })
        except Exception as e:
            info(f"获取GitHub分支列表失败: {e}")
        
        # 降级：返回常用分支列表
        return jsonify({
            'system_name': system_name,
            'branches': common_branches,
            'default_branch': default_branch,
            'common_branches': common_branches,
            'source': 'fallback'
        })
        
    except Exception as e:
        error(f"获取分支列表失败: {e}")
        return jsonify({'error': str(e)}), 500

@bp.route('/systems', methods=['GET'])
def get_systems():
    """获取所有系统列表"""
    try:
        # 检查是否启用静态模式
        if config_manager.is_static_mode_enabled():
            info("静态模式已启用，跳过动态获取，直接使用静态配置")
            all_systems = config_manager.get_all_systems()
            
            systems = []
            for system in all_systems:
                systems.append({
                    'id': system['id'],
                    'name': system['name'],
                    'projects': [p['name'] for p in system.get('projects', [])],
                    'git_provider': system.get('git_provider'),
                    'git_provider_url': system.get('git_provider_url'),
                    'project_count': len(system.get('projects', [])),
                    'dynamic': False,  # 标识为静态配置
                    'static_mode': True  # 标识为静态模式
                })
            
            return jsonify({
                'systems': systems,
                'source': 'static_mode',
                'total': len(systems),
                'static_mode_enabled': True
            })
        
        # 优先尝试动态获取
        from app.utils.git_api import GitAPIClient
        git_client = GitAPIClient()
        
        # 检查是否请求强制刷新
        force_refresh = request.args.get('force_refresh', 'false').lower() == 'true'
        
        try:
            # 尝试动态获取系统列表
            dynamic_systems = git_client.get_dynamic_systems(force_refresh=force_refresh)
            
            if dynamic_systems:
                systems = []
                for system in dynamic_systems:
                    systems.append({
                        'id': system['id'],
                        'name': system['name'],
                        'projects': [p['name'] for p in system.get('projects', [])],
                        'git_provider': system.get('git_provider'),
                        'git_provider_url': system.get('git_provider_url'),
                        'description': system.get('description', ''),
                        'avatar_url': system.get('avatar_url', ''),
                        'public_repos': system.get('public_repos', 0),
                        'project_count': len(system.get('projects', [])),
                        'dynamic': True,  # 标识为动态获取
                        'error': system.get('error')  # 如果有错误
                    })
                
                # 自动备份到systems.yaml
                try:
                    config_manager.backup_systems_to_yaml(dynamic_systems, 'dynamic')
                    info(f"系统配置已自动备份到systems.yaml，共{len(systems)}个系统")
                except Exception as backup_error:
                    warning(f"自动备份系统配置失败: {backup_error}")
                
                return jsonify({
                    'systems': systems,
                    'source': 'dynamic',
                    'total': len(systems)
                })
        
        except Exception as dynamic_error:
            info(f"动态获取系统列表失败，降级到静态配置: {dynamic_error}")
            # 降级到静态配置
            pass
        
        # 降级：使用静态配置
        all_systems = config_manager.get_all_systems()
        
        systems = []
        for system in all_systems:
            systems.append({
                'id': system['id'],
                'name': system['name'],
                'projects': [p['name'] for p in system.get('projects', [])],
                'git_provider': system.get('git_provider'),
                'git_provider_url': system.get('git_provider_url'),
                'project_count': len(system.get('projects', [])),
                'dynamic': False  # 标识为静态配置
            })
        
        return jsonify({
            'systems': systems,
            'source': 'static',
            'total': len(systems)
        })
        
    except Exception as e:
        error(f"获取系统列表失败: {e}")
        return jsonify({'error': str(e)}), 500

@bp.route('/config/status', methods=['GET'])
def get_config_status():
    """获取配置状态信息"""
    try:
        status = {
            'static_mode': config_manager.get_static_mode_config(),
            'redis_enabled': config_manager.is_redis_enabled(),
            'server_config': {
                'host': config_manager.get_server_host(),
                'port': config_manager.get_server_port()
            },
            'llm_config': {
                'has_api_key': bool(config_manager.get_deepseek_api_key())
            }
        }
        return jsonify(status)
    except Exception as e:
        error(f"获取配置状态失败: {e}")
        return jsonify({'error': str(e)}), 500

@bp.route('/review-multi', methods=['POST'])
def create_multi_review():
    """创建多系统代码审查任务"""
    try:
        data = request.get_json()
        system_names = data.get('system_names', [])
        branch_name = data.get('branch_name')
        
        if not system_names or not branch_name:
            return jsonify({'error': 'system_names and branch_name are required'}), 400
        
        if not isinstance(system_names, list):
            return jsonify({'error': 'system_names must be a list'}), 400
        
        # 如果只有一个系统，使用原有的单系统逻辑
        if len(system_names) == 1:
            return _create_single_review(system_names[0], branch_name)
        
        # 多系统并行处理
        task_ids = []
        main_task_id = None
        
        for i, system_name in enumerate(system_names):
            # 检查是否已有相同系统和分支的进行中任务
            existing_task = _find_running_task(system_name, branch_name)
            if existing_task:
                task_ids.append(existing_task['id'])
                if i == 0:  # 第一个作为主任务
                    main_task_id = existing_task['id']
                continue
            
            # 检查是否有失败的任务可以恢复
            failed_task = _find_failed_task(system_name, branch_name)
            if failed_task:
                task_id = failed_task['id']
            else:
                task_id = str(uuid.uuid4())
            
            task_ids.append(task_id)
            if i == 0:  # 第一个作为主任务
                main_task_id = task_id
            
            # 创建任务数据
            task_data = {
                'id': task_id,
                'system_name': system_name,
                'branch_name': branch_name,
                'status': 'pending',
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat(),
                'multi_system': True,
                'related_tasks': task_ids,  # 关联的其他任务
                'is_main_task': (i == 0)    # 标记主任务
            }
            
            # 保存任务文件
            task_file = f'data/tasks/{task_id}.yaml'
            os.makedirs(os.path.dirname(task_file), exist_ok=True)
            with open(task_file, 'w', encoding='utf-8') as f:
                yaml.dump(task_data, f, default_flow_style=False, allow_unicode=True)
            
            # 启动异步任务
            try:
                if hasattr(review_code_task, 'delay'):
                    review_code_task.delay(system_name, branch_name, task_id)
                else:
                    # 直接调用（非Celery模式）
                    import threading
                    thread = threading.Thread(
                        target=review_code_task, 
                        args=(system_name, branch_name, task_id),
                        name=f"Review-{system_name}-{task_id[:8]}"
                    )
                    thread.daemon = True
                    thread.start()
            except Exception as task_error:
                # 更新任务状态为失败
                task_data['status'] = 'failed'
                task_data['error'] = str(task_error)
                with open(task_file, 'w', encoding='utf-8') as f:
                    yaml.dump(task_data, f, default_flow_style=False, allow_unicode=True)
        
        # 返回主任务信息
        if main_task_id:
            with open(f'data/tasks/{main_task_id}.yaml', 'r', encoding='utf-8') as f:
                main_task_data = yaml.safe_load(f)
            
            return jsonify({
                'task_id': main_task_id,
                'task_ids': task_ids,
                'main_task_id': main_task_id,
                'system_names': system_names,
                'branch_name': branch_name,
                'status': main_task_data.get('status', 'pending'),
                'multi_system': True,
                'total_systems': len(system_names)
            })
        else:
            return jsonify({'error': 'Failed to create any tasks'}), 500
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

def _create_single_review(system_name: str, branch_name: str):
    """创建单系统审查任务的辅助函数"""
    # 检查是否已有相同系统和分支的进行中任务
    existing_task = _find_running_task(system_name, branch_name)
    if existing_task:
        return jsonify({
            'task_id': existing_task['id'],
            'existing': True,
            'message': f'已存在相同系统和分支的任务: {existing_task["id"]}',
            'system_name': system_name,
            'branch_name': branch_name,
            'status': existing_task.get('status', 'pending')
        })
    
    # 检查是否有失败的任务可以恢复
    failed_task = _find_failed_task(system_name, branch_name)
    if failed_task:
        task_id = failed_task['id']
    else:
        task_id = str(uuid.uuid4())
    
    # 创建初始任务文件
    task_data = {
        'id': task_id,
        'system_name': system_name,
        'branch_name': branch_name,
        'status': 'pending',
        'created_at': datetime.now().isoformat(),
        'updated_at': datetime.now().isoformat(),
        'multi_system': False
    }
    
    # 保存任务文件
    task_file = f'data/tasks/{task_id}.yaml'
    os.makedirs(os.path.dirname(task_file), exist_ok=True)
    with open(task_file, 'w', encoding='utf-8') as f:
        yaml.dump(task_data, f, default_flow_style=False, allow_unicode=True)
    
    # 启动任务
    try:
        if hasattr(review_code_task, 'delay'):
            review_code_task.delay(system_name, branch_name, task_id)
        else:
            review_code_task(system_name, branch_name, task_id)
    except Exception as task_error:
        task_data['status'] = 'failed'
        task_data['error'] = str(task_error)
        with open(task_file, 'w', encoding='utf-8') as f:
            yaml.dump(task_data, f, default_flow_style=False, allow_unicode=True)
    
    return jsonify({
        'task_id': task_id,
        'system_name': system_name,
        'branch_name': branch_name,
        'status': 'pending'
    })

@bp.route('/review', methods=['POST'])
def create_review():
    """创建代码审查任务（保持向后兼容）"""
    try:
        data = request.get_json()
        system_name = data.get('system_name')
        branch_name = data.get('branch_name')
        
        if not system_name or not branch_name:
            return jsonify({'error': 'system_name and branch_name are required'}), 400
        
        return _create_single_review(system_name, branch_name)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@bp.route('/result/<task_id>', methods=['GET'])
def get_task_result(task_id):
    """获取任务结果"""
    try:
        task_file = os.path.join('data', 'tasks', f'{task_id}.yaml')
        
        if not os.path.exists(task_file):
            return jsonify({'error': 'Task not found'}), 404
        
        with open(task_file, 'r', encoding='utf-8') as f:
            task_data = yaml.safe_load(f)
        
        # 尝试加载状态文件
        state_file = os.path.join('data', 'tasks', f'{task_id}_state.yaml')
        file_states = {}
        if os.path.exists(state_file):
            try:
                with open(state_file, 'r', encoding='utf-8') as f:
                    state_data = yaml.safe_load(f) or {}
                file_states = state_data.get('files', {})
                info(f"加载了任务 {task_id} 的状态文件，包含 {len(file_states)} 个文件状态")
            except Exception as e:
                warning(f"加载状态文件失败: {e}")
        
        # 将状态信息添加到任务数据中
        task_data['file_states'] = file_states
        
        return jsonify(task_data)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.route('/task/<task_id>', methods=['GET'])
def get_task(task_id):
    """获取任务详情"""
    return get_task_result(task_id)

@bp.route('/task/<task_id>/abort', methods=['POST'])
def abort_task(task_id):
    """中止任务"""
    try:
        task_file = os.path.join('data', 'tasks', f'{task_id}.yaml')
        
        if not os.path.exists(task_file):
            return jsonify({'error': 'Task not found'}), 404
        
        # 读取任务数据
        with open(task_file, 'r', encoding='utf-8') as f:
            task_data = yaml.safe_load(f)
        
        # 检查任务是否可以中止
        current_status = task_data.get('status')
        if current_status not in ['pending', 'processing']:
            if current_status == 'completed':
                return jsonify({'error': '任务已完成，无法中止'}), 400
            elif current_status == 'failed':
                return jsonify({'error': '任务已失败，无法中止'}), 400
            elif current_status == 'aborted':
                return jsonify({'error': '任务已中止'}), 400
            else:
                return jsonify({'error': f'任务状态为"{current_status}"，无法中止'}), 400
        
        # 更新任务状态为已中止
        task_data['status'] = 'aborted'
        task_data['updated_at'] = datetime.now().isoformat()
        
        # 添加中止原因到debug_log
        if 'debug_log' not in task_data:
            task_data['debug_log'] = []
        task_data['debug_log'].append(f"{datetime.now().isoformat()}: 任务被用户手动中止")
        
        # 设置错误结果
        task_data['result'] = {
            'error': '任务被用户手动中止',
            'aborted_by_user': True
        }
        
        # 保存更新后的任务数据
        with open(task_file, 'w', encoding='utf-8') as f:
            yaml.dump(task_data, f, default_flow_style=False, allow_unicode=True)
        
        info(f"任务 {task_id} 被用户手动中止")
        
        return jsonify({
            'message': 'Task aborted successfully',
            'task_id': task_id,
            'status': 'aborted'
        })
        
    except Exception as e:
        error(f"中止任务失败: {e}")
        return jsonify({'error': str(e)}), 500

@bp.route('/tasks', methods=['GET'])
def list_tasks():
    """获取所有任务列表"""
    try:
        tasks = []
        tasks_dir = 'data/tasks'
        
        if os.path.exists(tasks_dir):
            for filename in os.listdir(tasks_dir):
                # 只处理主任务文件，排除_state状态文件
                if filename.endswith('.yaml') and not filename.endswith('_state.yaml'):
                    task_id = filename[:-5]  # 移除.yaml后缀
                    task_file = os.path.join(tasks_dir, filename)
                    
                    with open(task_file, 'r', encoding='utf-8') as f:
                        task_data = yaml.safe_load(f)
                        tasks.append({
                            'id': task_data.get('id'),
                            'system_name': task_data.get('system_name'),
                            'branch_name': task_data.get('branch_name'),
                            'status': task_data.get('status'),
                            'created_at': task_data.get('created_at'),
                            'updated_at': task_data.get('updated_at')
                        })
        
        # 按创建时间倒序排列，处理None值
        tasks.sort(key=lambda x: x['created_at'] or '1970-01-01T00:00:00', reverse=True)
        
        return jsonify({'tasks': tasks})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def _find_running_task(system_name: str, branch_name: str):
    """查找正在执行的相同系统和分支的任务"""
    try:
        tasks_dir = 'data/tasks'
        if not os.path.exists(tasks_dir):
            return None
        
        for filename in os.listdir(tasks_dir):
            if filename.endswith('.yaml'):
                task_file = os.path.join(tasks_dir, filename)
                
                with open(task_file, 'r', encoding='utf-8') as f:
                    task_data = yaml.safe_load(f)
                
                # 检查是否是相同系统和分支且正在执行的任务
                if (task_data.get('system_name') == system_name and 
                    task_data.get('branch_name') == branch_name and 
                    task_data.get('status') in ['pending', 'processing']):
                    return task_data
        
        return None
        
    except Exception as e:
        error(f"查找运行中任务失败: {e}")
        return None

def _find_failed_task(system_name: str, branch_name: str):
    """查找失败的相同系统和分支的任务"""
    try:
        tasks_dir = 'data/tasks'
        if not os.path.exists(tasks_dir):
            return None
        
        latest_failed = None
        latest_time = None
        
        for filename in os.listdir(tasks_dir):
            if filename.endswith('.yaml'):
                task_file = os.path.join(tasks_dir, filename)
                
                with open(task_file, 'r', encoding='utf-8') as f:
                    task_data = yaml.safe_load(f)
                
                # 检查是否是相同系统和分支且失败的任务
                if (task_data.get('system_name') == system_name and 
                    task_data.get('branch_name') == branch_name and 
                    task_data.get('status') == 'failed'):
                    
                    task_time = task_data.get('updated_at')
                    if task_time and (latest_time is None or task_time > latest_time):
                        latest_failed = task_data
                        latest_time = task_time
        
        return latest_failed
        
    except Exception as e:
        error(f"查找失败任务失败: {e}")
        return None
