import os
import queue
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from replay_scanner import ReplayScanner
from replay_store import ReplayStore


def payload(number):
    return f'replaym-payload-{number}'.encode().hex()


class IndexTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = ReplayStore(Path(self.tmp.name))

    def test_warm_index_avoids_reading_unchanged_payloads(self):
        for index in range(100):
            (self.store.directory / f'{index}.replay').write_text(payload(index))
        with patch.object(self.store, 'read', wraps=self.store.read) as read:
            self.store.warm_index()
            self.assertEqual(read.call_count, 100)
            read.reset_mock()
            self.store.warm_index()
            self.assertEqual(read.call_count, 0)
            self.assertFalse(self.store.save(payload(99)).created)
            self.assertEqual(read.call_count, 1)  # Full verification of the matching candidate only.
            read.reset_mock()
            self.assertTrue(self.store.save(payload(101)).created)
            self.assertEqual(read.call_count, 0)

    def test_external_rename_edit_delete_and_addition_are_reconciled(self):
        original = self.store.save(payload(1)).path
        renamed = original.with_name('renamed.replay')
        original.rename(renamed)
        self.assertEqual(self.store.save(payload(1)).path, renamed)
        info = renamed.stat()
        renamed.write_text(payload(2))
        os.utime(renamed, ns=(info.st_atime_ns, info.st_mtime_ns))
        self.assertEqual(self.store.save(payload(2)).path, renamed)
        self.assertTrue(self.store.save(payload(1)).created)
        renamed.unlink()
        self.assertTrue(self.store.save(payload(2)).created)
        external = self.store.directory / 'external.replay'
        external.write_text(payload(3).upper())
        self.assertEqual(self.store.save(payload(3)).path, external)

    def test_invalid_file_is_cached_but_retried_after_repair(self):
        path = self.store.directory / 'invalid.replay'
        path.write_text('invalid')
        self.store.warm_index()
        with patch.object(self.store, 'read', wraps=self.store.read) as read:
            self.store.warm_index()
            read.assert_not_called()
        path.write_text(payload(1))
        self.assertEqual(self.store.save(payload(1)).path, path)

    def test_read_error_is_retried(self):
        path = self.store.directory / 'unreadable.replay'
        path.write_text(payload(1))
        with patch.object(self.store, 'read', side_effect=PermissionError()):
            self.store.warm_index()
        self.assertEqual(self.store.save(payload(1)).path, path)

    def test_digest_collision_still_checks_contents(self):
        with patch('replay_store.hashlib.sha256') as digest:
            digest.return_value.hexdigest.return_value = 'a' * 64
            first = self.store.save(payload(1))
            second = self.store.save(payload(2))
            self.assertTrue(second.created)
            self.assertNotEqual(first.path, second.path)
            self.assertEqual(self.store.read(first.path), payload(1))

    def test_changed_while_reading_is_not_cached(self):
        path = self.store.directory / 'changing.replay'
        path.write_text(payload(1))
        read = self.store.read
        def changing(candidate):
            value = read(candidate)
            candidate.write_text(payload(200))
            return value
        with patch.object(self.store, 'read', side_effect=changing):
            self.store.warm_index()
        self.assertNotIn(path, self.store._index)
        self.assertEqual(self.store.save(payload(200)).path, path)


class ScannerTests(unittest.TestCase):
    def test_coalesces_requests_and_publishes_before_indexing(self):
        entered, release = threading.Event(), threading.Event()
        def list_entries():
            entered.set()
            release.wait(5)
            return []
        store = Mock()
        store.list_entries.side_effect = list_entries
        scanner = ReplayScanner(store)
        self.addCleanup(scanner.close)
        self.addCleanup(release.set)
        scanner.request()
        self.assertTrue(entered.wait(2))
        for _ in range(30):
            latest = scanner.request()
        release.set()
        for _ in range(2):
            generation, rows, error = scanner.results.get(timeout=3)
            if generation == latest:
                break
        self.assertEqual(generation, latest)
        self.assertEqual(rows, [])
        self.assertIsNone(error)
        self.assertLessEqual(store.list_entries.call_count, 2)

    def test_error_is_reported_and_next_request_recovers(self):
        store = Mock()
        store.list_entries.side_effect = [PermissionError('denied'), []]
        scanner = ReplayScanner(store)
        self.addCleanup(scanner.close)
        scanner.request()
        self.assertIn('denied', scanner.results.get(timeout=3)[2])
        generation = scanner.request()
        self.assertEqual(scanner.results.get(timeout=3), (generation, [], None))

    def test_close_during_scan_does_not_publish_or_wait(self):
        entered, release = threading.Event(), threading.Event()
        def blocked():
            entered.set()
            release.wait(5)
            return []
        store = Mock()
        store.list_entries.side_effect = blocked
        scanner = ReplayScanner(store)
        self.addCleanup(release.set)
        scanner.request()
        self.assertTrue(entered.wait(2))
        scanner.close()
        release.set()
        scanner._thread.join(2)
        self.assertFalse(scanner._thread.is_alive())
        self.assertTrue(scanner.results.empty())
