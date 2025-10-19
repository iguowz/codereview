# -*- coding: utf-8 -*-
"""
高级缓存管理器 - 支持多级缓存、智能过期、压缩等高级功能
"""

import time
import threading
import heapq
import pickle
import gzip
import sys
from typing import Any, Dict, Optional, Callable, List, Tuple
from functools import wraps
from collections import OrderedDict, defaultdict
from ..logger import debug, info, warning

class AdvancedCacheManager:
    """高级缓存管理器 - 支持多级缓存和智能优化"""
    
    def __init__(self, 
                 default_ttl: int = 300,
                 max_memory_size: int = 100 * 1024 * 1024,  # 100MB
                 compression_threshold: int = 1024,  # 1KB
                 enable_statistics: bool = True):
        """
        初始化高级缓存管理器
        
        Args:
            default_ttl: 默认TTL（秒）
            max_memory_size: 最大内存使用量（字节）
            compression_threshold: 压缩阈值（字节）
            enable_statistics: 是否启用统计
        """
        self.default_ttl = default_ttl
        self.max_memory_size = max_memory_size
        self.compression_threshold = compression_threshold
        self.enable_statistics = enable_statistics
        
        # 多级缓存存储
        self.l1_cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()  # 热数据
        self.l2_cache: Dict[str, Dict[str, Any]] = {}  # 压缩数据
        
        # 访问统计
        self.access_freq: Dict[str, int] = defaultdict(int)
        self.access_time: Dict[str, float] = {}
        self.size_tracker: Dict[str, int] = {}
        
        # 过期队列 (time, key)
        self.expiry_heap: List[Tuple[float, str]] = []
        
        # 锁和统计
        self.lock = threading.RLock()
        self.stats = {
            'l1_hits': 0, 'l1_misses': 0,
            'l2_hits': 0, 'l2_misses': 0,
            'sets': 0, 'deletes': 0, 'evictions': 0,
            'compressions': 0, 'decompressions': 0,
            'memory_usage': 0, 'l1_size': 0, 'l2_size': 0
        }
        
        # 启动后台清理线程
        self._start_cleanup_thread()
    
    def _estimate_size(self, obj: Any) -> int:
        """估算对象内存大小"""
        try:
            return len(pickle.dumps(obj))
        except:
            return sys.getsizeof(obj)
    
    def _compress_data(self, data: Any) -> bytes:
        """压缩数据"""
        try:
            pickled = pickle.dumps(data)
            if len(pickled) > self.compression_threshold:
                compressed = gzip.compress(pickled)
                self.stats['compressions'] += 1
                return compressed
            return pickled
        except Exception as e:
            warning(f"数据压缩失败: {e}")
            return pickle.dumps(data)
    
    def _decompress_data(self, data: bytes) -> Any:
        """解压缩数据"""
        try:
            # 尝试解压缩
            if data[:2] == b'\x1f\x8b':  # gzip magic number
                decompressed = gzip.decompress(data)
                self.stats['decompressions'] += 1
                return pickle.loads(decompressed)
            else:
                return pickle.loads(data)
        except Exception as e:
            warning(f"数据解压缩失败: {e}")
            raise
    
    def _promote_to_l1(self, key: str) -> bool:
        """将数据从L2提升到L1"""
        if key in self.l2_cache and key not in self.l1_cache:
            l2_entry = self.l2_cache[key]
            
            # 检查是否过期
            if time.time() > l2_entry['expires']:
                del self.l2_cache[key]
                return False
            
            # 解压缩数据
            try:
                value = self._decompress_data(l2_entry['compressed_value'])
                l1_entry = {
                    'value': value,
                    'expires': l2_entry['expires'],
                    'compressed': False,
                    'size': self._estimate_size(value)
                }
                
                # 检查L1空间
                if self._can_fit_in_l1(l1_entry['size']):
                    self.l1_cache[key] = l1_entry
                    self.size_tracker[key] = l1_entry['size']
                    del self.l2_cache[key]
                    self._update_stats()
                    return True
                    
            except Exception as e:
                warning(f"L2到L1提升失败: {e}")
                del self.l2_cache[key]
        
        return False
    
    def _demote_to_l2(self, key: str) -> bool:
        """将数据从L1降级到L2"""
        if key in self.l1_cache:
            l1_entry = self.l1_cache[key]
            
            # 压缩并存储到L2
            try:
                compressed_value = self._compress_data(l1_entry['value'])
                l2_entry = {
                    'compressed_value': compressed_value,
                    'expires': l1_entry['expires'],
                    'compressed': True,
                    'size': len(compressed_value)
                }
                
                self.l2_cache[key] = l2_entry
                del self.l1_cache[key]
                if key in self.size_tracker:
                    del self.size_tracker[key]
                self._update_stats()
                return True
                
            except Exception as e:
                warning(f"L1到L2降级失败: {e}")
        
        return False
    
    def _can_fit_in_l1(self, size: int) -> bool:
        """检查是否可以放入L1缓存"""
        current_l1_size = sum(self.size_tracker.values())
        return current_l1_size + size <= self.max_memory_size * 0.7  # L1使用70%内存
    
    def _evict_lru_from_l1(self) -> bool:
        """从L1中驱逐最少使用的项"""
        if not self.l1_cache:
            return False
        
        # 找到最少访问的项
        lru_key = None
        min_score = float('inf')
        current_time = time.time()
        
        for key in self.l1_cache:
            freq = self.access_freq.get(key, 1)
            last_access = self.access_time.get(key, 0)
            # 综合考虑频率和时间的评分
            score = freq / (current_time - last_access + 1)
            
            if score < min_score:
                min_score = score
                lru_key = key
        
        if lru_key:
            if self._demote_to_l2(lru_key):
                self.stats['evictions'] += 1
                return True
            else:
                del self.l1_cache[lru_key]
                if lru_key in self.size_tracker:
                    del self.size_tracker[lru_key]
                self.stats['evictions'] += 1
                return True
        
        return False
    
    def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        current_time = time.time()
        
        with self.lock:
            # 更新访问统计
            if self.enable_statistics:
                self.access_freq[key] += 1
                self.access_time[key] = current_time
            
            # 首先检查L1缓存
            if key in self.l1_cache:
                entry = self.l1_cache[key]
                if current_time <= entry['expires']:
                    # 移动到最新位置（LRU）
                    self.l1_cache.move_to_end(key)
                    self.stats['l1_hits'] += 1
                    return entry['value']
                else:
                    # 过期，删除
                    del self.l1_cache[key]
                    if key in self.size_tracker:
                        del self.size_tracker[key]
            
            self.stats['l1_misses'] += 1
            
            # 检查L2缓存
            if key in self.l2_cache:
                entry = self.l2_cache[key]
                if current_time <= entry['expires']:
                    # 提升到L1
                    if self._promote_to_l1(key):
                        self.stats['l2_hits'] += 1
                        return self.l1_cache[key]['value']
                    else:
                        # 直接从L2返回
                        value = self._decompress_data(entry['compressed_value'])
                        self.stats['l2_hits'] += 1
                        return value
                else:
                    # 过期，删除
                    del self.l2_cache[key]
            
            self.stats['l2_misses'] += 1
            return None
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """设置缓存值"""
        ttl = ttl or self.default_ttl
        expires = time.time() + ttl
        size = self._estimate_size(value)
        
        with self.lock:
            # 删除旧值
            self.delete(key)
            
            # 创建条目
            entry = {
                'value': value,
                'expires': expires,
                'compressed': False,
                'size': size
            }
            
            # 尝试放入L1
            if self._can_fit_in_l1(size):
                # 确保有足够空间
                while not self._can_fit_in_l1(size) and self.l1_cache:
                    if not self._evict_lru_from_l1():
                        break
                
                self.l1_cache[key] = entry
                self.size_tracker[key] = size
            else:
                # 直接放入L2
                try:
                    compressed_value = self._compress_data(value)
                    l2_entry = {
                        'compressed_value': compressed_value,
                        'expires': expires,
                        'compressed': True,
                        'size': len(compressed_value)
                    }
                    self.l2_cache[key] = l2_entry
                except Exception:
                    # 压缩失败，尝试放入L1
                    while not self._can_fit_in_l1(size) and self.l1_cache:
                        if not self._evict_lru_from_l1():
                            break
                    if self._can_fit_in_l1(size):
                        self.l1_cache[key] = entry
                        self.size_tracker[key] = size
            
            # 添加到过期堆
            heapq.heappush(self.expiry_heap, (expires, key))
            
            self.stats['sets'] += 1
            self._update_stats()
    
    def delete(self, key: str) -> bool:
        """删除缓存项"""
        with self.lock:
            deleted = False
            
            if key in self.l1_cache:
                del self.l1_cache[key]
                if key in self.size_tracker:
                    del self.size_tracker[key]
                deleted = True
            
            if key in self.l2_cache:
                del self.l2_cache[key]
                deleted = True
            
            if key in self.access_freq:
                del self.access_freq[key]
            if key in self.access_time:
                del self.access_time[key]
            
            if deleted:
                self.stats['deletes'] += 1
                self._update_stats()
            
            return deleted
    
    def clear(self) -> None:
        """清空所有缓存"""
        with self.lock:
            self.l1_cache.clear()
            self.l2_cache.clear()
            self.access_freq.clear()
            self.access_time.clear()
            self.size_tracker.clear()
            self.expiry_heap.clear()
            self._update_stats()
    
    def _update_stats(self) -> None:
        """更新统计信息"""
        if self.enable_statistics:
            self.stats['l1_size'] = len(self.l1_cache)
            self.stats['l2_size'] = len(self.l2_cache)
            self.stats['memory_usage'] = sum(self.size_tracker.values())
    
    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        with self.lock:
            self._update_stats()
            total_requests = (self.stats['l1_hits'] + self.stats['l1_misses'] + 
                            self.stats['l2_hits'] + self.stats['l2_misses'])
            hit_rate = 0
            if total_requests > 0:
                hit_rate = ((self.stats['l1_hits'] + self.stats['l2_hits']) / total_requests) * 100
            
            return {
                **self.stats,
                'hit_rate': f"{hit_rate:.1f}%",
                'total_items': self.stats['l1_size'] + self.stats['l2_size'],
                'memory_usage_mb': self.stats['memory_usage'] / (1024 * 1024),
                'compression_ratio': (self.stats['compressions'] / max(self.stats['sets'], 1)) * 100
            }
    
    def _cleanup_expired(self) -> int:
        """清理过期缓存"""
        current_time = time.time()
        cleaned = 0
        
        with self.lock:
            # 从过期堆中清理
            while self.expiry_heap and self.expiry_heap[0][0] <= current_time:
                expires, key = heapq.heappop(self.expiry_heap)
                
                # 检查是否真的过期（可能已经被更新）
                if ((key in self.l1_cache and self.l1_cache[key]['expires'] <= current_time) or
                    (key in self.l2_cache and self.l2_cache[key]['expires'] <= current_time)):
                    
                    if self.delete(key):
                        cleaned += 1
            
            self._update_stats()
        
        return cleaned
    
    def _start_cleanup_thread(self) -> None:
        """启动后台清理线程"""
        def cleanup_worker():
            while True:
                try:
                    time.sleep(60)  # 每分钟清理一次
                    cleaned = self._cleanup_expired()
                    if cleaned > 0:
                        debug(f"清理了 {cleaned} 个过期缓存项")
                except Exception as e:
                    warning(f"缓存清理线程异常: {e}")
        
        cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True)
        cleanup_thread.start()

