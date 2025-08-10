"""
统计模块：用于计算和分析代码审查、单元测试、场景测试的统计信息
"""
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from collections import Counter, defaultdict
import re
from datetime import datetime

@dataclass
class StatisticsData:
    """统计数据基类"""
    total_count: int = 0
    category_counts: Dict[str, int] = None
    severity_counts: Dict[str, int] = None
    
    def __post_init__(self):
        if self.category_counts is None:
            self.category_counts = {}
        if self.severity_counts is None:
            self.severity_counts = {}

@dataclass
class ReviewStatistics(StatisticsData):
    """代码审查统计"""
    critical_issues: int = 0
    high_issues: int = 0
    medium_issues: int = 0
    low_issues: int = 0
    languages_detected: List[str] = None
    most_common_issues: List[Tuple[str, int]] = None
    files_reviewed: int = 0
    lines_reviewed: int = 0
    
    def __post_init__(self):
        super().__post_init__()
        if self.languages_detected is None:
            self.languages_detected = []
        if self.most_common_issues is None:
            self.most_common_issues = []

@dataclass
class TestStatistics(StatisticsData):
    """测试统计基类"""
    frameworks_used: List[str] = None
    test_methods_count: int = 0
    complexity_levels: Dict[str, int] = None
    
    def __post_init__(self):
        super().__post_init__()
        if self.frameworks_used is None:
            self.frameworks_used = []
        if self.complexity_levels is None:
            self.complexity_levels = {}

@dataclass
class UnitTestStatistics(TestStatistics):
    """单元测试统计"""
    assertion_count: int = 0
    mock_usage_count: int = 0
    coverage_estimate: float = 0.0

@dataclass
class ScenarioTestStatistics(TestStatistics):
    """场景测试统计"""
    modules_covered: List[str] = None
    business_scenarios: int = 0
    integration_tests: int = 0
    
    def __post_init__(self):
        super().__post_init__()
        if self.modules_covered is None:
            self.modules_covered = []

