"""Verify online backups include WAL writes and never overwrite a backup."""
from contextlib import closing
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from backup_event import backup


class BackupTests(unittest.TestCase):
    def test_backup_includes_committed_wal_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'live.sqlite3'
            destination = Path(directory) / 'backup.sqlite3'
            with closing(sqlite3.connect(source)) as connection:
                connection.execute('PRAGMA journal_mode=WAL')
                connection.execute('CREATE TABLE scores(team TEXT,score REAL)')
                connection.execute('INSERT INTO scores VALUES(?,?)', ('Test team', 9.5))
                connection.commit()
                backup(source, destination)
                with closing(sqlite3.connect(destination)) as saved:
                    self.assertEqual(saved.execute('SELECT * FROM scores').fetchall(), [('Test team', 9.5)])
                with self.assertRaises(ValueError):
                    backup(source, destination)


if __name__ == '__main__':
    unittest.main()
