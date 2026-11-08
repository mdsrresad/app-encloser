#!/bin/sh
set -e
PREFIX="${HOME}/.local"
BIN_DIR="${PREFIX}/bin"
LIB_DIR="${PREFIX}/lib/python3/dist-packages/app_encloser"
APP_DIR="${PREFIX}/share/applications"
ICON_DIR="${PREFIX}/share/icons/hicolor"

mkdir -p "${BIN_DIR}" "${LIB_DIR}" "${APP_DIR}"

cp -r src/app_encloser/* "${LIB_DIR}/"
cp debian/usr/bin/app-encloser "${BIN_DIR}/app-encloser"
chmod +x "${BIN_DIR}/app-encloser"

cp debian/usr/share/applications/app.encloser.desktop "${APP_DIR}/"

for size in 16x16 24x24 32x32 48x48 64x64 128x128 256x256 512x512 scalable; do
    mkdir -p "${ICON_DIR}/${size}/apps"
    if [ "${size}" = "scalable" ]; then
        cp "debian/usr/share/icons/hicolor/${size}/apps/app-encloser.svg" "${ICON_DIR}/${size}/apps/" 2>/dev/null || true
    else
        cp "debian/usr/share/icons/hicolor/${size}/apps/app-encloser.png" "${ICON_DIR}/${size}/apps/" 2>/dev/null || true
    fi
done

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "${APP_DIR}" 2>/dev/null || true
fi

echo "App Encloser v1.0.0 installed successfully to ${BIN_DIR}/app-encloser"
