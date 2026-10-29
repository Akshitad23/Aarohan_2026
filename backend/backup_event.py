"""Create a consistent SQLite backup while the event server is running."""
import argparse
from contextlib import closing
from pathlib import Path
import sqlite3


def backup(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if not source.is_file():
        raise ValueError('The source database does not exist.')
    if destination.exists():
        raise ValueError('Choose a new destination. Existing backups are never overwritten.')
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Reserve the filename exclusively before SQLite opens it.
    with destination.open('xb'):
        pass
    try:
        with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as origin:
            with closing(sqlite3.connect(destination)) as target:
                origin.backup(target)
                if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise RuntimeError('Backup integrity check failed.')
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    return destination


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', help='Path to the live event database')
    parser.add_argument('destination', help='Path to a new backup file')
    args = parser.parse_args()
    print(backup(args.source, args.destination))
