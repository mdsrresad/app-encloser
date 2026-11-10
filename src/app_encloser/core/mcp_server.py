import os
import sys
import json
from typing import Dict, Any

from app_encloser.core.lifecycle import (
    list_enclosed_apps, install_any_package, install_from_url_or_repo,
    repair_all_apps, uninstall_enclosed_app, batch_clear_cache,
    batch_uninstall
)
from app_encloser.core.container import (
    set_strict_sandbox, run_in_container, create_empty_container,
    kill_app_processes, inspect_container_contents,
    get_enclosing_level, set_enclosing_level, get_enclosing_level_details
)
from app_encloser.core.config import get_setting
from app_encloser.core.security import scan_app_security
from app_encloser.core.diagnostic import (
    generate_diagnostic_report, resolve_container_dependencies,
    analyze_container_incompatibility
)


def run_mcp_server():
    if not get_setting("mcp_enabled", True):
        err_res = {
            "jsonrpc": "2.0",
            "error": {"code": -32000, "message": "MCP server is disabled in App Encloser preferences."}
        }
        sys.stdout.write(json.dumps(err_res) + "\n")
        sys.stdout.flush()
        return

    from app_encloser import __version__
    server_info = {"name": "app-encloser-mcp", "version": __version__}
    tools = [
        {
            "name": "list_isolated_apps",
            "description": "List all applications currently enclosed and isolated.",
            "inputSchema": {"type": "object", "properties": {}}
        },
        {
            "name": "install_isolated_package",
            "description": "Install a local package into an isolated user container.",
            "inputSchema": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"]
            }
        },
        {
            "name": "install_from_url_or_repo",
            "description": "Install a package from APT repository or web URL.",
            "inputSchema": {
                "type": "object",
                "properties": {"target": {"type": "string"}},
                "required": ["target"]
            }
        },
        {
            "name": "scan_app_security",
            "description": "Inspect an application container for telemetry trackers and security permissions.",
            "inputSchema": {
                "type": "object",
                "properties": {"folder_name": {"type": "string"}},
                "required": ["folder_name"]
            }
        },
        {
            "name": "repair_all_apps",
            "description": "Retroactively repair desktop files and launch wrappers.",
            "inputSchema": {"type": "object", "properties": {}}
        },
        {
            "name": "set_strict_sandbox",
            "description": "Enable or disable strict Bubblewrap isolation.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "folder_name": {"type": "string"},
                    "enable": {"type": "boolean"}
                },
                "required": ["folder_name", "enable"]
            }
        },
        {
            "name": "run_container_cmd",
            "description": "Execute a command inside an isolated container.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "folder_name": {"type": "string"},
                    "command": {"type": "array", "items": {"type": "string"}}
                },
                "required": ["folder_name", "command"]
            }
        },
        {
            "name": "create_container",
            "description": "Create an empty isolated container environment.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "folder_name": {"type": "string"},
                    "strict": {"type": "boolean"}
                },
                "required": ["folder_name"]
            }
        },
        {
            "name": "get_diagnostic_report",
            "description": "Generate diagnostic report for an application container.",
            "inputSchema": {
                "type": "object",
                "properties": {"folder_name": {"type": "string"}},
                "required": ["folder_name"]
            }
        },
        {
            "name": "batch_action",
            "description": "Perform batch actions (clear_cache, uninstall) on apps.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["clear_cache", "uninstall"]},
                    "folders": {"type": "array", "items": {"type": "string"}}
                },
                "required": ["action", "folders"]
            }
        },
        {
            "name": "uninstall_isolated_app",
            "description": "Completely wipe an application container and shortcuts.",
            "inputSchema": {
                "type": "object",
                "properties": {"folder_name": {"type": "string"}},
                "required": ["folder_name"]
            }
        },
        {
            "name": "kill_container",
            "description": "Force stop and kill all running processes in an application container.",
            "inputSchema": {
                "type": "object",
                "properties": {"folder_name": {"type": "string"}},
                "required": ["folder_name"]
            }
        },
        {
            "name": "inspect_container",
            "description": "Inspect container contents, binaries, dependencies, running state, and isolation.",
            "inputSchema": {
                "type": "object",
                "properties": {"folder_name": {"type": "string"}},
                "required": ["folder_name"]
            }
        },
        {
            "name": "resolve_dependencies",
            "description": "Automatically resolve missing dependencies and library paths for a container with confirmation.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "folder_name": {"type": "string"},
                    "confirm": {"type": "boolean", "description": "Set to true to execute resolution after reviewing plan"}
                },
                "required": ["folder_name"]
            }
        },
        {
            "name": "get_enclosing_level",
            "description": "Get the current enclosing and isolation level for an application container.",
            "inputSchema": {
                "type": "object",
                "properties": {"folder_name": {"type": "string"}},
                "required": ["folder_name"]
            }
        },
        {
            "name": "set_enclosing_level",
            "description": "Set the enclosing and isolation level for a container (standard, strict, or integrated).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "folder_name": {"type": "string"},
                    "level": {"type": "string", "enum": ["standard", "strict", "integrated"]}
                },
                "required": ["folder_name", "level"]
            }
        }
    ]

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception:
            err_res = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "Parse error"}
            }
            sys.stdout.write(json.dumps(err_res) + "\n")
            sys.stdout.flush()
            continue

        req_id = req.get("id")
        method = req.get("method")

        if method == "initialize":
            res = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": server_info,
                    "capabilities": {"tools": {}}
                }
            }
            sys.stdout.write(json.dumps(res) + "\n")
            sys.stdout.flush()

        elif method == "tools/list":
            res = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"tools": tools}
            }
            sys.stdout.write(json.dumps(res) + "\n")
            sys.stdout.flush()

        elif method == "tools/call":
            params = req.get("params", {})
            name = params.get("name")
            args = params.get("arguments", {})
            content = ""
            is_err = False

            try:
                if name == "list_isolated_apps":
                    content = json.dumps(list_enclosed_apps(), indent=2)
                elif name == "install_isolated_package":
                    ok, msg = install_any_package(args["path"])
                    content = msg
                    is_err = not ok
                elif name == "install_from_url_or_repo":
                    ok, msg = install_from_url_or_repo(args["target"])
                    content = msg
                    is_err = not ok
                elif name == "scan_app_security":
                    content = json.dumps(scan_app_security(args["folder_name"]), indent=2)
                elif name == "repair_all_apps":
                    content = json.dumps(repair_all_apps(), indent=2)
                elif name == "set_strict_sandbox":
                    ok = set_strict_sandbox(args["folder_name"], args["enable"])
                    content = f"Strict sandbox: {ok}"
                elif name == "run_container_cmd":
                    from app_encloser.core.config import ENCLOSED_DIR
                    rc = run_in_container(args["folder_name"], args["command"])
                    log_file = os.path.join(ENCLOSED_DIR, args["folder_name"], "userdata", "last_run.log")
                    out = ""
                    if os.path.isfile(log_file):
                        try:
                            with open(log_file, "r", errors="ignore") as lf:
                                out = lf.read().strip()
                        except Exception:
                            pass
                    content = json.dumps({"exit_code": rc, "output": out}, indent=2)
                    is_err = (rc != 0)
                elif name == "create_container":
                    ok, msg = create_empty_container(args["folder_name"], args.get("strict", True))
                    content = msg
                    is_err = not ok
                elif name == "get_diagnostic_report":
                    content = generate_diagnostic_report(args["folder_name"])
                elif name == "batch_action":
                    act = args["action"]
                    fldrs = args["folders"]
                    if act == "clear_cache":
                        content = json.dumps(batch_clear_cache(fldrs), indent=2)
                    elif act == "uninstall":
                        content = json.dumps(batch_uninstall(fldrs), indent=2)
                elif name == "uninstall_isolated_app":
                    uninstall_enclosed_app(args["folder_name"])
                    content = f"Uninstalled {args['folder_name']}"
                elif name == "kill_container":
                    ok, msg, count = kill_app_processes(args["folder_name"])
                    content = msg
                elif name == "inspect_container":
                    content = json.dumps(inspect_container_contents(args["folder_name"]), indent=2)
                elif name == "resolve_dependencies":
                    fldr = args["folder_name"]
                    confirm = args.get("confirm", False)
                    if not confirm:
                        diag = analyze_container_incompatibility(fldr)
                        content = json.dumps({
                            "status": "Confirmation Required",
                            "folder": fldr,
                            "missing_libraries": diag.get("missing_libraries", []),
                            "plan": [
                                "Link internal container libraries",
                                "Ingest missing dependencies into container",
                                "Rebuild launch script & library paths"
                            ],
                            "message": "Set 'confirm': true to execute automated resolution."
                        }, indent=2)
                    else:
                        ok, msg, actions = resolve_container_dependencies(fldr)
                        content = json.dumps({"success": ok, "message": msg, "actions": actions}, indent=2)
                        is_err = not ok
                elif name == "get_enclosing_level":
                    lvl = get_enclosing_level(args["folder_name"])
                    det = get_enclosing_level_details(lvl)
                    content = json.dumps({"folder": args["folder_name"], "level": lvl, "details": det}, indent=2)
                elif name == "set_enclosing_level":
                    ok = set_enclosing_level(args["folder_name"], args["level"])
                    content = json.dumps({"folder": args["folder_name"], "level": args["level"], "success": ok}, indent=2)
                    is_err = not ok
                else:
                    content = f"Unknown tool: {name}"
                    is_err = True
            except Exception as e:
                content = str(e)
                is_err = True

            res = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": content}],
                    "isError": is_err
                }
            }
            sys.stdout.write(json.dumps(res) + "\n")
            sys.stdout.flush()

        else:
            res = {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"}
            }
            sys.stdout.write(json.dumps(res) + "\n")
            sys.stdout.flush()
