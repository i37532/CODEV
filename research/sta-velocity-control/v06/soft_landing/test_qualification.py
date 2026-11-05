import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from qualification import require_qualification

ROOT=Path(__file__).resolve().parent


class Qualification(unittest.TestCase):
    def test_actual_complete_qualification(self):
        self.assertEqual(require_qualification(ROOT/'qualified_contact.json')['accepted'],6)

    def test_wrong_budget_mode_or_configuration(self):
        original=json.loads((ROOT/'qualified_contact.json').read_text())
        for key,value in [('qualified',False),('accepted',5),('pairs',2),('contact_settings',{}),('contact_source_sha256','wrong')]:
            q=copy.deepcopy(original); q[key]=value
            # Only JSON is replaced; real source/evidence checks remain active.
            with patch('qualification.json.loads',return_value=q),self.assertRaises(ValueError):
                require_qualification(ROOT/'qualified_contact.json')

    def test_corrupt_evidence(self):
        q=json.loads((ROOT/'qualified_contact.json').read_text())
        q['evidence_sha256'][next(iter(q['evidence_sha256']))]='wrong'
        with patch('qualification.json.loads',return_value=q),self.assertRaises(ValueError):
            require_qualification(ROOT/'qualified_contact.json')


if __name__=='__main__': unittest.main()
