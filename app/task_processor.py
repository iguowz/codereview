# -*- coding: utf-8 -*-
"""
任务处理器 - 负责代码审查任务的具体处理逻辑
"""

import yaml
from typing import List, Dict, Any, Optional
from datetime import datetime
import threading
import time
import asyncio
import sys

from .models import (
    CodeIssue, ReviewReport, UnitTestCase, 
    ScenarioTestCase, ProcessingResult
)
from .utils.git_api import GitAPIClient
from .utils.llm_api import DeepSeekAPI
from .utils.async_llm_api import AsyncTaskProcessor
from .config_manager import config_manager
from .statistics import StatisticsCalculator, format_statistics_for_display
from .task_state import TaskStateManager
from .logger import get_task_logger, info, error, warning, debug


class TaskAbortedException(Exception):
    """任务被中止异常"""
    pass


class TaskProcessor:
    """任务处理器"""
    
    def __init__(self):
        self.git_client = GitAPIClient()
        self.llm_client = DeepSeekAPI()
        self.async_processor = None  # 延迟初始化，需要task_id
        self.stats_calculator = StatisticsCalculator()
        self.use_async = True  # 默认使用异步处理
    
    def _check_task_abort(self, task_id: str) -> None:
        """
        检查任务是否被中止，如果被中止则抛出异常
        
        Args:
            task_id: 任务ID
            
        Raises:
            TaskAbortedException: 如果任务被中止
        """
        try:
            task_dir = config_manager.ensure_task_data_dir()
            task_file = task_dir / f'{task_id}.yaml'
            
            if task_file.exists():
                with open(task_file, 'r', encoding='utf-8') as f:
                    task_data = yaml.safe_load(f) or {}
                
                if task_data.get('status') == 'aborted':
                    debug(task_id, "检测到任务已被中止，停止执行")
                    raise TaskAbortedException(f"任务 {task_id} 已被用户中止")
        except TaskAbortedException:
            raise
        except Exception as e:
            debug(task_id, f"检查任务状态失败: {e}")
            # 检查失败时不阻止任务继续执行
    
    def process_task(self, system_name: str, branch_name: str, task_id: str) -> ProcessingResult:
        """
        处理代码审查任务
        
        Args:
            system_name: 系统名称
            branch_name: 分支名称  
            task_id: 任务ID
            
        Returns:
            ProcessingResult: 处理结果
        """
        # 初始化任务专用日志器
        task_logger = get_task_logger(task_id)
        task_logger.task_start()
        task_logger.task_progress(task_id, f"系统: {system_name}, 分支: {branch_name}")
        
        # 初始化状态管理器
        state_manager = TaskStateManager(task_id)
        
        # 在文件中记录开始处理
        try:
            task_dir = config_manager.ensure_task_data_dir()
            task_file = task_dir / f'{task_id}.yaml'
            if task_file.exists():
                with open(task_file, 'r', encoding='utf-8') as f:
                    task_data = yaml.safe_load(f) or {}
                if 'debug_log' not in task_data:
                    task_data['debug_log'] = []
                task_data['debug_log'].append(f"{datetime.now().isoformat()}: 开始处理任务")
                task_data['updated_at'] = datetime.now().isoformat()
                with open(task_file, 'w', encoding='utf-8') as f:
                    yaml.dump(task_data, f, default_flow_style=False, allow_unicode=True)
        except Exception as e:
            debug(task_id, f"记录调试信息失败: {e}")
        
        # 获取Git diff
        try:
            # 检查任务是否被中止
            self._check_task_abort(task_id)
            
            debug(task_id, f"准备获取Git diff: {system_name}/{branch_name}")
            diff_results = self.git_client.get_diff(system_name, branch_name)
            config_manager.backup_branches_to_yaml(self.git_client.dynamic_branches_cache, source='dynamic')
            
            # Git API调用完成后立即检查是否被中止
            self._check_task_abort(task_id)
            
            debug(task_id, f"获取到 {len(diff_results) if diff_results else 0} 个项目的代码变更")
            
            # 记录Git diff获取结果
            try:
                task_dir = config_manager.ensure_task_data_dir()
                task_file = task_dir / f'{task_id}.yaml'
                if task_file.exists():
                    with open(task_file, 'r', encoding='utf-8') as f:
                        task_data = yaml.safe_load(f) or {}
                    if 'debug_log' not in task_data:
                        task_data['debug_log'] = []
                    task_data['debug_log'].append(f"{datetime.now().isoformat()}: Git diff获取完成，{len(diff_results) if diff_results else 0}个项目")
                    task_data['updated_at'] = datetime.now().isoformat()
                    with open(task_file, 'w', encoding='utf-8') as f:
                        yaml.dump(task_data, f, default_flow_style=False, allow_unicode=True)
            except Exception as e:
                debug(task_id, f"记录Git diff结果失败: {e}")
                
        except Exception as e:
            debug(task_id, f"Git diff获取失败: {e}")
            # 记录Git错误
            try:
                task_dir = config_manager.ensure_task_data_dir()
                task_file = task_dir / f'{task_id}.yaml'
                if task_file.exists():
                    with open(task_file, 'r', encoding='utf-8') as f:
                        task_data = yaml.safe_load(f) or {}
                    if 'debug_log' not in task_data:
                        task_data['debug_log'] = []
                    task_data['debug_log'].append(f"{datetime.now().isoformat()}: Git diff获取失败: {str(e)}")
                    task_data['updated_at'] = datetime.now().isoformat()
                    with open(task_file, 'w', encoding='utf-8') as f:
                        yaml.dump(task_data, f, default_flow_style=False, allow_unicode=True)
            except:
                pass
            raise
        
        # 处理结果
        all_reports = []
        all_unit_cases = []
        all_scenario_cases = []
        
        # 处理每个项目
        debug(task_id, f"准备处理 {len(diff_results)} 个项目")
        
        # 记录开始处理项目
        try:
            task_dir = config_manager.ensure_task_data_dir()
            task_file = task_dir / f'{task_id}.yaml'
            if task_file.exists():
                with open(task_file, 'r', encoding='utf-8') as f:
                    task_data = yaml.safe_load(f) or {}
                if 'debug_log' not in task_data:
                    task_data['debug_log'] = []
                task_data['debug_log'].append(f"{datetime.now().isoformat()}: 开始处理 {len(diff_results)} 个项目")
                task_data['updated_at'] = datetime.now().isoformat()
                with open(task_file, 'w', encoding='utf-8') as f:
                    yaml.dump(task_data, f, default_flow_style=False, allow_unicode=True)
        except Exception as e:
            debug(task_id, f"记录项目处理开始失败: {e}")
        
        for i, project_result in enumerate(diff_results):
            # 检查任务是否被中止
            self._check_task_abort(task_id)
            
            project_name = project_result.get('project_name', 'unknown')
            debug(task_id, f"处理项目 {i+1}: {project_name}")
            
            # 记录项目处理开始
            try:
                task_dir = config_manager.ensure_task_data_dir()
                task_file = task_dir / f'{task_id}.yaml'
                if task_file.exists():
                    with open(task_file, 'r', encoding='utf-8') as f:
                        task_data = yaml.safe_load(f) or {}
                    if 'debug_log' not in task_data:
                        task_data['debug_log'] = []
                    task_data['debug_log'].append(f"{datetime.now().isoformat()}: 开始处理项目 {i+1}: {project_name}")
                    task_data['updated_at'] = datetime.now().isoformat()
                    with open(task_file, 'w', encoding='utf-8') as f:
                        yaml.dump(task_data, f, default_flow_style=False, allow_unicode=True)
            except Exception as e:
                debug(task_id, f"记录项目处理失败: {e}")
            
            # 检查项目是否包含错误信息
            if 'error' in project_result:
                error_msg = project_result['error']
                debug(task_id, f"项目 {project_name} 包含错误，跳过处理: {error_msg}")
                
                # 记录项目错误信息
                try:
                    task_dir = config_manager.ensure_task_data_dir()
                    task_file = task_dir / f'{task_id}.yaml'
                    if task_file.exists():
                        with open(task_file, 'r', encoding='utf-8') as f:
                            task_data = yaml.safe_load(f) or {}
                        if 'debug_log' not in task_data:
                            task_data['debug_log'] = []
                        task_data['debug_log'].append(f"{datetime.now().isoformat()}: 项目错误跳过: {project_name} - {error_msg}")
                        task_data['updated_at'] = datetime.now().isoformat()
                        with open(task_file, 'w', encoding='utf-8') as f:
                            yaml.dump(task_data, f, default_flow_style=False, allow_unicode=True)
                except Exception as debug_e:
                    debug(task_id, f"记录项目错误跳过失败: {debug_e}")
                
                # 生成错误报告但继续处理其他项目
                error_report = ReviewReport(
                    project_name=project_name,
                    filename='N/A',
                    filestatus={},
                    summary='N/A',
                    business_logic='N/A',
                    language_detected='N/A',
                    issues=[CodeIssue(
                        type='系统错误',
                        description=f'项目处理失败: {error_msg}',
                        suggestion='请检查系统配置和网络连接',
                        severity='Critical'
                    )]
                )
                all_reports.append(error_report)
                continue
            
            try:
                debug(task_id, f"准备调用_process_project: {project_name}")
                
                # 转换Git API格式为TaskProcessor期望的格式
                processed_project = self._convert_git_result_to_project(project_result, task_id)
                
                # 记录转换后的文件数量
                file_count = len(processed_project.get('files', []))
                debug(task_id, f"项目 {project_name} 转换后文件数: {file_count}")
                
                # 记录准备调用_process_project
                try:
                    task_dir = config_manager.ensure_task_dir()
                    task_file = task_dir / f'{task_id}.yaml'
                    if task_file.exists():
                        with open(task_file, 'r', encoding='utf-8') as f:
                            task_data = yaml.safe_load(f) or {}
                        if 'debug_log' not in task_data:
                            task_data['debug_log'] = []
                        task_data['debug_log'].append(f"{datetime.now().isoformat()}: 转换后调用_process_project: {project_name}, {file_count}个文件")
                        task_data['updated_at'] = datetime.now().isoformat()
                        with open(task_file, 'w', encoding='utf-8') as f:
                            yaml.dump(task_data, f, default_flow_style=False, allow_unicode=True)
                except Exception as debug_e:
                    debug(task_id, f"记录_process_project调用失败: {debug_e}")
                
                project_reports, project_unit_cases, project_scenario_cases = self._process_project(
                    processed_project, task_id
                )
                
                debug(task_id, f"_process_project完成: {project_name}")
                all_reports.extend(project_reports)
                all_unit_cases.extend(project_unit_cases)
                all_scenario_cases.extend(project_scenario_cases)
                
            except Exception as e:
                debug(task_id, f"项目处理失败: {e}")
                import traceback
                traceback.print_exc()
                
                # 记录项目处理错误
                try:
                    task_dir = config_manager.ensure_task_data_dir()
                    task_file = task_dir / f'{task_id}.yaml'
                    if task_file.exists():
                        with open(task_file, 'r', encoding='utf-8') as f:
                            task_data = yaml.safe_load(f) or {}
                        if 'debug_log' not in task_data:
                            task_data['debug_log'] = []
                        task_data['debug_log'].append(f"{datetime.now().isoformat()}: 项目处理错误: {project_name} - {str(e)}")
                        task_data['updated_at'] = datetime.now().isoformat()
                        with open(task_file, 'w', encoding='utf-8') as f:
                            yaml.dump(task_data, f, default_flow_style=False, allow_unicode=True)
                except Exception as debug_e:
                    debug(task_id, f"记录项目处理错误失败: {debug_e}")
                
                # 检查是否是网络相关的错误，如果是则重新抛出异常使整个任务失败
                error_str = str(e)
                if ('网络连接失败' in error_str or '网络连接超时' in error_str or 
                    '网络连接被重置' in error_str or '分支或仓库不存在' in error_str or 'Git API调用失败' in error_str):
                    # 网络错误应该导致整个任务失败，而不是生成错误报告
                    raise e
                
                # 其他错误生成错误报告但继续处理
                error_report = ReviewReport(
                    project_name=project_name,
                    filename='N/A',
                    filestatus={},
                    summary='N/A',
                    business_logic='N/A',
                    language_detected='N/A',
                    issues=[CodeIssue(
                        type='系统错误',
                        description=f'项目处理失败: {str(e)}',
                        suggestion='请检查系统配置和网络连接',
                        severity='Critical'
                    )]
                )
                all_reports.append(error_report)
        
        debug(task_id, f"任务处理完成，准备返回结果: {task_id}")
        debug(task_id, f"最终统计 - 报告: {len(all_reports)}, 单元测试: {len(all_unit_cases)}, 场景测试: {len(all_scenario_cases)}")
        
        # 检查是否所有项目都失败了
        successful_projects = len([r for r in all_reports if not r.issues or not any(issue.type == '系统错误' for issue in r.issues)])
        error_description = [r.issues[0].description for r in all_reports if r.issues and r.issues[0].type == '系统错误']
        total_projects = len(diff_results)
        
        if successful_projects == 0 and total_projects > 0:
            debug(task_id, f"所有项目都失败了，中止任务")
            raise Exception("所有项目都处理失败，任务中止", ''.join(error_description))
        
        return ProcessingResult(
            reports=all_reports,
            unit_cases=all_unit_cases,
            scenario_cases=all_scenario_cases
        )
    
    def _log_debug(self, task_id: str, message: str):
        """记录调试信息到任务文件"""
        try:
            task_dir = config_manager.ensure_task_data_dir()
            task_file = task_dir / f'{task_id}.yaml'
            if task_file.exists():
                with open(task_file, 'r', encoding='utf-8') as f:
                    task_data = yaml.safe_load(f) or {}
                if 'debug_log' not in task_data:
                    task_data['debug_log'] = []
                task_data['debug_log'].append(f"{datetime.now().isoformat()}: {message}")
                task_data['updated_at'] = datetime.now().isoformat()
                with open(task_file, 'w', encoding='utf-8') as f:
                    yaml.dump(task_data, f, default_flow_style=False, allow_unicode=True)
        except Exception as e:
            debug(task_id, f"记录调试信息失败: {e}")
    
    def _convert_git_result_to_project(self, git_result: Dict[str, Any], task_id: str) -> Dict[str, Any]:
        """
        将Git API返回的结果转换为TaskProcessor期望的格式
        
        Args:
            git_result: Git API返回的项目结果
            task_id: 任务ID
            
        Returns:
            转换后的项目数据
        """
        project_name = git_result.get('project_name', 'unknown')
        debug(task_id, f"转换Git结果: {project_name}")
        
        # 检查是否有错误
        if 'error' in git_result:
            error_msg = git_result['error']
            debug(task_id, f"项目 {project_name} Git API错误: {error_msg}")
            
            # 根据错误类型提供友好提示并直接抛出异常
            if 'SSLError' in error_msg or 'SSL' in error_msg:
                debug(task_id, f"网络连接错误 - 可能需要检查网络连接或使用代理")
                raise Exception(f"网络连接失败: SSL错误。请检查网络连接或配置代理。详细信息: {error_msg}")
            elif 'Max retries exceeded' in error_msg:
                debug(task_id, f"网络超时 - 请检查网络连接")
                raise Exception(f"网络连接超时: 请检查网络连接后重试。详细信息: {error_msg}")
            elif 'Connection reset by peer' in error_msg or 'ConnectionResetError' in error_msg or 'Connection aborted' in error_msg:
                debug(task_id, f"网络连接被重置 - 请检查网络连接")
                raise Exception(f"网络连接被重置: 请检查网络连接或稍后重试。详细信息: {error_msg}")
            elif '404' in error_msg:
                debug(task_id, f"分支或仓库不存在 - 请检查分支名称")
                raise Exception(f"分支或仓库不存在: 请检查分支名称是否正确。详细信息: {error_msg}")
            else:
                raise Exception(f"Git API调用失败: {error_msg}")
        
        # 检查是否有diff_data
        diff_data = git_result.get('diff_data')
        if not diff_data or 'files' not in diff_data:
            debug(task_id, f"项目 {project_name} 无diff数据")
            return {
                'project_name': project_name,
                'files': []
            }
        
        # 转换文件格式
        files = []
        for file_info in diff_data['files']:
            filename = file_info.get('filename', '')
            patch = file_info.get('patch', '')
            filestatus = {
                'status': file_info.get('status', ''),
                'additions': file_info.get('additions', 0),
                'deletions': file_info.get('deletions', 0),
                'changes': file_info.get('changes', 0)
            }
            
            if filename and patch:
                files.append({
                    'filename': filename,
                    'filestatus': filestatus,
                    'diff_content': patch
                })
        
        debug(task_id, f"项目 {project_name} 转换得到 {len(files)} 个文件")
        
        return {
            'project_name': project_name,
            'files': files
        }
    
    def _extract_module_name(self, filename: str) -> str:
        """从文件名提取模块名"""
        # 移除文件扩展名
        import os
        base_name = os.path.splitext(os.path.basename(filename))[0]
        
        # 从路径中提取模块信息
        path_parts = filename.split('/')
        
        # 常见的模块分类
        if 'api' in path_parts:
            if 'models' in path_parts:
                return 'API模型层'
            elif 'services' in path_parts:
                return 'API服务层'
            elif 'controllers' in path_parts or 'routes' in path_parts:
                return 'API控制器'
            elif 'extensions' in path_parts:
                return 'API扩展'
            else:
                return 'API层'
        elif 'models' in path_parts:
            return '数据模型'
        elif 'services' in path_parts:
            return '业务服务'
        elif 'utils' in path_parts or 'helpers' in path_parts:
            return '工具函数'
        elif 'tests' in path_parts:
            return '测试模块'
        elif 'config' in path_parts:
            return '配置模块'
        else:
            return '核心功能'
    
    def _process_project(self, project_result: Dict[str, Any], task_id: str) -> tuple:
        """
        处理单个项目
        
        Args:
            project_result: 项目结果数据
            task_id: 任务ID
            
        Returns:
            tuple: (reports, unit_cases, scenario_cases)
        """
        project_name = project_result.get('project_name', 'unknown')
        debug(task_id, f"_process_project开始: {project_name}")
        
        # 记录进入_process_project
        self._log_debug(task_id, f"进入_process_project: {project_name}")
        
        # 初始化状态管理器
        state_manager = TaskStateManager(task_id)
        
        # 初始化所有文件状态
        for file_data in project_result.get('files', []):
            filename = file_data.get('filename', '')
            if filename:
                state_manager.initialize_file(filename, project_name)
        
        # 选择处理方式：异步或同步
        if self.use_async and len(project_result.get('files', [])) > 1:
            debug(task_id, f"使用异步处理模式，文件数量: {len(project_result.get('files', []))}")
            self._log_debug(task_id, f"使用异步处理模式，文件数量: {len(project_result.get('files', []))}")
            return self._process_project_async(project_result, task_id, state_manager)
        else:
            debug(task_id, f"使用同步处理模式")
            self._log_debug(task_id, f"使用同步处理模式")
            return self._process_project_sync(project_result, task_id, state_manager)
    
    def _process_project_async(self, project_result: Dict[str, Any], task_id: str, state_manager: TaskStateManager) -> tuple:
        """异步处理项目"""
        project_name = project_result.get('project_name', 'unknown')
        
        # 初始化异步处理器（如果还没有）
        if self.async_processor is None:
            self.async_processor = AsyncTaskProcessor(task_id)
        
        try:
            # 准备文件数据
            files_data = []
            for file_data in project_result.get('files', []):
                files_data.append({
                    'filename': file_data.get('filename', ''),
                    'filestatus': file_data.get('filestatus', {}),
                    'diff_content': file_data.get('diff_content', ''),
                    'project_name': project_name
                })
            
            # 运行异步处理
            if sys.platform == 'win32':
                # Windows需要特殊处理
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    result = loop.run_until_complete(
                        self.async_processor.process_files_async(files_data, task_id)
                    )
                finally:
                    loop.close()
            else:
                # Unix/Linux系统
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                
                result = loop.run_until_complete(
                    self.async_processor.process_files_async(files_data, task_id)
                )
            
            # 转换结果格式
            reports = []
            unit_cases = []
            scenario_cases = []
            
            # 处理审查结果
            for review_result in result.get('review_results', []):
                if review_result.get('issues'):
                    issues = []
                    for issue_data in review_result['issues']:
                        issue = CodeIssue(
                            type=issue_data.get('type', ''),
                            description=issue_data.get('description', ''),
                            suggestion=issue_data.get('suggestion', ''),
                            severity=issue_data.get('severity', 'Medium')
                        )
                        issues.append(issue)
                    
                    report = ReviewReport(
                        project_name=review_result['project_name'],
                        filename=review_result['filename'],
                        summary=review_result['summary'],
                        filestatus=review_result['filestatus'],
                        business_logic=review_result['business_logic'],
                        language_detected=review_result['language_detected'],
                        diff_content=review_result['diff_content'],
                        issues=issues
                    )
                    reports.append(report)
            
            # 处理单元测试结果
            for unit_case in result.get('unit_cases', []):
                case = UnitTestCase(
                    project_name=unit_case['project_name'],
                    filename=unit_case['filename'],
                    code=unit_case['code'],
                    description=unit_case['description']
                )
                unit_cases.append(case)
            
            # 处理场景测试结果
            for scenario_case in result.get('scenario_cases', []):
                case = ScenarioTestCase(
                    case_id=scenario_case.get('case_id', ''),
                    title=scenario_case.get('title', ''),
                    preconditions=scenario_case.get('preconditions', ''),
                    steps=scenario_case.get('steps', ''),
                    expected_result=scenario_case.get('expected_result', ''),
                    project_name=scenario_case.get('project_name', ''),
                    filename=scenario_case.get('filename', ''),
                    module=scenario_case.get('module', '')
                )
                scenario_cases.append(case)
            
            # 异步处理完成前检查是否被中止
            self._check_task_abort(task_id)
            
            debug(task_id, f"异步处理完成 - 报告: {len(reports)}, 单元测试: {len(unit_cases)}, 场景测试: {len(scenario_cases)}")
            self._log_debug(task_id, f"异步处理完成 - 报告: {len(reports)}, 单元测试: {len(unit_cases)}, 场景测试: {len(scenario_cases)}")
            
            return reports, unit_cases, scenario_cases
            
        except Exception as e:
            debug(task_id, f"异步处理失败，回退到同步模式: {e}")
            self._log_debug(task_id, f"异步处理失败，回退到同步模式: {str(e)}")
            return self._process_project_sync(project_result, task_id, state_manager)
    
    def _process_project_sync(self, project_result: Dict[str, Any], task_id: str, state_manager: TaskStateManager) -> tuple:
        """同步处理项目（原有逻辑）"""
        project_name = project_result.get('project_name', 'unknown')
        
        # 检查错误
        if 'error' in project_result:
            debug(task_id, f"项目有错误: {project_result['error']}")
            self._log_debug(task_id, f"项目有错误: {project_result['error']}")
            error_report = ReviewReport(
                project_name=project_name,
                filename='N/A',
                filestatus={},
                summary='N/A',
                business_logic='N/A',
                language_detected='N/A',
                issues=[CodeIssue(
                    type='Git API错误',
                    description=project_result['error'],
                    suggestion='请检查Git配置和权限',
                    severity='Critical'
                )]
            )
            return [error_report], [], []
        

        # 检查diff数据
        diff_data = project_result.get('diff_data')
        debug(task_id, f"检查diff数据: {bool(diff_data)}")
        self._log_debug(task_id, f"检查diff数据: {bool(diff_data)}")
        
        if not diff_data or not diff_data.get('files'):
            debug(task_id, f"无代码变更或无files字段")
            self._log_debug(task_id, "无代码变更或无files字段")
            return [], [], []
        
        files_count = len(diff_data['files'])
        debug(task_id, f"发现 {files_count} 个文件变更")
        self._log_debug(task_id, f"发现 {files_count} 个文件变更")
        
        reports = []
        unit_cases = []
        scenario_cases = []
        
        # 处理每个文件
        self._log_debug(task_id, f"开始文件处理循环，共{files_count}个文件")
        
        for i, file_diff in enumerate(diff_data['files'], 1):
            filename = file_diff.get('filename', 'unknown')
            patch = file_diff.get('patch', '')
            
            debug(task_id, f"文件 {i}/{files_count}: {filename}")
            self._log_debug(task_id, f"开始处理文件 {i}/{files_count}: {filename}")
            
            if not patch:
                debug(task_id, f"跳过文件: {filename} (无内容变更)")
                self._log_debug(task_id, f"跳过文件: {filename} (无内容变更)")
                continue
            
            debug(task_id, f"处理文件 {i}/{files_count}: {filename}")
            
            try:
                # 处理单个文件
                debug(task_id, f"准备调用_process_file: {filename}")
                self._log_debug(task_id, f"准备调用_process_file: {filename}")
                
                file_reports, file_unit_cases, file_scenario_cases = self._process_file(
                    project_name, filename, patch, task_id
                )
                
                debug(task_id, f"_process_file完成: {filename}")
                self._log_debug(task_id, f"_process_file完成: {filename} - 问题:{len(file_reports)}, 单元测试:{len(file_unit_cases)}, 场景测试:{len(file_scenario_cases)}")
                
                reports.extend(file_reports)
                unit_cases.extend(file_unit_cases)
                scenario_cases.extend(file_scenario_cases)
                
                debug(task_id, f"文件处理完成 - 问题:{len(file_reports)}, 单元测试:{len(file_unit_cases)}, 场景测试:{len(file_scenario_cases)}")
                
            except Exception as e:
                debug(task_id, f"文件处理失败: {filename} - {str(e)}")
                self._log_debug(task_id, f"文件处理失败: {filename} - {str(e)}")
                import traceback
                traceback.print_exc()
                # 创建错误报告
                error_report = ReviewReport(
                    project_name=project_name,
                    filename=filename,
                    filestatus={},
                    summary='N/A',
                    business_logic='N/A',
                    language_detected='N/A',
                    issues=[CodeIssue(
                        type='文件处理错误',
                        description=f'文件处理异常: {str(e)}',
                        suggestion='请检查文件内容或稍后重试',
                        severity='Warning'
                    )]
                )
                reports.append(error_report)
                continue
        
        debug(task_id, f"_process_project即将返回: {project_name}")
        self._log_debug(task_id, f"_process_project完成，准备返回: {project_name} - 总计报告:{len(reports)}, 单元测试:{len(unit_cases)}, 场景测试:{len(scenario_cases)}")
        return reports, unit_cases, scenario_cases
    
    def _process_file(self, project_name: str, filename: str, patch: str, task_id: str) -> tuple:
        """
        处理单个文件
        
        Args:
            project_name: 项目名称
            filename: 文件名
            patch: 补丁内容
            task_id: 任务ID
            
        Returns:
            tuple: (reports, unit_cases, scenario_cases)
        """
        debug(task_id, f"进入_process_file: {filename}")
        self._log_debug(task_id, f"进入_process_file: {filename}")
        
        reports = []
        unit_cases = []
        scenario_cases = []
        
        # 设置文件处理超时（8分钟，给API更多时间）
        timeout_occurred = threading.Event()
        start_time = time.time()
        
        def timeout_handler():
            time.sleep(480)  # 8分钟
            timeout_occurred.set()
        
        timeout_thread = threading.Thread(target=timeout_handler, daemon=True)
        timeout_thread.start()
        
        try:
            # 代码审查
            try:
                if timeout_occurred.is_set():
                    raise TimeoutError(f"文件处理超时: {filename}")
                    
                debug(task_id, f"准备调用LLM代码审查: {filename}")
                self._log_debug(task_id, f"准备调用LLM代码审查: {filename}")
                
                review_result = self.llm_client.code_review(filename, patch)
                
                debug(task_id, f"LLM代码审查完成: {filename}")
                self._log_debug(task_id, f"LLM代码审查完成: {filename}")
                
                if review_result.get('issues'):
                    issues = [
                        CodeIssue(**issue) for issue in review_result['issues']
                    ]
                    report = ReviewReport(
                        project_name=project_name,
                        filename=filename,
                        filestatus={},
                        summary='N/A',
                        business_logic='N/A',
                        language_detected='N/A',
                        issues=issues,
                        diff_content=patch  # 添加diff内容
                    )
                    reports.append(report)
                    debug(task_id, f"发现 {len(issues)} 个问题")
                    self._log_debug(task_id, f"代码审查发现 {len(issues)} 个问题: {filename}")
                else:
                    debug(task_id, f"未发现问题")
                    self._log_debug(task_id, f"代码审查未发现问题: {filename}")
            
            except TimeoutError as e:
                warning(f"代码审查超时: {e}")
                error_report = ReviewReport(
                    project_name=project_name,
                    filename=filename,
                    filestatus={},
                    summary='N/A',
                    business_logic='N/A',
                    language_detected='N/A',
                    issues=[CodeIssue(
                        type='超时错误',
                        description=f'代码审查超时: {str(e)}',
                        suggestion='文件可能过大或复杂，请考虑拆分文件',
                        severity='Warning'
                    )]
                )
                reports.append(error_report)
                return reports, unit_cases, scenario_cases  # 超时时直接返回
                
            except Exception as e:
                error(f"代码审查失败: {e}")
                error_report = ReviewReport(
                    project_name=project_name,
                    filename=filename,
                    filestatus={},
                    summary='N/A',
                    business_logic='N/A',
                    language_detected='N/A',
                    issues=[CodeIssue(
                        type='系统错误',
                        description=f'代码审查失败: {str(e)}',
                        suggestion='请检查网络连接或稍后重试',
                        severity='Info'
                    )]
                )
                reports.append(error_report)
            
            # 并行生成单元测试和场景测试
            debug(task_id, f"开始并行调用单元测试和场景测试生成: {filename}")
            self._log_debug(task_id, f"开始并行调用单元测试和场景测试生成: {filename}")
            
            import concurrent.futures
            
            def generate_unit_tests():
                try:
                    if timeout_occurred.is_set():
                        raise TimeoutError(f"文件处理超时: {filename}")
                    
                    debug(task_id, f"并行调用单元测试生成: {filename}")
                    unit_test_result = self.llm_client.generate_unit_tests(filename, patch)
                    
                    if unit_test_result.get('unit_test_code'):
                        return UnitTestCase(
                            project_name=project_name,
                            filename=filename,
                            code=unit_test_result['unit_test_code'],
                            description=unit_test_result.get('test_description', '')
                        )
                    return None
                    
                except Exception as e:
                    warning(f"单元测试生成失败: {e}")
                    return UnitTestCase(
                        project_name=project_name,
                        filename=filename,
                        code=f'# 单元测试生成失败: {str(e)}\n# 请稍后重试或手动编写单元测试',
                        description=f'生成失败: {str(e)}'
                    )
            
            def generate_scenario_tests():
                try:
                    if timeout_occurred.is_set():
                        raise TimeoutError(f"文件处理超时: {filename}")
                    
                    debug(task_id, f"并行调用场景测试生成: {filename}")
                    scenario_test_result = self.llm_client.generate_scenario_tests(filename, patch)
                    
                    generated_cases = []
                    if scenario_test_result.get('scenario_cases'):
                        for case in scenario_test_result['scenario_cases']:
                            # 从文件名推断模块名
                            module_name = self._extract_module_name(filename)
                            
                            scenario_case = ScenarioTestCase(
                                case_id=case.get('case_id', ''),
                                title=case.get('title', ''),
                                preconditions=case.get('preconditions', ''),
                                steps=case.get('steps', ''),
                                expected_result=case.get('expected_result', ''),
                                project_name=project_name,
                                filename=filename,
                                module=case.get('module', module_name)  # 优先使用LLM返回的模块名
                            )
                            generated_cases.append(scenario_case)
                    return generated_cases
                    
                except Exception as e:
                    warning(f"场景测试生成失败: {e}")
                    module_name = self._extract_module_name(filename)
                    return [ScenarioTestCase(
                        case_id=f'ERROR_{filename}',
                        title=f'场景测试生成失败: {filename}',
                        preconditions='系统异常',
                        steps=f'生成失败原因: {str(e)}',
                        expected_result='请稍后重试或手动编写场景测试',
                        project_name=project_name,
                        filename=filename,
                        module=module_name
                    )]
            
            # 使用线程池并行执行
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                # 提交两个任务
                unit_future = executor.submit(generate_unit_tests)
                scenario_future = executor.submit(generate_scenario_tests)
                
                # 等待结果
                try:
                    unit_result = unit_future.result(timeout=300)  # 5分钟超时
                    if unit_result:
                        unit_cases.append(unit_result)
                        debug(task_id, f"单元测试生成完成: {filename}")
                        self._log_debug(task_id, f"单元测试生成完成: {filename}")
                except Exception as e:
                    warning(f"单元测试生成异常: {e}")
                    self._log_debug(task_id, f"单元测试生成异常: {filename} - {str(e)}")
                
                try:
                    scenario_results = scenario_future.result(timeout=300)  # 5分钟超时
                    if scenario_results:
                        scenario_cases.extend(scenario_results)
                        debug(task_id, f"场景测试生成完成: {filename} - {len(scenario_results)}个用例")
                        self._log_debug(task_id, f"场景测试生成完成: {filename} - {len(scenario_results)}个用例")
                except Exception as e:
                    warning(f"场景测试生成异常: {e}")
                    self._log_debug(task_id, f"场景测试生成异常: {filename} - {str(e)}")
            
            debug(task_id, f"并行调用完成: {filename}")
            self._log_debug(task_id, f"并行调用完成: {filename}")
        
        finally:
            # 检查是否超时
            if timeout_occurred.is_set():
                warning(f"文件处理超时: {filename}")
                error_report = ReviewReport(
                    project_name=project_name,
                    filename=filename,
                    filestatus={},
                    summary='N/A',
                    business_logic='N/A',
                    language_detected='N/A',
                    issues=[CodeIssue(
                        type='超时错误',
                        description=f'文件处理超时: {filename}',
                        suggestion='文件可能过大或复杂，请考虑拆分文件',
                        severity='Warning'
                    )]
                )
                reports.append(error_report)
        
        return reports, unit_cases, scenario_cases
    
    def convert_result_to_dict(self, result: ProcessingResult) -> Dict[str, Any]:
        """将ProcessingResult转换为字典格式，包含统计信息"""
        result_dict = {
            'review_results': [
                {
                    'project_name': report.project_name,
                    'filename': report.filename,
                    'summary': report.summary,
                    'filestatus': report.filestatus,
                    'business_logic': report.business_logic,
                    'language_detected': report.language_detected,
                    'diff_content': report.diff_content,
                    'issues': [
                        {
                            'type': issue.type,
                            'description': issue.description,
                            'severity': issue.severity,
                            'suggestion': issue.suggestion
                        } for issue in report.issues
                    ]
                } for report in result.reports
            ],
            'unit_cases': [
                {
                    'project_name': case.project_name,
                    'filename': case.filename,
                    'unit_test_code': case.code,
                    'test_description': case.description
                } for case in result.unit_cases
            ],
            'scenario_cases': [
                {
                    'case_id': case.case_id,
                    'title': case.title,
                    'preconditions': case.preconditions,
                    'steps': case.steps,
                    'expected_result': case.expected_result,
                    'project_name': case.project_name,
                    'filename': case.filename,
                    'module': case.module
                } for case in result.scenario_cases
            ]
        }
        
        # 计算统计信息
        statistics = self.stats_calculator.calculate_overall_statistics(result_dict)
        result_dict['statistics'] = format_statistics_for_display(statistics)
        
        # 保持向后兼容性，同时添加report字段
        result_dict['report'] = result_dict['review_results']
        
        return result_dict


