import re
import unittest

from scripts.set_app_version import VERSION_PATTERN, replace_version


class SetAppVersionTests(unittest.TestCase):
    def test_release_version_format(self):
        self.assertIsNotNone(VERSION_PATTERN.fullmatch("v2.8.0_R1"))
        self.assertIsNone(VERSION_PATTERN.fullmatch("2.8.0_R1"))

    def test_replaces_version_declaration(self):
        pattern = re.compile(r'^(APP_VERSION\s*=\s*)"[^"]+"', re.MULTILINE)
        source = 'APP_VERSION = "v2.7.0_R5"\nMINIMUM_GAME_VERSION = "2.8.0"\n'
        updated = replace_version(source, pattern, "v2.8.0_R1")
        self.assertEqual(
            updated,
            'APP_VERSION = "v2.8.0_R1"\nMINIMUM_GAME_VERSION = "2.8.0"\n',
        )

    def test_requires_one_declaration(self):
        pattern = re.compile(r'^(APP_VERSION\s*=\s*)"[^"]+"', re.MULTILINE)
        with self.assertRaises(ValueError):
            replace_version("", pattern, "v2.8.0_R1")


if __name__ == "__main__":
    unittest.main()
