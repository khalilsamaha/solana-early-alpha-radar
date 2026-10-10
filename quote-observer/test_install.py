"""Installation control-flow tests use temporary files and mocked system services."""
import contextlib,hashlib,io,json,os,sqlite3,subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import install,rollback

class InstallTests(unittest.TestCase):
    def fixture(self,root):
        bundle=root/'bundle';bundle.mkdir();(bundle/'payload').write_text('known')
        manifest={'version':'0.6.0','files':{'payload':hashlib.sha256(b'known').hexdigest()}}
        (bundle/'manifest.json').write_text(json.dumps(manifest))
        project=root/'project';project.mkdir();(project/'package.json').write_text('{"version":"0.2.9"}')
        data=root/'data';data.mkdir();database=data/'radar.sqlite'
        with sqlite3.connect(database) as d:d.execute('CREATE TABLE evidence(x)');d.execute('INSERT INTO evidence VALUES(99)')
        reports=root/'reports';reports.mkdir();ledger=reports/'observer.sqlite'
        with sqlite3.connect(ledger) as d:d.execute('CREATE TABLE preserved(x)');d.execute("INSERT INTO preserved VALUES('cursor and data')")
        paths={'BUNDLE':bundle,'DEST':root/'lib'/'0.6.0','CONFIG':root/'config.json','REPORTS':reports,'UNIT':root/'quotes.service'}
        return project,database,ledger,paths

    @contextlib.contextmanager
    def environment(self,root,fail_restart=False):
        project,database,ledger,paths=self.fixture(root);calls=[];oldmask=os.umask(0o077)
        def run(args,**kwargs):
            calls.append(args)
            if args[0]=='node' and args[1]=='--version':return 'v24.19.0'
            if args[0]=='/usr/bin/node' and args[1]=='--version':return 'v24.19.0'
            if args[:3]==['docker','compose','ps']:return 'container'
            if args[:2]==['docker','inspect']:return json.dumps([{'Mounts':[{'Destination':'/app/data','Source':str(database.parent)}]}])
            if args[:2]==['systemctl','restart'] and fail_restart:raise RuntimeError('mock restart failure')
            return 'offline check accepted'
        try:
            with patch.multiple(install,**paths),patch('install.run',side_effect=run),patch('install.os.geteuid',return_value=0),patch('install.shutil.which',return_value='/usr/bin/node'),patch('install.subprocess.run',return_value=subprocess.CompletedProcess([],0)),patch('sys.argv',['install.py','--project',str(project),'--enable-service']),contextlib.redirect_stdout(io.StringIO()):
                expected=json.dumps({'managedBy':install.MARKER,'database':str(database),'reports':str(paths['REPORTS'])},indent=2)+'\n'
                paths['CONFIG'].write_text(expected.replace('0.6.0','0.5.0'))
                paths['UNIT'].write_text(install.unit('/usr/bin/node',database).replace('0.6.0','0.5.0'))
                yield project,database,ledger,paths,calls
        finally:os.umask(oldmask)

    def test_upgrade_and_reinstall_preserve_scanner_ledger_and_private_backup(self):
        with tempfile.TemporaryDirectory() as d,self.environment(Path(d)) as (_,database,ledger,paths,calls):
            before=(database.read_bytes(),ledger.read_bytes());install.main();install.main()
            self.assertEqual((database.read_bytes(),ledger.read_bytes()),before)
            self.assertIn('/0.6.0/observer.mjs',paths['UNIT'].read_text())
            backups=list(paths['REPORTS'].glob('pre-0.6.0-*.sqlite'));self.assertEqual(len(backups),2)
            for b in backups:
                self.assertEqual(b.stat().st_mode&0o777,0o600)
                with sqlite3.connect(b) as db:self.assertEqual(db.execute('SELECT * FROM preserved').fetchall(),[('cursor and data',)])
            self.assertFalse(any('compose' in c and 'up' in c for c in calls))

    def test_restart_failure_restores_previous_configuration_and_service(self):
        with tempfile.TemporaryDirectory() as d,self.environment(Path(d),True) as (_,database,ledger,paths,calls):
            previous=(paths['CONFIG'].read_bytes(),paths['UNIT'].read_bytes(),ledger.read_bytes())
            with self.assertRaisesRegex(RuntimeError,'mock restart'):install.main()
            self.assertEqual((paths['CONFIG'].read_bytes(),paths['UNIT'].read_bytes(),ledger.read_bytes()),previous)
            self.assertIn(['systemctl','start',paths['UNIT'].name],calls)

    def test_edited_configuration_rejected_before_service_stop(self):
        with tempfile.TemporaryDirectory() as d,self.environment(Path(d)) as (_,database,ledger,paths,calls):
            paths['UNIT'].write_text('custom service')
            with self.assertRaisesRegex(RuntimeError,'configuration differs'):install.main()
            self.assertEqual(paths['UNIT'].read_text(),'custom service')
            self.assertFalse(any(c[:2]==['systemctl','stop'] for c in calls))

    def test_verified_program_rollback_preserves_current_ledger(self):
        with tempfile.TemporaryDirectory() as d,self.environment(Path(d)) as (_,database,ledger,paths,calls):
            install.main();before=ledger.read_bytes();old=paths['DEST'].parent/'0.5.0';old.mkdir()
            (old/'payload').write_text('old');(old/'manifest.json').write_text(json.dumps({'version':'0.5.0','files':{'payload':hashlib.sha256(b'old').hexdigest()}}))
            rollback.main()
            self.assertIn('/0.5.0/observer.mjs',paths['UNIT'].read_text());self.assertEqual(ledger.read_bytes(),before)

if __name__=='__main__':unittest.main()
