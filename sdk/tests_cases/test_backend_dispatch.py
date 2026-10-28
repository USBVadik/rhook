from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest import mock
from developer.files import save
from test_capsules import fixture
from rhook_alpha.cases.api import CaseSDK
from rhook_alpha.cases import backends
from rhook_alpha.cases.capsule import seal

class BackendDispatch(unittest.TestCase):
    def test_capsule_profile_does_not_import_arbitrary_code(self):
        with self.assertRaisesRegex(ValueError,'UNSUPPORTED_EXECUTION_PROFILE'):
            backends.get_backend('module.selected.by.untrusted.data')
    def test_a_registered_profile_routes_without_core_case_constants(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();d,p=fixture();d['execution']['profile']='synthetic/profile';d=seal(d)
            src=root/'src';src.mkdir();save(src/'CAPSULE.json',d);(src/'BLOCK_PACKAGE.json').write_bytes(p)
            sdk=CaseSDK(root/'home');sdk.import_case(src)
            backend=SimpleNamespace(authenticate=lambda sdk,case,**kw:{'status':'SYNTHETIC_ROUTE_ONLY','routedCase':case})
            with mock.patch.dict(backends.BUILTINS,{'synthetic/profile':backend}):
                self.assertEqual(sdk.authenticate('one')['routedCase'],'one')
if __name__=='__main__':unittest.main()
