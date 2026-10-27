# Build on macOS. PyInstaller includes the interpreter, Tcl/Tk and dependencies.
import os

a = Analysis(['boro_ocr.py'], pathex=[], binaries=[], datas=[],
             hiddenimports=['PIL._tkinter_finder'], hookspath=[], hooksconfig={},
             runtime_hooks=[], excludes=[])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='BoroOCR',
          debug=False, bootloader_ignore_signals=False, strip=False,
          upx=False, console=False, argv_emulation=False,
          target_arch=os.environ.get('BUILD_ARCH'), codesign_identity=None,
          entitlements_file=None)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='BoroOCR')
app = BUNDLE(coll, name='BoroOCR.app', icon=None,
             bundle_identifier='studio.rainy.boroocr',
             info_plist={
                 'CFBundleDisplayName': 'BoroOCR',
                 'CFBundleShortVersionString': '0.1.0',
                 'CFBundleVersion': os.environ.get('GITHUB_RUN_NUMBER', '1'),
                 'NSHighResolutionCapable': True,
                 'LSMinimumSystemVersion': '15.0',
                 'NSScreenCaptureUsageDescription': 'BoroOCR captures the selected question region to analyze it with Groq AI.'
             })
