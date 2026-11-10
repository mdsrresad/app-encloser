#!/bin/sh
set -e
PREFIX="${HOME}/.local"
BIN_DIR="${PREFIX}/bin"
USER_SITE="$(python3 -m site --user-site 2>/dev/null || echo "${PREFIX}/lib/python3/site-packages")"
LIB_DIR="${USER_SITE}/app_encloser"
APP_DIR="${PREFIX}/share/applications"
ICON_DIR="${PREFIX}/share/icons/hicolor"

mkdir -p "${BIN_DIR}" "${LIB_DIR}" "${APP_DIR}"

rm -rf "${LIB_DIR}"
mkdir -p "${LIB_DIR}"
cp -r src/app_encloser/* "${LIB_DIR}/"
cp debian/usr/bin/app-encloser "${BIN_DIR}/app-encloser"
chmod +x "${BIN_DIR}/app-encloser"

sed "s|Exec=/usr/bin/app-encloser|Exec=${BIN_DIR}/app-encloser|" debian/usr/share/applications/app.encloser.desktop > "${APP_DIR}/app.encloser.desktop"

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

echo "App Encloser installed successfully to ${BIN_DIR}/app-encloser"
