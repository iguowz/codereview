# -*- coding: utf-8 -*-
"""
配置管理器 - 统一管理系统配置
"""

import os
import yaml
import asyncio
from typing import Dict, Any, Optional, List
from pathlib import Path
from datetime import datetime
from .utils.file_cache import file_cache
from .utils.advanced_cache import advanced_cache, cache_with_fallback

# 延迟导入logger以避免循环导入
def get_logger():
    try:
        from .logger import info, warning, error
        return info, warning, error
    except ImportError:
        # 回退到print
        return print, print, print

class ConfigManager:
    """配置管理器"""
    
    def __init__(self):
        self.project_root = self._find_project_root()
        self._config_cache = {}
    
    def _find_project_root(self) -> Path:
        """查找项目根目录"""
        current = Path(__file__).parent
        while current != current.parent:
            if (current / 'config').exists():
                return current
            current = current.parent
        return Path.cwd()
    
    @cache_with_fallback(ttl=300, fallback_ttl=3600)
    def get_systems_config(self) -> Dict[str, Any]:
        """获取系统配置"""
        info, warning, error = get_logger()
        
        # 尝试从文件缓存获取
        cache_key = 'systems_config'
        cached_data = file_cache.get(cache_key)
        if cached_data:
            return cached_data
        
        if 'systems' not in self._config_cache:
            # 获取系统配置config/systems_XXX.yaml
            list_config_path = self.project_root / 'config'
            exclude = {'systems_backup.yaml', 'systems_user.yaml'}
            possible_paths = [
                os.path.join(list_config_path, f)
                for f in os.listdir(list_config_path)
                if f.startswith('systems_') and not f.endswith('_backup.yaml') and f not in exclude
            ]
            projects = []
            for config_path in possible_paths:
                if os.path.isfile(config_path):
                    try:
                        with open(config_path, 'r', encoding='utf-8') as f:
                            for system in yaml.safe_load(f).get('systems', []):
                                projects.append(system)
                    except FileNotFoundError:
                        warning(f"配置文件不存在: {config_path}")
                    except Exception as e:
                        error(f"读取系统配置失败: {e}")
            self._config_cache['systems'] = {'systems': projects}
        
        # 保存到文件缓存
        result = self._config_cache['systems']
        file_cache.set(cache_key, result, ttl=600)  # 10分钟缓存
        
        return result

    def get_user_system_config(self) -> Dict[str, Any]:
        """获取用户系统配置"""
        info, warning, error = get_logger()
        if 'user_systems' not in self._config_cache:
            config_path = self.project_root / 'config' / 'systems_user.yaml'
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    self._config_cache['user_systems'] = yaml.safe_load(f) or {}
                    # 将name字段改为首字母大写
                    for system in self._config_cache['user_systems'].get('systems', []):
                        system['name'] = system['name'].capitalize()
            except FileNotFoundError:
                warning(f"配置文件不存在: {config_path}")
                self._config_cache['user_systems'] = {'systems': []}
            except Exception as e:
                error(f"读取用户系统配置失败: {e}")
                self._config_cache['user_systems'] = {'systems': []}

        return self._config_cache['user_systems']

    def get_branches_config(self) -> Dict[str, Any]:
        """获取所有分支配置"""
        if 'branches' not in self._config_cache:
            config_path = self.project_root / 'config' / 'branches.yaml'
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    self._config_cache['branches'] = yaml.safe_load(f) or {}
            except FileNotFoundError:
                info, warning, error = get_logger()
                warning(f"配置文件不存在: {config_path}")
                self._config_cache['branches'] = {'branches': []}
            except Exception as e:
                info, warning, error = get_logger()
                error(f"读取分支配置失败: {e}")
                self._config_cache['branches'] = {'branches': []}

        return self._config_cache['branches']
    
    def get_prompts_config(self) -> Dict[str, str]:
        """获取提示词配置"""
        if 'prompts' not in self._config_cache:
            config_path = self.project_root / 'config' / 'prompts.yaml'
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    self._config_cache['prompts'] = yaml.safe_load(f) or {}
            except FileNotFoundError:
                info, warning, error = get_logger()
                warning(f"配置文件不存在: {config_path}")
                self._config_cache['prompts'] = {}
            except Exception as e:
                info, warning, error = get_logger()
                error(f"读取提示词配置失败: {e}")
                self._config_cache['prompts'] = {}
        
        return self._config_cache['prompts']
    
    def get_system_by_name(self, system_name: str) -> Optional[Dict[str, Any]]:
        """根据名称获取系统配置"""
        systems_config = self.get_systems_config()
        for system in systems_config.get('systems', []):
            if system.get('name') == system_name:
                return system
        return None
    
    def get_all_systems(self) -> List[Dict[str, Any]]:
        """获取所有系统配置"""
        systems_config = self.get_systems_config()
        return systems_config.get('systems', [])

    def get_user_systems(self) -> List[Dict[str, Any]]:
        """获取用户系统配置"""
        user_systems_config = self.get_user_system_config()
        return user_systems_config.get('systems', [])

    def get_all_branches(self) -> List[Dict[str, Any]]:
        """获取所有分支配置"""
        branches_config = self.get_branches_config()
        return branches_config.get('branches', [])
    
    def get_prompt(self, prompt_name: str) -> str:
        """获取提示词"""
        prompts_config = self.get_prompts_config()
        return prompts_config.get(prompt_name, '')
    
    def get_env_var(self, var_name: str, default: str = '') -> str:
        """获取环境变量"""
        return os.environ.get(var_name, default)
    
    
    def is_static_mode_enabled(self) -> bool:
        """检查是否启用静态模式（强制使用静态配置文件）"""
        return self.get_env_var('USE_STATIC_MODE', 'false').lower() == 'true'
    
    def get_notification_config(self) -> Dict[str, Any]:
        """获取通知配置"""
        try:
            config_path = self.project_root / 'config' / 'notifications.yaml'
            
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    notification_config = yaml.safe_load(f) or {}
            else:
                # 使用默认配置
                notification_config = {
                    'email': {
                        'enabled': False,
                        'recipients': []
                    },
                    'wechat_work': {
                        'enabled': False,
                        'mentioned_list': [],
                        'mentioned_mobile_list': []
                    }
                }
            
            # 从环境变量获取私密配置
            self._load_private_config_from_env(notification_config)
            
            return notification_config
            
        except Exception as e:
            info, warning, error = get_logger()
            error(f"加载通知配置失败: {e}")
            return {}
    
    def get_notification_public_config(self) -> Dict[str, Any]:
        """获取通知公开配置（不包含私密信息）"""
        try:
            config_path = self.project_root / 'config' / 'notifications.yaml'
            
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    notification_config = yaml.safe_load(f) or {}
            else:
                notification_config = {
                    'email': {
                        'enabled': False,
                        'recipients': []
                    },
                    'wechat_work': {
                        'enabled': False,
                        'mentioned_list': [],
                        'mentioned_mobile_list': []
                    }
                }
            
            # 添加私密配置的状态信息（不包含实际值）
            self._add_private_config_status(notification_config)
            
            return notification_config
            
        except Exception as e:
            info, warning, error = get_logger()
            error(f"加载通知公开配置失败: {e}")
            return {}
    
    def _load_private_config_from_env(self, config: Dict[str, Any]) -> None:
        """从环境变量加载私密配置"""
        info, warning, error = get_logger()
        
        # 邮件私密配置
        if config.get('email'):
            config['email'].update({
                'smtp_server': os.environ.get('NOTIFICATION_EMAIL_SMTP_SERVER', ''),
                'smtp_port': int(os.environ.get('NOTIFICATION_EMAIL_SMTP_PORT', 587)),
                'username': os.environ.get('NOTIFICATION_EMAIL_USERNAME', ''),
                'password': os.environ.get('NOTIFICATION_EMAIL_PASSWORD', ''),
                'use_ssl': os.environ.get('NOTIFICATION_EMAIL_USE_SSL', 'true').lower() == 'true',
                'from_name': os.environ.get('NOTIFICATION_EMAIL_FROM_NAME', 'Code Review System')
            })
        
        # 企业微信私密配置
        if config.get('wechat_work'):
            config['wechat_work'].update({
                'webhook_url': os.environ.get('NOTIFICATION_WECHAT_WEBHOOK_URL', '')
            })
    
    def _add_private_config_status(self, config: Dict[str, Any]) -> None:
        """添加私密配置状态信息"""
        # 邮件配置状态
        if config.get('email'):
            config['email']['smtp_configured'] = bool(os.environ.get('NOTIFICATION_EMAIL_SMTP_SERVER'))
            config['email']['auth_configured'] = bool(
                os.environ.get('NOTIFICATION_EMAIL_USERNAME') and 
                os.environ.get('NOTIFICATION_EMAIL_PASSWORD')
            )
        
        # 企业微信配置状态
        if config.get('wechat_work'):
            config['wechat_work']['webhook_configured'] = bool(os.environ.get('NOTIFICATION_WECHAT_WEBHOOK_URL'))
    
    def save_notification_public_config(self, config: Dict[str, Any]) -> bool:
        """保存通知公开配置（不包含私密信息）"""
        try:
            config_path = self.project_root / 'config' / 'notifications.yaml'
            config_path.parent.mkdir(exist_ok=True)
            
            # 只保存公开配置字段
            public_config = {}
            
            if 'email' in config:
                public_config['email'] = {
                    'enabled': config['email'].get('enabled', False),
                    'recipients': config['email'].get('recipients', [])
                }
            
            if 'wechat_work' in config:
                public_config['wechat_work'] = {
                    'enabled': config['wechat_work'].get('enabled', False),
                    'mentioned_list': config['wechat_work'].get('mentioned_list', []),
                    'mentioned_mobile_list': config['wechat_work'].get('mentioned_mobile_list', [])
                }
            
            with open(config_path, 'w', encoding='utf-8') as f:
                yaml.safe_dump(public_config, f, default_flow_style=False, allow_unicode=True)
            
            info, warning, error = get_logger()
            info(f"通知公开配置已保存: {config_path}")
            return True
            
        except Exception as e:
            info, warning, error = get_logger()
            error(f"保存通知公开配置失败: {e}")
            return False
    
    def get_static_mode_config(self) -> Dict[str, Any]:
        """获取静态模式配置"""
        return {
            'enabled': self.is_static_mode_enabled(),
            'description': '强制使用静态配置文件，跳过动态API获取',
            'env_var': 'USE_STATIC_MODE'
        }
    
    def get_deepseek_api_key(self) -> str:
        """获取DeepSeek API密钥"""
        return self.get_env_var('DEEPSEEK_API_KEY')
    
    def get_server_port(self) -> int:
        """获取服务器端口"""
        return int(self.get_env_var('PORT', '5001'))
    
    def get_llm_config(self) -> Dict[str, Any]:
        """获取LLM配置"""
        return {
            'deepseek_api_key': self.get_deepseek_api_key(),
            'base_url': 'https://api.deepseek.com/v1/chat/completions',
            'timeout': 300  # 5分钟超时
        }
    
    def get_server_host(self) -> str:
        """获取服务器主机"""
        return self.get_env_var('HOST', '0.0.0.0')

    def get_server(self):  # -> aiohttp.web.Application:
        """获取服务器实例"""
        def machine_ip():
            """ return current machine ip """
            import socket
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            try:
                return s.getsockname()[0]
            finally:
                s.close()
        return 'http://'+str(machine_ip())+':'+str(self.get_server_port())
    
    def get_task_data_dir(self) -> Path:
        """获取任务数据目录"""
        return self.project_root / 'data' / 'tasks'
    
    def ensure_task_data_dir(self) -> Path:
        """确保任务数据目录存在"""
        task_dir = self.get_task_data_dir()
        task_dir.mkdir(parents=True, exist_ok=True)
        return task_dir
    
    def clear_cache(self):
        """清除配置缓存"""
        self._config_cache.clear()
    
    def backup_systems_to_yaml(self, systems_data: List[Dict], source: str = 'dynamic') -> bool:
        """将系统数据备份到systems_backup.yaml文件"""
        info, warning, error = get_logger()
        try:
            # 转换动态系统数据为配置格式
            for system in systems_data:
                file_name = f'systems_{system.get("name", "unknown")}'
                config_path = self.project_root / 'config' / f'{file_name}.yaml'

                # 读取现有配置
                existing_config = {}
                if config_path.exists():
                    with open(config_path, 'r', encoding='utf-8') as f:
                        existing_config = yaml.safe_load(f) or {}

                # 准备备份数据
                backup_data = {
                    'backup_info': {
                        'timestamp': datetime.now().isoformat(),
                        'source': source,
                        'total_projects': len(system.get('projects', [])),
                        'backup_type': 'auto_backup'
                    },
                    'systems': []
                }

                backup_system = {
                    'id': system.get('id', system.get('name', 'unknown')),
                    'name': system.get('name', 'Unknown System'),
                    'git_provider': system.get('git_provider', 'github'),
                    'git_provider_url': system.get('git_provider_url', ''),
                    'description': system.get('description', ''),
                    'avatar_url': system.get('avatar_url', ''),
                    'projects': []
                }
                
                # 处理项目信息
                for project in system.get('projects', []):
                    if isinstance(project, dict):
                        backup_project = {
                            'name': project.get('name', 'unknown'),
                            'repo_url': project.get('repo_url', ''),
                            'owner': project.get('owner', ''),
                            'repo': project.get('repo', ''),
                            'description': project.get('description', ''),
                            'language': project.get('language', ''),
                            'stars': project.get('stars', 0),
                            'forks': project.get('forks', 0)
                        }
                    else:
                        # 如果project是字符串
                        backup_project = {
                            'name': str(project),
                            'repo_url': '',
                            'owner': '',
                            'repo': '',
                            'description': '',
                            'language': '',
                            'stars': 0,
                            'forks': 0
                        }
                    backup_system['projects'].append(backup_project)
                
                backup_data['systems'].append(backup_system)

                # 生成备份文件名（直接保存在config目录下）
                backup_filename = f'{file_name}_backup.yaml'
                backup_path = self.project_root / 'config' / backup_filename
                # 写入备份文件
                with open(backup_path, 'w', encoding='utf-8') as f:
                    yaml.dump(backup_data, f, default_flow_style=False, allow_unicode=True, indent=2)
                    info(f"系统配置已自动备份到: {backup_path}")

                # 同时更新主配置文件
                with open(config_path, 'w', encoding='utf-8') as f:
                    yaml.dump(backup_data, f, default_flow_style=False, allow_unicode=True, indent=2)
            
            # 清除缓存
            self.clear_cache()
            return True
            
        except Exception as e:
            error(f"备份系统配置失败: {e}")
            return False

    def backup_branches_to_yaml(self, branches_data: List[Dict], source: str = 'dynamic') -> bool:
        """将分支数据备份到branches.yaml文件"""
        info, warning, error = get_logger()
        try:
            config_path = self.project_root / 'config' / 'branches.yaml'

            # 读取现有配置
            existing_config = {}
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    existing_config = yaml.safe_load(f) or {}
            existing_config = existing_config.get('branches', [])

            # 合并现有配置和新数据
            from collections import OrderedDict  # 保持顺序
            def merge_branches(a, b):
                # 1. 把 a、b 拍平成 项目→{name: 记录} 的字典，自动去重
                pool = OrderedDict()
                for src in (a, b):
                    for item in src:  # 每个 item 是 {项目: [分支]}
                        proj, branches = next(iter(item.items()))
                        pool.setdefault(proj, {})  # 保证有这个项目
                        pool[proj].update({br['name']: br for br in branches})

                # 2. 还原成前端要的数组格式
                return [{proj: list(br_map.values())} for proj, br_map in pool.items()]

            existing_config = merge_branches(existing_config, branches_data)
            # 准备备份数据
            backup_data = {
                'backup_info': {
                    'timestamp': datetime.now().isoformat(),
                    'source': source,
                    'total_systems': len(existing_config),
                    'backup_type': 'auto_backup'
                },
                'branches': existing_config
            }

            # 写入备份文件
            with open(config_path, 'w', encoding='utf-8') as f:
                yaml.dump(backup_data, f, default_flow_style=False, allow_unicode=True, indent=2)
                info(f"分支配置已自动备份到: {config_path}")

            # 清除缓存
            self.clear_cache()
            return True

        except Exception as e:
            error(f"备份分支配置失败: {e}")
            return False

    def add_user_system(self, system_data: Dict[str, Any]) -> bool:
        """添加用户自定义系统,非system_id, 而是name,非system_user.yaml文件"""
        info, warning, error = get_logger()
        try:
            config_path = self.project_root / 'config' / f'systems_{system_data.get("name", "unknown")}.yaml'
            
            # 读取现有配置
            user_config = {}
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    user_config = yaml.safe_load(f) or {}
            
            if 'systems' not in user_config:
                user_config['systems'] = []
            
            # 检查是否已存在相同ID的系统
            existing_ids = [s.get('id') for s in user_config['systems']]
            if system_data.get('id') in existing_ids:
                error(f"系统ID {system_data.get('id')} 已存在")
                return False
            
            # 添加新系统
            user_config['systems'].append(system_data)
            
            # 保存配置
            with open(config_path, 'w', encoding='utf-8') as f:
                yaml.safe_dump(user_config, f, default_flow_style=False, allow_unicode=True, indent=2)
            
            # 清除缓存
            self.clear_cache()
            info(f"用户系统 {system_data.get('name')} 添加成功")
            return True
            
        except Exception as e:
            error(f"添加用户系统失败: {e}")
            return False
    
    def remove_user_system(self, system_id: str) -> bool:
        """删除用户自定义系统"""
        info, warning, error = get_logger()
        try:
            # 检查独立的系统配置文件
            config_path = self.project_root / 'config' / f'systems_{system_id}.yaml'
            if config_path.exists():
                os.remove(config_path)
                self.clear_cache()
                info(f"删除系统配置文件 {system_id} 成功")
                return True
            
            warning(f"未找到要删除的系统: {system_id}")
            return False
            
        except Exception as e:
            error(f"删除用户系统失败: {e}")
            return False

# 全局配置管理器实例
config_manager = ConfigManager()
