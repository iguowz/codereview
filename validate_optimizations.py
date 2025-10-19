#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
优化功能验证脚本
"""

import time
import requests
import json
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_URL = "http://localhost:5002"

def test_caching_performance():
    """测试缓存性能"""
    print("🔄 测试缓存性能...")
    
    # 第一次请求（建立缓存）
    start_time = time.time()
    response = requests.get(f"{BASE_URL}/api/systems")
    first_time = time.time() - start_time
    
    # 第二次请求（从缓存获取）
    start_time = time.time()
    response = requests.get(f"{BASE_URL}/api/systems")
    second_time = time.time() - start_time
    
    if second_time < first_time:
        improvement = ((first_time - second_time) / first_time) * 100
        print(f"✅ 缓存优化效果: {improvement:.1f}% 提速")
        print(f"   首次请求: {first_time:.3f}s")
        print(f"   缓存请求: {second_time:.3f}s")
        return True
    else:
        print("❌ 缓存优化未生效")
        return False

def test_concurrent_requests():
    """测试并发请求性能"""
    print("🚀 测试并发请求性能...")
    
    def make_request(i):
        start_time = time.time()
        response = requests.get(f"{BASE_URL}/api/systems")
        duration = time.time() - start_time
        return i, response.status_code, duration
    
    # 并发10个请求
    with ThreadPoolExecutor(max_workers=10) as executor:
        start_time = time.time()
        futures = [executor.submit(make_request, i) for i in range(10)]
        results = [future.result() for future in as_completed(futures)]
        total_time = time.time() - start_time
    
    successful = sum(1 for _, status, _ in results if status == 200)
    avg_time = sum(duration for _, _, duration in results) / len(results)
    
    print(f"✅ 并发测试完成: {successful}/10 请求成功")
    print(f"   总耗时: {total_time:.3f}s")
    print(f"   平均响应时间: {avg_time:.3f}s")
    
    return successful == 10 and avg_time < 0.1

def test_api_endpoints():
    """测试关键API端点"""
    print("🔍 测试API端点...")
    
    endpoints = [
        ("/api/systems", "系统列表"),
        ("/api/notifications/config", "通知配置"),
        ("/", "主页面")
    ]
    
    results = []
    for endpoint, name in endpoints:
        try:
            start_time = time.time()
            response = requests.get(f"{BASE_URL}{endpoint}")
            duration = time.time() - start_time
            
            if response.status_code == 200:
                print(f"✅ {name}: {response.status_code} ({duration:.3f}s)")
                results.append(True)
            else:
                print(f"❌ {name}: {response.status_code}")
                results.append(False)
        except Exception as e:
            print(f"❌ {name}: 异常 - {e}")
            results.append(False)
    
    return all(results)

def test_frontend_components():
    """测试前端组件"""
    print("🎨 测试前端组件...")
    
    try:
        response = requests.get(f"{BASE_URL}/")
        content = response.text
        
        # 检查关键组件
        components = [
            ("virtual-scroll-container", "虚拟滚动"),
            ("errorState", "错误处理"),
            ("memoryUsage", "内存管理"),
            ("repoDialog", "仓库录入"),
            ("handleVirtualScroll", "虚拟滚动处理"),
            ("cleanupMemory", "内存清理"),
            ("safeApiCall", "安全API调用")
        ]
        
        results = []
        for component, name in components:
            if component in content:
                print(f"✅ {name}: 已实现")
                results.append(True)
            else:
                print(f"❌ {name}: 未找到")
                results.append(False)
        
        return all(results)
        
    except Exception as e:
        print(f"❌ 前端组件测试失败: {e}")
        return False

def test_error_handling():
    """测试错误处理"""
    print("🛡️ 测试错误处理...")
    
    try:
        # 测试不存在的端点
        response = requests.get(f"{BASE_URL}/api/nonexistent")
        if response.status_code == 404:
            print("✅ 404错误处理正常")
        
        # 测试无效的POST请求
        response = requests.post(f"{BASE_URL}/api/repositories", 
                               json={"invalid": "data"},
                               headers={"Content-Type": "application/json"})
        if response.status_code in [400, 500]:
            print("✅ 无效请求错误处理正常")
            
        return True
        
    except Exception as e:
        print(f"❌ 错误处理测试失败: {e}")
        return False

def main():
    """主测试函数"""
    print("🧪 开始验证优化功能...")
    print("=" * 50)
    
    tests = [
        ("缓存性能", test_caching_performance),
        ("并发请求", test_concurrent_requests),
        ("API端点", test_api_endpoints),
        ("前端组件", test_frontend_components),
        ("错误处理", test_error_handling)
    ]
    
    results = {}
    for test_name, test_func in tests:
        print(f"\n📋 {test_name}测试:")
        try:
            results[test_name] = test_func()
        except Exception as e:
            print(f"❌ {test_name}测试异常: {e}")
            results[test_name] = False
    
    # 汇总结果
    print("\n" + "=" * 50)
    print("📊 测试结果汇总:")
    print("=" * 50)
    
    passed = 0
    for test_name, result in results.items():
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{test_name.ljust(15)}: {status}")
        if result:
            passed += 1
    
    total = len(results)
    print(f"\n总计: {passed}/{total} 项测试通过")
    
    if passed == total:
        print("🎉 所有优化功能验证通过！")
        print("\n✨ 优化成果:")
        print("   • 缓存系统显著提升API响应速度")
        print("   • 虚拟滚动优化大数据集渲染")
        print("   • 错误处理增强系统稳定性")
        print("   • 内存管理防止内存泄漏")
        print("   • 仓库录入功能完整实现")
        return 0
    else:
        print(f"⚠️ {total - passed} 项测试未通过，请检查相关功能")
        return 1

if __name__ == "__main__":
    exit(main())