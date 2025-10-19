# -*- coding: utf-8 -*-
"""
数据模型定义
"""

from dataclasses import dataclass
from typing import List, Dict, Any, Optional


@dataclass
class TaskInfo:
    """任务信息"""
    id: str
    system_name: str
    branch_name: str
    status: str
    created_at: str
    updated_at: str
    result: Optional[Dict[str, Any]] = None


@dataclass
class CodeIssue:
    """代码问题"""
    type: str
    description: str
    suggestion: str
    severity: str
    line_hint: Optional[str] = None
    language_specific: Optional[str] = None


@dataclass
class ReviewReport:
    """审查报告"""
    project_name: str
    filename: str
    filestatus: Dict[str, Any]
    summary: str
    business_logic: str
    language_detected: str
    issues: List[CodeIssue]
    diff_content: Optional[str] = None


@dataclass
class UnitTestCase:
    """单元测试用例"""
    project_name: str
    filename: str
    code: str
    description: str


@dataclass
class ScenarioTestCase:
    """场景测试用例"""
    case_id: str
    title: str
    preconditions: str
    steps: str
    expected_result: str
    project_name: str
    filename: str
    module: Optional[str] = None  # 添加模块字段用于分组


@dataclass
class ProcessingResult:
    """处理结果"""
    reports: List[ReviewReport]
    unit_cases: List[UnitTestCase]
    scenario_cases: List[ScenarioTestCase]


@dataclass
class ProjectResult:
    """项目结果"""
    project_name: str
    diff_data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
