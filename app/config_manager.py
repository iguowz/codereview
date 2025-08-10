# -*- coding: utf-8 -*-
"""
配置管理器 - 统一管理系统配置
"""

import os
import yaml
from typing import Dict, Any, Optional, List
from pathlib import Path
from datetime import datetime

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
    
    def get_systems_config(self) -> Dict[str, Any]:
        """获取系统配置"""
        if 'systems' not in self._config_cache:
            config_path = self.project_root / 'config' / 'systems.yaml'
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    self._config_cache['systems'] = yaml.safe_load(f) or {}
            except FileNotFoundError:
                info, warning, error = get_logger()
                warning(f"配置文件不存在: {config_path}")
                self._config_cache['systems'] = {'systems': []}
            except Exception as e:
                info, warning, error = get_logger()
                error(f"读取系统配置失败: {e}")
                self._config_cache['systems'] = {'systems': []}
        
        return self._config_cache['systems']
    
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
    
    def get_prompt(self, prompt_name: str) -> str:
        """获取提示词"""
        prompts_config = self.get_prompts_config()
        return prompts_config.get(prompt_name, '')
    
    def get_env_var(self, var_name: str, default: str = '') -> str:
        """获取环境变量"""
        return os.environ.get(var_name, default)
    
    def is_redis_enabled(self) -> bool:
        """检查是否启用Redis"""
        return self.get_env_var('USE_REDIS', 'false').lower() == 'true'
    
    def is_static_mode_enabled(self) -> bool:
        """检查是否启用静态模式（强制使用静态配置文件）"""
        return self.get_env_var('USE_STATIC_MODE', 'false').lower() == 'true'
    
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
        """将系统数据备份到systems.yaml文件"""
        try:
            config_path = self.project_root / 'config' / 'systems.yaml'
            
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
                    'total_systems': len(systems_data),
                    'backup_type': 'auto_backup'
                },
                'systems': []
            }
            
            # 转换动态系统数据为配置格式
            for system in systems_data:
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
            backup_filename = f'systems_backup.yaml'
            backup_path = self.project_root / 'config' / backup_filename
            
            # 同时更新主配置文件
            with open(config_path, 'w', encoding='utf-8') as f:
                yaml.dump(backup_data, f, default_flow_style=False, allow_unicode=True, indent=2)
            
            # 清除缓存
            self.clear_cache()
            
            info, warning, error = get_logger()
            info(f"系统配置已自动备份到: {backup_path}")
            return True
            
        except Exception as e:
            info, warning, error = get_logger()
            error(f"备份系统配置失败: {e}")
            return False


# 全局配置管理器实例
config_manager = ConfigManager()
