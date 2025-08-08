import os
import pickle


class LocalKeyVault:

    VAULT_FILE = "key\\local_key_vault.pkl"

    def __init__(self):
        os.makedirs(os.path.dirname(self.VAULT_FILE), exist_ok=True)
        if not os.path.exists(self.VAULT_FILE):
            with open(self.VAULT_FILE, "wb") as f:
                pickle.dump({}, f)

    def _load_vault(self) -> dict:
        try:
            with open(self.VAULT_FILE, "rb") as f:
                return pickle.load(f)
        except (EOFError, pickle.UnpicklingError):
            return {}

    def _save_vault(self, data: dict):
        with open(self.VAULT_FILE, "wb") as f:
            pickle.dump(data, f)

    def store(self, new_data: dict):
        vault = self._load_vault()
        vault.update(new_data)
        self._save_vault(vault)

    def retrieve(self, key: str):
        vault = self._load_vault()
        return vault.get(key)

    def contains(self, key: str) -> bool:
        vault = self._load_vault()
        return key in vault
