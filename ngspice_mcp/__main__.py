"""Launch the local stdio MCP server."""
import argparse
import json
import os
from pathlib import Path


def main():
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library', help='Full path to the shared ngspice library')
    default_config = root/'.local/mcp-config.json'
    if not default_config.exists():
        default_config = root/'.local/config.json'
    parser.add_argument('--config', type=Path, default=default_config, help='Optional local setup configuration')
    parser.add_argument('--workspace', type=Path, default=root, help='Root for trusted circuit paths')
    parser.add_argument('--output', type=Path, default=root/'runs/mcp', help='Persistent run and replay directory')
    parser.add_argument('--max-sessions', type=int, default=4)
    args = parser.parse_args()
    config = json.loads(args.config.read_text()) if args.config.exists() else {}
    library = args.library or os.environ.get('NGSPICE_LIBRARY') or config.get('ngspice_library')
    if not library or not Path(library).is_file():
        parser.error('Supply --library /path/to/libngspice.so (or .dylib), or run setup-mcp.sh')
    if not 1 <= args.max_sessions <= 16:
        parser.error('--max-sessions must be in [1,16]')
    from .server import Manager, make_server
    manager = Manager(library, args.workspace, args.output, args.max_sessions)
    try:
        make_server(manager).run(transport='stdio')
    finally:
        manager.close()

if __name__ == '__main__':
    main()
