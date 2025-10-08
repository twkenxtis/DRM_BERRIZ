from functools import wraps
from typing import Callable, Any, Dict, Optional, TypeVar, Type

# 定義一個 TypeVar 來表示被裝飾函式的型別以保留原始簽名資訊
F = TypeVar('F', bound=Callable[..., Any])
# 定義一個 TypeVar 來表示 ParamStore 類別本身
T = TypeVar('T', bound='ParamStore')


class ParamStore:
    # 類別變數的型別註釋
    _instance: Optional['ParamStore'] = None
    # 實例變數的型別註釋
    _store: Dict[str, Any]
    _initialized: bool

    # cls 的型別是 Type[ParamStore]但用 T 來更好地表達單例返回的實例型別
    def __new__(cls: Type[T], external_dict: Optional[Dict[str, Any]] = None) -> T:
        if cls._instance is None:
            # Type hinting for super().__new__(cls) returns an instance of T
            cls._instance = super().__new__(cls)
            # 在 __new__ 中進行初始化以確保 _store 只被建立一次
            cls._instance._store = dict(external_dict) if external_dict else {}
            # 標記已初始化以便 __init__ 跳過重複的初始化邏輯
            cls._instance._initialized = True
        return cls._instance
    
    # external_dict 的型別註釋
    def __init__(self, external_dict: Optional[Dict[str, Any]] = None) -> None:
        # 單例模式中__init__ 僅在第一次實例化時執行核心邏輯
        if not hasattr(self, '_initialized'):
            # 由於 __new__ 已經處理了 _store 的初始化和 _initialized 的設定
            self._store = dict(external_dict) if external_dict else {}
            self._initialized = True
    
    # 裝飾器的方法型別註釋
    # 接受一個 key: str回傳一個裝飾器函式 (Callable[[F], F])
    def persist(self, key: str) -> Callable[[F], F]:
        def decorator(func: F) -> F:
            # wrapper 函式的型別註釋 (使用 *args, **kwargs 來接受任意參數)
            @wraps(func)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                # result 的型別應是 func 的回傳型別使用 Any
                result: Any = func(*args, **kwargs)
                self._store[key] = result
                return result
            # 由於 @wrapswrapper 的型別被視為 F
            return wrapper
        return decorator

    # get 方法的型別註釋回傳儲存的值或 None (如果鍵不存在)
    def get(self, key: str) -> Optional[Any]:
        return self._store.get(key)

    def has(self, key: str) -> bool:
        return key in self._store

    # all 方法的型別註釋回傳一個副本 (Dict[str, Any])
    def all(self) -> Dict[str, Any]:
        return dict(self._store)

paramstore: ParamStore = ParamStore()