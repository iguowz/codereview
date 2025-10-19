# -*- coding: utf-8 -*-
"""
文件缓存管理器 - 优化文件IO性能
"""

import asyncio
import aiofiles
import hashlib
import json
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import threading
import time

class FileCache:
    """文件缓存管理器"""
    
    def __init__(self, cache_dir: str = "cache", ttl: int = 3600):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self.ttl = ttl
        self._memory_cache = {}
        self._lock = threading.RLock()
        self._stats = {
            'hits': 0,
            'misses': 0,
            'file_reads': 0,
            'file_writes': 0
        }
    
    def _get_cache_key(self, key: str) -> str:
        """生成缓存键的哈希值"""
        return hashlib.md5(key.encode()).hexdigest()
    
    def _get_cache_path(self, cache_key: str) -> Path:
        """获取缓存文件路径"""
        return self.cache_dir / f"{cache_key}.json"
    
    def _is_expired(self, cache_data: Dict[str, Any]) -> bool:
        """检查缓存是否过期"""
        created_at = datetime.fromisoformat(cache_data.get('created_at', '1970-01-01'))
        return datetime.now() - created_at > timedelta(seconds=self.ttl)
    
    def get(self, key: str) -> Optional[Any]:
        """获取缓存数据"""
        with self._lock:
            # 先检查内存缓存
            if key in self._memory_cache:
                cache_data = self._memory_cache[key]
                if not self._is_expired(cache_data):
                    self._stats['hits'] += 1
                    return cache_data['data']
                else:
                    del self._memory_cache[key]
            
            # 检查文件缓存
            cache_key = self._get_cache_key(key)
            cache_path = self._get_cache_path(cache_key)
            
            if cache_path.exists():
                try:
                    with open(cache_path, 'r', encoding='utf-8') as f:
                        cache_data = json.load(f)
                    
                    self._stats['file_reads'] += 1
                    
                    if not self._is_expired(cache_data):
                        # 加载到内存缓存
                        self._memory_cache[key] = cache_data
                        self._stats['hits'] += 1
                        return cache_data['data']
                    else:
                        # 删除过期文件
                        cache_path.unlink(missing_ok=True)
                
                except (json.JSONDecodeError, IOError):
                    cache_path.unlink(missing_ok=True)
            
            self._stats['misses'] += 1
            return None
    
    def set(self, key: str, data: Any, ttl: Optional[int] = None) -> None:
        """设置缓存数据"""
        with self._lock:
            cache_ttl = ttl or self.ttl
            cache_data = {
                'data': data,
                'created_at': datetime.now().isoformat(),
                'ttl': cache_ttl
            }
            
            # 保存到内存缓存
            self._memory_cache[key] = cache_data
            
            # 异步保存到文件
            cache_key = self._get_cache_key(key)
            cache_path = self._get_cache_path(cache_key)
            
            # 使用线程池异步写入文件，避免阻塞
            threading.Thread(
                target=self._write_cache_file,
                args=(cache_path, cache_data),
                daemon=True
            ).start()
    
    def _write_cache_file(self, cache_path: Path, cache_data: Dict[str, Any]) -> None:
        """异步写入缓存文件"""
        try:
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
            self._stats['file_writes'] += 1
        except Exception:
            # 写入失败时静默忽略，不影响主流程
            pass
    
    def delete(self, key: str) -> bool:
        """删除缓存"""
        with self._lock:
            # 删除内存缓存
            if key in self._memory_cache:
                del self._memory_cache[key]
            
            # 删除文件缓存
            cache_key = self._get_cache_key(key)
            cache_path = self._get_cache_path(cache_key)
            
            if cache_path.exists():
                cache_path.unlink()
                return True
            
            return False
    
    def clear(self) -> None:
        """清空所有缓存"""
        with self._lock:
            self._memory_cache.clear()
            
            # 删除所有缓存文件
            for cache_file in self.cache_dir.glob("*.json"):
                cache_file.unlink(missing_ok=True)
    
    def stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        with self._lock:
            total_requests = self._stats['hits'] + self._stats['misses']
            hit_rate = (self._stats['hits'] / total_requests * 100) if total_requests > 0 else 0
            
            return {
                'hits': self._stats['hits'],
                'misses': self._stats['misses'],
                'hit_rate': f"{hit_rate:.1f}%",
                'file_reads': self._stats['file_reads'],
                'file_writes': self._stats['file_writes'],
                'memory_cache_size': len(self._memory_cache),
                'disk_cache_files': len(list(self.cache_dir.glob("*.json")))
            }
    
    def cleanup_expired(self) -> int:
        """清理过期缓存"""
        with self._lock:
            cleaned_count = 0
            
            # 清理内存缓存
            expired_keys = []
            for key, cache_data in self._memory_cache.items():
                if self._is_expired(cache_data):
                    expired_keys.append(key)
            
            for key in expired_keys:
                del self._memory_cache[key]
                cleaned_count += 1
            
            # 清理文件缓存
            for cache_file in self.cache_dir.glob("*.json"):
                try:
                    with open(cache_file, 'r', encoding='utf-8') as f:
                        cache_data = json.load(f)
                    
                    if self._is_expired(cache_data):
                        cache_file.unlink()
                        cleaned_count += 1
                        
                except (json.JSONDecodeError, IOError):
                    cache_file.unlink()
                    cleaned_count += 1
            
            return cleaned_count

# 全局文件缓存实例
file_cache = FileCache()

class AsyncConfigLoader:
    """异步配置加载器"""
    
    @staticmethod
    async def load_yaml_async(file_path: Path) -> Optional[Dict[str, Any]]:
        """异步加载YAML文件"""
        try:
            async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
                content = await f.read()
            
            # 在线程池中解析YAML，避免阻塞事件循环
            import yaml
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(None, yaml.safe_load, content)
            
            return data or {}
        except Exception:
            return None
    
    @staticmethod
    async def save_yaml_async(file_path: Path, data: Dict[str, Any]) -> bool:
        """异步保存YAML文件"""
        try:
            import yaml
            loop = asyncio.get_event_loop()
            
            # 在线程池中序列化YAML
            content = await loop.run_in_executor(
                None, 
                lambda: yaml.safe_dump(data, default_flow_style=False, allow_unicode=True, indent=2)
            )
            
            # 异步写入文件
            async with aiofiles.open(file_path, 'w', encoding='utf-8') as f:
                await f.write(content)
            
            return True
        except Exception:
            return False
    
    @staticmethod
    async def load_multiple_configs(file_paths: List[Path]) -> Dict[str, Optional[Dict[str, Any]]]:
        """并发加载多个配置文件"""
        tasks = {
            str(path): AsyncConfigLoader.load_yaml_async(path) 
            for path in file_paths
        }
        
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        
        return {
            path: result if not isinstance(result, Exception) else None
            for path, result in zip(tasks.keys(), results)
        }

# 批量操作工具
class BatchProcessor:
    """批量处理器"""
    
    def __init__(self, batch_size: int = 100):
        self.batch_size = batch_size
    
    def process_in_batches(self, items: List[Any], processor_func) -> List[Any]:
        """批量处理数据"""
        results = []
        
        for i in range(0, len(items), self.batch_size):
            batch = items[i:i + self.batch_size]
            batch_results = processor_func(batch)
            results.extend(batch_results)
        
        return results
    
    async def process_in_batches_async(self, items: List[Any], processor_func) -> List[Any]:
        """异步批量处理数据"""
        results = []
        
        for i in range(0, len(items), self.batch_size):
            batch = items[i:i + self.batch_size]
            batch_results = await processor_func(batch)
            results.extend(batch_results)
        
        return results