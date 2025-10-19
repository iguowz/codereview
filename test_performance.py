#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
性能测试脚本 - 验证代码优化效果
"""

import time
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
import requests
import json

def test_cache_performance():
    """测试缓存性能"""
    print("=== 测试缓存性能 ===")
    
    try:
        from app.utils.cache_manager import CacheManager, global_cache
        
        cache = CacheManager()
        
        # 测试基本缓存操作
        start_time = time.time()
        for i in range(1000):
            cache.set(f"key_{i}", f"value_{i}")
        set_time = time.time() - start_time
        
        start_time = time.time()
        for i in range(1000):
            cache.get(f"key_{i}")
        get_time = time.time() - start_time
        
        print(f"缓存设置 1000 个键值对耗时: {set_time:.4f}秒")
        print(f"缓存获取 1000 个键值对耗时: {get_time:.4f}秒")
        print(f"缓存大小: {cache.size()}")
        print(f"缓存统计: {cache.stats()}")
        
        return True
        
    except Exception as e:
        print(f"缓存性能测试失败: {e}")
        return False


def test_notification_performance():
    """测试通知系统性能"""
    print("\n=== 测试通知系统性能 ===")
    
    try:
        from app.utils.notification_manager import (
            NotificationManager, NotificationMessage, NotificationLevel,
            EmailProvider, WeChatWorkProvider
        )
        
        # 创建测试配置
        email_config = {
            'enabled': True,
            'smtp_server': 'smtp.gmail.com',
            'smtp_port': 587,
            'username': 'test@example.com',
            'password': 'test_password',
            'use_ssl': True,
            'from_name': 'Test System'
        }
        
        wechat_config = {
            'enabled': True,
            'webhook_url': 'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test',
            'mentioned_list': [],
            'mentioned_mobile_list': []
        }
        
        # 测试配置验证
        email_provider = EmailProvider(email_config)
        wechat_provider = WeChatWorkProvider(wechat_config)
        
        print(f"邮件提供者配置验证: {'通过' if email_provider.validate_config() else '失败'}")
        print(f"企业微信提供者配置验证: {'通过' if wechat_provider.validate_config() else '失败'}")
        
        # 测试消息创建性能
        start_time = time.time()
        for i in range(100):
            message = NotificationMessage(
                title=f"测试消息 {i}",
                content=f"这是第 {i} 条测试消息内容",
                level=NotificationLevel.INFO
            )
        create_time = time.time() - start_time
        
        print(f"创建 100 个通知消息耗时: {create_time:.4f}秒")
        
        return True
        
    except Exception as e:
        print(f"通知系统性能测试失败: {e}")
        return False


def test_http_client_performance():
    """测试HTTP客户端性能"""
    print("\n=== 测试HTTP客户端性能 ===")
    
    try:
        from app.utils.git_api import GitAPIClient
        
        client = GitAPIClient()
        
        # 测试连接池创建
        start_time = time.time()
        session = client.session
        setup_time = time.time() - start_time
        
        print(f"HTTP客户端初始化耗时: {setup_time:.4f}秒")
        print(f"连接池配置: 最大连接数={session.adapters['https://'].config['pool_maxsize']}")
        
        return True
        
    except Exception as e:
        print(f"HTTP客户端性能测试失败: {e}")
        return False


async def test_async_performance():
    """测试异步处理性能"""
    print("\n=== 测试异步处理性能 ===")
    
    try:
        from app.utils.async_llm_api import AsyncDeepSeekAPI
        
        # 模拟异步任务
        async def mock_async_task(task_id):
            await asyncio.sleep(0.01)  # 模拟异步操作
            return f"Task {task_id} completed"
        
        # 测试并发执行
        start_time = time.time()
        tasks = [mock_async_task(i) for i in range(100)]
        results = await asyncio.gather(*tasks)
        async_time = time.time() - start_time
        
        print(f"异步执行 100 个任务耗时: {async_time:.4f}秒")
        print(f"平均每个任务耗时: {async_time/100:.6f}秒")
        
        # 测试AsyncDeepSeekAPI初始化
        start_time = time.time()
        async with AsyncDeepSeekAPI() as api:
            init_time = time.time() - start_time
            print(f"异步API客户端初始化耗时: {init_time:.4f}秒")
            print(f"并发限制: {api.semaphore._value}")
            print(f"连接池配置: 最大连接数={api.connector._limit}")
        
        return True
        
    except Exception as e:
        print(f"异步处理性能测试失败: {e}")
        return False


def test_concurrent_performance():
    """测试并发处理性能"""
    print("\n=== 测试并发处理性能 ===")
    
    def mock_task(task_id):
        time.sleep(0.01)  # 模拟任务处理
        return f"Task {task_id} completed"
    
    # 测试线程池性能
    start_time = time.time()
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(mock_task, i) for i in range(100)]
        results = [future.result() for future in futures]
    thread_time = time.time() - start_time
    
    print(f"线程池执行 100 个任务耗时: {thread_time:.4f}秒")
    
    # 测试串行执行对比
    start_time = time.time()
    for i in range(100):
        mock_task(i)
    serial_time = time.time() - start_time
    
    print(f"串行执行 100 个任务耗时: {serial_time:.4f}秒")
    print(f"并发提升比例: {serial_time/thread_time:.2f}x")
    
    return True


def test_memory_usage():
    """测试内存使用情况"""
    print("\n=== 测试内存使用情况 ===")
    
    try:
        import psutil
        import os
        
        process = psutil.Process(os.getpid())
        memory_info = process.memory_info()
        
        print(f"当前进程内存使用: {memory_info.rss / 1024 / 1024:.2f} MB")
        print(f"虚拟内存使用: {memory_info.vms / 1024 / 1024:.2f} MB")
        
        # 测试大量缓存对象的内存使用
        from app.utils.cache_manager import CacheManager
        
        cache = CacheManager()
        start_memory = process.memory_info().rss
        
        # 创建大量缓存对象
        for i in range(10000):
            cache.set(f"large_key_{i}", "x" * 1000)  # 每个值1KB
        
        end_memory = process.memory_info().rss
        memory_increase = (end_memory - start_memory) / 1024 / 1024
        
        print(f"缓存 10000 个1KB对象后内存增加: {memory_increase:.2f} MB")
        print(f"平均每个缓存对象内存开销: {memory_increase * 1024 / 10000:.2f} KB")
        
        return True
        
    except ImportError:
        print("psutil 未安装，跳过内存测试")
        return True
    except Exception as e:
        print(f"内存使用测试失败: {e}")
        return False


def main():
    """主测试函数"""
    print("开始性能测试...")
    print("=" * 50)
    
    test_results = {}
    
    # 执行各项测试
    test_results['cache'] = test_cache_performance()
    test_results['notification'] = test_notification_performance()
    test_results['http_client'] = test_http_client_performance()
    test_results['concurrent'] = test_concurrent_performance()
    test_results['memory'] = test_memory_usage()
    
    # 异步测试
    try:
        test_results['async'] = asyncio.run(test_async_performance())
    except Exception as e:
        print(f"异步测试失败: {e}")
        test_results['async'] = False
    
    # 汇总结果
    print("\n" + "=" * 50)
    print("性能测试结果汇总:")
    print("=" * 50)
    
    passed = 0
    total = len(test_results)
    
    for test_name, result in test_results.items():
        status = "通过" if result else "失败"
        print(f"{test_name.ljust(15)}: {status}")
        if result:
            passed += 1
    
    print(f"\n总计: {passed}/{total} 项测试通过")
    
    if passed == total:
        print("🎉 所有性能测试通过！")
        return 0
    else:
        print("⚠️  部分测试失败，请检查相关功能")
        return 1


if __name__ == "__main__":
    exit(main())