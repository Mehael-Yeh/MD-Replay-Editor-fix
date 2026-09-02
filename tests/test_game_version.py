import unittest

from main import is_supported_game_version, parse_game_version


class GameVersionTests(unittest.TestCase):
    def test_parses_numeric_version_prefix(self):
        self.assertEqual(parse_game_version("2.8.0"), (2, 8, 0))
        self.assertEqual(parse_game_version("2.9.1-preview"), (2, 9, 1))

    def test_accepts_minimum_and_future_versions(self):
        self.assertTrue(is_supported_game_version("2.8.0"))
        self.assertTrue(is_supported_game_version("2.8.1"))
        self.assertTrue(is_supported_game_version("2.9.0"))
        self.assertTrue(is_supported_game_version("3.0.0"))

    def test_rejects_older_or_unrecognized_versions(self):
        self.assertFalse(is_supported_game_version("2.7.9"))
        self.assertFalse(is_supported_game_version("unknown"))


if __name__ == "__main__":
    unittest.main()
