# -*- coding: utf-8 -*-
"""
通知管理器 - 支持邮件、企业微信等多种通知方式
"""

import time
import smtplib
import json
import asyncio
import aiohttp
from abc import ABC, abstractmethod
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass
from enum import Enum

from ..config_manager import config_manager
from ..logger import info, error, warning, exception, debug


class NotificationType(Enum):
    """通知类型枚举"""
    EMAIL = "email"
    WECHAT_WORK = "wechat_work"
    WEBHOOK = "webhook"


class NotificationLevel(Enum):
    """通知级别"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    SUCCESS = "success"


@dataclass
class NotificationMessage:
    """通知消息数据类"""
    title: str
    content: str
    level: NotificationLevel = NotificationLevel.INFO
    attachments: Optional[List[str]] = None
    extra_data: Optional[Dict[str, Any]] = None


@dataclass
class NotificationResult:
    """通知发送结果"""
    success: bool
    message: str
    provider: str
    timestamp: str


class NotificationProvider(ABC):
    """通知提供者抽象基类"""
    
    @abstractmethod
    def __init__(self, config: Dict[str, Any]):
        """初始化通知提供者"""
        pass
    
    @abstractmethod
    async def send_async(self, recipients: List[str], message: NotificationMessage) -> NotificationResult:
        """异步发送通知"""
        pass
    
    @abstractmethod
    def send_sync(self, recipients: List[str], message: NotificationMessage) -> NotificationResult:
        """同步发送通知"""
        pass
    
    @abstractmethod
    def validate_config(self) -> bool:
        """验证配置是否有效"""
        pass


class EmailProvider(NotificationProvider):
    """邮件通知提供者"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化邮件提供者
        
        Args:
            config: 邮件配置字典
                - smtp_server: SMTP服务器地址
                - smtp_port: SMTP端口
                - username: 用户名
                - password: 密码
                - use_ssl: 是否使用SSL
                - from_name: 发件人名称
        """
        self.config = config
        self.smtp_server = config.get('smtp_server')
        self.smtp_port = config.get('smtp_port', 587)
        self.username = config.get('username')
        self.password = config.get('password')
        self.use_ssl = config.get('use_ssl', True)
        self.from_name = config.get('from_name', 'Code Review System')
        
    def validate_config(self) -> bool:
        """验证邮件配置"""
        required_fields = ['smtp_server', 'username', 'password']
        for field in required_fields:
            if not self.config.get(field):
                error(f"邮件配置缺少必需字段: {field}")
                return False
        return True
    
    def _create_message(self, recipients: List[str], message: NotificationMessage) -> MIMEMultipart:
        """创建邮件消息"""
        msg = MIMEMultipart()
        msg['From'] = f"{self.from_name} <{self.username}>"
        msg['To'] = ', '.join(recipients)
        msg['Subject'] = message.title
        
        # 根据通知级别设置邮件内容格式
        level_colors = {
            NotificationLevel.INFO: '#2196F3',
            NotificationLevel.SUCCESS: '#4CAF50',
            NotificationLevel.WARNING: '#FF9800',
            NotificationLevel.ERROR: '#F44336'
        }
        
        level_icons = {
            NotificationLevel.INFO: 'ℹ️',
            NotificationLevel.SUCCESS: '✅',
            NotificationLevel.WARNING: '⚠️',
            NotificationLevel.ERROR: '❌'
        }
        
        color = level_colors.get(message.level, '#2196F3')
        icon = level_icons.get(message.level, 'ℹ️')
        
        # 获取任务相关数据
        task_data = message.extra_data or {}
        task_id = task_data.get('task_id', '')
        report_url = task_data.get('report_url', '')
        summary = task_data.get('summary', {})
        # 构建报告汇总HTML
        summary_html = ""
        if summary:
            critical_issues = summary.get('review_statistics', {}).get('critical_issues', '-')
            high_issues = summary.get('review_statistics', {}).get('high_issues', '-')
            medium_issues = summary.get('review_statistics', {}).get('medium_issues', '-')
            low_issues = summary.get('review_statistics', {}).get('low_issues', '-')
            total_issues = summary.get('summary', {}).get('total_issues_found', '-')
            test_cases = summary.get('summary', {}).get('total_unit_tests', 0) + summary.get('summary', {}).get('total_scenario_tests', 0)
            
            summary_html = f"""
            <div class="summary-section">
                <h3>📊 审查结果汇总</h3>
                <div class="summary-grid">
                    <div class="summary-item critical">
                        <span class="summary-label">严重问题</span>
                        <span class="summary-value">{critical_issues}</span>
                    </div>
                    <div class="summary-item high">
                        <span class="summary-label">高危问题</span>
                        <span class="summary-value">{high_issues}</span>
                    </div>
                    <div class="summary-item medium">
                        <span class="summary-label">中等问题</span>
                        <span class="summary-value">{medium_issues}</span>
                    </div>
                    <div class="summary-item low">
                        <span class="summary-label">低危问题</span>
                        <span class="summary-value">{low_issues}</span>
                    </div>
                </div>
                <div class="summary-total">
                    <p><strong>总计发现 {total_issues} 个问题，生成 {test_cases} 个测试用例</strong></p>
                </div>
            </div>
            """
        
        # 报告链接部分
        report_link_html = ""
        if report_url:
            report_link_html = f"""
            <div class="report-link-section">
                <a href="{report_url}" target="_blank">🔗 查看详细报告</a>
                <div class="link-container">
                    <p class="link-note">点击查看详细的代码审查报告和测试用例</p>
                </div>
            </div>
            """

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5; }}
                .container {{ max-width: 600px; margin: 0 auto; background-color: white; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 20px rgba(0,0,0,0.1); }}
                .header {{ background: linear-gradient(135deg, {color} 0%, {color}dd 100%); color: white; padding: 30px 20px; text-align: center; }}
                .header h1 {{ margin: 0; font-size: 24px; font-weight: 600; }}
                .content {{ padding: 30px; line-height: 1.6; }}
                .footer {{ background-color: #f8f9fa; padding: 20px; text-align: center; font-size: 12px; color: #6c757d; }}
                .level-badge {{ display: inline-block; padding: 6px 16px; border-radius: 20px; background-color: {color}; color: white; font-size: 12px; font-weight: 600; margin-bottom: 20px; }}
                
                .summary-section {{ margin: 20px 0; padding: 20px; background-color: #f8f9ff; border-radius: 8px; border-left: 4px solid {color}; }}
                .summary-section h3 {{ margin-top: 0; color: #333; }}
                .summary-grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; margin: 15px 0; }}
                .summary-item {{ padding: 12px; border-radius: 6px; text-align: center; font-size: 14px; }}
                .summary-item.critical {{ background-color: #fee; border: 1px solid #f56c6c; color: #c53030; }}
                .summary-item.high {{ background-color: #fff3cd; border: 1px solid #ffc107; color: #b45309; }}
                .summary-item.medium {{ background-color: #cff4fc; border: 1px solid #0dcaf0; color: #055160; }}
                .summary-item.low {{ background-color: #d1e7dd; border: 1px solid #198754; color: #0f5132; }}
                .summary-label {{ display: block; font-weight: 500; margin-bottom: 4px; }}
                .summary-value {{ display: block; font-size: 18px; font-weight: 700; }}
                .summary-total {{ text-align: center; margin-top: 15px; padding: 15px; background-color: white; border-radius: 6px; }}
                
                .report-link-section {{ margin: 20px 0; padding: 20px; background-color: #f0f9ff; border-radius: 8px; border-left: 4px solid #0ea5e9; }}
                .report-link-section h3 {{ margin-top: 0; color: #333; }}
                .link-container {{ text-align: center; }}
                .link-note {{ margin: 5px 0; font-size: 12px; color: #9ca3af; }}
                code {{ background-color: #f3f4f6; padding: 2px 6px; border-radius: 3px; font-family: 'Monaco', 'Consolas', monospace; }}
                
                pre {{ background-color: #f8f9fa; padding: 15px; border-radius: 6px; overflow-x: auto; border: 1px solid #e5e7eb; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>{icon} {message.title}</h1>
                </div>
                <div class="content">
                    <div class="level-badge">{message.level.value.upper()}</div>
                    <div>{message.content.replace(chr(10), '<br>')}</div>
                    {summary_html}
                    {report_link_html}
                </div>
                <div class="footer">
                    <p>此邮件由 Git 代码审查系统自动发送</p>
                    <p>请勿直接回复此邮件</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # 添加HTML和纯文本版本
        msg.attach(MIMEText(message.content, 'plain', 'utf-8'))
        msg.attach(MIMEText(html_content, 'html', 'utf-8'))
        
        # 添加附件
        if message.attachments:
            for attachment_path in message.attachments:
                try:
                    with open(attachment_path, 'rb') as f:
                        part = MIMEBase('application', 'octet-stream')
                        part.set_payload(f.read())
                        encoders.encode_base64(part)
                        part.add_header(
                            'Content-Disposition',
                            f'attachment; filename= {attachment_path.split("/")[-1]}'
                        )
                        msg.attach(part)
                except Exception as e:
                    warning(f"添加邮件附件失败: {attachment_path}, 错误: {e}")
        
        return msg
    
    def send_sync(self, recipients: List[str], message: NotificationMessage) -> NotificationResult:
        """同步发送邮件"""
        if not self.validate_config():
            return NotificationResult(
                success=False,
                message="邮件配置无效",
                provider="email",
                timestamp=str(time.time())
            )
        
        try:
            msg = self._create_message(recipients, message)
            
            # 连接SMTP服务器
            if self.use_ssl:
                with smtplib.SMTP_SSL(self.smtp_server, self.smtp_port) as server:
                    server.login(self.username, self.password)
                    server.send_message(msg)
            else:
                with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                    server.login(self.username, self.password)
                    text = msg.as_string()
                    server.sendmail(self.username, recipients, text)

            info(f"邮件发送成功: {recipients}")
            return NotificationResult(
                success=True,
                message=f"邮件已发送给 {len(recipients)} 个收件人",
                provider="email",
                timestamp=str(time.time())
            )
        except smtplib.SMTPResponseException as e:
            # 仅放过 quit 阶段的 -1 空包
            if len(e.args) >= 2 and e.args[0] == -1 and (not e.args[1] or b'\x00' in e.args[1]):
                info(f"邮件发送成功: {recipients}")
                return NotificationResult(
                    success=True,
                    message=f"邮件已发送给 {len(recipients)} 个收件人",
                    provider="email",
                    timestamp=str(time.time())
                )
            raise
            
        except Exception as e:
            exception(f"邮件发送失败: {e}")
            return NotificationResult(
                success=False,
                message=f"邮件发送失败: {str(e)}",
                provider="email",
                timestamp=str(time.time())
            )
    
    async def send_async(self, recipients: List[str], message: NotificationMessage) -> NotificationResult:
        """异步发送邮件（在线程池中执行同步操作）"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.send_sync, recipients, message)


