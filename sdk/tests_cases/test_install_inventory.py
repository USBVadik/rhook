"""Install only accepted runtime source, never a modified research tree."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
spec=importlib.util.spec_from_file_location('case_installer_under_test',ROOT/'install_cases.py')
installer=importlib.util.module_from_spec(spec);spec.loader.exec_module(installer)

class InstallationInventory(unittest.TestCase):
    def source(self,root):
        source=root/'source';source.mkdir()
        for name in ('rhook_alpha','developer','engine'):
            shutil.copytree(ROOT/name,source/name,ignore=shutil.ignore_patterns('__pycache__','*.pyc','node_modules','.DS_Store'))
        if (ROOT/'case-install-inventory.json').exists():
            shutil.copyfile(ROOT/'case-install-inventory.json',source/'case-install-inventory.json')
        return source

    def test_changed_resource_policy_is_rejected_before_destination_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();source=self.source(root);prefix=root/'install'
            path=source/'engine/case_sdk/policy.json';policy=json.loads(path.read_bytes())
            policy['minimumAdmissionFreeBytes']=policy['minimumRuntimeFreeBytes']=0
            path.write_text(json.dumps(policy))
            with patch.object(installer,'ROOT',source),self.assertRaisesRegex(ValueError,'INSTALL_SOURCE_DRIFT'):
                installer.install(prefix)
            self.assertFalse(prefix.exists())

    def test_unreviewed_research_module_cannot_enter_installation(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();source=self.source(root);prefix=root/'install'
            extra=source/'rhook_alpha/cases/calibration25';extra.mkdir()
            (extra/'__init__.py').write_text('raise RuntimeError("unreviewed research")\n')
            with patch.object(installer,'ROOT',source),self.assertRaisesRegex(ValueError,'INSTALL_SOURCE_INVENTORY'):
                installer.install(prefix)
            self.assertFalse(prefix.exists())

    def test_inventory_edit_cannot_authorize_a_policy_change(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();source=self.source(root);prefix=root/'install'
            path=source/'case-install-inventory.json';path.write_bytes(path.read_bytes()+b' ')
            with patch.object(installer,'ROOT',source),self.assertRaisesRegex(ValueError,'INSTALL_INVENTORY_PIN_MISMATCH'):
                installer.install(prefix)
            self.assertFalse(prefix.exists())

    def test_source_symlink_cannot_enter_installation(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();source=self.source(root);prefix=root/'install'
            path=source/'engine/case_sdk/policy.json';content=path.read_bytes();path.unlink()
            outside=root/'external-policy';outside.write_bytes(content);path.symlink_to(outside)
            with patch.object(installer,'ROOT',source),self.assertRaisesRegex(ValueError,'INSTALL_SOURCE_SYMLINK'):
                installer.install(prefix)
            self.assertFalse(prefix.exists())

    def test_copy_uses_admitted_bytes_even_if_source_changes_after_admission(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();source=self.source(root);prefix=root/'install'
            path=source/'engine/case_sdk/policy.json';expected=path.read_bytes();mkdir=Path.mkdir
            def mutate_at_creation(target,*args,**kwargs):
                if target==prefix:path.write_bytes(b'changed after source admission')
                return mkdir(target,*args,**kwargs)
            with patch.object(installer,'ROOT',source),patch.object(Path,'mkdir',mutate_at_creation):
                installer.install(prefix)
            self.assertEqual((prefix/'lib/engine/case_sdk/policy.json').read_bytes(),expected)
            receipt=json.loads((prefix/'CASE_INSTALL.json').read_bytes())
            self.assertEqual(receipt['sourceInventorySha256'],installer.INVENTORY_SHA256)
            self.assertFalse((prefix/'lib/rhook_alpha/cases/calibration25').exists())

    def test_missing_native_runtime_has_an_explicit_setup_error(self):
        from test_plans import hookr
        from developer.files import save
        from rhook_alpha.cases.api import CaseSDK
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();bundle=root/'bundle';bundle.mkdir()
            descriptor,raw=hookr();save(bundle/'CAPSULE.json',descriptor);(bundle/'BLOCK_PACKAGE.json').write_bytes(raw)
            sdk=CaseSDK(root/'home');sdk.import_case(bundle)
            with patch('subprocess.Popen',side_effect=AssertionError('NATIVE_FORBIDDEN')):
                with self.assertRaisesRegex(FileNotFoundError,'NATIVE_RUNTIME_MISSING'):
                    sdk.authenticate('hookr-one')

    def test_existing_runtime_entrypoint_modes_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            prefix=Path(directory).resolve()/'install'
            installer.install(prefix)
            for name in ('rhook','rhook-case','rhook-v2'):
                self.assertEqual((prefix/'lib/engine'/name).stat().st_mode&0o777,0o755)

    def test_tampered_validation_helper_is_not_imported_in_fresh_process(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();source=self.source(root);prefix=root/'install';marker=root/'helper-imported'
            shutil.copyfile(ROOT/'install_cases.py',source/'install_cases.py')
            helper=source/'developer/files.py'
            helper.write_bytes(helper.read_bytes()+('\ndef require(ok,code): return None\nPath('+repr(str(marker))+').write_text("untrusted import ran")\n').encode())
            policy=source/'engine/case_sdk/policy.json';value=json.loads(policy.read_bytes());value['minimumAdmissionFreeBytes']=0;policy.write_text(json.dumps(value))
            result=subprocess.run([sys.executable,'-I','-S','-B',str(source/'install_cases.py'),'--prefix',str(prefix)],capture_output=True,text=True,timeout=10)
            self.assertNotEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertFalse(prefix.exists())
            self.assertFalse(marker.exists(),'untrusted helper must be rejected before any import')

if __name__=='__main__':unittest.main()
