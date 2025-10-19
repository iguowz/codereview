"""
异步LLM API客户端 - 使用协程提升并发性能
"""
import aiohttp
import asyncio
import json
import time
from typing import Dict, Any, Optional, List
from ..config_manager import config_manager
from ..logger import info, error, warning, debug
from ..task_state import TaskStateManager

# 需要在这里定义TaskAbortedException或者从task_processor导入
# 但为了避免循环导入，我们在这里直接定义一个
class TaskAbortedException(Exception):
    """任务被中止异常"""
    pass

class AsyncDeepSeekAPI:
    """异步DeepSeek API客户端"""
    
    def __init__(self):
        self.config = config_manager.get_llm_config()
        self.api_key = self.config.get('deepseek_api_key')
        self.base_url = self.config.get('base_url', 'https://api.deepseek.com/v1/chat/completions')
        self.timeout = aiohttp.ClientTimeout(total=180, connect=30)  # 优化超时配置
        self.semaphore = asyncio.Semaphore(10)  # 增加并发数到10
        self.connector = aiohttp.TCPConnector(
            limit=20,  # 最大连接池大小
            limit_per_host=10,  # 每个主机最大连接数
            ttl_dns_cache=300,  # DNS缓存5分钟
            use_dns_cache=True,
            keepalive_timeout=60  # 保持连接60秒
        )
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        self.session = aiohttp.ClientSession(
            timeout=self.timeout,
            connector=self.connector,
            headers={'User-Agent': 'CodeReview-AsyncClient/1.0'}
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        if hasattr(self, 'session'):
            await self.session.close()
        if hasattr(self, 'connector'):
            await self.connector.close()
    
    async def call_api_async(self, prompt: str, max_retries: int = 3) -> Dict[str, Any]:
        """
        异步调用DeepSeek API
        
        Args:
            prompt: 提示词
            max_retries: 最大重试次数
            
        Returns:
            API响应结果
        """
        if not self.api_key:
            raise ValueError("未配置DeepSeek API密钥")
        
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }
        
        data = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1,
            "max_tokens": 4000,
            "stream": False
        }
        
        async with self.semaphore:  # 限制并发
            for attempt in range(max_retries):
                try:
                    start_time = time.time()
                    
                    async with self.session.post(self.base_url, headers=headers, json=data) as response:
                        response_data = await response.json()
                        
                        elapsed = time.time() - start_time
                        debug(f"AsyncLLM API调用完成，耗时: {elapsed:.2f}秒")
                        
                        if response.status == 200:
                            if 'choices' in response_data and response_data['choices']:
                                content = response_data['choices'][0]['message']['content']
                                return {'content': content}
                            else:
                                raise Exception("API响应格式异常")
                        
                        elif response.status == 429:  # 请求频率限制
                            wait_time = 2 ** attempt  # 指数退避
                            warning(f"AsyncLLM 遇到频率限制，等待 {wait_time} 秒后重试")
                            await asyncio.sleep(wait_time)
                            continue
                        
                        else:
                            error_msg = response_data.get('error', {}).get('message', f'HTTP {response.status}')
                            raise Exception(f"API调用失败: {error_msg}")
                            
                except asyncio.TimeoutError:
                    warning(f"AsyncLLM 第{attempt + 1}次调用超时")
                    if attempt == max_retries - 1:
                        raise Exception("API调用超时")
                    await asyncio.sleep(1)
                    
                except aiohttp.ClientError as e:
                    warning(f"AsyncLLM 第{attempt + 1}次调用网络错误: {e}")
                    if attempt == max_retries - 1:
                        raise Exception(f"网络错误: {e}")
                    await asyncio.sleep(1)
                    
                except Exception as e:
                    warning(f"AsyncLLM 第{attempt + 1}次调用异常: {e}")
                    if attempt == max_retries - 1:
                        raise
                    await asyncio.sleep(1)
        
        raise Exception("API调用失败，已达最大重试次数")

