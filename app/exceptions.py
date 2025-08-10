# -*- coding: utf-8 -*-
"""
自定义异常类
"""


class CodeReviewException(Exception):
    """代码审查相关异常的基类"""
    pass


class GitAPIException(CodeReviewException):
    """Git API异常"""
    pass


class LLMAPIException(CodeReviewException):
    """LLM API异常"""
    pass


class ConfigurationException(CodeReviewException):
    """配置异常"""
    pass


class TaskProcessingException(CodeReviewException):
    """任务处理异常"""
    pass


class FileProcessingException(CodeReviewException):
    """文件处理异常"""
    pass
