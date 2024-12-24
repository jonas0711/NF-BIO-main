# sweetspot_app.spec
# -*- mode: python ; coding: utf-8 -*-

import sys
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules
import certifi

block_cipher = None

# Dynamisk base path
base_path = os.path.abspath('.')

added_files = [
    (os.path.join(base_path, 'sweetspot_logo.ico'), '.'),
    (os.path.join(base_path, 'dropbox_icon.png'), '.'),
    (os.path.join(base_path, 'config.py'), '.'),
    (os.path.join(base_path, 'crypt.py'), '.'),
    (os.path.join(base_path, 'secure_dropbox_auth.py'), '.'),
    (certifi.where(), '.'),  # Brug certifi.where() til at finde cacert.pem
]

hidden_imports = collect_submodules('dropbox') + [
    'numpy',
    'pandas',
    'PyQt5',
    'fitz',
    'sqlite3',
    'cryptography',
    'appdirs',
    'tempfile',
    'sip',  # Tilføjet 'sip' for at løse hidden import advarsel
    'jinja2',
    'jinja2.ext',
    'pytz',
    'tzdata',
]

# Indsaml datafiler fra fitz (PyMuPDF), hvis nødvendigt
fitz_data_files = collect_data_files('fitz')

a = Analysis(
    [os.path.join(base_path, 'app.py')],
    pathex=[base_path],
    binaries=[],
    datas=added_files + fitz_data_files,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Sweetspot Data Håndtering',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(base_path, 'sweetspot_logo.ico'),
    version='file_version_info.txt',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Sweetspot Data Håndtering',
    destdir=os.path.join('dist', 'Sweetspot Data Håndtering')  # Angiv destdir
)
