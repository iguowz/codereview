import requests
import yaml
import os
from typing import Dict, List, Optional
from .crypto import CryptoManager
from ..logger import info, warning, error, debug

class GitAPIClient:
    def __init__(self):
        self.crypto = CryptoManager()
        self.config = self._load_config()
        self.dynamic_systems_cache = None  # 缓存动态获取的系统列表
    
    def _load_config(self) -> Dict:
        """加载系统配置"""
        # 尝试多个可能的配置文件路径
        possible_paths = [
            os.path.join(os.path.dirname(__file__), '..', '..', 'config', 'systems.yaml'),
            os.path.join(os.getcwd(), 'config', 'systems.yaml'),
            'config/systems.yaml'
        ]
        
        for config_path in possible_paths:
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    return yaml.safe_load(f)
        
        # 如果找不到配置文件，返回默认配置
        return {
            'systems': []
        }
    
    def _get_auth_headers(self, system_config: Dict) -> Dict:
        """获取认证头"""
        try:
            token = self.crypto.decrypt(system_config['git_provider_token'])
        except Exception:
            token = system_config.get('git_provider_token')
        
        # 环境变量兜底
        if not token or token == 'your_github_token_here':
            token = os.environ.get('GITHUB_TOKEN') or os.environ.get('GH_TOKEN') or token
        
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
        else:
            raise ValueError(f"Unsupported git provider: {provider}")
    
    def get_diff(self, system_name: str, branch_name: str, master_branch: str = 'main') -> List[Dict]:
        """获取指定系统和分支的diff信息"""
        info(f"开始获取系统 '{system_name}' 的diff信息")
        debug(f"请求参数: branch_name={branch_name}, master_branch={master_branch}")
        
        # 查找系统配置
        system_config = None
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
        
        info(f"找到系统配置: {system_config.get('name', 'unknown')}, 项目数量: {len(system_config.get('projects', []))}")
        debug(f"系统 '{system_name}' 包含项目: {[p.get('name', 'unknown') for p in system_config.get('projects', [])]}")
        auth_headers = self._get_auth_headers(system_config)
        results = []
        
        for project in system_config['projects']:
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
            except Exception as e:
                error(f"系统 '{system_name}' 的项目 {project_name} 获取diff失败: {str(e)}")
                # 不抛出整体异常，返回到结果中
                results.append({
                    'project_name': project['name'],
                    'repo_url': project['repo_url'],
                    'error': str(e)
                })
        
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
    
    def get_dynamic_systems(self, force_refresh: bool = False) -> List[Dict]:
        """通过git_provider_url动态获取系统列表"""
        if self.dynamic_systems_cache and not force_refresh:
            return self.dynamic_systems_cache
        
        dynamic_systems = []
        
        # 从配置文件中获取基础git provider信息
        for system in self.config.get('systems', []):
            git_provider_url = system.get('git_provider_url')
            if not git_provider_url:
                continue
                
            try:
                # 解析git_provider_url获取owner信息
                system_data = self._fetch_system_from_url(system, git_provider_url)
                if system_data:
                    dynamic_systems.append(system_data)
            except Exception as e:
                print(f"获取系统 {system.get('name', 'unknown')} 失败: {e}")
                # 失败时使用静态配置作为降级
                dynamic_systems.append({
                    'id': system.get('id', system.get('name', 'unknown')),
                    'name': system.get('name', 'Unknown System'),
                    'projects': system.get('projects', []),
                    'git_provider': system.get('git_provider'),
                    'git_provider_url': git_provider_url,
                    'error': str(e)
                })
        
        self.dynamic_systems_cache = dynamic_systems
        return dynamic_systems
    
    def _fetch_system_from_url(self, system_config: Dict, git_provider_url: str) -> Optional[Dict]:
        """从git_provider_url获取系统信息"""
        git_provider = system_config.get('git_provider', 'github')
        
        if git_provider == 'github':
            return self._fetch_github_system(system_config, git_provider_url)
        elif git_provider == 'gitlab':
            return self._fetch_gitlab_system(system_config, git_provider_url)
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
