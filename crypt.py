from cryptography.fernet import Fernet
import os

KEY_FILE = 'encryption_key.key'

def generate_key():
    return Fernet.generate_key()

def save_key(key, filename=KEY_FILE):
    with open(filename, 'wb') as key_file:
        key_file.write(key)

def load_key(filename=KEY_FILE):
    if not os.path.exists(filename):
        key = generate_key()
        save_key(key, filename)
    with open(filename, 'rb') as key_file:
        return key_file.read()

def encrypt_data(data):
    key = load_key()
    f = Fernet(key)
    return f.encrypt(data.encode())

def decrypt_data(encrypted_data):
    key = load_key()
    f = Fernet(key)
    return f.decrypt(encrypted_data).decode()

if __name__ == "__main__":
    if not os.path.exists(KEY_FILE):
        new_key = generate_key()
        save_key(new_key)
        print(f"Ny krypteringsnøgle genereret og gemt i '{KEY_FILE}'")
    else:
        print(f"Eksisterende krypteringsnøgle fundet i '{KEY_FILE}'")