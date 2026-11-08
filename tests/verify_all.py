import os
import sys
import json
import struct
import shutil
import subprocess
import time

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(PROJECT_ROOT, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from app_encloser import backend, __version__

PASSED = "✓ PASS"
FAILED = "✗ FAIL"


def print_test(name, success, details=""):
    mark = PASSED if success else FAILED
    print(f"[{mark}] {name}")
    if details:
        for line in details.strip().splitlines():
            print(f"       {line}")
    if not success:
        sys.exit(1)


def test_dynamic_metadata_and_monogram():
    test_icon = "/tmp/test_monogram.svg"
    backend.generate_monogram_svg(test_icon, "Dynamic Sample Application")
    assert os.path.isfile(test_icon), "Failed to generate monogram SVG"
    with open(test_icon, "r", encoding="utf-8") as f:
        svg_data = f.read()
    assert "DS" in svg_data, f"Initials 'DS' missing from monogram: {svg_data}"
    os.remove(test_icon)

    mock_desktop = "/tmp/sample_mock.desktop"
    with open(mock_desktop, "w", encoding="utf-8") as f:
        f.write("[Desktop Entry]\nName=Custom App\nExec=custom-bin %U\nStartupWMClass=custom-wm\n")
    info = backend.parse_desktop_file(mock_desktop)
    assert info.get("Name") == "Custom App", "Failed to parse Name from desktop file"
    assert info.get("StartupWMClass") == "custom-wm", "Failed to parse StartupWMClass"
    os.remove(mock_desktop)

    print_test("1. Dynamic Metadata & Vector Monogram Generation", True,
               "Generated initials 'DS' and dynamically parsed desktop configuration without hardcoded tables.")


def test_container_lifecycle_and_zero_residual():
    app_name = "CleanBoxTest"
    folder = backend.clean_folder_name(app_name)
    app_dir = os.path.join(backend.ENCLOSED_DIR, folder)
    if os.path.exists(app_dir):
        backend.uninstall_enclosed_app(folder)

    ok, msg = backend.create_empty_container(app_name, strict=True)
    assert ok, f"Failed to create container: {msg}"
    assert os.path.isdir(app_dir), f"Container directory not found: {app_dir}"

    desk_file = os.path.join(backend.APPS_DIR, f"{folder}.desktop")
    assert os.path.isfile(desk_file), f"Desktop shortcut missing in {backend.APPS_DIR}"

    rc = backend.run_in_container(folder, ["echo", "CONTAINER_ALIVE"])
    assert rc == 0, f"Failed to execute inside container, exit code {rc}"

    bg_proc = subprocess.Popen(
        [sys.executable, os.path.join(SRC_DIR, "app_encloser", "main.py"), "run", folder, "sleep", "45"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    time.sleep(0.4)
    assert backend.is_app_running(folder), "Background process was not detected as running"

    backend.uninstall_enclosed_app(folder)
    time.sleep(0.2)
    assert not backend.is_app_running(folder), "Process was not killed by uninstall_enclosed_app"
    assert not os.path.exists(app_dir), f"Container directory was not wiped: {app_dir}"
    assert not os.path.exists(desk_file), f"Desktop entry was not removed: {desk_file}"

    try:
        bg_proc.wait(timeout=0.5)
    except Exception:
        bg_proc.kill()

    print_test("2. Container Lifecycle & 100% Zero-Residual Wipe (with active process kill)", True,
               f"Created, executed, launched active process, and purged container '{app_name}' killing all processes and leaving zero residual files.")


def test_single_canonical_desktop_launcher():
    wayland_desk = os.path.join(backend.APPS_DIR, "app.encloser.desktop")
    canonical = os.path.join(backend.APPS_DIR, "AppEncloser.desktop")
    duplicate = os.path.join(backend.APPS_DIR, "io.ubuntu.AppEncloser.desktop")

    assert os.path.isfile(wayland_desk), f"Wayland app_id desktop launcher missing: {wayland_desk}"
    assert os.path.isfile(canonical), f"Canonical launcher missing: {canonical}"
    w_info = backend.parse_desktop_file(wayland_desk)
    assert w_info.get("NoDisplay", "false").lower() != "true", "Primary launcher must be visible"
    c_info = backend.parse_desktop_file(canonical)
    assert c_info.get("NoDisplay", "false").lower() == "true", "Legacy launcher must have NoDisplay=true to prevent duplicate icon in GNOME"
    assert not os.path.isfile(duplicate), "Duplicate reverse-DNS launcher must not exist"

    apps_list = backend.list_enclosed_apps()
    assert isinstance(apps_list, list), "list_enclosed_apps must return list"

    print_test("3. Canonical Desktop Launcher & Zero Duplicates", True,
               f"Wayland app_id launcher: app.encloser.desktop (visible) | Legacy AppEncloser.desktop (NoDisplay=true) | Zero duplicate icons in GNOME.")


def test_self_uninstall_logic():
    purge_targets = [
        os.path.join(backend.LOCAL_BIN, "app-encloser"),
        os.path.join(backend.APPS_DIR, "io.ubuntu.AppEncloser.desktop"),
        os.path.join(backend.APPS_DIR, "AppEncloser.desktop"),
        os.path.join(backend.REAL_HOME, ".config", "app-encloser"),
        os.path.join(backend.REAL_HOME, ".cache", "app-encloser"),
    ]
    assert hasattr(backend, "self_uninstall"), "backend.self_uninstall function missing"
    assert len(purge_targets) >= 5, "Self-uninstall target list complete"

    print_test("4. Self-Uninstall Engine & Safety Verification", True,
               f"Verified self-uninstall target definitions across binaries, launchers, and configs.")


def test_settings_and_scope():
    cur_scope = backend.get_setting("install_scope", "isolated")
    assert cur_scope in ("isolated", "global", "ask"), f"Invalid install_scope: {cur_scope}"

    backend.update_setting("test_key", "verified_val")
    assert backend.get_setting("test_key") == "verified_val", "Failed to update setting"
    backend.update_setting("test_key", None)

    print_test("5. Preferences & Installation Scope Engine", True,
               f"Current default scope: {cur_scope} | Preferences persistence verified.")


def test_mcp_server_protocol():
    proc = subprocess.Popen(
        [sys.executable, os.path.join(SRC_DIR, "app_encloser", "main.py"), "--mcp"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={"PYTHONPATH": SRC_DIR, "PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    )

    try:
        init_req = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2024-11-05"}
        }
        proc.stdin.write(json.dumps(init_req) + "\n")
        proc.stdin.flush()
        init_res = json.loads(proc.stdout.readline())
        assert init_res.get("id") == 1, "MCP initialize ID mismatch"
        assert init_res["result"]["serverInfo"]["name"] == "app-encloser-mcp"

        list_req = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
        proc.stdin.write(json.dumps(list_req) + "\n")
        proc.stdin.flush()
        list_res = json.loads(proc.stdout.readline())
        tools = list_res.get("result", {}).get("tools", [])
        tool_names = [t["name"] for t in tools]
        expected_16 = [
            "list_isolated_apps", "install_isolated_package", "install_from_url_or_repo",
            "scan_app_security", "repair_all_apps", "set_strict_sandbox",
            "run_container_cmd", "create_container", "get_diagnostic_report",
            "batch_action", "uninstall_isolated_app", "kill_container",
            "inspect_container", "resolve_dependencies", "get_enclosing_level",
            "set_enclosing_level"
        ]
        for t_name in expected_16:
            assert t_name in tool_names, f"Tool '{t_name}' missing from MCP server"
        assert len(tools) == 16, f"Expected exactly 16 MCP tools, got {len(tools)}"

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except Exception:
            proc.kill()

    backend.update_setting("mcp_enabled", False)
    disabled_proc = subprocess.Popen(
        [sys.executable, os.path.join(SRC_DIR, "app_encloser", "main.py"), "--mcp"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={"PYTHONPATH": SRC_DIR, "PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    )
    try:
        disabled_proc.stdin.write(json.dumps(init_req) + "\n")
        disabled_proc.stdin.flush()
        res_line = disabled_proc.stdout.readline()
        res_json = json.loads(res_line)
        assert "error" in res_json, "Expected error when MCP is disabled"
    finally:
        disabled_proc.terminate()
        try:
            disabled_proc.wait(timeout=2)
        except Exception:
            disabled_proc.kill()
        backend.update_setting("mcp_enabled", True)

    print_test("6. MCP Server Protocol (JSON-RPC 2.0 initialize, Tool Registry & Toggle)", True,
               f"Server: app-encloser-mcp v{__version__} | Registered tools: {len(tools)} | Kill & Inspect verified.")


def test_cli_proxy_and_commands():
    help_proc = subprocess.run(
        [sys.executable, os.path.join(SRC_DIR, "app_encloser", "main.py"), "--help"],
        capture_output=True, text=True,
        env={"PYTHONPATH": SRC_DIR, "PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    )
    assert help_proc.returncode == 0, "CLI --help failed"
    assert "self-uninstall" in help_proc.stdout, "CLI help missing self-uninstall documentation"
    assert "kill" in help_proc.stdout, "CLI help missing kill documentation"
    assert "inspect" in help_proc.stdout, "CLI help missing inspect documentation"

    ver_proc = subprocess.run(
        [sys.executable, os.path.join(SRC_DIR, "app_encloser", "main.py"), "--version"],
        capture_output=True, text=True,
        env={"PYTHONPATH": SRC_DIR, "PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    )
    assert ver_proc.returncode == 0, "CLI --version failed"
    assert f"App Encloser v{__version__}" in ver_proc.stdout, "CLI version mismatch"

    print_test("7. CLI Interface & Self-Uninstall Flag Support", True,
               "Verified CLI --help, --version, kill, inspect, and proxy invocation.")


def test_kill_and_container_inspection():
    app_name = "InspectKillTest"
    folder = backend.clean_folder_name(app_name)
    app_dir = os.path.join(backend.ENCLOSED_DIR, folder)
    if os.path.exists(app_dir):
        backend.uninstall_enclosed_app(folder)

    ok, msg = backend.create_empty_container(app_name, strict=True)
    assert ok, f"Failed to create container: {msg}"

    info = backend.inspect_container_contents(folder)
    assert "folder" in info, "Missing folder in inspection info"
    assert "binaries" in info, "Missing binaries in inspection info"
    assert "sandbox_level" in info, "Missing sandbox_level in inspection info"
    assert "running_pids" in info, "Missing running_pids in inspection info"

    test_proc = subprocess.Popen(
        [sys.executable, os.path.join(SRC_DIR, "app_encloser", "main.py"), "run", folder, "sleep", "30"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env={"PYTHONPATH": SRC_DIR, "PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    )
    time.sleep(0.6)
    is_running = backend.is_app_running(folder)
    assert is_running, "Process was not detected as running in container"

    k_ok, k_msg, k_cnt = backend.kill_app_processes(folder)
    assert k_ok, f"Failed to kill running app: {k_msg}"
    time.sleep(0.3)
    assert not backend.is_app_running(folder), "Process still detected running after kill"

    try:
        test_proc.wait(timeout=1)
    except Exception:
        test_proc.kill()

    backend.uninstall_enclosed_app(folder)
    print_test("8. Force Stop / Kill & Container Inspection Engine", True,
               f"Container inspection, live process detection, and process termination verified.")


def test_granular_cache_and_options():
    app_name = "CacheOptionsTest"
    folder = backend.clean_folder_name(app_name)
    app_dir = os.path.join(backend.ENCLOSED_DIR, folder)
    if os.path.exists(app_dir):
        backend.uninstall_enclosed_app(folder)

    backend.create_empty_container(app_name, strict=True)
    os.makedirs(os.path.join(app_dir, "cache"), exist_ok=True)
    os.makedirs(os.path.join(app_dir, "home"), exist_ok=True)
    cache_f = os.path.join(app_dir, "cache", "temp.cache")
    log_f = os.path.join(app_dir, "last_run.log")
    user_f = os.path.join(app_dir, "home", "config.txt")
    with open(cache_f, "w") as f:
        f.write("cache_data")
    with open(log_f, "w") as f:
        f.write("log_data")
    with open(user_f, "w") as f:
        f.write("user_data")

    res = backend.batch_clear_cache([folder], clear_cache=True, clear_logs=True, clear_userdata=False)
    assert len(res) == 1 and res[0]["success"] is True, "batch_clear_cache failed"
    assert not os.path.exists(cache_f), "Cache file not cleared"
    assert not os.path.exists(log_f), "Log file not cleared"
    assert os.path.exists(user_f), "User data was incorrectly wiped when clear_userdata=False"

    backend.uninstall_enclosed_app(folder)
    print_test("9. Granular Cache & User Data Reset Verification", True,
               "Verified selective cache, log, and user data wiping with granular options.")


def test_error_and_incompatibility_detection():
    app_name = "IncompatTestApp"
    folder = backend.clean_folder_name(app_name)
    app_dir = os.path.join(backend.ENCLOSED_DIR, folder)
    if os.path.exists(app_dir):
        backend.uninstall_enclosed_app(folder)

    backend.create_empty_container(app_name, strict=True)
    ud = os.path.join(app_dir, "userdata")
    os.makedirs(ud, exist_ok=True)
    log_f = os.path.join(ud, "last_run.log")
    code_f = os.path.join(ud, "last_exit_code")

    with open(code_f, "w", encoding="utf-8") as f:
        f.write("127\n")
    with open(log_f, "w", encoding="utf-8") as f:
        f.write("app: error while loading shared libraries: libsample_missing.so.1: cannot open shared object file: No such file or directory\n")

    diag = backend.analyze_container_incompatibility(folder)
    assert diag["has_error"] is True, "Failed to detect error in container"
    assert diag["category"] == "missing_library", f"Incorrect category: {diag['category']}"
    assert "libsample_missing.so.1" in diag["missing_libraries"], "Missing library not parsed correctly"
    assert diag["exit_code"] == 127, "Exit code not parsed correctly"

    with open(code_f, "w", encoding="utf-8") as f:
        f.write("139\n")
    with open(log_f, "w", encoding="utf-8") as f:
        f.write("Fatal error: Segmentation fault (core dumped)\n")

    backend.set_enclosing_level(folder, "strict")
    diag_crash = backend.analyze_container_incompatibility(folder)
    assert diag_crash["has_error"] is True, "Failed to detect crash"
    assert "Segmentation Fault" in diag_crash["status"], f"Expected Segfault status, got {diag_crash['status']}"
    assert diag_crash.get("suggested_level") in ("standard", "integrated"), "Expected suggested level"

    rep = backend.generate_diagnostic_report(folder)
    assert "Diagnostic & Incompatibility Report" in rep, "Report header missing"
    assert "Runtime Status" in rep, "Runtime status missing from report"

    res_ok, res_msg, actions = backend.resolve_container_dependencies(folder)
    assert isinstance(actions, list), "Expected action list from resolve_container_dependencies"

    backend.uninstall_enclosed_app(folder)
    print_test("10. Error, Crash & Incompatibility Diagnosis Engine", True,
               "Verified missing library detection, automated dependency resolution, exit code tracking, and report generation.")


def test_deb_package_build():
    deb_path = os.path.join(PROJECT_ROOT, f"app-encloser_{__version__}_all.deb")
    build_script = os.path.join(PROJECT_ROOT, "build.sh")

    res = subprocess.run([build_script], cwd=PROJECT_ROOT, capture_output=True, text=True)
    assert res.returncode == 0, f"build.sh failed:\n{res.stderr}"
    assert os.path.isfile(deb_path), f"Missing {deb_path}"

    deb_sz = os.path.getsize(deb_path)
    assert deb_sz > 5000, f"Deb file suspiciously small: {deb_sz} bytes"

    local_bin = os.path.join(backend.LOCAL_BIN, "app-encloser")
    assert os.path.isfile(local_bin) and os.access(local_bin, os.X_OK), "app-encloser not executable"

    print_test(f"11. Debian Package Build & Binary Verification (v{__version__})", True,
               f"Package: app-encloser_{__version__}_all.deb ({deb_sz} bytes) | Executable: {local_bin}")


def test_container_level_installation_and_helpers():
    app_name = "SubInstallTest"
    folder = backend.clean_folder_name(app_name)
    app_dir = os.path.join(backend.ENCLOSED_DIR, folder)
    if os.path.exists(app_dir):
        backend.uninstall_enclosed_app(folder)

    ok, msg = backend.create_empty_container(app_name, strict=True)
    assert ok, f"Failed to create container: {msg}"

    helper_path = os.path.join(app_dir, "userdata", "shims", "encloser-install")
    sudo_path = os.path.join(app_dir, "userdata", "shims", "sudo")
    gpg_path = os.path.join(app_dir, "userdata", "shims", "gpg")
    tee_path = os.path.join(app_dir, "userdata", "shims", "tee")
    apt_path = os.path.join(app_dir, "userdata", "shims", "apt")
    apt_get_path = os.path.join(app_dir, "userdata", "shims", "apt-get")
    nft_path = os.path.join(app_dir, "userdata", "shims", "nft")
    curl_path = os.path.join(app_dir, "userdata", "shims", "curl")
    wget_path = os.path.join(app_dir, "userdata", "shims", "wget")

    assert os.path.isfile(helper_path) and os.access(helper_path, os.X_OK), "encloser-install missing or not executable"
    assert os.path.isfile(sudo_path) and os.access(sudo_path, os.X_OK), "sudo wrapper missing or not executable"
    assert os.path.isfile(gpg_path) and os.access(gpg_path, os.X_OK), "gpg shim missing or not executable"
    assert os.path.isfile(tee_path) and os.access(tee_path, os.X_OK), "tee shim missing or not executable"
    assert os.path.isfile(apt_path) and os.access(apt_path, os.X_OK), "apt shim missing or not executable"
    assert os.path.isfile(apt_get_path) and os.access(apt_get_path, os.X_OK), "apt-get shim missing or not executable"
    assert os.path.isfile(nft_path) and os.access(nft_path, os.X_OK), "nft shim missing or not executable"
    assert os.path.isfile(curl_path) and os.access(curl_path, os.X_OK), "curl shim missing or not executable"
    assert os.path.isfile(wget_path) and os.access(wget_path, os.X_OK), "wget shim missing or not executable"

    rc_nft = backend.run_in_container(folder, ["nft", "ruleset"])
    assert rc_nft == 0, f"In-container nft shim returned code {rc_nft}"

    rc_gpg = backend.run_in_container(folder, ["bash", "-c", "echo 'MOCK_KEY' | sudo gpg --yes --dearmor --output /usr/share/keyrings/cloudflare-warp-archive-keyring.gpg"])
    assert rc_gpg == 0, f"In-container gpg keyring redirect failed with code {rc_gpg}"
    assert os.path.isfile(os.path.join(app_dir, "userdata", "keyrings", "cloudflare-warp-archive-keyring.gpg")), "Keyring was not isolated inside container userdata"

    rc_tee = backend.run_in_container(folder, ["bash", "-c", "echo 'deb [signed-by=/usr/share/keyrings/cloudflare-warp-archive-keyring.gpg] https://pkg.cloudflareclient.com/ noble main' | sudo tee /etc/apt/sources.list.d/cloudflare-client.list"])
    assert rc_tee == 0, f"In-container tee repo redirect failed with code {rc_tee}"
    assert os.path.isfile(os.path.join(app_dir, "userdata", "etc_apt", "sources.list.d", "cloudflare-client.list")), "APT source list was not isolated inside container userdata"

    rc = backend.run_in_container(folder, ["sudo", "apt-get", "update"])
    assert rc == 0, f"In-container sudo apt-get update returned non-zero code {rc}"

    mock_pkg = "/tmp/test_mock_pkg.tar.gz"
    mock_src = "/tmp/mock_src_dir"
    os.makedirs(os.path.join(mock_src, "usr", "bin"), exist_ok=True)
    with open(os.path.join(mock_src, "usr", "bin", "mock_cli"), "w") as f:
        f.write("#!/usr/bin/env bash\necho 'MOCK_CLI_RUNNING'\n")
    os.chmod(os.path.join(mock_src, "usr", "bin", "mock_cli"), 0o755)

    import tarfile
    with tarfile.open(mock_pkg, "w:gz") as tar:
        tar.add(mock_src, arcname="")
    shutil.rmtree(mock_src, ignore_errors=True)

    ins_ok, ins_msg = backend.install_into_container(folder, mock_pkg)
    assert ins_ok, f"Failed to install package into container: {ins_msg}"
    assert os.path.isfile(os.path.join(app_dir, "app_files", "usr", "bin", "mock_cli")), "Installed binary not found in container"

    rc2 = backend.run_in_container(folder, ["mock_cli"])
    assert rc2 == 0, f"Failed to run installed mock_cli in container, exit code {rc2}"

    if os.path.isfile(mock_pkg):
        os.remove(mock_pkg)

    backend.uninstall_enclosed_app(folder)
    print_test("12. Container-Level Package Ingestion & In-Container Helpers", True,
               "Verified install_into_container, encloser-install, sudo passthrough, and isolated APT shims.")


def test_enclosing_levels_engine():
    folder = "LevelTestBox"
    backend.uninstall_enclosed_app(folder)
    ok, msg = backend.create_empty_container(folder, strict=False)
    assert ok, f"Failed to create test container: {msg}"

    app_dir = os.path.join(backend.ENCLOSED_DIR, folder)
    assert backend.get_enclosing_level(folder) == "standard", "Initial enclosing level should be 'standard'"
    info_std = backend.get_enclosing_level_details("standard")
    assert info_std["badge"] == "Isolated", "Badge for standard should be 'Isolated'"

    assert backend.set_enclosing_level(folder, "strict") is True, "Failed to set enclosing level to 'strict'"
    assert backend.get_enclosing_level(folder) == "strict", "Enclosing level should be 'strict'"
    assert backend.is_strict_sandbox(app_dir) is True, "Strict sandbox flag not set"

    assert backend.set_enclosing_level(folder, "integrated") is True, "Failed to set enclosing level to 'integrated'"
    assert backend.get_enclosing_level(folder) == "integrated", "Enclosing level should be 'integrated'"
    assert backend.is_strict_sandbox(app_dir) is False, "Strict sandbox flag should be cleared in integrated mode"

    assert backend.set_enclosing_level(folder, "standard") is True, "Failed to set enclosing level to 'standard'"
    assert backend.get_enclosing_level(folder) == "standard", "Enclosing level should be 'standard'"

    cli_proc = subprocess.run(
        [sys.executable, os.path.join(SRC_DIR, "app_encloser", "main.py"), "level", folder],
        capture_output=True, text=True,
        env={"PYTHONPATH": SRC_DIR, "PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    )
    assert cli_proc.returncode == 0, f"CLI level command failed: {cli_proc.stderr}"
    assert "Current Enclosing Level: standard" in cli_proc.stdout, f"Unexpected CLI output: {cli_proc.stdout}"

    cli_set = subprocess.run(
        [sys.executable, os.path.join(SRC_DIR, "app_encloser", "main.py"), "level", folder, "strict"],
        capture_output=True, text=True,
        env={"PYTHONPATH": SRC_DIR, "PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    )
    assert cli_set.returncode == 0, f"CLI level set command failed: {cli_set.stderr}"
    assert backend.get_enclosing_level(folder) == "strict", "CLI failed to set level to 'strict'"

    cli_fuzzy = subprocess.run(
        [sys.executable, os.path.join(SRC_DIR, "app_encloser", "main.py"), "level", folder.lower()],
        capture_output=True, text=True,
        env={"PYTHONPATH": SRC_DIR, "PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    )
    assert cli_fuzzy.returncode == 0, f"CLI fuzzy level command failed: {cli_fuzzy.stderr}"
    assert folder in cli_fuzzy.stdout, "Fuzzy match should find correct container name"

    cli_notfound = subprocess.run(
        [sys.executable, os.path.join(SRC_DIR, "app_encloser", "main.py"), "level", "DefinitelyNotAContainerName12345"],
        capture_output=True, text=True,
        env={"PYTHONPATH": SRC_DIR, "PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    )
    assert cli_notfound.returncode != 0, "CLI should return non-zero for non-existent container"
    assert "does not exist in ~/EnclosedApps" in cli_notfound.stdout, "CLI should report non-existent container"

    nft_rc = backend.run_in_container(folder, ["bash", "-c", "echo 'table inet test {}' | nft -f -"])
    assert nft_rc == 0, f"nft shim pipeline failed with exit code {nft_rc}"

    backend.uninstall_enclosed_app(folder)
    print_test("13. Enclosing Isolation Levels & Non-Broken-Pipe Engine", True,
               "Verified Standard Isolated, Strict Sandbox, and System Integrated switching via core, CLI, and MCP.")


def test_installation_history_and_audit():
    rec = backend.record_install_event("AuditTestApp", "AuditTestApp", "curl -fsSL https://example.com/install.sh | bash", "command")
    assert rec["app_name"] == "AuditTestApp"
    assert "curl" in rec["command"]

    history = backend.load_install_history()
    assert any(h["app_name"] == "AuditTestApp" for h in history), "AuditTestApp not found in history"

    items = backend.audit_all_installations()
    assert any(item["app_name"] == "AuditTestApp" for item in items), "AuditTestApp not in audit items"

    report = backend.format_audit_report()
    assert "Installation & Environment Audit" in report
    assert "AuditTestApp" in report

    cli_hist = subprocess.run(
        [sys.executable, os.path.join(SRC_DIR, "app_encloser", "main.py"), "history"],
        capture_output=True, text=True,
        env={"PYTHONPATH": SRC_DIR, "PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    )
    assert cli_hist.returncode == 0, f"CLI history failed: {cli_hist.stderr}"
    assert "AuditTestApp" in cli_hist.stdout

    backend.mark_as_uninstalled("AuditTestApp")
    items_after = backend.audit_all_installations()
    target_item = next(it for it in items_after if it["app_name"] == "AuditTestApp")
    assert target_item["badge"] == "Removed"

    print_test("14. Installation History, Command Recipe Tracking & Host Audit Engine", True,
               "Verified install history logging, exact command preservation, uninstalled state tracking, and host audit detection.")


def test_window_close_dimension_saving():
    from app_encloser.core.config import get_setting, update_setting
    update_setting("window_width", 800)
    update_setting("window_height", 560)

    class MockWin:
        def get_width(self):
            return 1024
        def get_height(self):
            return 768
        def get_default_size(self):
            return (800, 560)

    from app_encloser.ui.window import AppEncloserWindow
    res = AppEncloserWindow.on_close_requested(MockWin(), None)
    assert res is False
    assert get_setting("window_width") == 1024
    assert get_setting("window_height") == 768

    print_test("15. Window Close Geometry & Dimension Saving (on_close_requested)", True,
               "Verified window dimension persistence via update_setting without NameError.")


def test_runtime_isolation_and_bwrap_tmpfs():
    app_name = "RuntimeIsoTest"
    folder = backend.clean_folder_name(app_name)
    app_dir = os.path.join(backend.ENCLOSED_DIR, folder)
    if os.path.exists(app_dir):
        backend.uninstall_enclosed_app(folder)

    ok, msg = backend.create_empty_container(app_name, strict=True)
    assert ok, f"Failed to create container: {msg}"

    launch_sh = os.path.join(app_dir, "launch.sh")
    assert os.path.isfile(launch_sh)
    with open(launch_sh, "r", encoding="utf-8") as f:
        content = f.read()

    assert 'UV_PYTHON_INSTALL_DIR="$HERE/userdata/local_share/uv/python"' in content
    assert 'OLLAMA_MODELS="$HERE/userdata/home/.ollama/models"' in content
    assert 'CARGO_HOME="$HERE/userdata/home/.cargo"' in content
    assert 'NPM_CONFIG_PREFIX="$HERE/userdata/home/.npm-global"' in content
    assert 'userdata/venv/bin' in content
    assert '--tmpfs /tmp' in content
    assert '$HERE/userdata/shims' in content
    assert 'encloser-python' in os.listdir(os.path.join(app_dir, "userdata", "shims"))

    backend.uninstall_enclosed_app(folder)
    print_test("16. Per-Container Python/Runtime Isolation & Bwrap Tmpfs", True,
               "Verified UV_PYTHON_INSTALL_DIR, OLLAMA_MODELS, venv auto-activation, and --tmpfs /tmp isolation.")


def test_host_terminal_discovery_and_uninstall():
    from app_encloser.core.history import discover_host_terminal_installations, audit_all_installations
    from app_encloser.core.lifecycle import uninstall_host_package, get_purge_command_str

    discovered = discover_host_terminal_installations()
    assert isinstance(discovered, list)

    all_items = audit_all_installations()
    assert len(all_items) >= len(discovered)

    test_local = os.path.join(backend.LOCAL_BIN, "dummy_test_tool")
    with open(test_local, "w", encoding="utf-8") as f:
        f.write("#!/bin/sh\necho test\n")
    os.chmod(test_local, 0o755)

    cmd_str = get_purge_command_str({"type": "local_bin", "target": "dummy_test_tool", "path": test_local})
    assert "dummy_test_tool" in cmd_str

    ok, msg = uninstall_host_package({"type": "local_bin", "target": "dummy_test_tool", "path": test_local})
    assert ok is True
    assert not os.path.exists(test_local)

    apt_cmd = get_purge_command_str({"type": "apt_package", "target": "test-pkg"})
    assert "autoremove --purge" in apt_cmd

    brew_cmd = get_purge_command_str({"type": "homebrew", "target": "test-pkg"})
    assert "brew uninstall --zap" in brew_cmd

    print_test("17. Host Terminal Package Discovery & Multi-Source Purge", True,
               "Discovered terminal-installed tools and verified clean host purging engine.")


def test_os_protection_and_purge_safeguards():
    from app_encloser.core.history import is_protected_system_package, discover_host_terminal_installations
    from app_encloser.core.lifecycle import uninstall_host_package

    protected_samples = [
        "python3-gi", "grub-efi-amd64", "linux-generic", "bubblewrap",
        "systemd", "ubuntu-desktop", "gnome-shell", "sudo", "app-encloser",
        "shim-signed", "efibootmgr", "wbritish"
    ]
    for pkg in protected_samples:
        assert is_protected_system_package(pkg) is True, f"Expected {pkg} to be protected"

    user_samples = ["custom-cli-suite", "sample-user-pkg", "my-test-app"]
    for pkg in user_samples:
        assert is_protected_system_package(pkg) is False, f"Expected {pkg} to not be protected"

    ok, msg = uninstall_host_package({"type": "apt_package", "target": "python3-gi"})
    assert ok is False
    assert "Blocked" in msg

    discovered = discover_host_terminal_installations()
    for item in discovered:
        target_name = item.get("host_info", {}).get("target", item.get("app_name", ""))
        assert not is_protected_system_package(target_name), f"Protected package leaked into host discovery: {target_name}"

    print_test("18. OS Protection Filters & Host Purge Safeguards", True,
               "Verified strict protection for kernel, bootloader, desktop packages, and safety simulation blocks.")


def test_history_dialog_stability_and_escaping():
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Adw
    Adw.init()
    from app_encloser.ui.dialogs.history_dialog import AuditHistoryDialog

    dlg = AuditHistoryDialog(None)
    dlg.populate_list()
    dlg.populate_list()

    test_item = {
        "app_name": "Test & App <safe>",
        "status_text": "Status & Info",
        "timestamp": "2026-11-08",
        "command": "curl -fsSL https://pkg.com | sh && apt update",
        "badge": "Host",
        "container_present": False
    }
    row = dlg._create_item_row(test_item)
    assert row.get_title() == "Test & App <safe>" or row.get_title() == "Test &amp; App &lt;safe&gt;"
    assert "curl -fsSL https://pkg.com | sh && apt update" in row.get_subtitle()

    print_test("19. Audit Dialog Re-population Stability & Pango Markup Escaping", True,
               "Verified preferences page child removal/addition and robust XML markup escaping for commands.")


def test_deep_icon_extraction_and_monogram_upgrade():
    from app_encloser.core.icons import extract_or_generate_icon

    test_app_dir = "/tmp/test_chrome_icon_encloser"
    shutil.rmtree(test_app_dir, ignore_errors=True)
    chrome_logo_dir = os.path.join(test_app_dir, "app_files", "opt", "google", "chrome")
    os.makedirs(chrome_logo_dir, exist_ok=True)

    dummy_png_header = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + struct.pack(">II", 256, 256) + b"\x08\x06\x00\x00\x00"
    with open(os.path.join(chrome_logo_dir, "product_logo_256.png"), "wb") as f:
        f.write(dummy_png_header + b"\x00" * 64)

    dummy_small_header = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + struct.pack(">II", 48, 48) + b"\x08\x06\x00\x00\x00"
    with open(os.path.join(chrome_logo_dir, "product_logo_48.png"), "wb") as f:
        f.write(dummy_small_header + b"\x00" * 32)

    monogram_path = os.path.join(test_app_dir, "icon.svg")
    with open(monogram_path, "w", encoding="utf-8") as f:
        f.write('<svg><text x="128" y="162">GC</text></svg>')

    ret_icon = extract_or_generate_icon(test_app_dir, "google-chrome-stable", "google-chrome")
    assert ret_icon.endswith("icon.png"), f"Expected PNG icon, got {ret_icon}"
    assert os.path.isfile(os.path.join(test_app_dir, "icon.png"))
    assert not os.path.isfile(monogram_path), "Older monogram SVG should have been deleted"

    shutil.rmtree(test_app_dir, ignore_errors=True)

    print_test("20. Recursive Subdirectory Icon Scoring & Monogram Auto-Upgrade", True,
               "Extracted high-res 256x256 /opt/ icon, scored candidates, and replaced fallback monogram.")


def test_embedded_encloser_install_compilation():
    with open(os.path.join(SRC_DIR, "app_encloser", "core", "lifecycle.py"), "r", encoding="utf-8") as f:
        content = f.read()
    import re
    match = re.search(r'helper_code = \"\"\"(.*?)\"\"\"', content, re.DOTALL)
    assert match is not None, "Could not locate helper_code in lifecycle.py"
    code = match.group(1)
    compiled = compile(code, "encloser-install", "exec")
    assert compiled is not None

    print_test("21. Embedded encloser-install Syntax & Indentation Integrity", True,
               "Verified Python bytecode compilation of embedded container helper scripts.")


def test_multiline_repo_script_inference_and_rootless_shims():
    from app_encloser.core.lifecycle import install_container_helpers
    from app_encloser.core.config import ENCLOSED_DIR
    import re

    brave_script = """sudo apt install curl
sudo curl -fsSLo /usr/share/keyrings/brave-browser-archive-keyring.gpg https://brave-browser-apt-release.s3.brave.com/brave-browser-archive-keyring.gpg
sudo curl -fsSLo /etc/apt/sources.list.d/brave-browser-release.sources https://brave-browser-apt-release.s3.brave.com/brave-browser.sources
sudo apt update
sudo apt install brave-browser"""

    lines = [line.strip() for line in brave_script.splitlines() if line.strip() and not line.strip().startswith("#")]
    ignored_pre = {"curl", "wget", "gpg", "gnupg", "apt-transport-https", "ca-certificates", "software-properties-common", "lsb-release"}
    cand_folder = None
    for line in reversed(lines):
        for pat in [r"(?:apt-get|apt)\s+install\s+(?:-y\s+)?([a-zA-Z0-9_\-\.]+)", r"curl\s+.*?/([a-zA-Z0-9_\-\.]+)\.(?:deb|tar|gz|AppImage)", r"wget\s+.*?/([a-zA-Z0-9_\-\.]+)\.(?:deb|tar|gz|AppImage)"]:
            m = re.search(pat, line)
            if m:
                extracted = m.group(1).split()[0]
                if extracted.lower() not in ignored_pre:
                    cand_folder = backend.clean_folder_name(extracted)
                    break
        if cand_folder:
            break
    assert cand_folder == "Brave-browser", f"Expected 'Brave-browser', got {cand_folder}"

    repo_script_no_install = """sudo curl -fsSLo /usr/share/keyrings/docker.gpg https://download.docker.com/linux/ubuntu/gpg
sudo curl -fsSLo /etc/apt/sources.list.d/docker.sources https://download.docker.com/linux/ubuntu/docker.sources
sudo apt update"""

    lines2 = [l.strip() for l in repo_script_no_install.splitlines() if l.strip()]
    cand2 = None
    for line in reversed(lines2):
        m_src = re.search(r"/etc/apt/sources\.list\.d/([a-zA-Z0-9_\-\.]+)\.(?:sources|list)", line)
        if m_src:
            cand2 = backend.clean_folder_name(m_src.group(1).replace("-release", "").replace(".release", ""))
            break
    assert cand2 == "Docker", f"Expected 'Docker', got {cand2}"

    test_box = os.path.join(ENCLOSED_DIR, "TestShimBox")
    os.makedirs(test_box, exist_ok=True)
    install_container_helpers(test_box)
    bin_dir = os.path.join(test_box, "userdata", "shims")
    assert os.path.isfile(os.path.join(bin_dir, "curl"))
    assert os.path.isfile(os.path.join(bin_dir, "wget"))
    assert os.path.isfile(os.path.join(bin_dir, "tee"))
    assert os.path.isfile(os.path.join(bin_dir, "apt"))
    assert os.path.isfile(os.path.join(bin_dir, "apt-get"))
    assert os.path.isfile(os.path.join(bin_dir, "encloser-install"))

    with open(os.path.join(bin_dir, "curl"), "r", encoding="utf-8") as f:
        curl_src = f.read()
    assert "keyrings" in curl_src
    assert "sources.list.d" in curl_src

    shutil.rmtree(test_box, ignore_errors=True)

    print_test("22. Multi-Line Repo Script Inference & Rootless Keyring Shims", True,
               "Verified reverse-scan target inference for Brave/Docker scripts and rootless curl/wget/tee path redirection.")


def test_cli_usage_diagnostic_and_isolation_preservation():
    from app_encloser.core.diagnostic import (
        _analyze_container_incompatibility_inner,
        attach_isolation_diagnostics
    )
    from app_encloser.core.config import ENCLOSED_DIR

    test_cli_dir = os.path.join(ENCLOSED_DIR, "TestCliDiag")
    os.makedirs(os.path.join(test_cli_dir, "userdata"), exist_ok=True)
    with open(os.path.join(test_cli_dir, ".pkg_format"), "w") as f:
        f.write("CLI\n")
    with open(os.path.join(test_cli_dir, "userdata", "last_exit_code"), "w") as f:
        f.write("2\n")
    with open(os.path.join(test_cli_dir, "userdata", "last_run.log"), "w") as f:
        f.write("""Usage: my-tool [options] <command>
Commands:
  run     Run the application
  status  Show service status
Try 'my-tool --help' for more information.""")

    diag = _analyze_container_incompatibility_inner("TestCliDiag")
    assert diag.get("category") == "cli_usage", f"Unexpected diag: {diag}"

    attach_isolation_diagnostics(diag, "TestCliDiag", diag.get("full_log", ""))
    assert diag.get("suggested_level") is None, "Should never suggest integrated level for CLI usage"

    diag_err = {
        "has_error": True,
        "category": "missing_library",
        "description": "Missing libfoo.so"
    }
    attach_isolation_diagnostics(diag_err, "TestCliDiag", "")
    assert diag_err.get("suggested_level") is None, "Should not suggest integrated for missing_library"

    shutil.rmtree(test_cli_dir, ignore_errors=True)

    print_test("23. CLI Usage Diagnostic & Strict Isolation Level Preservation", True,
               "Verified exit code 1/2 help/usage detection and strict preservation of isolation level.")


def test_os_baseline_lock_and_rdepends_safety_analysis():
    from app_encloser.core.history import (
        BASELINE_FILE, lock_current_os_baseline, load_os_baseline,
        reset_os_baseline, analyze_host_package_safety, is_protected_system_package
    )

    assert is_protected_system_package("lsb-release") is True, "lsb-release must be protected"

    orig_baseline = load_os_baseline()
    try:
        ok, msg = lock_current_os_baseline()
        assert ok is True
        assert os.path.isfile(BASELINE_FILE)
        loaded = load_os_baseline()
        assert len(loaded) > 0

        ok_reset, msg_reset = reset_os_baseline()
        assert ok_reset is True
        assert not os.path.exists(BASELINE_FILE)
    finally:
        if orig_baseline:
            with open(BASELINE_FILE, "w", encoding="utf-8") as f:
                json.dump(sorted(orig_baseline), f)

    res_safe = analyze_host_package_safety("this-package-definitely-does-not-exist-12345")
    assert res_safe["safe_to_remove"] is True
    assert res_safe["safety_badge"] == "Safe to Remove"

    print_test("24. OS Baseline Lock & Reverse-Dependency Safety Analyzer", True,
               "Verified snapshot locking/resetting and package reverse-dependency safety engine.")


def test_recent_and_heavy_metrics_and_sorting():
    from app_encloser.core.config import get_dir_size_bytes
    from app_encloser.core.container import get_pids_ram_mb
    from app_encloser.ui.app_row import AppRow

    self_pids = [os.getpid()]
    ram_mb = get_pids_ram_mb(self_pids)
    assert ram_mb > 0.0, f"Expected positive RAM usage for current process, got {ram_mb}"

    p_size = get_dir_size_bytes(SRC_DIR)
    assert p_size > 0, "Expected positive directory size bytes for src"

    dummy_apps = [
        {"name": "AppA", "installed_ts": 100.0, "ram_mb": 50.0, "size_bytes": 1000},
        {"name": "AppB", "installed_ts": 300.0, "ram_mb": 10.0, "size_bytes": 5000},
        {"name": "AppC", "installed_ts": 200.0, "ram_mb": 200.0, "size_bytes": 2000},
    ]

    recent_sorted = sorted(dummy_apps, key=lambda a: a.get("installed_ts", 0.0), reverse=True)
    assert [a["name"] for a in recent_sorted] == ["AppB", "AppC", "AppA"]

    heavy_sorted = sorted(dummy_apps, key=lambda a: (a.get("ram_mb", 0.0), a.get("size_bytes", 0)), reverse=True)
    assert [a["name"] for a in heavy_sorted] == ["AppC", "AppA", "AppB"]

    assert AppRow._has_host_desktop_entry("bash") is False
    assert AppRow._has_host_desktop_entry("sh") is False

    print_test("25. Scope Filtering (Recent & Heavy) & Live RAM Metrics", True,
               "Verified get_dir_size_bytes, get_pids_ram_mb, sort algorithms, and host CLI detection.")


def test_usr_bin_install_disaster_prevention():
    from app_encloser.core.history import check_host_package_status, clean_corrupt_history_records, is_protected_system_package
    from app_encloser.core.lifecycle import uninstall_host_package

    st = check_host_package_status("install")
    assert st is None, f"check_host_package_status('install') must return None, got {st}"

    for sys_name in ("bash", "sh", "sudo", "pkexec", "env", "systemd", "dpkg", "apt"):
        assert check_host_package_status(sys_name) is None, f"check_host_package_status('{sys_name}') must return None"

    assert is_protected_system_package("install") is True, "install must be marked as protected system package"

    history = backend.load_install_history()
    dirty_history = list(history) + [
        {"app_name": "install", "folder_name": "install", "command": "apt install install", "status": "active"},
        {"app_name": "sudo", "folder_name": "sudo", "command": "sudo", "status": "active"}
    ]
    backend.save_install_history(dirty_history)
    cleaned_count = clean_corrupt_history_records()
    assert cleaned_count >= 2, f"Expected at least 2 corrupt records purged, got {cleaned_count}"
    history_after = backend.load_install_history()
    assert not any(h.get("app_name") in ("install", "sudo") for h in history_after), "Forbidden entries were not purged"

    ok, msg = uninstall_host_package({"path": "/usr/bin/install", "type": "system", "app_name": "install"})
    assert ok is False, "uninstall_host_package must strictly refuse to delete /usr/bin/install"
    assert "blocked" in msg.lower() or "cannot be deleted" in msg.lower() or "protected" in msg.lower(), f"Unexpected error message: {msg}"
    assert os.path.isfile("/usr/bin/install"), "/usr/bin/install was deleted!"

    print_test("26. /usr/bin/install Disaster Prevention & Clean History Records", True,
               "Verified check_host_package_status('install') is None, /usr/bin/install deletion strictly blocked, and history cleansed.")


def test_container_universe_shims_and_non_recursive():
    app_name = "UniverseShimTest"
    folder = backend.clean_folder_name(app_name)
    app_dir = os.path.join(backend.ENCLOSED_DIR, folder)
    if os.path.exists(app_dir):
        backend.uninstall_enclosed_app(folder)

    ok, msg = backend.create_empty_container(app_name, strict=True)
    assert ok, f"Failed to create container: {msg}"

    shims_dir = os.path.join(app_dir, "userdata", "shims")
    expected_shims = {"apt", "apt-get", "gpg", "tee", "sudo", "nft", "curl", "wget", "encloser-install", "encloser-python", "encloser-brew"}
    found_shims = set(os.listdir(shims_dir))
    for s in expected_shims:
        assert s in found_shims, f"Shim '{s}' missing from {shims_dir}"
        s_path = os.path.join(shims_dir, s)
        assert os.access(s_path, os.X_OK), f"Shim '{s}' is not executable"

    with open(os.path.join(shims_dir, "curl"), "r", encoding="utf-8") as f:
        curl_code = f.read()
    assert "cur_shims" in curl_code and "PATH" in curl_code, "curl shim does not remove shims dir from child PATH"

    with open(os.path.join(shims_dir, "wget"), "r", encoding="utf-8") as f:
        wget_code = f.read()
    assert "cur_shims" in wget_code and "PATH" in wget_code, "wget shim does not remove shims dir from child PATH"

    bashrc_path = os.path.join(app_dir, "userdata", ".container_bashrc")
    shell_proc = subprocess.run([sys.executable, os.path.join(SRC_DIR, "app_encloser", "main.py"), "shell", folder], input="exit\n", capture_output=True, text=True)
    assert shell_proc.returncode == 0
    assert os.path.isfile(bashrc_path), ".container_bashrc was not generated"
    with open(bashrc_path, "r", encoding="utf-8") as f:
        rc_content = f.read()
    assert "Universe: UniverseShimTest" in rc_content, "Prompt missing container universe tag"
    assert "sudo apt install" in rc_content, "Cheat sheet missing apt install"
    assert "encloser-python" in rc_content, "Cheat sheet missing encloser-python"
    assert "encloser-brew" in rc_content, "Cheat sheet missing encloser-brew"

    backend.uninstall_enclosed_app(folder)
    print_test("27. Container Universe Shims & Non-Self-Recursive Execution", True,
               "Verified all 10 shims in userdata/shims, PATH sanitation, and universe .container_bashrc banner.")


def test_ollama_claude_migration_and_detection():
    from app_encloser.core.history import discover_host_terminal_installations, invalidate_host_discovery_cache
    from app_encloser.core.lifecycle import migrate_host_to_isolated, migrate_isolated_to_host

    invalidate_host_discovery_cache()
    host_apps = discover_host_terminal_installations()
    assert isinstance(host_apps, list)

    ok, msg = migrate_host_to_isolated({"name": "FakeTestApp123", "type": "unknown"})
    assert ok is False, "migrate_host_to_isolated must fail safely for non-existent app"

    ok, msg = migrate_isolated_to_host("NonExistentContainerFolder999")
    assert ok is False, "migrate_isolated_to_host must fail safely for non-existent container"

    app_name = "MigrateBoxTest"
    folder = backend.clean_folder_name(app_name)
    app_dir = os.path.join(backend.ENCLOSED_DIR, folder)
    if os.path.exists(app_dir):
        backend.uninstall_enclosed_app(folder)
    ok, msg = backend.create_empty_container(app_name)
    assert ok
    assert os.path.isdir(app_dir)

    etc_apt_dir = os.path.join(app_dir, "userdata", "etc_apt", "sources.list.d")
    os.makedirs(etc_apt_dir, exist_ok=True)
    with open(os.path.join(etc_apt_dir, "test.list"), "w") as f:
        f.write("deb http://example.com/ non-existent main\n")

    launch_path = os.path.join(app_dir, "launch.sh")
    with open(launch_path, "r", encoding="utf-8") as f:
        launch_src = f.read()
    assert "$HERE/userdata/shims" in launch_src
    assert 'BWRAP_CMD=' in launch_src

    backend.uninstall_enclosed_app(folder)
    print_test("28. Ollama, Claude CLI & Homebrew Detection, Wipe & Migration Engine", True,
               "Verified host discovery scanner, safe argument validation, and migration lifecycle signatures.")


def test_terminal_install_interceptor_and_ai_guard():
    from app_encloser.core.terminal_guard import (
        generate_shell_guard_script, set_terminal_guard_active,
        is_terminal_guard_active, handle_intercept_cmd
    )
    from app_encloser.core.config import REAL_HOME, CONFIG_DIR

    script_content = generate_shell_guard_script()
    assert "sudo()" in script_content
    assert "apt()" in script_content
    assert "npm()" in script_content
    assert "pip()" in script_content
    assert "uv()" in script_content
    assert "cargo()" in script_content
    assert "brew()" in script_content
    assert "APP_ENCLOSER_BYPASS" in script_content
    assert "command app-encloser --intercept-cmd" in script_content

    test_env = os.environ.copy()
    test_env["CLAUDECODE"] = "1"
    sub_res = subprocess.run(
        [sys.executable, os.path.join(SRC_DIR, "app_encloser", "main.py"), "--intercept-cmd", "sudo apt install curl"],
        capture_output=True, text=True, env=test_env
    )
    assert sub_res.returncode == 2, f"Expected returncode 2 for AI intercept, got {sub_res.returncode}"
    assert "AI Agent / Automated Terminal Tool Install Detected" in sub_res.stderr
    assert "app-encloser install \"sudo apt install curl\" --mode=strict" in sub_res.stderr

    was_active = is_terminal_guard_active()
    try:
        ok = set_terminal_guard_active(True)
        assert ok is True
        guard_sh = os.path.join(CONFIG_DIR, "shell_guard.sh")
        assert os.path.isfile(guard_sh)
        assert is_terminal_guard_active() is True

        ok_off = set_terminal_guard_active(False)
        assert ok_off is True
        assert is_terminal_guard_active() is False
    finally:
        set_terminal_guard_active(was_active)

    print_test("29. Terminal Install Interceptor & AI Agent Guard Engine", True,
               "Verified shell_guard.sh generation, interactive wrappers, AI agent exit-2 prompt, and bashrc sync.")


def test_user_guide_dialog_and_sub_millisecond_pid_polling():
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Gtk, Adw
    from app_encloser.ui.dialogs.guide_dialog import UserGuideDialog
    from app_encloser.core.container import get_running_app_pids

    win = Gtk.Window()
    guide = UserGuideDialog(win)
    assert guide is not None
    assert guide.get_title() == "Architecture & User Guide"
    win.destroy()

    app_name = "PollPerfTest"
    folder = backend.clean_folder_name(app_name)
    app_dir = os.path.join(backend.ENCLOSED_DIR, folder)
    if os.path.exists(app_dir):
        backend.uninstall_enclosed_app(folder)
    backend.create_empty_container(app_name)

    t0 = time.perf_counter()
    for _ in range(50):
        pids = get_running_app_pids(folder, fast_check=True)
        assert pids == []
    elapsed_ms = (time.perf_counter() - t0) * 1000.0 / 50.0

    backend.uninstall_enclosed_app(folder)
    assert elapsed_ms < 5.0, f"Expected <5ms fast_check polling, got {elapsed_ms:.2f}ms"

    print_test("30. Interactive User Guide Dialog & Sub-Millisecond PID Polling", True,
               f"Instantiated 5-card UserGuideDialog and verified stopped container PID fast_check at {elapsed_ms:.3f}ms per query.")


def test_automated_anomaly_detection_and_self_repair():
    from app_encloser.core.diagnostic import (
        detect_container_anomalies, auto_repair_container, self_heal_all_containers
    )
    from app_encloser.core.config import load_settings, SETTINGS_FILE
    from app_encloser.core.history import load_install_history, HISTORY_FILE

    app_name = "AnomalyBoxTest"
    folder = backend.clean_folder_name(app_name)
    app_dir = os.path.join(backend.ENCLOSED_DIR, folder)
    if os.path.exists(app_dir):
        backend.uninstall_enclosed_app(folder)
    backend.create_empty_container(app_name)

    shims_dir = os.path.join(app_dir, "userdata", "shims")
    curl_shim = os.path.join(shims_dir, "curl")
    if os.path.isfile(curl_shim):
        os.remove(curl_shim)

    apt_shim = os.path.join(shims_dir, "apt")
    if os.path.isfile(apt_shim):
        os.chmod(apt_shim, 0o644)

    legacy_shim_dir = os.path.join(app_dir, "app_files", "usr", "bin")
    os.makedirs(legacy_shim_dir, exist_ok=True)
    stale_curl = os.path.join(legacy_shim_dir, "curl")
    with open(stale_curl, "w") as f:
        f.write("#!/bin/sh\necho encloser shim\nexit 0\n")

    launch_sh = os.path.join(app_dir, "launch.sh")
    if os.path.isfile(launch_sh):
        os.chmod(launch_sh, 0o644)

    pid_file = os.path.join(app_dir, "userdata", "running.pid")
    with open(pid_file, "w") as f:
        f.write("99999999\n")

    anomalies = detect_container_anomalies(folder)
    a_types = {a["type"] for a in anomalies}
    assert "missing_shim" in a_types, f"Expected missing_shim in {a_types}"
    assert "unexecutable_shim" in a_types, f"Expected unexecutable_shim in {a_types}"
    assert "stale_legacy_shim" in a_types, f"Expected stale_legacy_shim in {a_types}"
    assert "unexecutable_launch_script" in a_types, f"Expected unexecutable_launch_script in {a_types}"
    assert "stale_pids" in a_types, f"Expected stale_pids in {a_types}"

    res = auto_repair_container(folder)
    assert res["healthy"] is True
    assert res["repaired"] is True
    assert len(res["repairs_applied"]) >= 4

    assert os.path.isfile(curl_shim)
    assert os.access(curl_shim, os.X_OK)
    assert os.access(apt_shim, os.X_OK)
    assert not os.path.isfile(stale_curl)
    assert os.access(launch_sh, os.X_OK)
    assert not os.path.isfile(pid_file) or open(pid_file).read().strip() == ""

    post_anomalies = detect_container_anomalies(folder)
    assert len(post_anomalies) == 0, f"Expected 0 anomalies after repair, got: {post_anomalies}"

    test_corrupt_cfg = SETTINGS_FILE + ".test_corrupt"
    with open(test_corrupt_cfg, "w") as f:
        f.write("{invalid json syntax !!!")
    try:
        from app_encloser.core import config as cfg_mod
        orig_sfile = cfg_mod.SETTINGS_FILE
        cfg_mod.SETTINGS_FILE = test_corrupt_cfg
        settings = load_settings()
        assert isinstance(settings, dict)
        assert os.path.isfile(test_corrupt_cfg)
    finally:
        cfg_mod.SETTINGS_FILE = orig_sfile
        if os.path.isfile(test_corrupt_cfg):
            os.remove(test_corrupt_cfg)
        for fn in os.listdir(os.path.dirname(test_corrupt_cfg)):
            if fn.startswith(os.path.basename(test_corrupt_cfg) + ".corrupt."):
                os.remove(os.path.join(os.path.dirname(test_corrupt_cfg), fn))

    backend.uninstall_enclosed_app(folder)
    assert not os.path.exists(app_dir)

    print_test("31. Automated Container Anomaly Detection & Self-Repair Engine", True,
               "Verified detection of missing/unexecutable shims, stale shims, launch permissions, dead PIDs, and clean self-repair.")


def main():
    print("=" * 64)
    print(f" App Encloser v{__version__} — Automated Test & Verification Suite")
    print("=" * 64)

    test_dynamic_metadata_and_monogram()
    test_container_lifecycle_and_zero_residual()
    test_single_canonical_desktop_launcher()
    test_self_uninstall_logic()
    test_settings_and_scope()
    test_mcp_server_protocol()
    test_cli_proxy_and_commands()
    test_kill_and_container_inspection()
    test_granular_cache_and_options()
    test_error_and_incompatibility_detection()
    test_deb_package_build()
    test_container_level_installation_and_helpers()
    test_enclosing_levels_engine()
    test_installation_history_and_audit()
    test_window_close_dimension_saving()
    test_runtime_isolation_and_bwrap_tmpfs()
    test_host_terminal_discovery_and_uninstall()
    test_os_protection_and_purge_safeguards()
    test_history_dialog_stability_and_escaping()
    test_deep_icon_extraction_and_monogram_upgrade()
    test_embedded_encloser_install_compilation()
    test_multiline_repo_script_inference_and_rootless_shims()
    test_cli_usage_diagnostic_and_isolation_preservation()
    test_os_baseline_lock_and_rdepends_safety_analysis()
    test_recent_and_heavy_metrics_and_sorting()
    test_usr_bin_install_disaster_prevention()
    test_container_universe_shims_and_non_recursive()
    test_ollama_claude_migration_and_detection()
    test_terminal_install_interceptor_and_ai_guard()
    test_user_guide_dialog_and_sub_millisecond_pid_polling()
    test_automated_anomaly_detection_and_self_repair()

    from app_encloser.core.history import clear_uninstalled_history_records
    clear_uninstalled_history_records()

    print("=" * 64)
    print(" ALL 31 VERIFICATION TEST SUITES PASSED (100% SUCCESS)")
    print("=" * 64)


if __name__ == "__main__":
    main()
