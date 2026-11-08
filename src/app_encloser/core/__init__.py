from app_encloser.core.config import (
    REAL_HOME, ENCLOSED_DIR, APPS_DIR, ICONS_DIR, LOCAL_BIN, CONFIG_DIR, CACHE_DIR,
    SETTINGS_FILE, DEFAULT_SETTINGS, load_settings, save_settings, get_setting,
    update_setting, clean_folder_name, is_supported_file, get_dir_size,
    get_dir_size_bytes, invalidate_dir_size_cache
)
from app_encloser.core.container import (
    find_lib_dirs, resolve_executable, is_strict_sandbox, set_strict_sandbox,
    write_launch_script, run_in_container, open_container_shell, create_empty_container,
    get_running_app_pids, is_app_running, kill_app_processes, inspect_container_contents,
    get_enclosing_level, set_enclosing_level, get_enclosing_level_details, find_container_folder,
    get_pids_ram_mb
)
from app_encloser.core.extractor import (
    safe_extract_tar, safe_extract_zip, extract_deb, extract_rpm, extract_appimage,
    unpack_archive
)
from app_encloser.core.icons import (
    get_png_dimensions, generate_monogram_svg, extract_icon_from_asar,
    extract_or_generate_icon
)
from app_encloser.core.desktop import (
    parse_desktop_file, find_best_desktop_file, update_desktop_files_for_app,
    ensure_clean_desktop_environment
)
from app_encloser.core.lifecycle import (
    list_enclosed_apps, repair_app, repair_all_apps, uninstall_enclosed_app,
    batch_uninstall, batch_clear_cache, install_globally, install_any_package,
    install_from_url_or_repo, install_into_container, uninstall_host_package,
    get_purge_command_str, migrate_host_to_isolated, migrate_isolated_to_host
)
from app_encloser.core.backup import (
    export_selective, batch_export, export_all_apps, inspect_backup_archive,
    import_selective
)
from app_encloser.core.self_uninstall import self_uninstall
from app_encloser.core.security import (
    scan_app_security, batch_security_scan
)
from app_encloser.core.diagnostic import (
    analyze_container_incompatibility, check_missing_libraries,
    check_elf_architecture, generate_diagnostic_report,
    resolve_container_dependencies, detect_container_anomalies,
    auto_repair_container, self_heal_all_containers
)
from app_encloser.core.history import (
    load_install_history, save_install_history, record_install_event,
    mark_as_uninstalled, audit_all_installations, format_audit_report,
    discover_host_terminal_installations, is_protected_system_package,
    lock_current_os_baseline, reset_os_baseline, load_os_baseline,
    analyze_host_package_safety, analyze_host_packages_safety_batch,
    clean_corrupt_history_records, invalidate_host_discovery_cache,
    delete_history_record, clear_uninstalled_history_records
)
from app_encloser.core.terminal_guard import (
    generate_shell_guard_script, is_terminal_guard_active,
    set_terminal_guard_active, sync_terminal_guard, handle_intercept_cmd
)
from app_encloser.core.mcp_server import run_mcp_server