class WeChatWorkProvider(NotificationProvider):
    """企业微信通知提供者"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化企业微信提供者
        
        Args:
            config: 企业微信配置字典
                - webhook_url: Webhook URL
                - mentioned_list: @用户列表
                - mentioned_mobile_list: @手机号列表
        """
        self.config = config
        self.webhook_url = config.get('webhook_url')
        self.mentioned_list = config.get('mentioned_list', [])
        self.mentioned_mobile_list = config.get('mentioned_mobile_list', [])
    
    def validate_config(self) -> bool:
        """验证企业微信配置"""
        if not self.webhook_url:
            error("企业微信配置缺少 webhook_url")
            return False
        return True
    
    def _create_message_data(self, message: NotificationMessage) -> Dict[str, Any]:
        """创建企业微信消息数据"""
        level_colors = {
            NotificationLevel.INFO: 'info',
            NotificationLevel.SUCCESS: 'comment',
            NotificationLevel.WARNING: 'warning',
            NotificationLevel.ERROR: 'error'
        }
        
        level_icons = {
            NotificationLevel.INFO: '📋',
            NotificationLevel.SUCCESS: '✅',
            NotificationLevel.WARNING: '⚠️',
            NotificationLevel.ERROR: '❌'
        }
        
        color = level_colors.get(message.level, 'info')
        icon = level_icons.get(message.level, '📋')
        
        # 构建Markdown格式消息
        content = f"{icon} **{message.title}**\\n\\n{message.content}"
        
        data = {
            "msgtype": "markdown",
            "markdown": {
                "content": content,
                "mentioned_list": self.mentioned_list,
                "mentioned_mobile_list": self.mentioned_mobile_list
            }
        }
        
        return data
    
    def send_sync(self, recipients: List[str], message: NotificationMessage) -> NotificationResult:
        """同步发送企业微信消息"""
        if not self.validate_config():
            return NotificationResult(
                success=False,
                message="企业微信配置无效",
                provider="wechat_work",
                timestamp=str(time.time())
            )
        
        try:
            import requests
            
            data = self._create_message_data(message)
            response = requests.post(
                self.webhook_url,
                json=data,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get('errcode') == 0:
                    info("企业微信消息发送成功")
                    return NotificationResult(
                        success=True,
                        message="企业微信消息发送成功",
                        provider="wechat_work",
                        timestamp=str(time.time())
                    )
                else:
                    error(f"企业微信消息发送失败: {result.get('errmsg')}")
                    return NotificationResult(
                        success=False,
                        message=f"企业微信API错误: {result.get('errmsg')}",
                        provider="wechat_work",
                        timestamp=str(time.time())
                    )
            else:
                error(f"企业微信HTTP请求失败: {response.status_code}")
                return NotificationResult(
                    success=False,
                    message=f"HTTP错误: {response.status_code}",
                    provider="wechat_work",
                    timestamp=str(time.time())
                )
                
        except Exception as e:
            error(f"企业微信消息发送异常: {e}")
            return NotificationResult(
                success=False,
                message=f"发送异常: {str(e)}",
                provider="wechat_work",
                timestamp=str(time.time())
            )
    
    async def send_async(self, recipients: List[str], message: NotificationMessage) -> NotificationResult:
        """异步发送企业微信消息"""
        if not self.validate_config():
            return NotificationResult(
                success=False,
                message="企业微信配置无效",
                provider="wechat_work",
                timestamp=str(time.time())
            )
        
        try:
            data = self._create_message_data(message)
            
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(self.webhook_url, json=data) as response:
                    if response.status == 200:
                        result = await response.json()
                        if result.get('errcode') == 0:
                            info("企业微信消息发送成功")
                            return NotificationResult(
                                success=True,
                                message="企业微信消息发送成功",
                                provider="wechat_work",
                                timestamp=str(time.time())
                            )
                        else:
                            error(f"企业微信消息发送失败: {result.get('errmsg')}")
                            return NotificationResult(
                                success=False,
                                message=f"企业微信API错误: {result.get('errmsg')}",
                                provider="wechat_work",
                                timestamp=str(time.time())
                            )
                    else:
                        error(f"企业微信HTTP请求失败: {response.status}")
                        return NotificationResult(
                            success=False,
                            message=f"HTTP错误: {response.status}",
                            provider="wechat_work",
                            timestamp=str(time.time())
                        )
                        
        except Exception as e:
            error(f"企业微信消息发送异常: {e}")
            return NotificationResult(
                success=False,
                message=f"发送异常: {str(e)}",
                provider="wechat_work",
                timestamp=str(time.time())
            )


class NotificationManager:
    """通知管理器"""
    
    def __init__(self):
        """初始化通知管理器"""
        self.providers: Dict[str, NotificationProvider] = {}
        self._load_providers()
    
    def _load_providers(self):
        """加载通知提供者"""
        try:
            notification_config = config_manager.get_notification_config()
            
            # 初始化邮件提供者
            email_config = notification_config.get('email')
            if email_config and email_config.get('enabled', False):
                self.providers['email'] = EmailProvider(email_config)
                debug("邮件通知提供者已加载")
            
            # 初始化企业微信提供者
            wechat_config = notification_config.get('wechat_work')
            if wechat_config and wechat_config.get('enabled', False):
                self.providers['wechat_work'] = WeChatWorkProvider(wechat_config)
                debug("企业微信通知提供者已加载")
                
        except Exception as e:
            warning(f"加载通知提供者失败: {e}")
    
    def reload_providers(self):
        """重新加载通知提供者"""
        self.providers.clear()
        self._load_providers()
    
    def get_available_providers(self) -> List[str]:
        """获取可用的通知提供者列表"""
        return list(self.providers.keys())

    async def send_notification_async(
        self,
        providers: Union[str, List[str]],
        recipients: List[str],
        message: NotificationMessage
    ) -> List[NotificationResult]:
        """
        异步发送通知
        
        Args:
            providers: 通知提供者名称或列表
            recipients: 收件人列表
            message: 通知消息
            
        Returns:
            通知结果列表
        """
        if isinstance(providers, str):
            providers = [providers]
        
        results = []
        tasks = []
        
        for provider_name in providers:
            print(f"开始发送通知 : {provider_name}")
            provider = self.providers.get(provider_name)
            if provider:
                task = provider.send_async(recipients, message)
                tasks.append(task)
            else:
                warning(f"通知提供者不存在: {provider_name}")
                results.append(NotificationResult(
                    success=False,
                    message=f"通知提供者不存在: {provider_name}",
                    provider=provider_name,
                    timestamp=str(time.time())
                ))
        
        if tasks:
            task_results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in task_results:
                if isinstance(result, Exception):
                    error(f"通知发送异常: {result}")
                    results.append(NotificationResult(
                        success=False,
                        message=f"发送异常: {str(result)}",
                        provider="unknown",
                        timestamp=str(time.time())
                    ))
                else:
                    results.append(result)
        
        return results
    
    def send_notification_sync(
        self,
        providers: Union[str, List[str]],
        recipients: List[str],
        message: NotificationMessage
    ) -> List[NotificationResult]:
        """
        同步发送通知
        
        Args:
            providers: 通知提供者名称或列表
            recipients: 收件人列表
            message: 通知消息
            
        Returns:
            通知结果列表
        """
        if isinstance(providers, str):
            providers = [providers]
        
        results = []
        for provider_name in providers:
            print(f"开始发送通知: {provider_name}，收件人: {recipients}")
            provider = self.providers.get(provider_name)
            if provider:
                try:
                    result = provider.send_sync(recipients, message)
                    results.append(result)
                except Exception as e:
                    error(f"通知发送异常: {e}")
                    results.append(NotificationResult(
                        success=False,
                        message=f"发送异常: {str(e)}",
                        provider=provider_name,
                        timestamp=str(time.time())
                    ))
            else:
                warning(f"通知提供者不存在: {provider_name}")
                results.append(NotificationResult(
                    success=False,
                    message=f"通知提供者不存在: {provider_name}",
                    provider=provider_name,
                    timestamp=str(time.time())
                ))
        
        return results


# 全局通知管理器实例
notification_manager = NotificationManager()