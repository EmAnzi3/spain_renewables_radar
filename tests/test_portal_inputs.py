import tempfile,unittest,zipfile
from pathlib import Path
from scripts.portal_inputs import extract_checked

class ArtifactTests(unittest.TestCase):
    def test_normal_artifact_paths_are_retained(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);z=root/'a.zip'
            with zipfile.ZipFile(z,'w') as f:f.writestr('reports/data.json','{}')
            extract_checked(z,root/'out');self.assertEqual((root/'out/reports/data.json').read_text(),'{}')
    def test_parent_paths_are_not_extracted(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);z=root/'a.zip'
            with zipfile.ZipFile(z,'w') as f:f.writestr('../escape','unsafe')
            with self.assertRaises(ValueError):extract_checked(z,root/'out')
            self.assertFalse((root/'escape').exists())
    def test_symlinks_are_not_extracted(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);z=root/'a.zip';item=zipfile.ZipInfo('link');item.external_attr=0o120777<<16
            with zipfile.ZipFile(z,'w') as f:f.writestr(item,'/etc/passwd')
            with self.assertRaises(ValueError):extract_checked(z,root/'out')
