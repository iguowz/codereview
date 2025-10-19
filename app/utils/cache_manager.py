# -*- coding: utf-8 -*-
"""
缓存管理器 - 提供内存缓存和性能优化
"""

import time
import threading
from typing import Any, Dict, Optional, Callable
from functools import wraps
from ..logger import debug, info


class CacheManager:
    """内存缓存管理器"""
    
    def __init__(self, default_ttl: int = 300):
        """
        初始化缓存管理器
        
        Args:
            default_ttl: 默认缓存生存时间（秒）
        """
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.default_ttl = default_ttl
        self.lock = threading.RLock()
    
    def get(self, key: str) -> Optional[Any]:
        """
        获取缓存值
        
        Args:
            key: 缓存键
            
        Returns:
            缓存值，如果不存在或已过期则返回None
        """
        with self.lock:
            if key not in self.cache:
                return None
            
            entry = self.cache[key]
            if time.time() > entry['expires']:
                del self.cache[key]
                return None
            
            return entry['value']
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """
        设置缓存值
        
        Args:
            key: 缓存键
            value: 缓存值
            ttl: 生存时间（秒），如果为None则使用默认值
        """
        if ttl is None:
            ttl = self.default_ttl
        
        with self.lock:
            self.cache[key] = {
                'value': value,
                'expires': time.time() + ttl
            }
    
    def delete(self, key: str) -> bool:
        """
        删除缓存
        
        Args:
            key: 缓存键
            
        Returns:
            是否成功删除
        """
        with self.lock:
            if key in self.cache:
                del self.cache[key]
                return True
            return False
    
    def clear(self) -> None:
        """清空所有缓存"""
        with self.lock:
            self.cache.clear()
    
    def cleanup_expired(self) -> int:
        """
        清理过期缓存
        
        Returns:
            清理的缓存数量
        """
        current_time = time.time()
        expired_keys = []
        
        with self.lock:
            for key, entry in self.cache.items():
                if current_time > entry['expires']:
                    expired_keys.append(key)
            
            for key in expired_keys:
                del self.cache[key]
        
        if expired_keys:
            debug(f"清理了 {len(expired_keys)} 个过期缓存")
        
        return len(expired_keys)
    
    def size(self) -> int:
        """获取缓存大小"""
        with self.lock:
            return len(self.cache)
    
    def stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        current_time = time.time()
        expired_count = 0
        
        with self.lock:
            total_count = len(self.cache)
            for entry in self.cache.values():
                if current_time > entry['expires']:
                    expired_count += 1
        
        return {
            'total': total_count,
            'expired': expired_count,
            'active': total_count - expired_count
        }


def cached(key_func: Callable = None, ttl: int = 300, cache_instance: CacheManager = None):
    """
    缓存装饰器
    
    Args:
        key_func: 生成缓存键的函数，如果为None则使用函数名和参数
        ttl: 缓存生存时间（秒）
        cache_instance: 缓存实例，如果为None则使用全局缓存
    """
    if cache_instance is None:
        cache_instance = global_cache
    
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # 生成缓存键
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                # 简单的键生成策略
                cache_key = f"{func.__name__}:{hash(str(args) + str(sorted(kwargs.items())))}"
            
            # 尝试从缓存获取
            result = cache_instance.get(cache_key)
            if result is not None:
                debug(f"缓存命中: {cache_key}")
                return result
            
            # 执行函数并缓存结果
            result = func(*args, **kwargs)
            cache_instance.set(cache_key, result, ttl)
            debug(f"缓存存储: {cache_key}")
            
            return result
        
        # 添加缓存管理方法
        wrapper.clear_cache = lambda: cache_instance.clear()
        wrapper.cache_stats = lambda: cache_instance.stats()
        
        return wrapper
    
    return decorator


# 全局缓存实例
global_cache = CacheManager(default_ttl=300)


class LRUCache:
    """LRU缓存实现"""
    
    def __init__(self, capacity: int = 100):
        """
        初始化LRU缓存
        
        Args:
            capacity: 缓存容量
        """
        self.capacity = capacity
        self.cache = {}
        self.order = []
        self.lock = threading.RLock()
    
    def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        with self.lock:
            if key in self.cache:
                # 移动到最新位置
                self.order.remove(key)
                self.order.append(key)
                return self.cache[key]
            return None
    
    def set(self, key: str, value: Any) -> None:
        """设置缓存值"""
        with self.lock:
            if key in self.cache:
                # 更新现有键
                self.order.remove(key)
            elif len(self.cache) >= self.capacity:
                # 移除最久未使用的键
                oldest = self.order.pop(0)
                del self.cache[oldest]
            
            self.cache[key] = value
            self.order.append(key)
    
    def delete(self, key: str) -> bool:
        """删除缓存"""
        with self.lock:
            if key in self.cache:
                del self.cache[key]
                self.order.remove(key)
                return True
            return False
    
    def clear(self) -> None:
        """清空缓存"""
        with self.lock:
            self.cache.clear()
            self.order.clear()
    
    def size(self) -> int:
        """获取缓存大小"""
        with self.lock:
            return len(self.cache)


# 全局LRU缓存实例
global_lru_cache = LRUCache(capacity=500)