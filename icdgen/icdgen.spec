# PyInstaller spec for icdgen.
#
# Bundles the Jinja2 templates as data files. The runtime uses resources.py
# (template_dir) which resolves them whether running from source, an installed
# wheel, or a PyInstaller onefile bundle (sys._MEIPASS).
#
# The input ICD is YAML; validation uses a JSON Schema generated at load time
# from the field registry, so there is no on-disk schema file to bundle.
#
# Build:  pyinstaller icdgen.spec
# Output: dist/icdgen (single-file executable; .exe on Windows)

block_cipher = None

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Third-party packages that ship runtime data files (templates, fonts, etc.)
# which the frozen binary must carry.
_third_party_datas = (
    collect_data_files('docx')        # default.docx template + part templates
    + collect_data_files('reportlab')  # fonts and rl_settings
)

a = Analysis(
    ['run.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('icdgen/templates/header.h.j2', 'icdgen/templates'),
        ('icdgen/templates/simulink_bus.m.j2', 'icdgen/templates'),
    ] + _third_party_datas,
    hiddenimports=collect_submodules('openpyxl'),
    hookspath=[],
    runtime_hooks=['pyi_rth_docx.py'],
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
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='icdgen',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,           # UPX off: keep the binary auditable/reproducible
    runtime_tmpdir=None,
    console=True,
)