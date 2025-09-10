from functools import wraps
from typing import Callable


class ParamStore:
    _instance = None
    
    def __new__(cls, external_dict=None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._store = dict(external_dict) if external_dict else {}
        return cls._instance
    
    def __init__(self, external_dict=None):
        if not hasattr(self, '_initialized'):
            self._store = dict(external_dict) if external_dict else {}
            self._initialized = True
    
    def persist(self, key: str):
        def decorator(func: Callable):
            @wraps(func)
            def wrapper(*args, **kwargs):
                result = func(*args, **kwargs)
                self._store[key] = result
                return result
            return wrapper
        return decorator

    def get(self, key: str):
        return self._store.get(key)

    def has(self, key: str) -> bool:
        return key in self._store

    def all(self) -> dict:
        return dict(self._store)

paramstore = ParamStore()