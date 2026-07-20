import tempfile
import unittest
from pathlib import Path
from string import Formatter

from main import (
    DEFAULT_LANGUAGE,
    ENGLISH_TRANSLATIONS,
    ReplayManager,
    ReplayStore,
    load_language,
    save_language,
    settings_path,
    translate,
)


class LanguageTests(unittest.TestCase):
    def test_translation_placeholders_match_source_text(self):
        for source, target in ENGLISH_TRANSLATIONS.items():
            with self.subTest(source=source):
                source_fields = {name for _, name, _, _ in Formatter().parse(source) if name}
                target_fields = {name for _, name, _, _ in Formatter().parse(target) if name}
                self.assertEqual(target_fields, source_fields)

    def test_english_translation_formats_values(self):
        self.assertEqual(
            translate("en", "Master Duel 回放助手"),
            "Master Duel Replay Editor",
        )
        self.assertEqual(
            translate("en", "已保存的回放（{count}）", count=3),
            "Saved Replays (3)",
        )
        self.assertEqual(
            translate("zh-CN", "已保存的回放（{count}）", count=3),
            "已保存的回放（3）",
        )

    def test_language_setting_is_saved_and_loaded(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "replays"
            data_dir.mkdir()
            self.assertEqual(load_language(data_dir), DEFAULT_LANGUAGE)

            save_language(data_dir, "en")

            self.assertEqual(load_language(data_dir), "en")
            self.assertTrue(settings_path(data_dir).exists())

    def test_unknown_or_invalid_language_falls_back_to_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "replays"
            data_dir.mkdir()
            settings_path(data_dir).write_text('{"language": "xx"}', encoding="utf-8")
            self.assertEqual(load_language(data_dir), DEFAULT_LANGUAGE)

            settings_path(data_dir).write_text("not json", encoding="utf-8")
            self.assertEqual(load_language(data_dir), DEFAULT_LANGUAGE)

    def test_replay_store_uses_selected_language_for_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ReplayStore(Path(tmp), lambda text, **values: translate("en", text, **values))
            with self.assertRaisesRegex(ValueError, "Enter a new replay name"):
                replay = store.save((b"\x01replaym-data").hex()).path
                store.rename(replay, "")

    def test_structured_agent_messages_use_selected_language(self):
        with tempfile.TemporaryDirectory() as tmp:
            events = []
            translator = lambda text, **values: translate("en", text, **values)
            store = ReplayStore(Path(tmp), translator)
            manager = ReplayManager(store, lambda kind, data=None: events.append((kind, data)), translator)
            manager._on_message(
                {
                    "type": "send",
                    "payload": {
                        "type": "log",
                        "data": {
                            "message": "agent.game_version_read_failed",
                            "error": "unavailable",
                        },
                    },
                },
                None,
            )
            self.assertEqual(events[-1], ("log", "Failed to read the game version: unavailable"))


if __name__ == "__main__":
    unittest.main()
