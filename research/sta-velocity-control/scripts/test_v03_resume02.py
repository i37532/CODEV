import json
import unittest
import run_v03_resume02 as resume


class ResumeProtocolTest(unittest.TestCase):
    def test_only_authorization_and_provenance_change(self):
        old = json.loads((resume.CONFIG.parent/'protocol01/protocol.json').read_text())
        new = json.loads((resume.CONFIG/'protocol.json').read_text())
        for key in ('stage', 'authorization', 'history'):
            old.pop(key, None)
            new.pop(key, None)
        self.assertEqual(old, new)
        self.assertEqual(new['maximum_attempts'], 1)

    def test_entry_selects_same_new_protocol_for_runner_and_analysis(self):
        previous = (resume.analysis.CONFIG, resume.runner.CONFIG,
                    resume.runner.Checks, resume.runner.analyze)
        try:
            resume.configure()
            self.assertEqual(resume.runner.CONFIG, resume.CONFIG)
            self.assertEqual(resume.analysis.CONFIG, resume.CONFIG)
            self.assertIs(resume.runner.Checks, resume.Checks)
            self.assertIs(resume.runner.analyze, resume.analysis.analyze)
        finally:
            (resume.analysis.CONFIG, resume.runner.CONFIG,
             resume.runner.Checks, resume.runner.analyze) = previous