class TaskStatusManager:
    """任务状态管理器"""
    
    @staticmethod
    def update_task_status(task_id: str, status: str, result: Optional[Dict] = None):
        """更新任务状态"""
        try:
            # 确保目录存在
            task_dir = config_manager.ensure_task_data_dir()
            task_file = task_dir / f'{task_id}.yaml'
            
            # 读取现有数据
            existing_data = {}
            if task_file.exists():
                with open(task_file, 'r', encoding='utf-8') as f:
                    existing_data = yaml.safe_load(f) or {}
            
            # 更新任务数据
            task_data = {
                'id': task_id,
                'status': status,
                'updated_at': datetime.now().isoformat()
            }
            
            # 保留原有数据
            task_data.update(existing_data)
            
            # 更新状态和时间
            task_data['status'] = status
            task_data['updated_at'] = datetime.now().isoformat()
            
            # 添加调试信息
            if 'debug_log' not in task_data:
                task_data['debug_log'] = []
            task_data['debug_log'].append(f"{datetime.now().isoformat()}: 状态更新为 {status}")
            
            # 如果有结果，更新结果
            if result:
                task_data['result'] = result
                task_data['debug_log'].append(f"{datetime.now().isoformat()}: 结果数据已设置 (大小: {len(str(result))} 字符)")
            
            # 写入更新后的数据
            with open(task_file, 'w', encoding='utf-8') as f:
                yaml.dump(task_data, f, default_flow_style=False, allow_unicode=True)
            
            info(f"任务状态已更新: {task_id} -> {status}")
            
        except Exception as e:
            error(f"更新任务状态失败: {e}")
            # 尝试写入错误信息到文件
            try:
                task_dir = config_manager.ensure_task_data_dir()
                task_file = task_dir / f'{task_id}.yaml'
                if task_file.exists():
                    with open(task_file, 'r', encoding='utf-8') as f:
                        existing_data = yaml.safe_load(f) or {}
                    if 'debug_log' not in existing_data:
                        existing_data['debug_log'] = []
                    existing_data['debug_log'].append(f"{datetime.now().isoformat()}: 状态更新失败: {str(e)}")
                    with open(task_file, 'w', encoding='utf-8') as f:
                        yaml.dump(existing_data, f, default_flow_style=False, allow_unicode=True)
            except:
                pass

