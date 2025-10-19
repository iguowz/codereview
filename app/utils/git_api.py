import requests
import yaml
import os
from pathlib import Path
from typing import Dict, List, Optional
from functools import lru_cache
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
from .crypto import CryptoManager
from .cache_manager import global_cache, cached
from ..logger import info, warning, error, debug

class GitAPIClient:
    def __init__(self):
        self.crypto = CryptoManager()
        self.config = self._load_config()
        self.dynamic_systems_cache = []  # 缓存动态获取的系统列表
        self.dynamic_branches_cache = self._load_branches_config()  # 缓存动态获取的分支列表
        self.dynamic_rate_limit_cache = {}  # 缓存动态获取的速率限制
        
        # 优化HTTP客户端性能
        self.session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=20,
            pool_maxsize=20
        )
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        self.session.headers.update({
            'User-Agent': 'CodeReview-GitClient/1.0',
            'Accept': 'application/vnd.github.v3+json'
        })

    def _load_config(self) -> Dict:
        """加载系统配置并只返回 projects 列表"""
        possible_paths = [
            os.path.join(os.path.dirname(__file__), '..', '..', 'config'),
            os.path.join(os.getcwd(), 'config'),
            'config'
        ]
        #获取系统配置config/systems_XXX.yaml
        list_config_path = [i for i in possible_paths if os.path.exists(i)]
        if not list_config_path:
            return {
                'systems': []
            }
        exclude = {'systems_backup.yaml', 'systems_user.yaml'}
        possible_paths = [
            os.path.join(list_config_path[0], f)
            for f in os.listdir(list_config_path[0])
            if f.startswith('systems_') and not f.endswith('_backup.yaml') and f not in exclude
        ]
        projects = []
        for config_path in possible_paths:
            if os.path.isfile(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    full_config = yaml.safe_load(f) or {}
                    # 只提取 projects 列表
                    for system in full_config.get('systems', []):
                        for proj in system.get('projects', []):
                            # 保留你需要的字段
                            projects.append({
                                'git_provider': system.get('git_provider'),
                                'git_provider_url': system.get('git_provider_url'),
                                'name': proj.get('name'),
                                'owner': proj.get('owner'),
                                'repo': proj.get('repo'),
                                'repo_url': proj.get('repo_url'),
                                'language': proj.get('language'),
                                'stars': proj.get('stars'),
                                'forks': proj.get('forks'),
                                'description': proj.get('description')
                            })
        return {'systems': projects}

    def _load_systems_config(self) -> Dict:
        """加载系统配置"""
        # 尝试多个可能的配置文件路径
        possible_paths = [
            os.path.join(os.path.dirname(__file__), '..', '..', 'config'),
            os.path.join(os.getcwd(), 'config'),
            'config'
        ]
        systems_config = []
        #获取系统配置config/systems_XXX.yaml
        list_config_path = [i for i in possible_paths if os.path.exists(i)]
        if not list_config_path:
            return systems_config
        exclude = {'systems_backup.yaml', 'systems_user.yaml'}
        possible_paths = [
            os.path.join(list_config_path[0], f)
            for f in os.listdir(list_config_path[0])
            if f.startswith('systems_') and not f.endswith('_backup.yaml') and f not in exclude
        ]
        for config_path in possible_paths:
            if os.path.isfile(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    full_config = yaml.safe_load(f) or {}
                    if full_config:
                        systems_config.append(full_config.get('systems', []))
        return systems_config

    def _load_branches_config(self) -> List[Dict]:
        '''加载分支配置'''
        # 尝试多个可能的配置文件路径
        possible_paths = [
            os.path.join(os.path.dirname(__file__), '..', '..', 'config', 'branches.yaml'),
            os.path.join(os.getcwd(), 'config', 'branches.yaml'),
            'config/branches.yaml'
        ]

        for config_path in possible_paths:
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    res = yaml.safe_load(f)
                    if res:
                        return res.get('branches', [])

        # 如果找不到配置文件，返回默认配置
        return []
    
    def _get_auth_headers(self, system_config: Dict) -> Dict:
        """获取认证头"""
        try:
            token = self.crypto.decrypt(system_config['git_provider_token'])
        except Exception:
            token = system_config.get('git_provider_token')
        
        # 环境变量兜底
        if not token or token == 'your_github_token_here':
            token = os.environ.get('GITHUB_TOKEN') or os.environ.get('GITLAB_TOKEN') or os.environ.get('GITEE_TOKEN') or os.environ.get('GH_TOKEN') or token
        
        # 允许无 token：使用未认证请求（受 Git 平台限速）
        if not token or token == 'your_github_token_here':
            # 警告：未配置 Git Token
            pass
            return {}
        
        provider = system_config.get('git_provider')
        if provider == 'github':
            return {'Authorization': f'token {token}'}
        elif provider == 'gitlab':
            return {'Authorization': f'Bearer {token}'}
        elif provider == 'gitee':
            return {'Authorization': f'token {token}'}
        else:
            raise ValueError(f"Unsupported git provider: {provider}")

    def _get_rate_limit(self, system_config: Dict) -> Dict:
        """获取速率限制"""
        provider = system_config.get('git_provider')
        if provider == 'github':
            self.dynamic_rate_limit_cache = self._get_github_rate_limit(system_config)
        elif provider == 'gitlab':
            self.dynamic_rate_limit_cache = self._get_gitlab_rate_limit(system_config)
        elif provider == 'gitee':
            self.dynamic_rate_limit_cache = self._get_gitee_rate_limit(system_config)
        else:
            raise ValueError(f"Unsupported git provider: {provider}")

    def _get_github_rate_limit(self, system_config: Dict) -> Dict:
        """获取GitHub速率限制"""
        url = 'https://api.github.com/rate_limit'
        auth_headers = self._get_auth_headers(system_config)

        try:
            response = requests.get(url, headers=auth_headers)

            if response.status_code == 200:
                data = response.json()
                return {
                   'limit': data['resources']['core']['limit'],
                   'remaining': data['resources']['core']['remaining'],
                   'reset': data['resources']['core']['reset']
                }
            else:
                error(f"GitHub API速率限制响应错误: {response.status_code}")
                try:
                    error_msg = response.json().get('message', '')
                    if error_msg:
                        error(f"GitHub API速率限制响应错误详情: {error_msg}")
                except Exception:
                    pass
                raise ValueError(f"GitHub API error: {response.status_code}")

        except requests.exceptions.RequestException as e:
            error(f"GitHub API速率限制请求异常: {str(e)}")
            raise

    def _get_gitlab_rate_limit(self, system_config: Dict) -> Dict:
        """获取GitLab速率限制"""
        url = 'https://gitlab.com/api/v4/rate_limit'
        auth_headers = self._get_auth_headers(system_config)

        try:
            response = requests.get(url, headers=auth_headers)

            if response.status_code == 200:
                data = response.json()
                return {
                    'limit': data['core']['limit'],
                    'remaining': data['core']['remaining'],
                    'reset': data['core']['reset']
                }
            else:
                error(f"GitLab API速率限制响应错误: {response.status_code}")
                try:
                    error_msg = response.json().get('message', '')
                    if error_msg:
                        error(f"GitLab API速率限制响应错误详情: {error_msg}")
                except Exception:
                    pass
                raise ValueError(f"GitLab API error: {response.status_code}")

        except requests.exceptions.RequestException as e:
            error(f"GitLab API速率限制请求异常: {str(e)}")
            raise

    def _get_gitee_rate_limit(self, system_config: Dict) -> Dict:
        """获取Gitee速率限制"""
        url = 'https://gitee.com/api/v5/rate_limit'
        auth_headers = self._get_auth_headers(system_config)

        try:
            response = requests.get(url, headers=auth_headers)

            if response.status_code == 200:
                data = response.json()
                return {
                    'limit': data['rate']['limit'],
                    'remaining': data['rate']['remaining'],
                    'reset': data['rate']['reset_time']
                }
            else:
                error(f"Gitee API速率限制响应错误: {response.status_code}")
                try:
                    error_msg = response.json().get('message', '')
                    if error_msg:
                        error(f"Gitee API速率限制响应错误详情: {error_msg}")
                except Exception:
                    pass
                raise ValueError(f"Gitee API error: {response.status_code}")

        except requests.exceptions.RequestException as e:
            error(f"Gitee API速率限制请求异常: {str(e)}")
            raise
    
    def get_diff(self, system_name: str, branch_name: str, master_branch: str = 'main') -> List[Dict]:
        """获取指定系统和分支的diff信息"""
        info(f"开始获取系统 '{system_name}' 的diff信息")
        debug(f"请求参数: branch_name={branch_name}, master_branch={master_branch}")
        
        # 查找系统配置
        system_config = None
        info(f"开始查找系统config文件: '{self.config}' 的配置")
        for system in self.config.get('systems', []):
            if system['name'] == system_name:
                system_config = system
                break
        
        if not system_config:
            error(f"系统 '{system_name}' 未找到")
            # 返回包含错误信息的结果，而不是抛出异常
            return [{
                'project_name': 'unknown',
                'repo_url': '',
                'error': f"System '{system_name}' not found"
            }]
        
        info(f"找到系统配置: {system_config.get('name', 'unknown')}, 项目数量: {len(system_config.get('projects', []))},找到系统配置: {system_config}")
        debug(f"系统 '{system_name}' 包含项目: {[p.get('name', 'unknown') for p in system_config.get('projects', [])]}")
        auth_headers = self._get_auth_headers(system_config)
        results = []
        
        for project in system_config.get('projects', [system_config]):
            project_name = project.get('name', 'unknown')
            info(f"处理系统 '{system_name}' 下的项目: {project_name}")
            debug(f"项目详情: owner={project.get('owner', 'unknown')}, repo={project.get('repo', 'unknown')}")
            
            try:
                diff_data = self._get_project_diff(
                    system_config, project, branch_name, master_branch, auth_headers
                )
                if diff_data:
                    info(f"系统 '{system_name}' 的项目 {project_name} 获取diff成功")
                    results.append({
                        'project_name': project['name'],
                        'repo_url': project['repo_url'],
                        'diff_data': diff_data
                    })
                else:
                    info(f"系统 '{system_name}' 的项目 {project_name} 无代码变更")
                    # 无差异也返回占位，便于前端呈现"无变更"
                    results.append({
                        'project_name': project['name'],
                        'repo_url': project['repo_url'],
                        'diff_data': None
                    })
                self.set_dynamic_branches(system_config, project_name, project['repo_url'], branch_name)
            except Exception as e:
                error(f"系统 '{system_name}' 的项目 {project_name} 获取diff失败: {str(e)}")
                # 不抛出整体异常，返回到结果中
                results.append({
                    'project_name': project['name'],
                    'repo_url': project['repo_url'],
                    'error': str(e)
                })

        self._get_rate_limit(system_config)
        info(f"系统 '{system_name}' diff获取完成，成功项目数: {len([r for r in results if 'error' not in r])}, 失败项目数: {len([r for r in results if 'error' in r])}")
        return results
    
    def _get_project_diff(self, system_config: Dict, project: Dict, branch_name: str, 
                         master_branch: str, auth_headers: Dict) -> Optional[Dict]:
        """获取单个项目的diff信息"""
        git_provider = system_config['git_provider']
        project_name = project.get('name', 'unknown')
        
        info(f"开始获取项目 {project_name} 的diff信息 (Git提供商: {git_provider})")
        debug(f"项目参数: branch_name={branch_name}, master_branch={master_branch}")
        
        if git_provider == 'github':
            return self._get_github_diff(project, branch_name, master_branch, auth_headers)
        elif git_provider == 'gitlab':
            return self._get_gitlab_diff(project, branch_name, master_branch, auth_headers)
        elif git_provider == 'gitee':
            return self._get_gitee_diff(project, branch_name, master_branch, auth_headers)
        else:
            error(f"不支持的Git提供商: {git_provider}")
            raise ValueError(f"Unsupported git provider: {git_provider}")
    
    def _get_github_diff(self, project: Dict, branch_name: str, master_branch: str, 
                        auth_headers: Dict) -> Optional[Dict]:
        """获取GitHub项目的diff信息"""
        owner = project['owner']
        repo = project['repo']
        url = f"https://api.github.com/repos/{owner}/{repo}/compare/{master_branch}...{branch_name}"
        
        info(f"GitHub API请求: {url}")
        debug(f"请求头: {auth_headers}")
        
        try:
            response = requests.get(url, headers={**auth_headers, 'Accept': 'application/vnd.github+json'})
            info(f"GitHub API响应状态码: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                info(f"GitHub API响应成功: {data}")
                status = data.get('status', 'unknown')
                file_count = len(data.get('files', []))
                commit_count = data.get('total_commits', 0)
                
                info(f"GitHub API响应成功: 状态={status}, 文件数={file_count}, 提交数={commit_count}")
                
                if status == 'ahead':
                    debug(f"分支 {branch_name} 领先 {master_branch}，有代码变更")
                    return {
                        'files': data['files'],
                        'total_commits': data['total_commits'],
                        'status': data['status']
                    }
                elif status == 'identical':
                    info(f"分支 {branch_name} 与 {master_branch} 相同，无代码变更")
                    return None  # 无差异
                else:
                    info(f"分支 {branch_name} 状态: {status}")
                    return {
                        'files': data.get('files', []),
                        'total_commits': data.get('total_commits', 0),
                        'status': data['status']
                    }
            elif response.status_code == 404:
                error(f"GitHub API 404: 分支 '{branch_name}' 未找到")
                raise ValueError(f"Branch '{branch_name}' not found")
            elif response.status_code == 401:
                error("GitHub API 401: 认证失败")
                raise ValueError("Authentication failed")
            elif response.status_code == 403:
                try:
                    msg = response.json().get('message', '')
                except Exception:
                    msg = ''
                
                if 'rate limit' in msg.lower():
                    error("GitHub API 403: 速率限制超出")
                    raise ValueError("GitHub API rate limit exceeded for unauthenticated requests. 请配置 git_provider_token 或稍后再试")
                else:
                    error(f"GitHub API 403: {msg}")
                    raise ValueError("GitHub API 403 Forbidden. 目标仓库可能为私有或需要更高权限的 Token")
            else:
                error(f"GitHub API 错误: {response.status_code}")
                try:
                    error_msg = response.json().get('message', '')
                    if error_msg:
                        error(f"GitHub API 错误详情: {error_msg}")
                except Exception:
                    pass
                raise ValueError(f"GitHub API error: {response.status_code}")
                
        except requests.exceptions.RequestException as e:
            error(f"GitHub API 请求异常: {str(e)}")
            raise
    
    def _get_gitlab_diff(self, project: Dict, branch_name: str, master_branch: str, 
                        auth_headers: Dict) -> Optional[Dict]:
        """获取GitLab项目的diff信息"""
        project_name = f"{project['owner']}/{project['repo']}"
        info(f"开始获取GitLab项目 {project_name} 的diff信息")
        debug(f"项目参数: branch_name={branch_name}, master_branch={master_branch}")
        
        # 首先获取项目ID
        project_url = f"https://gitlab.com/api/v4/projects/{project['owner']}%2F{project['repo']}"
        info(f"GitLab API项目信息请求: {project_url}")
        debug(f"请求头: {auth_headers}")
        
        response = requests.get(project_url, headers=auth_headers)
        info(f"GitLab API项目信息响应状态码: {response.status_code}")
        
        if response.status_code != 200:
            error(f"GitLab API获取项目信息失败: {response.status_code}")
            try:
                error_msg = response.json().get('message', '')
                if error_msg:
                    error(f"GitLab API错误详情: {error_msg}")
            except Exception:
                pass
            raise ValueError(f"Failed to get project info: {response.status_code}")
        
        project_id = response.json()['id']
        info(f"GitLab项目 {project_name} ID: {project_id}")
        
        # 获取diff信息
        diff_url = f"https://gitlab.com/api/v4/projects/{project_id}/repository/compare"
        params = {
            'from': master_branch,
            'to': branch_name
        }
        
        info(f"GitLab API diff请求: {diff_url}")
        debug(f"请求参数: {params}")
        debug(f"请求头: {auth_headers}")
        
        response = requests.get(diff_url, headers=auth_headers, params=params)
        info(f"GitLab API diff响应状态码: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            file_count = len(data.get('diffs', []))
            commit_count = len(data.get('commits', []))
            
            info(f"GitLab API diff响应成功: 文件数={file_count}, 提交数={commit_count}")
            
            if data.get('diffs'):
                debug(f"分支 {branch_name} 领先 {master_branch}，有代码变更")
                return {
                    'files': data['diffs'],
                    'total_commits': commit_count,
                    'status': 'ahead'
                }
            else:
                info(f"分支 {branch_name} 与 {master_branch} 相同，无代码变更")
                return None  # 无差异
        elif response.status_code == 404:
            error(f"GitLab API 404: 分支 '{branch_name}' 未找到")
            raise ValueError(f"Branch '{branch_name}' not found")
        elif response.status_code == 401:
            error("GitLab API 401: 认证失败")
            raise ValueError("Authentication failed")
        elif response.status_code == 403:
            try:
                error_msg = response.json().get('message', '')
                if error_msg:
                    error(f"GitLab API 403: {error_msg}")
            except Exception:
                pass
            error("GitLab API 403: 权限不足")
            raise ValueError("GitLab API 403 Forbidden. 目标仓库可能为私有或需要更高权限的 Token")
        else:
            error(f"GitLab API 错误: {response.status_code}")
            try:
                error_msg = response.json().get('message', '')
                if error_msg:
                    error(f"GitLab API 错误详情: {error_msg}")
            except Exception:
                pass
            raise ValueError(f"GitLab API error: {response.status_code}")

    def _get_gitee_diff(self, project: Dict, branch_name: str, master_branch: str,
                        auth_headers: Dict) -> Optional[Dict]:
        """获取Gitee项目的diff信息"""
        owner = project['owner']
        repo = project['repo']
        url = f"https://gitee.com/api/v5/repos/{owner}/{repo}/compare/{master_branch}...{branch_name}"

        info(f"Gitee API请求: {url}")
        debug(f"请求头: {auth_headers}")

        try:
            response = requests.get(url, headers={**auth_headers, 'Content-Type': 'application/json'})
            info(f"Gitee API响应状态码: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                info(f"Gitee API响应成功: {data}")
                status = data.get('status', 'unknown')
                file_count = len(data.get('files', []))
                commit_count = data.get('total_commits', 0)

                info(f"Gitee API响应成功: 状态={status}, 文件数={file_count}, 提交数={commit_count}")

                if status == 'ahead':
                    debug(f"分支 {branch_name} 领先 {master_branch}，有代码变更")
                    return {
                        'files': data['files'],
                        'total_commits': data['total_commits'],
                        'status': data['status']
                    }
                elif status == 'identical':
                    info(f"分支 {branch_name} 与 {master_branch} 相同，无代码变更")
                    return None  # 无差异
                else:
                    info(f"分支 {branch_name} 状态: {status}")
                    return {
                        'files': data.get('files', []),
                        'total_commits': data.get('total_commits', 0),
                        'status': data['status']
                    }
            elif response.status_code == 404:
                error(f"Gitee API 404: 分支 '{branch_name}' 未找到")
                raise ValueError(f"Branch '{branch_name}' not found")
            elif response.status_code == 401:
                error("Gitee API 401: 认证失败")
                raise ValueError("Authentication failed")
            elif response.status_code == 403:
                try:
                    error_msg = response.json().get('message', '')
                    if error_msg:
                        error(f"Gitee API 403: {error_msg}")
                except Exception:
                    pass
                error("Gitee API 403: 权限不足")
                raise ValueError("Gitee API 403 Forbidden. 目标仓库可能为私有或需要更高权限的 Token")
            else:
                error(f"Gitee API 错误: {response.status_code}")
                try:
                    error_msg = response.json().get('message', '')
                    if error_msg:
                        error(f"Gitee API 错误详情: {error_msg}")
                except Exception:
                    pass
                raise ValueError(f"Gitee API error: {response.status_code}")

        except requests.exceptions.RequestException as e:
            error(f"Gitee API 请求异常: {str(e)}")
            raise
    
    def get_dynamic_systems(self, force_refresh: bool = False) -> List[Dict]:
        """通过git_provider_url动态获取系统列表"""
        dynamic_systems = []
        
        # 从配置文件中获取基础git provider信息
        for system_config in self._load_systems_config():
            for system in system_config:
                git_provider_url = system.get('git_provider_url', '')
                if not git_provider_url:
                    continue
                if git_provider_url in set([s.get('git_provider_url', '') for s in self.dynamic_systems_cache]) and not force_refresh:
                    continue
                try:
                    # 解析git_provider_url获取owner信息
                    info(f"开始获取系统 {git_provider_url} 的动态配置")
                    system_data = self._fetch_system_from_url(system, git_provider_url)

                    if system_data:
                        dynamic_systems.append(system_data)
                    self.dynamic_systems_cache = dynamic_systems
                    print(f"dynamic_systems_cache: {self.dynamic_systems_cache}")
                except Exception as e:
                    print(f"获取系统 {system.get('name', 'unknown')} 失败: {e}")
                self._get_rate_limit(system)
        return self.dynamic_systems_cache

    def set_dynamic_branches(self,system_config: Dict, name: str, repo_url: str, branch_name: str = ''):
        """设置动态分支数据"""
        if [b for b in self.dynamic_branches_cache if b.get(name, None)] and not branch_name:
            return
        project_id = repo_url.split('.com/')[-1]
        branch_data = self._fetch_branch_from_url(system_config, project_id)
        if branch_data:
            self.dynamic_branches_cache.append({name: branch_data})
        self._get_rate_limit(system_config)

    def _fetch_system_from_url(self, system_config: Dict, git_provider_url: str) -> Optional[Dict]:
        """从git_provider_url获取系统信息"""
        git_provider = system_config.get('git_provider', 'github')
        
        if git_provider == 'github':
            return self._fetch_github_system(system_config, git_provider_url)
        elif git_provider == 'gitlab':
            return self._fetch_gitlab_system(system_config, git_provider_url)
        elif git_provider == 'gitee':
            return self._fetch_gitee_system(system_config, git_provider_url)
        else:
            raise ValueError(f"Unsupported git provider: {git_provider}")
    
    def _fetch_github_system(self, system_config: Dict, git_provider_url: str) -> Optional[Dict]:
        """从GitHub URL获取系统信息"""
        # 解析GitHub URL: https://github.com/owner/repo 或 https://github.com/owner
        url_parts = git_provider_url.rstrip('/').split('/')
        if len(url_parts) < 4:
            raise ValueError(f"Invalid GitHub URL: {git_provider_url}")
        
        owner = url_parts[-2] if len(url_parts) >= 5 else url_parts[-1]
        repo = url_parts[-1] if len(url_parts) >= 5 else None
        
        auth_headers = self._get_auth_headers(system_config)
        
        if repo:
            # 获取单个仓库信息
            return self._fetch_github_repo(system_config, owner, repo, auth_headers)
        else:
            # 获取用户/组织的仓库列表
            return self._fetch_github_user_repos(system_config, owner, auth_headers)
    
    def _fetch_github_repo(self, system_config: Dict, owner: str, repo: str, auth_headers: Dict) -> Dict:
        """获取GitHub单个仓库信息"""
        url = f"https://api.github.com/repos/{owner}/{repo}"
        response = requests.get(url, headers={**auth_headers, 'Accept': 'application/vnd.github+json'})
        
        if response.status_code == 200:
            repo_data = response.json()
            info(f"GitHub API获取仓库信息成功: {repo_data}")
            self.set_dynamic_branches(system_config, repo_data['name'], repo_data['html_url'])
            info(f"动态分支数据: {self.dynamic_branches_cache}")
            return {
                'id': system_config.get('id', f"github-{owner}-{repo}"),
                'name': system_config.get('name', repo_data['name']),
                'git_provider': 'github',
                'git_provider_url': repo_data['html_url'],
                'projects': [{
                    'name': repo_data['name'],
                    'repo_url': repo_data['html_url'],
                    'owner': owner,
                    'repo': repo,
                    'description': repo_data.get('description', ''),
                    'language': repo_data.get('language', ''),
                    'stars': repo_data.get('stargazers_count', 0),
                    'forks': repo_data.get('forks_count', 0)
                }]
            }
        else:
            raise ValueError(f"Failed to fetch GitHub repo {owner}/{repo}: {response.status_code}")
    
    def _fetch_github_user_repos(self, system_config: Dict, owner: str, auth_headers: Dict) -> Dict:
        """获取GitHub用户/组织的仓库列表"""
        # 首先获取用户/组织信息
        user_url = f"https://api.github.com/users/{owner}"
        user_response = requests.get(user_url, headers={**auth_headers, 'Accept': 'application/vnd.github+json'})
        
        if user_response.status_code != 200:
            raise ValueError(f"Failed to fetch GitHub user {owner}: {user_response.status_code}")
        
        user_data = user_response.json()
        
        # 获取仓库列表
        repos_url = f"https://api.github.com/users/{owner}/repos"
        params = {
            'type': 'all',  # 包括own、member等
            'sort': 'updated',
            'direction': 'desc',
            'per_page': 50  # 限制数量
        }
        
        repos_response = requests.get(repos_url, headers={**auth_headers, 'Accept': 'application/vnd.github+json'}, params=params)
        
        if repos_response.status_code == 200:
            repos_data = repos_response.json()
            projects = []
            
            for repo in repos_data:
                # 跳过fork的仓库（可选）
                if repo.get('fork', False):
                    continue
                self.set_dynamic_branches(system_config, repo['name'], repo['html_url'])
                projects.append({
                    'name': repo['name'],
                    'repo_url': repo['html_url'],
                    'owner': owner,
                    'repo': repo['name'],
                    'description': repo.get('description', ''),
                    'language': repo.get('language', ''),
                    'stars': repo.get('stargazers_count', 0),
                    'forks': repo.get('forks_count', 0),
                    'updated_at': repo.get('updated_at', '')
                })
            
            return {
                'id': system_config.get('id', f"github-{owner}"),
                'name': system_config.get('name', user_data.get('name', owner)),
                'git_provider': 'github',
                'git_provider_url': user_data['html_url'],
                'description': user_data.get('bio', ''),
                'avatar_url': user_data.get('avatar_url', ''),
                'public_repos': user_data.get('public_repos', 0),
                'projects': projects
            }
        else:
            raise ValueError(f"Failed to fetch GitHub repos for {owner}: {repos_response.status_code}")
    
    def _fetch_gitlab_system(self, system_config: Dict, git_provider_url: str) -> Optional[Dict]:
        """从GitLab URL获取系统信息"""
        # 解析GitLab URL: https://gitlab.com/owner/repo 或 https://gitlab.com/owner
        url_parts = git_provider_url.rstrip('/').split('/')
        if len(url_parts) < 4:
            raise ValueError(f"Invalid GitLab URL: {git_provider_url}")
        
        auth_headers = self._get_auth_headers(system_config)
        
        if len(url_parts) >= 5:
            # 单个项目: https://gitlab.com/owner/repo
            owner = url_parts[-2]
            repo = url_parts[-1]
            return self._fetch_gitlab_project(system_config, owner, repo, auth_headers)
        else:
            # 用户/组织: https://gitlab.com/owner
            owner = url_parts[-1]
            return self._fetch_gitlab_user_projects(system_config, owner, auth_headers)
    
    def _fetch_gitlab_project(self, system_config: Dict, owner: str, repo: str, auth_headers: Dict) -> Dict:
        """获取GitLab单个项目信息"""
        project_url = f"https://gitlab.com/api/v4/projects/{owner}%2F{repo}"
        response = requests.get(project_url, headers=auth_headers)
        
        if response.status_code == 200:
            project_data = response.json()
            self.set_dynamic_branches(system_config, project_data['name'], project_data['web_url'])
            return {
                'id': system_config.get('id', f"gitlab-{owner}-{repo}"),
                'name': system_config.get('name', project_data['name']),
                'git_provider': 'gitlab',
                'git_provider_url': project_data['web_url'],
                'projects': [{
                    'name': project_data['name'],
                    'repo_url': project_data['web_url'],
                    'owner': owner,
                    'repo': repo,
                    'description': project_data.get('description', ''),
                    'stars': project_data.get('star_count', 0),
                    'forks': project_data.get('forks_count', 0)
                }]
            }
        else:
            raise ValueError(f"Failed to fetch GitLab project {owner}/{repo}: {response.status_code}")
    
    def _fetch_gitlab_user_projects(self, system_config: Dict, owner: str, auth_headers: Dict) -> Dict:
        """获取GitLab用户/组织的项目列表"""
        # 首先尝试作为用户获取
        user_url = f"https://gitlab.com/api/v4/users?username={owner}"
        user_response = requests.get(user_url, headers=auth_headers)
        
        user_id = None
        user_data = {}
        
        if user_response.status_code == 200:
            users = user_response.json()
            if users:
                user_data = users[0]
                user_id = user_data['id']
        
        if not user_id:
            # 尝试作为组织获取
            group_url = f"https://gitlab.com/api/v4/groups?search={owner}"
            group_response = requests.get(group_url, headers=auth_headers)
            
            if group_response.status_code == 200:
                groups = group_response.json()
                for group in groups:
                    if group['path'] == owner:
                        user_id = group['id']
                        user_data = group
                        break
        
        if not user_id:
            raise ValueError(f"Failed to find GitLab user/group: {owner}")
        
        # 获取项目列表
        projects_url = f"https://gitlab.com/api/v4/users/{user_id}/projects" if 'username' in user_data else f"https://gitlab.com/api/v4/groups/{user_id}/projects"
        params = {
            'order_by': 'updated_at',
            'sort': 'desc',
            'per_page': 50
        }
        
        projects_response = requests.get(projects_url, headers=auth_headers, params=params)
        
        if projects_response.status_code == 200:
            projects_data = projects_response.json()
            projects = []
            
            for project in projects_data:
                self.set_dynamic_branches(system_config, project['name'], project['web_url'])
                projects.append({
                    'name': project['name'],
                    'repo_url': project['web_url'],
                    'owner': owner,
                    'repo': project['path'],
                    'description': project.get('description', ''),
                    'stars': project.get('star_count', 0),
                    'forks': project.get('forks_count', 0),
                    'updated_at': project.get('last_activity_at', '')
                })
            
            return {
                'id': system_config.get('id', f"gitlab-{owner}"),
                'name': system_config.get('name', user_data.get('name', owner)),
                'git_provider': 'gitlab',
                'git_provider_url': f"https://gitlab.com/{owner}",
                'description': user_data.get('description', ''),
                'avatar_url': user_data.get('avatar_url', ''),
                'projects': projects
            }
        else:
            raise ValueError(f"Failed to fetch GitLab projects for {owner}: {projects_response.status_code}")

    def _fetch_gitee_system(self, system_config: Dict, git_provider_url: str) -> Optional[Dict]:
        """从Gitee URL获取系统信息"""
        # 解析Gitee URL: https://gitee.com/owner/repo 或 https://gitee.com/owner
        url_parts = git_provider_url.rstrip('/').split('/')
        if len(url_parts) < 4:
            raise ValueError(f"Invalid Gitee URL: {git_provider_url}")

        auth_headers = self._get_auth_headers(system_config)

        if len(url_parts) >= 5:
            # 单个项目: https://gitee.com/owner/repo
            owner = url_parts[-2]
            repo = url_parts[-1]
            return self._fetch_gitee_project(system_config, owner, repo, auth_headers)
        else:
            # 用户/组织: https://gitee.com/owner
            owner = url_parts[-1]
            return self._fetch_gitee_user_projects(system_config, owner, auth_headers)

    def _fetch_gitee_project(self, system_config: Dict, owner: str, repo: str, auth_headers: Dict) -> Dict:
        """获取Gitee单个项目信息"""
        project_url = f"https://gitee.com/api/v5/repos/{owner}/{repo}"
        response = requests.get(project_url, headers=auth_headers)

        if response.status_code == 200:
            project_data = response.json()
            self.set_dynamic_branches(system_config, project_data['name'], project_data['html_url'])
            return {
                'id': system_config.get('id', f"gitee-{owner}-{repo}"),
                'name': system_config.get('name', project_data['name']),
                'git_provider': 'gitee',
                'git_provider_url': project_data['html_url'],
                'projects': [{
                    'name': project_data['name'],
                    'repo_url': project_data['html_url'],
                    'owner': owner,
                    'repo': repo,
                    'description': project_data.get('description', ''),
                    'stars': project_data.get('stargazers_count', 0),
                    'forks': project_data.get('forks_count', 0)
                }]
            }
        else:
            raise ValueError(f"Failed to fetch Gitee project {owner}/{repo}: {response.status_code}")

    def _fetch_gitee_user_projects(self, system_config: Dict, owner: str, auth_headers: Dict) -> Dict:
        """获取Gitee用户/组织的项目列表"""
        # 首先尝试作为用户获取
        user_url = f"https://gitee.com/api/v5/users/{owner}"
        user_response = requests.get(user_url, headers=auth_headers)

        user_id = None
        user_data = {}

        if user_response.status_code == 200:
            user_data = user_response.json()
            user_id = user_data['id']

        if not user_id:
            # 尝试作为组织获取
            group_url = f"https://gitee.com/api/v5/orgs/{owner}"
            group_response = requests.get(group_url, headers=auth_headers)

            if group_response.status_code == 200:
                group_data = group_response.json()
                user_id = group_data['id']
                user_data = group_data

        if not user_id:
            raise ValueError(f"Failed to find Gitee user/group: {owner}")

        # 获取项目列表
        projects_url = f"https://gitee.com/api/v5/users/{user_id}/repos" if 'username' in user_data else f"https://gitee.com/api/v5/orgs/{user_id}/repos"
        params = {
            'type': 'all',  # 包括own、member等
            'sort': 'updated',
            'direction': 'desc',
            'per_page': 50  # 限制数量
        }

        projects_response = requests.get(projects_url, headers=auth_headers, params=params)

        if projects_response.status_code == 200:
            projects_data = projects_response.json()
            projects = []

            for project in projects_data:
                self.set_dynamic_branches(system_config, project['name'], project['html_url'])
                projects.append({
                    'name': project['name'],
                    'repo_url': project['html_url'],
                    'owner': owner,
                    'repo': project['name'],
                    'description': project.get('description', ''),
                    'language': project.get('language', ''),
                    'stars': project.get('stargazers_count', 0),
                    'forks': project.get('forks_count', 0),
                    'updated_at': project.get('updated_at', '')
                })

            return {
                'id': system_config.get('id', f"gitee-{owner}"),
                'name': system_config.get('name', user_data.get('name', owner)),
                'git_provider': 'gitee',
                'git_provider_url': f"https://gitee.com/{owner}",
                'description': user_data.get('bio', ''),
                'avatar_url': user_data.get('avatar_url', ''),
                'public_repos': user_data.get('public_repos', 0),
                'projects': projects
            }
        else:
            raise ValueError(f"Failed to fetch Gitee projects for {owner}: {projects_response.status_code}")


    # 获取项目分支列表
    def _fetch_branch_from_url(self, system_config: Dict, project_id: str) -> List[Dict]:
        """获取项目分支列表"""
        if not system_config:
            raise ValueError(f"System not found: {system_config}")
        info(f"Fetching branches for project {project_id} from {system_config['git_provider']}...")
        git_provider = system_config.get('git_provider', 'github')
        if git_provider == 'github':
            return self._get_github_project_branches(system_config, project_id)
        elif git_provider == 'gitlab':
            return self._get_gitlab_project_branches(system_config, project_id)
        elif git_provider == 'gitee':
            return self._get_gitee_project_branches(system_config, project_id)
        else:
            raise ValueError(f"Unsupported git provider: {git_provider}")

    def _get_github_project_branches(self, system_config: Dict, project_id: str) -> List[Dict]:
        """获取GitHub项目分支列表"""
        auth_headers = self._get_auth_headers(system_config)
        url = f"https://api.github.com/repos/{project_id}/branches"
        info(f"Fetching branches from {url}")
        response = requests.get(url, headers={**auth_headers, 'Accept': 'application/vnd.github+json'})

        if response.status_code == 200:
            branches_data = response.json()
            return [{
                'name': branch['name'],
                'commit_sha': branch['commit']['sha'],
                'commit_url': branch['commit']['url'],
                'protected': branch['protected']
            } for branch in branches_data]
        else:
            error(f"Failed to fetch GitHub project branches {project_id}: {response.status_code}")
            return []

    def _get_gitlab_project_branches(self, system_config: Dict, project: str) -> List[Dict]:
        """获取GitLab项目分支列表"""
        auth_headers = self._get_auth_headers(system_config)
        project = project.replace('/', '%2F')

        #获取项目ID
        project_url = f"https://gitlab.com/api/v4/projects/{project}"
        response = requests.get(project_url, headers=auth_headers)
        if response.status_code == 200:
            project_data = response.json()
            project_id = project_data['id']
        else:
            error(f"Failed to fetch GitLab project {project}: {response.status_code}")
            return []

        url = f"https://gitlab.com/api/v4/projects/{project_id}/repository/branches"
        response = requests.get(url, headers=auth_headers)

        if response.status_code == 200:
            branches_data = response.json()
            return [{
                'name': branch['name'],
                'commit_sha': branch['commit']['id'],
                'commit_url': branch['commit']['web_url'],
                'protected': branch['protected']
            } for branch in branches_data]
        else:
            error(f"Failed to fetch GitLab project branches {project_id}: {response.status_code}")
            return []

    def _get_gitee_project_branches(self, system_config: Dict, project_id: str) -> List[Dict]:
        """获取Gitee项目分支列表"""
        auth_headers = self._get_auth_headers(system_config)
        url = f"https://gitee.com/api/v5/repos/{project_id}/branches"
        response = requests.get(url, headers=auth_headers)

        if response.status_code == 200:
            branches_data = response.json()
            return [{
                'name': branch['name'],
                'commit_sha': branch['commit']['sha'],
                'commit_url': branch['commit']['url'],
                'protected': branch['protected']
            } for branch in branches_data]
        else:
            error(f"Failed to fetch Gitee project branches {project_id}: {response.status_code}")
            return []