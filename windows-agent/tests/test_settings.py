import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import lecture_agent


class SettingsTests(unittest.TestCase):
    def test_location_rules_persist_and_partial_updates_preserve_other_settings(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(lecture_agent, "SETTINGS_FILE", Path(directory) / "settings.json"):
            defaults = lecture_agent.load_settings()
            self.assertFalse(defaults["locationRules"]["thirdSite"])
            self.assertFalse(defaults["locationRules"]["nanjing"])
            result = lecture_agent.update_settings(auto_enabled=False, location_rules={"thirdSite": True})
            self.assertFalse(result["autoEnabled"])
            self.assertTrue(result["locationRules"]["thirdSite"])
            result = lecture_agent.update_settings(location_rules={"firstSite": False})
            self.assertFalse(result["autoEnabled"])
            self.assertTrue(result["locationRules"]["thirdSite"])
            self.assertFalse(result["locationRules"]["firstSite"])
            self.assertTrue(result["locationRules"]["secondSite"])

    def test_invalid_rules_are_rejected_without_writing(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(lecture_agent, "SETTINGS_FILE", Path(directory) / "settings.json"):
            with self.assertRaises(ValueError):
                lecture_agent.update_settings(location_rules={"unknown": True})
            with self.assertRaises(ValueError):
                lecture_agent.update_settings(location_rules={"thirdSite": "yes"})
            self.assertFalse(lecture_agent.SETTINGS_FILE.exists())


if __name__ == "__main__":
    unittest.main()