class StatisticsCalculator:
    """统计计算器"""
    
    def __init__(self):
        self.severity_order = ['Critical', 'High', 'Medium', 'Low']
        self.priority_order = ['High', 'Medium', 'Low']
        self.language_extensions = {
            '.py': 'Python',
            '.js': 'JavaScript',
            '.ts': 'TypeScript', 
            '.jsx': 'React JSX',
            '.tsx': 'React TSX',
            '.java': 'Java',
            '.go': 'Go',
            '.php': 'PHP',
            '.rb': 'Ruby',
            '.cpp': 'C++',
            '.c': 'C',
            '.cs': 'C#',
            '.swift': 'Swift',
            '.kt': 'Kotlin',
            '.rs': 'Rust',
            '.scala': 'Scala',
            '.sh': 'Shell',
            '.sql': 'SQL',
            '.html': 'HTML',
            '.css': 'CSS',
            '.scss': 'SCSS',
            '.less': 'LESS',
            '.vue': 'Vue',
            '.yaml': 'YAML',
            '.yml': 'YAML',
            '.json': 'JSON',
            '.xml': 'XML',
            '.md': 'Markdown'
        }
    
    def _detect_language_from_filename(self, filename: str) -> str:
        """根据文件名检测编程语言"""
        import os
        _, ext = os.path.splitext(filename.lower())
        return self.language_extensions.get(ext, 'Unknown')
    
    def calculate_review_statistics(self, result_data: Dict[str, Any]) -> ReviewStatistics:
        """计算代码审查统计信息"""
        stats = ReviewStatistics()
        
        if not result_data or 'review_results' not in result_data:
            return stats
        
        review_results = result_data['review_results']
        all_issues = []
        languages = set()
        files_count = 0
        
        # 收集所有问题和语言信息
        for file_result in review_results:
            if isinstance(file_result, dict) and 'issues' in file_result:
                files_count += 1
                issues = file_result['issues']
                all_issues.extend(issues)
                
                # 从文件名检测编程语言
                filename = file_result.get('filename', '')
                if filename:
                    detected_language = self._detect_language_from_filename(filename)
                    if detected_language != 'Unknown':
                        languages.add(detected_language)
        
        stats.files_reviewed = files_count
        stats.total_count = len(all_issues)
        stats.languages_detected = list(languages)
        
        # 统计严重程度
        severity_counter = Counter()
        issue_type_counter = Counter()
        
        for issue in all_issues:
            if isinstance(issue, dict):
                severity = issue.get('severity', 'Unknown')
                issue_type = issue.get('type', 'Unknown')
                
                severity_counter[severity] += 1
                issue_type_counter[issue_type] += 1
                
                # 按严重程度分类计数
                if severity == 'Critical':
                    stats.critical_issues += 1
                elif severity == 'High':
                    stats.high_issues += 1
                elif severity == 'Medium':
                    stats.medium_issues += 1
                elif severity == 'Low':
                    stats.low_issues += 1
        
        stats.severity_counts = dict(severity_counter)
        stats.category_counts = dict(issue_type_counter)
        # 将tuple列表转换为字典列表，避免YAML序列化问题
        stats.most_common_issues = [
            {"type": item[0], "count": item[1]} 
            for item in issue_type_counter.most_common(5)
        ]
        
        return stats
    
    def calculate_unit_test_statistics(self, result_data: Dict[str, Any]) -> UnitTestStatistics:
        """计算单元测试统计信息"""
        stats = UnitTestStatistics()
        
        if not result_data or 'unit_cases' not in result_data:
            return stats
        
        unit_cases = result_data['unit_cases']
        stats.total_count = len(unit_cases)
        
        frameworks = set()
        total_assertions = 0
        total_mocks = 0
        test_methods = 0
        
        for case in unit_cases:
            if isinstance(case, dict):
                # 检测测试框架
                framework = case.get('test_framework', 'Unknown')
                if framework != 'Unknown':
                    frameworks.add(framework)
                
                # 分析测试代码
                test_code = case.get('code', '')
                if test_code:
                    # 统计断言数量（简单正则匹配）
                    assertions = len(re.findall(r'\bassert\w*\(|\bassertThat\(|\bexpected?\(', test_code, re.IGNORECASE))
                    total_assertions += assertions
                    
                    # 统计Mock使用
                    mocks = len(re.findall(r'\bmock\w*\(|\bMock\w*\(|\b@mock\b', test_code, re.IGNORECASE))
                    total_mocks += mocks
                    
                    # 统计测试方法数量
                    methods = len(re.findall(r'\bdef test_|\btest\w*\(|\b@Test\b', test_code, re.IGNORECASE))
                    test_methods += methods
        
        stats.frameworks_used = list(frameworks)
        stats.assertion_count = total_assertions
        stats.mock_usage_count = total_mocks
        stats.test_methods_count = test_methods
        
        # 估算覆盖率（基于测试方法数量的简单估算）
        if stats.total_count > 0:
            stats.coverage_estimate = min(100.0, (test_methods / stats.total_count) * 80)
        
        return stats
    
    def calculate_scenario_test_statistics(self, result_data: Dict[str, Any]) -> ScenarioTestStatistics:
        """计算场景测试统计信息"""
        stats = ScenarioTestStatistics()
        
        if not result_data or 'scenario_cases' not in result_data:
            return stats
        
        scenario_cases = result_data['scenario_cases']
        stats.total_count = len(scenario_cases)
        
        modules = set()
        priority_counter = Counter()
        business_scenarios = 0
        integration_tests = 0
        
        for case in scenario_cases:
            if isinstance(case, dict):
                # 收集模块信息
                module = case.get('module', 'Unknown')
                if module != 'Unknown':
                    modules.add(module)
                
                # 统计优先级
                priority = case.get('priority', 'Medium')
                priority_counter[priority] += 1
                
                # 分析场景类型
                title = case.get('title', '').lower()
                steps_raw = case.get('steps', '')
                # 处理steps可能是列表或字符串的情况
                if isinstance(steps_raw, list):
                    steps = ' '.join(str(step) for step in steps_raw).lower()
                else:
                    steps = str(steps_raw).lower()
                
                # 简单的业务场景检测
                if any(keyword in title or keyword in steps for keyword in 
                       ['用户', '业务', '流程', '操作', '交互', '场景']):
                    business_scenarios += 1
                
                # 简单的集成测试检测
                if any(keyword in title or keyword in steps for keyword in 
                       ['集成', '接口', 'api', '服务', '系统', '数据库']):
                    integration_tests += 1
        
        stats.modules_covered = list(modules)
        stats.severity_counts = dict(priority_counter)
        stats.business_scenarios = business_scenarios
        stats.integration_tests = integration_tests
        
        return stats
    
    def calculate_overall_statistics(self, result_data: Dict[str, Any]) -> Dict[str, Any]:
        """计算总体统计信息"""
        review_stats = self.calculate_review_statistics(result_data)
        unit_stats = self.calculate_unit_test_statistics(result_data)
        scenario_stats = self.calculate_scenario_test_statistics(result_data)
        
        # 计算总体质量得分
        quality_score = self._calculate_quality_score(review_stats, unit_stats, scenario_stats)
        
        # 计算完成度
        completion_rate = self._calculate_completion_rate(result_data)
        
        return {
            'review_statistics': review_stats,
            'unit_test_statistics': unit_stats,
            'scenario_test_statistics': scenario_stats,
            'quality_score': quality_score,
            'completion_rate': completion_rate,
            'summary': {
                'total_files_reviewed': review_stats.files_reviewed,
                'total_issues_found': review_stats.total_count,
                'total_unit_tests': unit_stats.total_count,
                'total_scenario_tests': scenario_stats.total_count,
                'languages_covered': len(review_stats.languages_detected),
                'languages_list': review_stats.languages_detected,
                'modules_covered': len(scenario_stats.modules_covered),
            }
        }
    
    def _calculate_quality_score(self, review_stats: ReviewStatistics, 
                                unit_stats: UnitTestStatistics, 
                                scenario_stats: ScenarioTestStatistics) -> float:
        """计算代码质量得分 (0-100)"""
        score = 100.0
        
        # 根据问题严重程度扣分
        score -= review_stats.critical_issues * 15
        score -= review_stats.high_issues * 8
        score -= review_stats.medium_issues * 3
        score -= review_stats.low_issues * 1
        
        # 根据测试覆盖度加分
        if unit_stats.total_count > 0:
            score += min(10, unit_stats.total_count * 2)
        if scenario_stats.total_count > 0:
            score += min(10, scenario_stats.total_count * 1.5)
        
        return max(0.0, min(100.0, score))
    
    def _calculate_completion_rate(self, result_data: Dict[str, Any]) -> float:
        """计算任务完成率"""
        expected_sections = ['review_results', 'unit_cases', 'scenario_cases']
        completed_sections = sum(1 for section in expected_sections 
                               if section in result_data and result_data[section])
        
        return (completed_sections / len(expected_sections)) * 100.0

