import os
import shutil
import tarfile
import zipfile
import subprocess
from typing import Tuple


def safe_extract_tar(tf: tarfile.TarFile, target_dir: str):
    target_dir = os.path.abspath(target_dir)
    safe_members = []
    for member in tf.getmembers():
        dest_path = os.path.abspath(os.path.join(target_dir, member.name))
        if not dest_path.startswith(target_dir + os.sep) and dest_path != target_dir:
            raise RuntimeError(f"Security Alert: Path traversal attempt: {member.name}")
        if member.isdev() or member.ischr() or member.isblk() or member.isfifo():
            continue
        if member.issym() or member.islnk():
            link_target = os.path.abspath(os.path.join(os.path.dirname(dest_path), member.linkname))
            if not link_target.startswith(target_dir + os.sep) and link_target != target_dir:
                continue
        safe_members.append(member)
    if hasattr(tarfile, "data_filter"):
        tf.extractall(target_dir, members=safe_members, filter="data")
    else:
        tf.extractall(target_dir, members=safe_members)


def safe_extract_zip(zf: zipfile.ZipFile, target_dir: str):
    target_dir = os.path.abspath(target_dir)
    for name in zf.namelist():
        dest_path = os.path.abspath(os.path.join(target_dir, name))
        if not dest_path.startswith(target_dir + os.sep) and dest_path != target_dir:
            raise RuntimeError(f"Security Alert: Path traversal attempt: {name}")
    zf.extractall(target_dir)


def extract_deb(deb_path: str, target_dir: str) -> bool:
    try:
        subprocess.run(["dpkg-deb", "-x", deb_path, target_dir], check=True, stderr=subprocess.PIPE)
        return True
    except Exception:
        pass

    try:
        tmp_ar = os.path.join(target_dir, ".ar_tmp")
        os.makedirs(tmp_ar, exist_ok=True)
        subprocess.run(["ar", "x", os.path.abspath(deb_path)], cwd=tmp_ar, check=True)
        for f in os.listdir(tmp_ar):
            if f.startswith("data.tar"):
                full_tar = os.path.join(tmp_ar, f)
                with tarfile.open(full_tar, "r:*") as tf:
                    safe_extract_tar(tf, target_dir)
                break
        shutil.rmtree(tmp_ar, ignore_errors=True)
        return True
    except Exception:
        return False


def extract_rpm(rpm_path: str, target_dir: str) -> bool:
    try:
        abs_target = os.path.realpath(target_dir)
        os.makedirs(abs_target, exist_ok=True)
        p_list1 = subprocess.Popen(["rpm2cpio", rpm_path], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        p_list2 = subprocess.Popen(["cpio", "-t"], stdin=p_list1.stdout, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        p_list1.stdout.close()
        listing, _ = p_list2.communicate()
        if p_list2.returncode != 0:
            return False
        for raw_entry in listing.splitlines():
            entry = raw_entry.strip()
            if not entry:
                continue
            if entry.startswith(("/", "\\")) or ".." in entry.split("/"):
                return False
            dest_path = os.path.realpath(os.path.join(abs_target, entry))
            if dest_path != abs_target and not dest_path.startswith(abs_target + os.sep):
                return False
        p1 = subprocess.Popen(["rpm2cpio", rpm_path], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        p2 = subprocess.Popen(["cpio", "--no-absolute-filenames", "-idmv"], stdin=p1.stdout, cwd=abs_target, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        p1.stdout.close()
        p2.communicate()
        return p2.returncode == 0
    except Exception:
        return False


def extract_appimage(appimage_path: str, target_dir: str) -> bool:
    abs_app = os.path.abspath(appimage_path)
    target_dir = os.path.abspath(target_dir)
    os.makedirs(target_dir, exist_ok=True)

    if shutil.which("unsquashfs"):
        try:
            res = subprocess.run(
                ["unsquashfs", "-f", "-d", target_dir, abs_app],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            if res.returncode == 0 and os.listdir(target_dir):
                return True
        except Exception:
            pass

    seven_z = shutil.which("7z") or shutil.which("7za")
    if seven_z:
        try:
            res = subprocess.run(
                [seven_z, "x", "-y", f"-o{target_dir}", abs_app],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            if res.returncode == 0 and os.listdir(target_dir):
                return True
        except Exception:
            pass

    if shutil.which("bwrap"):
        try:
            os.chmod(abs_app, os.stat(abs_app).st_mode | 0o111)
            bwrap_cmd = [
                "bwrap",
                "--die-with-parent",
                "--unshare-pid",
                "--unshare-ipc",
                "--unshare-uts",
                "--ro-bind", "/", "/",
                "--dev", "/dev",
                "--proc", "/proc",
                "--tmpfs", "/tmp",
                "--tmpfs", os.path.expanduser("~"),
                "--bind", target_dir, target_dir,
                "--ro-bind", abs_app, "/tmp/app.appimage",
                "/tmp/app.appimage", "--appimage-extract"
            ]
            res = subprocess.run(bwrap_cmd, cwd=target_dir, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            squash = os.path.join(target_dir, "squashfs-root")
            if os.path.isdir(squash):
                for item in os.listdir(squash):
                    s = os.path.join(squash, item)
                    d = os.path.join(target_dir, item)
                    if os.path.exists(d):
                        if os.path.isdir(d):
                            shutil.rmtree(d, ignore_errors=True)
                        else:
                            os.remove(d)
                    shutil.move(s, d)
                shutil.rmtree(squash, ignore_errors=True)
                return True
        except Exception:
            pass

    return False


def unpack_archive(src_path: str, dest_dir: str) -> Tuple[bool, str]:
    low = src_path.lower()
    os.makedirs(dest_dir, exist_ok=True)

    if low.endswith(".deb"):
        ok = extract_deb(src_path, dest_dir)
        return (True, "DEB") if ok else (False, "Failed to extract .deb")

    if low.endswith(".rpm"):
        ok = extract_rpm(src_path, dest_dir)
        return (True, "RPM") if ok else (False, "Failed to extract .rpm")

    if low.endswith(".appimage"):
        ok = extract_appimage(src_path, dest_dir)
        return (True, "APPIMAGE") if ok else (False, "Failed to extract .AppImage")

    if any(low.endswith(ext) for ext in (".tar.gz", ".tgz", ".tar.xz", ".tar.bz2", ".tar")):
        try:
            with tarfile.open(src_path, "r:*") as tf:
                safe_extract_tar(tf, dest_dir)
            return True, "TAR.GZ"
        except Exception as e:
            return False, f"Failed to extract tar archive: {e}"

    if low.endswith(".zip") or low.endswith(".jar"):
        try:
            with zipfile.ZipFile(src_path, "r") as zf:
                safe_extract_zip(zf, dest_dir)
            return True, "ZIP"
        except Exception as e:
            return False, f"Failed to extract zip archive: {e}"

    if any(low.endswith(ext) for ext in (".sh", ".run", ".bin")):
        try:
            bin_dir = os.path.join(dest_dir, "usr", "bin")
            os.makedirs(bin_dir, exist_ok=True)
            bn = os.path.basename(src_path)
            target = os.path.join(bin_dir, bn)
            shutil.copy2(src_path, target)
            os.chmod(target, 0o755)
            return True, "SCRIPT"
        except Exception as e:
            return False, f"Failed to ingest script executable: {e}"

    return False, "Unsupported archive format"
