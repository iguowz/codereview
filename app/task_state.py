"""
任务状态跟踪模块 - 记录任务中每个文件的处理状态
"""
import yaml
import os
from typing import Dict, List, Any, Optional
from datetime import datetime
from dataclasses import dataclass, asdict
from .config_manager import config_manager
from .logger import info, error, warning, debug

@dataclass
class FileProcessState:
    """文件处理状态"""
    filename: str
    project_name: str
    review_status: str = 'pending'  # pending, completed, failed
    unit_test_status: str = 'pending'
    scenario_test_status: str = 'pending'
    review_result: Optional[Dict[str, Any]] = None
    unit_test_result: Optional[Dict[str, Any]] = None
    scenario_test_result: Optional[List[Dict[str, Any]]] = None
    last_updated: Optional[str] = None
    error_message: Optional[str] = None

class TaskStateManager:
    """任务状态管理器"""
    
    def __init__(self, task_id: str):
        self.task_id = task_id
        self.task_dir = config_manager.ensure_task_data_dir()
        self.state_file = self.task_dir / f'{task_id}_state.yaml'
        self.file_states: Dict[str, FileProcessState] = {}
        self._load_state()
    
    def _load_state(self):
        """加载任务状态"""
        try:
            if self.state_file.exists():
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f) or {}
                
                files_data = data.get('files', {})
                for filename, file_data in files_data.items():
                    self.file_states[filename] = FileProcessState(
                        filename=file_data['filename'],
                        project_name=file_data['project_name'],
                        review_status=file_data.get('review_status', 'pending'),
                        unit_test_status=file_data.get('unit_test_status', 'pending'),
                        scenario_test_status=file_data.get('scenario_test_status', 'pending'),
                        review_result=file_data.get('review_result'),
                        unit_test_result=file_data.get('unit_test_result'),
                        scenario_test_result=file_data.get('scenario_test_result'),
                        last_updated=file_data.get('last_updated'),
                        error_message=file_data.get('error_message')
                    )
                    
                debug(self.task_id, f"加载了 {len(self.file_states)} 个文件的状态")
            
        except Exception as e:
            warning(f"TaskState加载状态失败: {e}")
            self.file_states = {}
    
    def _save_state(self):
        """保存任务状态"""
        try:
            state_data = {
                'task_id': self.task_id,
                'updated_at': datetime.now().isoformat(),
                'files': {}
            }
            
            for filename, file_state in self.file_states.items():
                state_data['files'][filename] = asdict(file_state)
            
            with open(self.state_file, 'w', encoding='utf-8') as f:
                yaml.dump(state_data, f, default_flow_style=False, allow_unicode=True)
                
        except Exception as e:
            warning(f"TaskState保存状态失败: {e}")
    
    def initialize_file(self, filename: str, project_name: str):
        """初始化文件状态"""
        if filename not in self.file_states:
            self.file_states[filename] = FileProcessState(
                filename=filename,
                project_name=project_name,
                last_updated=datetime.now().isoformat()
            )
            self._save_state()
            debug(self.task_id, f"初始化文件状态: {filename}")
    
    def update_review_status(self, filename: str, status: str, result: Optional[Dict[str, Any]] = None, error: Optional[str] = None):
        """更新代码审查状态"""
        if filename in self.file_states:
            file_state = self.file_states[filename]
            file_state.review_status = status
            file_state.last_updated = datetime.now().isoformat()
            
            if result:
                file_state.review_result = result
            if error:
                file_state.error_message = error
                
            self._save_state()
            debug(self.task_id, f"更新审查状态: {filename} -> {status}")
    
    def update_unit_test_status(self, filename: str, status: str, result: Optional[Dict[str, Any]] = None, error: Optional[str] = None):
        """更新单元测试状态"""
        if filename in self.file_states:
            file_state = self.file_states[filename]
            file_state.unit_test_status = status
            file_state.last_updated = datetime.now().isoformat()
            
            if result:
                file_state.unit_test_result = result
            if error:
                file_state.error_message = error
                
            self._save_state()
            debug(self.task_id, f"更新单元测试状态: {filename} -> {status}")
    
    def update_scenario_test_status(self, filename: str, status: str, result: Optional[List[Dict[str, Any]]] = None, error: Optional[str] = None):
        """更新场景测试状态"""
        if filename in self.file_states:
            file_state = self.file_states[filename]
            file_state.scenario_test_status = status
            file_state.last_updated = datetime.now().isoformat()
            
            if result:
                file_state.scenario_test_result = result
            if error:
                file_state.error_message = error
                
            self._save_state()
            debug(self.task_id, f"更新场景测试状态: {filename} -> {status}")
    
    def is_file_review_completed(self, filename: str) -> bool:
        """检查文件的代码审查是否已完成"""
        return (filename in self.file_states and 
                self.file_states[filename].review_status == 'completed')
    
    def is_file_unit_test_completed(self, filename: str) -> bool:
        """检查文件的单元测试是否已完成"""
        return (filename in self.file_states and 
                self.file_states[filename].unit_test_status == 'completed')
    
    def is_file_scenario_test_completed(self, filename: str) -> bool:
        """检查文件的场景测试是否已完成"""
        return (filename in self.file_states and 
                self.file_states[filename].scenario_test_status == 'completed')
    
    def get_file_review_result(self, filename: str) -> Optional[Dict[str, Any]]:
        """获取文件的审查结果"""
        if filename in self.file_states:
            return self.file_states[filename].review_result
        return None
    
    def get_file_unit_test_result(self, filename: str) -> Optional[Dict[str, Any]]:
        """获取文件的单元测试结果"""
        if filename in self.file_states:
            return self.file_states[filename].unit_test_result
        return None
    
    def get_file_scenario_test_result(self, filename: str) -> Optional[List[Dict[str, Any]]]:
        """获取文件的场景测试结果"""
        if filename in self.file_states:
            return self.file_states[filename].scenario_test_result
        return None
    
    def get_files_to_process(self, file_list: List[str]) -> Dict[str, List[str]]:
        """获取需要处理的文件列表"""
        result = {
            'review_files': [],
            'unit_test_files': [],
            'scenario_test_files': []
        }
        
        for filename in file_list:
            if not self.is_file_review_completed(filename):
                result['review_files'].append(filename)
            
            if not self.is_file_unit_test_completed(filename):
                result['unit_test_files'].append(filename)
            
            if not self.is_file_scenario_test_completed(filename):
                result['scenario_test_files'].append(filename)
        
        return result
    
    def get_completed_results(self) -> Dict[str, Any]:
        """获取所有已完成的结果"""
        review_results = []
        unit_cases = []
        scenario_cases = []
        
        for filename, file_state in self.file_states.items():
            # 收集审查结果
            if file_state.review_status == 'completed' and file_state.review_result:
                review_results.append({
                    'project_name': file_state.project_name,
                    'filename': filename,
                    'issues': file_state.review_result.get('issues', [])
                })
            
            # 收集单元测试结果
            if file_state.unit_test_status == 'completed' and file_state.unit_test_result:
                unit_cases.append({
                    'project_name': file_state.project_name,
                    'filename': filename,
                    'code': file_state.unit_test_result.get('unit_test_code', ''),
                    'description': file_state.unit_test_result.get('test_description', '')
                })
            
            # 收集场景测试结果
            if file_state.scenario_test_status == 'completed' and file_state.scenario_test_result:
                for case in file_state.scenario_test_result:
                    case_data = case.copy()
                    case_data['project_name'] = file_state.project_name
                    case_data['filename'] = filename
                    scenario_cases.append(case_data)
        
        return {
            'review_results': review_results,
            'unit_cases': unit_cases,
            'scenario_cases': scenario_cases
        }
    
    def get_progress_summary(self) -> Dict[str, Any]:
        """获取进度摘要"""
        total_files = len(self.file_states)
        if total_files == 0:
            return {
                'total_files': 0,
                'review_completed': 0,
                'unit_test_completed': 0,
                'scenario_test_completed': 0,
                'overall_progress': 0.0
            }
        
        review_completed = sum(1 for state in self.file_states.values() 
                              if state.review_status == 'completed')
        unit_test_completed = sum(1 for state in self.file_states.values() 
                                 if state.unit_test_status == 'completed')
        scenario_test_completed = sum(1 for state in self.file_states.values() 
                                    if state.scenario_test_status == 'completed')
        
        total_tasks = total_files * 3  # 每个文件3个任务
        completed_tasks = review_completed + unit_test_completed + scenario_test_completed
        overall_progress = (completed_tasks / total_tasks) * 100.0 if total_tasks > 0 else 0.0
        
        return {
            'total_files': total_files,
            'review_completed': review_completed,
            'unit_test_completed': unit_test_completed,
            'scenario_test_completed': scenario_test_completed,
            'overall_progress': overall_progress
        }
    
    def cleanup_state_file(self):
        """清理状态文件"""
        try:
            if self.state_file.exists():
                os.remove(self.state_file)
                info(f"清理状态文件: {self.state_file}")
        except Exception as e:
            warning(f"TaskState清理状态文件失败: {e}")