def format_statistics_for_display(stats_data: Dict[str, Any]) -> Dict[str, Any]:
    """格式化统计数据用于前端显示"""
    def dataclass_to_dict(obj):
        """将dataclass转换为字典"""
        if hasattr(obj, '__dict__'):
            result = {}
            for key, value in obj.__dict__.items():
                if isinstance(value, list):
                    result[key] = value
                elif isinstance(value, dict):
                    result[key] = value
                else:
                    result[key] = value
            return result
        return obj
    
    formatted = {}
    
    for key, value in stats_data.items():
        if hasattr(value, '__dict__'):
            formatted[key] = dataclass_to_dict(value)
        else:
            formatted[key] = value
    
    return formatted

# 示例使用
if __name__ == "__main__":
    calculator = StatisticsCalculator()
    
    # 示例数据
    sample_data = {
        'review_results': [
            {
                'issues': [
                    {'type': '安全漏洞', 'severity': 'Critical'},
                    {'type': '性能问题', 'severity': 'High'},
                ],
                'language_detected': 'Python'
            }
        ],
        'unit_cases': [
            {'code': 'def test_example(): assert True', 'test_framework': 'pytest'}
        ],
        'scenario_cases': [
            {'module': 'API层', 'priority': 'High', 'title': '用户登录场景'}
        ]
    }
    
    stats = calculator.calculate_overall_statistics(sample_data)
    formatted_stats = format_statistics_for_display(stats)
    
    # print("统计结果示例：")
    # import json
    # print(json.dumps(formatted_stats, indent=2, ensure_ascii=False))