# 全局高级缓存实例
advanced_cache = AdvancedCacheManager()

def cache_with_fallback(ttl: int = 300, fallback_ttl: int = 3600):
    """
    带降级的缓存装饰器
    
    Args:
        ttl: 正常TTL
        fallback_ttl: 降级TTL（用于异常时）
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # 生成缓存键
            cache_key = f"{func.__name__}:{hash(str(args) + str(sorted(kwargs.items())))}"
            
            # 尝试获取缓存
            cached_result = advanced_cache.get(cache_key)
            if cached_result is not None:
                return cached_result
            
            try:
                # 执行函数
                result = func(*args, **kwargs)
                advanced_cache.set(cache_key, result, ttl)
                return result
            except Exception as e:
                # 尝试获取降级缓存
                fallback_key = f"{cache_key}:fallback"
                fallback_result = advanced_cache.get(fallback_key)
                
                if fallback_result is not None:
                    warning(f"使用降级缓存: {func.__name__}")
                    return fallback_result
                
                # 如果有之前的成功结果，保存为降级缓存
                if cached_result is None:
                    try:
                        result = func(*args, **kwargs)
                        advanced_cache.set(fallback_key, result, fallback_ttl)
                        advanced_cache.set(cache_key, result, ttl)
                        return result
                    except:
                        pass
                
                raise e
        
        return wrapper
    return decorator