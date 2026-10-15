import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app_i18n import load_language, save_language
from app_settings import settings_path, save_setting
from app_theme import DARK, LIGHT, load_theme, resolve_theme, save_theme, system_theme
from replay_store import ReplayStore


class ThemeTests(unittest.TestCase):
    def test_default_and_invalid_preferences(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / 'replays'
            self.assertEqual(load_theme(directory), 'system')
            for content in ('bad json', '[]', 'null', '{"theme": []}', '{"theme": "unknown"}'):
                settings_path(directory).write_text(content, encoding='utf-8')
                self.assertEqual(load_theme(directory), 'system')

    def test_preferences_preserve_each_other_and_unknown_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / 'replays'
            save_setting(directory, 'future', 'preserved')
            save_theme(directory, 'dark')
            save_language(directory, 'en')
            self.assertEqual(load_theme(directory), 'dark')
            save_theme(directory, 'system')
            self.assertEqual(load_language(directory), 'en')
            self.assertEqual(json.loads(settings_path(directory).read_text())['future'], 'preserved')

    def test_failed_atomic_replace_preserves_settings_and_cleans_temporary(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / 'replays'
            save_theme(directory, 'light')
            with patch('app_settings.os.replace', side_effect=OSError('disk full')):
                with self.assertRaises(OSError):
                    save_theme(directory, 'dark')
            self.assertEqual(load_theme(directory), 'light')
            self.assertEqual(list(Path(tmp).glob('*.tmp')), [])

    def test_manual_theme_does_not_query_system(self):
        with patch('app_theme.system_theme', return_value='dark') as system:
            self.assertEqual(resolve_theme('light'), 'light')
            system.assert_not_called()
            self.assertEqual(resolve_theme('system'), 'dark')

    def test_windows_registry_and_fallback(self):
        registry = MagicMock()
        with patch('app_theme.sys.platform', 'win32'), patch.dict('sys.modules', winreg=registry):
            registry.QueryValueEx.return_value = (0, 4)
            self.assertEqual(system_theme(), 'dark')
            registry.QueryValueEx.return_value = (1, 4)
            self.assertEqual(system_theme(), 'light')
            registry.OpenKey.side_effect = OSError('missing registry key')
            self.assertEqual(system_theme(), 'light')

    def test_palette_roles_have_unambiguous_round_trip(self):
        self.assertEqual(LIGHT.keys(), DARK.keys())
        for palette in (LIGHT, DARK):
            self.assertEqual(len(set(palette.values())), len(palette))


class StoreRobustnessTests(unittest.TestCase):
    def test_reserved_basename_with_extension_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ReplayStore(Path(tmp))
            path = store.save(b'replaym-data'.hex()).path
            for name in ('CON.txt', 'nul.backup', 'LPT1.log', 'COM9.foo'):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    store.rename(path, name)
            self.assertTrue(path.exists())

    def test_listing_skips_directories_and_disappearing_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ReplayStore(Path(tmp))
            (Path(tmp) / 'folder.replay').mkdir()
            self.assertEqual(store.list(), [])
            vanished = MagicMock()
            vanished.stat.side_effect = FileNotFoundError()
            with patch.object(Path, 'glob', return_value=[vanished]):
                self.assertEqual(store.list_entries(), [])


class ThemeGuiTests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f'Display unavailable: {exc}')
        root.destroy()
        from main import ReplayApp
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.app = ReplayApp(Path(self.directory.name) / 'replays')
        self.addCleanup(self.app.close)

    def test_live_switch_preserves_selection_and_open_dialogs(self):
        app = self.app
        replay = app.store.save(b'replaym-data'.hex()).path
        app.refresh()
        app.tree.selection_set(str(replay))
        app.show_log_window()
        app.show_tutorial()
        app.show_rename_dialog(replay)
        app.root.update_idletasks()
        for theme in ('dark', 'light', 'dark'):
            app.theme_choice.set(theme)
            app.change_theme()
            app.root.update_idletasks()
            self.assertEqual(app.root.cget('bg'), app.BG)
            self.assertEqual(app.log_text.cget('bg'), app.CARD)
            self.assertEqual(app.selected_path(), replay)
            self.assertTrue(app.rename_window.winfo_exists())
            self.assertEqual(load_theme(app.store.directory), theme)
        app.change_language()
        self.assertEqual(load_theme(app.store.directory), 'dark')

    def test_system_changes_only_apply_in_system_mode(self):
        app = self.app
        app.theme_preference = 'system'
        app.root.after_cancel(app._theme_job)
        with patch('app_theme.system_theme', return_value='dark'):
            app.poll_system_theme()
        self.assertEqual(app.theme, 'dark')
        app.theme_preference = 'light'
        app.apply_theme('light')
        app.root.after_cancel(app._theme_job)
        with patch('app_theme.system_theme', return_value='dark'):
            app.poll_system_theme()
        self.assertEqual(app.theme, 'light')
