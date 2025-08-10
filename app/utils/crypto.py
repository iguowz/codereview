from cryptography.fernet import Fernet
import base64
import os

class CryptoManager:
    def __init__(self, key=None):
        if key is None:
            # 从环境变量获取密钥，如果没有则生成新的
            key = os.environ.get('CRYPTO_KEY')
            if key is None:
                key = Fernet.generate_key()
                # Generated new crypto key
        
        if isinstance(key, str):
            key = key.encode()
        
        self.cipher = Fernet(key)
    
    def encrypt(self, data):
        """加密数据"""
        if isinstance(data, str):
            data = data.encode()
        return self.cipher.encrypt(data).decode()
    
    def decrypt(self, encrypted_data):
        """解密数据"""
        if isinstance(encrypted_data, str):
            encrypted_data = encrypted_data.encode()
        return self.cipher.decrypt(encrypted_data).decode()
