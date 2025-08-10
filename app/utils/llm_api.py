import requests
import json
import re
from typing import Dict, Any

from ..config_manager import config_manager
from ..logger import info, error, warning, debug

class DeepSeekAPI:
    def __init__(self, api_key: str = None):
        self.api_key = api_key or config_manager.get_deepseek_api_key()
        self.base_url = "https://api.deepseek.com/v1/chat/completions"
        
        if self.api_key and self.api_key.startswith('sk-'):
            self.headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            self.mock_mode = False
        else:
            # 模拟模式：没有真实 API key 时使用
            warning("DEEPSEEK_API_KEY 未设置或无效，启用模拟模式")
            self.headers = {}
            self.mock_mode = True
    
    def chat_completion(self, messages: list, temperature: float = 0.1, max_retries: int = 3) -> str:
        """调用DeepSeek API进行对话，支持重试"""
        if self.mock_mode:
            info("使用模拟模式，返回空结果")
            # 模拟模式：返回模拟结果
            return self._mock_response(messages)
        
        info(f"调用DeepSeek API，消息数量: {len(messages)}")
        payload = {
            "model": "deepseek-chat",
            "messages": messages,
            "temperature": temperature,
            "max_tokens": 4000
        }
        
        last_error = None
        for attempt in range(max_retries + 1):
            try:
                if attempt > 0:
                    info(f"第 {attempt + 1} 次重试API调用")
                
                response = requests.post(self.base_url, headers=self.headers, json=payload, timeout=300)
                info(f"API响应状态: {response.status_code}")
                
                if response.status_code == 200:
                    result = response.json()
                    content = result['choices'][0]['message']['content']
                    info(f"API返回内容长度: {len(content)} 字符")
                    if attempt > 0:
                        info(f"重试成功！")
                    return content
                else:
                    error_msg = f"DeepSeek API error: {response.status_code} - {response.text}"
                    error(f"API调用失败: {error_msg}")
                    last_error = Exception(error_msg)
                    
            except requests.exceptions.Timeout:
                error_msg = f"DeepSeek API调用超时 (5分钟) - 尝试 {attempt + 1}/{max_retries + 1}"
                warning(f"{error_msg}")
                last_error = Exception(f"DeepSeek API调用超时 (5分钟)")
                
            except requests.exceptions.RequestException as e:
                error_msg = f"DeepSeek API网络错误: {e} - 尝试 {attempt + 1}/{max_retries + 1}"
                warning(error_msg)
                last_error = Exception(f"DeepSeek API网络错误: {e}")
            
            # 如果不是最后一次尝试，等待一下再重试
            if attempt < max_retries:
                import time
                wait_time = (attempt + 1) * 2  # 递增等待时间: 2秒, 4秒
                info(f"等待 {wait_time} 秒后重试...")
                time.sleep(wait_time)
        
        # 所有重试都失败了
        error(f"API调用失败，已重试 {max_retries} 次")
        raise last_error
    
    def _mock_response(self, messages: list) -> str:
        """模拟 API 响应 - 返回空结果"""
        user_message = messages[-1].get('content', '') if messages else ''
        
        if '代码审查' in user_message or 'code review' in user_message.lower():
            return '''```json
{
  "issues": []
}
```'''
        elif '测试用例' in user_message or 'test case' in user_message.lower():
            return '''```json
{
  "unit_test_code": "",
  "scenario_cases": []
}
```'''
        else:
            return '{"result": "需要配置 DEEPSEEK_API_KEY"}'

    def _extract_json(self, content: str) -> Dict[str, Any]:
        """尽最大努力从 LLM 文本中提取 JSON 对象。
        处理场景：```json 代码块```、普通 ``` 代码块、前后解释文本、换行与缩进。
        """
        # 直接尝试
        try:
            return json.loads(content)
        except Exception:
            pass
        
        # 去除代码块围栏
        content_no_fence = re.sub(r"```(json|JSON)?", "", content)
        content_no_fence = content_no_fence.replace("```", "").strip()
        try:
            return json.loads(content_no_fence)
        except Exception:
            pass
        
        # 正则提取第一个大括号块（可能过宽，逐步收敛）
        # 贪婪取最外层
        candidates = re.findall(r"\{[\s\S]*\}", content)
        for cand in candidates:
            try:
                return json.loads(cand)
            except Exception:
                continue
        
        # 再对去围栏后的文本做一次
        candidates2 = re.findall(r"\{[\s\S]*\}", content_no_fence)
        for cand in candidates2:
            try:
                return json.loads(cand)
            except Exception:
                continue
        
        raise json.JSONDecodeError("无法从响应中提取有效JSON", content, 0)
    
    def code_review(self, filename: str, diff_content: str) -> Dict[str, Any]:
        """进行代码审查"""
        prompt = self._load_prompt('code_review_prompt')
        formatted_prompt = prompt.format(filename=filename, diff_content=diff_content)
        
        messages = [
            {"role": "system", "content": "你是一名资深代码审查工程师，请严格按照JSON格式中文返回审查结果。"},
            {"role": "user", "content": formatted_prompt}
        ]
        
        response = self.chat_completion(messages)
        
        try:
            result = self._extract_json(response)
            return result
        except json.JSONDecodeError as e:
            error_msg = f"JSON解析失败: {str(e)}"
            warning(error_msg)
            warning(f"响应内容前200字符: {response[:200]}")
            warning(f"响应内容后200字符: {response[-200:] if len(response) > 200 else response}")
            return {
                "summary": "AI响应格式错误",
                "issues": [{
                    "type": "系统错误",
                    "description": f"AI响应无法解析为JSON格式。错误: {str(e)}。响应: {response[:100]}...",
                    "suggestion": "请检查AI服务是否正常",
                    "severity": "Critical"
                }]
            }
        except Exception as e:
            error_msg = f"代码审查异常: {str(e)}"
            error(error_msg)
            return {
                "summary": "代码审查异常",
                "issues": [{
                    "type": "系统异常",
                    "description": f"代码审查过程中发生异常: {str(e)}",
                    "suggestion": "请检查系统配置和网络连接",
                    "severity": "Critical"
                }]
            }
    
    def generate_unit_tests(self, filename: str, diff_content: str) -> Dict[str, Any]:
        """生成单元测试用例"""
        prompt = self._load_prompt('unit_test_prompt')
        formatted_prompt = prompt.format(filename=filename, diff_content=diff_content)
        
        messages = [
            {"role": "system", "content": "你是一名资深测试工程师，专门负责单元测试编写。请严格按照JSON格式中文返回单元测试代码。"},
            {"role": "user", "content": formatted_prompt}
        ]
        
        response = self.chat_completion(messages, max_retries=1)
        debug(filename, f"单元测试原始响应: {response[:500]}...")
        
        try:
            result = self._extract_json(response)
            debug(filename, f"单元测试JSON解析成功，键: {list(result.keys()) if isinstance(result, dict) else type(result)}")
            return result
        except json.JSONDecodeError as e:
            error_msg = f"单元测试JSON解析失败: {str(e)}"
            warning(error_msg)
            warning(f"响应内容前200字符: {response[:200]}")
            return {
                "unit_test_code": f"# 单元测试生成失败\n# JSON解析错误: {str(e)}\n# 响应内容: {response[:100]}",
                "test_description": f"单元测试生成失败，JSON解析错误: {str(e)}"
            }
        except Exception as e:
            error_msg = f"单元测试生成异常: {str(e)}"
            error(error_msg)
            return {
                "unit_test_code": f"# 单元测试生成异常\n# 错误: {str(e)}",
                "test_description": f"单元测试生成异常: {str(e)}"
            }
    
    def generate_scenario_tests(self, filename: str, diff_content: str) -> Dict[str, Any]:
        """生成场景测试用例"""
        prompt = self._load_prompt('scenario_test_prompt')
        formatted_prompt = prompt.format(filename=filename, diff_content=diff_content)
        
        messages = [
            {"role": "system", "content": "你是一名资深测试工程师，专门负责场景测试设计。请严格按照JSON格式中文返回场景测试用例。"},
            {"role": "user", "content": formatted_prompt}
        ]
        
        response = self.chat_completion(messages, max_retries=1)
        debug(filename, f"场景测试原始响应: {response[:500]}...")
        
        try:
            result = self._extract_json(response)
            debug(filename, f"场景测试JSON解析成功，键: {list(result.keys()) if isinstance(result, dict) else type(result)}")
            return result
        except json.JSONDecodeError as e:
            error_msg = f"场景测试JSON解析失败: {str(e)}"
            warning(error_msg)
            warning(f"响应内容前200字符: {response[:200]}")
            return {
                "scenario_cases": [{
                    "case_id": "ERROR_001",
                    "title": "场景测试生成失败",
                    "preconditions": f"JSON解析错误: {str(e)}",
                    "steps": f"检查AI响应格式。响应内容: {response[:100]}",
                    "expected_result": "AI服务正常响应"
                }]
            }
        except Exception as e:
            error_msg = f"场景测试生成异常: {str(e)}"
            error(error_msg)
            return {
                "scenario_cases": [{
                    "case_id": "ERROR_002",
                    "title": "场景测试生成异常",
                    "preconditions": f"系统异常: {str(e)}",
                    "steps": "检查系统配置和网络连接",
                    "expected_result": "系统正常运行"
                }]
            }
    