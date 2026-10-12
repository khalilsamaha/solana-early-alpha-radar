import importlib.util,json,tempfile,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('backup_status',Path(__file__).with_name('backup-status.py'));x=importlib.util.module_from_spec(spec);spec.loader.exec_module(x)
class BackupStatusTests(unittest.TestCase):
 def test_private_fields_are_never_exported_and_stale_success_keeps_date(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'status';p.write_text(json.dumps({'success':True,'remote':'private','error':'private','state':'complete','started_at':'2026-10-01T01:00:00+00:00','bytes':100}));r=x.load(p,1800000000);self.assertNotIn('private',str(r));self.assertTrue(r['hasError']);self.assertTrue(r['success']);self.assertEqual(r['bytes'],100);self.assertEqual(r['started_at'],'2026-10-01T01:00:00+00:00')
 def test_missing_bad_oversized_symlink_and_inventory_cap(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'status';self.assertEqual(x.load(p,0)['status'],'missing');p.write_text('bad');self.assertEqual(x.load(p,0)['status'],'unreadable-or-invalid');p.write_text('x'*65537);self.assertEqual(x.load(p,0)['status'],'refused-input');link=Path(d)/'link';link.symlink_to(p);self.assertEqual(x.load(link,0)['status'],'refused-input');self.assertTrue(x.inventory(Path(d),limit=1)['truncated'])
if __name__=='__main__':unittest.main()
