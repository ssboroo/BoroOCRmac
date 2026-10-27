#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
[[ "$(uname -s)" == Darwin ]]
export BUILD_ARCH="${BUILD_ARCH:-$(uname -m)}"
python -m PyInstaller --clean --noconfirm BoroOCR.spec
codesign --verify --deep --strict dist/BoroOCR.app
python scripts/verify_bundle.py
mkdir -p dmg-stage
cp -R dist/BoroOCR.app dmg-stage/
ln -s /Applications dmg-stage/Applications
cp INSTALL.txt dmg-stage/
hdiutil create -volname BoroOCR -srcfolder dmg-stage -ov -format UDZO "dist/BoroOCR-${BUILD_ARCH}.dmg"
hdiutil verify "dist/BoroOCR-${BUILD_ARCH}.dmg"
shasum -a 256 "dist/BoroOCR-${BUILD_ARCH}.dmg" > "dist/BoroOCR-${BUILD_ARCH}.dmg.sha256"