class AsyncTaskProcessor:
    """异步任务处理器"""
    
    def __init__(self, task_id: str = None):
        self.prompts_config = config_manager.get_prompts_config()
        self.task_id = task_id
        self.state_manager = TaskStateManager(task_id) if task_id else None
    
    async def _check_task_abort(self, task_id: str) -> None:
        """
        异步检查任务是否被中止
        
        Args:
            task_id: 任务ID
            
        Raises:
            TaskAbortedException: 如果任务被中止
        """
        try:
            import yaml
            from pathlib import Path
            
            task_dir = config_manager.ensure_task_data_dir()
            task_file = task_dir / f'{task_id}.yaml'
            
            if task_file.exists():
                with open(task_file, 'r', encoding='utf-8') as f:
                    task_data = yaml.safe_load(f) or {}
                
                if task_data.get('status') == 'aborted':
                    debug(f"AsyncProcessor 检测到任务已被中止: {task_id}")
                    raise TaskAbortedException(f"任务 {task_id} 已被用户中止")
        except TaskAbortedException:
            raise
        except Exception as e:
            debug(f"AsyncProcessor 检查任务状态失败: {e}")
            # 检查失败时不阻止任务继续执行
    
    async def process_files_async(self, files_data: List[Dict[str, Any]], task_id: str) -> Dict[str, Any]:
        """
        异步并发处理多个文件
        
        Args:
            files_data: 文件数据列表
            task_id: 任务ID
            
        Returns:
            处理结果汇总
        """
        results = {
            'review_results': [],
            'unit_cases': [],
            'scenario_cases': []
        }
        
        async with AsyncDeepSeekAPI() as api_client:
            # 检查任务是否被中止
            await self._check_task_abort(task_id)
            
            # 创建所有文件的处理任务
            tasks = []
            for file_data in files_data:
                task = self._process_single_file_async(api_client, file_data, task_id)
                tasks.append(task)
            
            info(f"AsyncProcessor 开始并发处理 {len(tasks)} 个文件")
            
            # 并发执行所有任务
            file_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 处理结果前再次检查是否被中止
            await self._check_task_abort(task_id)
            
            # 汇总结果
            for i, result in enumerate(file_results):
                filename = files_data[i].get('filename', f'file_{i}') if i < len(files_data) else f'file_{i}'
                
                if isinstance(result, Exception):
                    error(f"AsyncProcessor 文件处理失败: {filename} - {result}")
                    continue
                
                if result:
                    # 记录每个文件的处理结果
                    review_count = 1 if 'review_result' in result else 0
                    unit_count = 1 if 'unit_case' in result else 0
                    scenario_count = len(result.get('scenario_cases', []))
                    
                    debug(f"AsyncProcessor 文件 {filename} 结果汇总: 审查{review_count}, 单元测试{unit_count}, 场景测试{scenario_count}")
                    
                    if 'review_result' in result:
                        results['review_results'].append(result['review_result'])
                    if 'unit_case' in result:
                        results['unit_cases'].append(result['unit_case'])
                    if 'scenario_cases' in result:
                        results['scenario_cases'].extend(result['scenario_cases'])
                else:
                    warning(f"AsyncProcessor 文件 {filename} 返回空结果")
        
        info(f"AsyncProcessor 处理完成 - 审查: {len(results['review_results'])}, 单元测试: {len(results['unit_cases'])}, 场景测试: {len(results['scenario_cases'])}")
        
        return results
    
    async def _process_single_file_async(self, api_client: AsyncDeepSeekAPI, 
                                       file_data: Dict[str, Any], task_id: str) -> Dict[str, Any]:
        """
        异步处理单个文件
        
        Args:
            api_client: 异步API客户端
            file_data: 文件数据
            task_id: 任务ID
            
        Returns:
            文件处理结果
        """
        filename = file_data.get('filename', '')
        diff_content = file_data.get('diff_content', '')
        filestatus = file_data.get('filestatus', {})
        
        if not diff_content:
            return {}
        
        # 检查任务是否被中止
        await self._check_task_abort(task_id)
        
        info(f"AsyncProcessor 开始处理文件: {filename}")
        
        # 初始化文件状态
        if self.state_manager:
            self.state_manager.initialize_file(filename, file_data.get('project_name', ''))
        
        # 创建三个异步任务：代码审查、单元测试、场景测试
        review_task = self._generate_code_review_async(api_client, filename, diff_content, filestatus)
        unit_test_task = self._generate_unit_test_async(api_client, filename, diff_content)
        scenario_test_task = self._generate_scenario_tests_async(api_client, filename, diff_content)
        
        # 并发执行三个任务
        try:
            debug(f"AsyncProcessor 开始并发执行三个任务: {filename}")
            review_result, unit_result, scenario_results = await asyncio.gather(
                review_task, unit_test_task, scenario_test_task,
                return_exceptions=True
            )
            debug(f"AsyncProcessor 三个任务执行完成: {filename}")
            
            result = {}
            
            # 处理审查结果
            if not isinstance(review_result, Exception) and review_result:
                result['review_result'] = {
                    'project_name': file_data.get('project_name', ''),
                    'filename': filename,
                    'filestatus': review_result.get('filestatus', ''),
                    'diff_content': diff_content,
                    "summary": review_result.get('summary', ''),
                    "business_logic": review_result.get('business_logic', ''),
                    "language_detected": review_result.get('language_detected', ''),
                    'issues': review_result.get('issues', [])
                }
                # 更新审查状态
                if self.state_manager:
                    self.state_manager.update_review_status(filename, 'completed', review_result)
            else:
                # 审查失败
                if self.state_manager:
                    error_msg = str(review_result) if isinstance(review_result, Exception) else "审查失败"
                    self.state_manager.update_review_status(filename, 'failed', error=error_msg)
            
            # 处理单元测试结果
            if not isinstance(unit_result, Exception) and unit_result:
                result['unit_case'] = {
                    'project_name': file_data.get('project_name', ''),
                    'filename': filename,
                    'code': unit_result.get('unit_test_code', ''),
                    'description': unit_result.get('test_description', '')
                }
                # 更新单元测试状态
                if self.state_manager:
                    self.state_manager.update_unit_test_status(filename, 'completed', unit_result)
            else:
                # 单元测试失败
                if self.state_manager:
                    error_msg = str(unit_result) if isinstance(unit_result, Exception) else "单元测试失败"
                    self.state_manager.update_unit_test_status(filename, 'failed', error=error_msg)
            
            # 处理场景测试结果
            if not isinstance(scenario_results, Exception) and scenario_results:
                scenario_cases = scenario_results.get('scenario_cases', [])
                for case in scenario_cases:
                    case['project_name'] = file_data.get('project_name', '')
                    case['filename'] = filename
                    # 添加模块信息
                    if 'module' not in case:
                        case['module'] = self._extract_module_name(filename)
                
                result['scenario_cases'] = scenario_cases
                # 更新场景测试状态
                if self.state_manager:
                    self.state_manager.update_scenario_test_status(filename, 'completed', scenario_results)
            else:
                # 场景测试失败
                if self.state_manager:
                    error_msg = str(scenario_results) if isinstance(scenario_results, Exception) else "场景测试失败"
                    self.state_manager.update_scenario_test_status(filename, 'failed', error=error_msg)
            
            info(f"AsyncProcessor 文件处理完成: {filename}")
            return result
            
        except Exception as e:
            error(f"AsyncProcessor 文件处理异常: {filename} - {e}")
            return {}
    
    async def _generate_code_review_async(self, api_client: AsyncDeepSeekAPI, 
                                         filename: str, diff_content: str, filestatus: Dict[str, Any]) -> Dict[str, Any]:
        """异步生成代码审查"""
        # 检查任务是否被中止
        if self.task_id:
            await self._check_task_abort(self.task_id)
            
        prompt_template = self.prompts_config.get('code_review_prompt', '')
        prompt = prompt_template.format(filename=filename, diff_content=diff_content)
        
        try:
            response = await api_client.call_api_async(prompt)
            content = response.get('content', '')
            
            # 解析JSON响应
            import re
            json_match = re.search(r'```json\s*(\{.*?\})\s*```', content, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group(1))
            else:
                # 尝试直接解析
                result = json.loads(content)

            # 补充项目名
            result['filestatus'] = filestatus
            return result
                
        except Exception as e:
            error(f"AsyncProcessor 代码审查生成失败: {filename} - {e}")
            return {}
    
    async def _generate_unit_test_async(self, api_client: AsyncDeepSeekAPI, 
                                      filename: str, diff_content: str) -> Dict[str, Any]:
        """异步生成单元测试"""
        # 检查任务是否被中止
        if self.task_id:
            await self._check_task_abort(self.task_id)
            
        prompt_template = self.prompts_config.get('unit_test_prompt', '')
        prompt = prompt_template.format(filename=filename, diff_content=diff_content)
        
        try:
            response = await api_client.call_api_async(prompt)
            content = response.get('content', '')
            
            # 解析JSON响应
            import re
            json_match = re.search(r'```json\s*(\{.*?\})\s*```', content, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group(1))
                return result
            else:
                return json.loads(content)
                
        except json.JSONDecodeError as e:
            error(f"AsyncProcessor 单元测试JSON解析失败: {filename} - {e}")
            warning(f"响应内容前200字符: {content[:200] if 'content' in locals() else 'N/A'}")
            # 返回错误恢复用例
            return {
                "unit_test_code": f"# 单元测试生成失败 - JSON解析错误\n# 文件: {filename}\n# 错误: {str(e)}",
                "test_description": f"单元测试生成失败: JSON解析错误 - {str(e)}"
            }
        except Exception as e:
            error(f"AsyncProcessor 单元测试生成失败: {filename} - {e}")
            # 返回错误恢复用例  
            return {
                "unit_test_code": f"# 单元测试生成异常\n# 文件: {filename}\n# 错误: {str(e)}",
                "test_description": f"单元测试生成异常: {str(e)}"
            }
    
    async def _generate_scenario_tests_async(self, api_client: AsyncDeepSeekAPI, 
                                           filename: str, diff_content: str) -> Dict[str, Any]:
        """异步生成场景测试"""
        # 检查任务是否被中止
        if self.task_id:
            await self._check_task_abort(self.task_id)
            
        prompt_template = self.prompts_config.get('scenario_test_prompt', '')
        prompt = prompt_template.format(filename=filename, diff_content=diff_content)
        
        try:
            response = await api_client.call_api_async(prompt)
            content = response.get('content', '')
            
            # 解析JSON响应
            import re
            json_match = re.search(r'```json\s*(\{.*?\})\s*```', content, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group(1))
                return result
            else:
                return json.loads(content)
                
        except json.JSONDecodeError as e:
            error(f"AsyncProcessor 场景测试JSON解析失败: {filename} - {e}")
            warning(f"响应内容前200字符: {content[:200] if 'content' in locals() else 'N/A'}")
            # 返回错误恢复用例
            return {
                "scenario_cases": [{
                    "case_id": "ASYNC_ERROR_001",
                    "title": "场景测试生成失败(异步)",
                    "preconditions": f"JSON解析错误: {str(e)}",
                    "steps": f"检查AI响应格式。文件: {filename}",
                    "expected_result": "AI服务正常响应"
                }]
            }
        except Exception as e:
            error(f"AsyncProcessor 场景测试生成失败: {filename} - {e}")
            # 返回错误恢复用例
            return {
                "scenario_cases": [{
                    "case_id": "ASYNC_ERROR_002", 
                    "title": "场景测试生成异常(异步)",
                    "preconditions": f"系统异常: {str(e)}",
                    "steps": f"检查系统配置。文件: {filename}",
                    "expected_result": "系统正常运行"
                }]
            }
    
    def _extract_module_name(self, filename: str) -> str:
        """从文件名提取模块名"""
        import os
        path_parts = filename.split('/')
        
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

# 使用示例
async def example_usage():
    """异步处理示例"""
    processor = AsyncTaskProcessor()
    
    files_data = [
        {
            'filename': 'app/models.py',
            'diff_content': 'some diff content',
            'project_name': 'TestProject'
        },
        # ... 更多文件
    ]
    
    try:
        results = await processor.process_files_async(files_data, 'task-123')
        # 处理结果: {results}
        pass
    except Exception as e:
        # 处理失败: {e}
        pass

if __name__ == "__main__":
    asyncio.run(example_usage())
