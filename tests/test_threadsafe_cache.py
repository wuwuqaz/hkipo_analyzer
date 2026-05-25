"""ThreadSafeLRUCache 并发安全验证."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import threading
from ipo_analyzer._threadsafe_cache import ThreadSafeLRUCache


def test_basic_get_put():
    cache = ThreadSafeLRUCache(maxsize=4)
    cache.put("a", 1)
    assert cache.get("a") == 1
    assert cache.get("missing") is None


def test_lru_eviction():
    cache = ThreadSafeLRUCache(maxsize=3)
    cache.put("a", 1)
    cache.put("b", 2)
    cache.put("c", 3)
    cache.put("d", 4)
    assert cache.get("a") is None
    assert cache.get("d") == 4


def test_invalidate():
    cache = ThreadSafeLRUCache()
    cache.put("a", 1)
    cache.invalidate("a")
    assert cache.get("a") is None


def test_clear():
    cache = ThreadSafeLRUCache()
    cache.put("a", 1)
    cache.put("b", 2)
    cache.clear()
    assert len(cache) == 0


def test_concurrent_access():
    cache = ThreadSafeLRUCache(maxsize=128)
    errors = []

    def writer(start, count):
        try:
            for i in range(start, start + count):
                cache.put(f"key_{i}", i)
        except Exception as e:
            errors.append(e)

    def reader(start, count):
        try:
            for i in range(start, start + count):
                cache.get(f"key_{i}")
        except Exception as e:
            errors.append(e)

    threads = [
        threading.Thread(target=writer, args=(0, 500)),
        threading.Thread(target=writer, args=(500, 500)),
        threading.Thread(target=reader, args=(0, 500)),
        threading.Thread(target=reader, args=(250, 500)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0, f"并发错误: {errors}"


def test_len_and_contains():
    cache = ThreadSafeLRUCache(maxsize=10)
    cache.put("x", 1)
    cache.put("y", 2)
    assert len(cache) == 2
    assert "x" in cache
    assert "z" not in cache


def test_update_existing_key():
    cache = ThreadSafeLRUCache(maxsize=3)
    cache.put("a", 1)
    cache.put("a", 2)
    assert cache.get("a") == 2
    assert len(cache) == 1
