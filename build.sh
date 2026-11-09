#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(dirname "$(readlink -f "${0}")")"
cd "$SCRIPT_DIR"

export SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH:-1731110400}"
PACKAGE_ONLY=0
for arg in "$@"; do
    if [[ "$arg" == "--package-only" || "$arg" == "--no-install" ]]; then
        PACKAGE_ONLY=1
    fi
done
if [[ "${BUILD_NO_INSTALL:-0}" == "1" ]]; then
    PACKAGE_ONLY=1
fi
VERSION=$(python3 -c "import re; f=open('src/app_encloser/__init__.py'); m=re.search(r'__version__\s*=\s*[\"\']([^\"\']+)[\"\']', f.read()); print(m.group(1))")

echo "=== Building App Encloser ${VERSION} ==="

find src -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find debian -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

if command -v gcc >/dev/null 2>&1; then
    mkdir -p debian/usr/lib/app-encloser src/app_encloser/data
    gcc -fPIC -shared -O2 src/app_encloser/data/libencloser_shim.c -o debian/usr/lib/app-encloser/libencloser_shim.so -ldl
    gcc -fPIC -shared -O2 src/app_encloser/data/libencloser_shim.c -o src/app_encloser/data/libencloser_shim.so -ldl
fi

mkdir -p debian/usr/lib/python3/dist-packages/app_encloser
cp -r src/app_encloser/* debian/usr/lib/python3/dist-packages/app_encloser/
find debian/usr/lib/python3/dist-packages/app_encloser -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

echo "Packaging app-encloser_${VERSION}_all.deb..."
dpkg-deb --root-owner-group --build debian "app-encloser_${VERSION}_all.deb"

if [[ "$PACKAGE_ONLY" -eq 0 ]]; then
    REAL_HOME=$(python3 -c "import pwd, os; print(pwd.getpwuid(os.getuid()).pw_dir)")
    LOCAL_BIN="$REAL_HOME/.local/bin"
    USER_SITE=$(python3 -c "import site; print(site.getusersitepackages())")
    mkdir -p "$LOCAL_BIN" "$USER_SITE"
    rm -f "$LOCAL_BIN/app-encloser"
    cp debian/usr/bin/app-encloser "$LOCAL_BIN/app-encloser"
    chmod +x "$LOCAL_BIN/app-encloser"

    rm -rf "$USER_SITE/app_encloser"
    cp -r src/app_encloser "$USER_SITE/"
    find "$USER_SITE/app_encloser" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    echo "Updated $LOCAL_BIN/app-encloser and $USER_SITE/app_encloser"

    if [ -w /usr/bin/app-encloser ]; then
        cp debian/usr/bin/app-encloser /usr/bin/app-encloser
        chmod +x /usr/bin/app-encloser
        echo "Updated /usr/bin/app-encloser"
    elif [ -w /usr/bin ]; then
        cp debian/usr/bin/app-encloser /usr/bin/app-encloser
        chmod +x /usr/bin/app-encloser
        echo "Updated /usr/bin/app-encloser"
    else
        echo "Notice: /usr/bin/app-encloser is owned by root. $LOCAL_BIN/app-encloser will be used by current user."
    fi

    for TARGET_HOME in "$REAL_HOME" "$HOME"; do
        [ -d "$TARGET_HOME" ] || continue
        USER_BIN="$TARGET_HOME/.local/bin"
        USER_APPS="$TARGET_HOME/.local/share/applications"
        USER_ICONS="$TARGET_HOME/.local/share/icons"
        mkdir -p "$USER_BIN" "$USER_APPS" "$USER_ICONS"

        cp debian/usr/bin/app-encloser "$USER_BIN/app-encloser"
        chmod +x "$USER_BIN/app-encloser"

        rm -f "$USER_APPS/io.ubuntu.AppEncloser.desktop" "$USER_APPS/AppEncloser.desktop"

        cat > "$USER_APPS/app.encloser.desktop" <<EOF
[Desktop Entry]
Version=1.0
Name=App Encloser
Comment=Isolated Portable Application & Package Manager
Exec=$USER_BIN/app-encloser %f
Icon=app-encloser
Terminal=false
Type=Application
Categories=System;PackageManager;Utility;
MimeType=application/vnd.debian.binary-package;application/x-appimage;application/x-rpm;application/zip;application/x-compressed-tar;application/x-tar;
StartupWMClass=app.encloser
Keywords=sandbox;package;isolate;bwrap;portable;settings;
EOF
        cp -r debian/usr/share/icons/* "$USER_ICONS/" 2>/dev/null || true

        if command -v update-desktop-database >/dev/null 2>&1; then
            update-desktop-database "$USER_APPS" 2>/dev/null || true
        fi
        if command -v gtk-update-icon-cache >/dev/null 2>&1; then
            gtk-update-icon-cache -q -t -f "$USER_ICONS" 2>/dev/null || true
        fi
    done
fi

tar --sort=name --owner=root:0 --group=root:0 --mtime="@$SOURCE_DATE_EPOCH" -czf "app-encloser-${VERSION}-linux-universal.tar.gz" src debian tests build.sh install.sh LICENSE README.md SECURITY.md CHANGELOG.md CONTRIBUTING.md
sha256sum "app-encloser_${VERSION}_all.deb" "app-encloser-${VERSION}-linux-universal.tar.gz" > SHA256SUMS.txt

echo "=== Build & Installation Complete ==="
