import unittest

from scripts.sync_ygomaster import (
    make_snapshot,
    parse_client_settings,
    parse_updatediff_version,
    replace_supported_game_version,
    TRACKED_FILES,
)


class YgoMasterSyncTests(unittest.TestCase):
    def test_parse_client_settings_allows_json_comments(self):
        text = """
        {
          "SupportedGameVersion": "2.8.0",
          "UnityPlayerVersion": "6000.1.2f1", // comment
        }
        """
        self.assertEqual(parse_client_settings(text), ("2.8.0", "6000.1.2f1"))

    def test_parse_updatediff_version(self):
        self.assertEqual(parse_updatediff_version("// Client version 2.8.0\nclass A {}"), "2.8.0")

    def test_replace_supported_version_is_idempotent(self):
        source = 'APP_VERSION = "v2.7.0_R2"\nSUPPORTED_GAME_VERSION = "2.7.0"\n'
        updated, changed = replace_supported_game_version(source, "2.8.0")
        self.assertTrue(changed)
        self.assertIn('SUPPORTED_GAME_VERSION = "2.8.0"', updated)
        second, changed_again = replace_supported_game_version(updated, "2.8.0")
        self.assertFalse(changed_again)
        self.assertEqual(second, updated)

    def test_snapshot_rejects_disagreeing_versions(self):
        contents = {}
        for path, patterns in TRACKED_FILES.items():
            text = "\n".join(patterns)
            contents[path] = (text, f"blob-{len(contents)}")
        contents["YgoMaster/Data/ClientData/ClientSettings.json"] = (
            '"SupportedGameVersion": "2.8.0"\n"UnityPlayerVersion": "6000.1.2f1"',
            "settings",
        )
        contents["Docs/updatediff.cs"] = ("// Client version 2.7.0", "updatediff")
        with self.assertRaises(ValueError):
            make_snapshot(contents)


if __name__ == "__main__":
    unittest.main()
