import tempfile
from pathlib import Path
import unittest
from rhook_alpha.cases.authority import issue, consume
from developer.files import load, save

class Authority(unittest.TestCase):

    def test_one_shot_and_exact_binding(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp).resolve()
            key = b'k' * 32
            b = {'planId': 'c-' + 'a' * 32, 'capsuleId': '1' * 64, 'operationCommitment': '2' * 64}
            grant = issue(p, b, key, now=1000)
            with self.assertRaisesRegex(ValueError, 'GRANT_BINDING'):
                consume(grant, p, dict(b, capsuleId='3' * 64), key, now=1001)
            self.assertEqual(consume(grant, p, b, key, now=1001)['binding'], b)
            with self.assertRaises(FileExistsError):
                consume(grant, p, b, key, now=1001)

    def test_invalid_hmac_and_expiry_never_consume(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp).resolve()
            key = b'k' * 32
            b = {'planId': 'c-' + 'a' * 32, 'capsuleId': '1' * 64, 'operationCommitment': '2' * 64}
            g = issue(p, b, key, now=1000)
            with self.assertRaises(ValueError):
                consume(g, p, b, key, now=1500)
            with self.assertRaises(ValueError):
                consume(g, p, b, b'z' * 32, now=1001)
            self.assertFalse((g.parent / 'CONSUMED.json').exists())
if __name__ == '__main__':
    unittest.main()
