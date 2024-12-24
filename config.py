from crypt import encrypt_data, decrypt_data
import os
import appdirs

def get_user_data_dir():
    return appdirs.user_data_dir("Sweetspot Data Håndtering", "Nordisk Film Biografer")

# Dropbox konfiguration
_DROPBOX_APP_KEY = encrypt_data("8uiiz6ri4vf8xu3")
_DROPBOX_APP_SECRET = encrypt_data("gewungrlcrgqi9c")
_DROPBOX_REFRESH_TOKEN = encrypt_data("lxt4Ys5AalkAAAAAAAAAAX5UhLtDU22LLpUdUtIEcRELhXJIynW9ACkaSnb0X-7M")

def get_dropbox_app_key():
    return decrypt_data(_DROPBOX_APP_KEY)

def get_dropbox_app_secret():
    return decrypt_data(_DROPBOX_APP_SECRET)

def get_dropbox_refresh_token():
    return decrypt_data(_DROPBOX_REFRESH_TOKEN)

# Database konfiguration
DATABASE_PATH = os.path.join(get_user_data_dir(), "products.db")

# GUI konfiguration
WINDOW_TITLE = "Nordisk Film Biografer Produktstyring - Aalborg City Syd"
WINDOW_WIDTH = 1000
WINDOW_HEIGHT = 800

# Filtrer muligheder
FILTER_OPTIONS = ["Alle", "SKU", "Article Description", "ID", "EAN", "Expiry Date"]