"""Private tmpfs ownership, durable archival and exact flight diff regression."""
import inspect
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import ram_log
import common
import run


class RamLogTest(unittest.TestCase):
    def root(self):
        t=tempfile.TemporaryDirectory(prefix='px4-v07-',dir='/dev/shm')
        self.addCleanup(t.cleanup)
        return Path(t.name)

    def source(self,root):
        p=root/'sess001/log001.ulg';p.parent.mkdir();p.write_bytes(b'ULog-test\x00'*1000)
        return p

    def test_private_tmpfs_create_and_validate(self):
        root=ram_log.create()
        self.addCleanup(root.rmdir)
        self.assertEqual(ram_log.validate(root),root)
        self.assertEqual(root.stat().st_mode&0o777,0o700)

    def test_wrong_root_permissions_owner_filesystem(self):
        root=self.root()
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(ValueError):ram_log.validate(Path(t))
        root.chmod(0o755)
        with self.assertRaises(ValueError):ram_log.validate(root)
        root.chmod(0o700)
        with patch.object(ram_log.os,'geteuid',return_value=os.geteuid()+1):
            with self.assertRaises(ValueError):ram_log.validate(root)
        with patch.object(ram_log.subprocess,'check_output',return_value='ext4\n'):
            with self.assertRaises(ValueError):ram_log.validate(root)

    def test_capacity_rejects_before_creating_root(self):
        from collections import namedtuple
        usage=namedtuple('Usage','total used free')(100,99,1)
        with patch.object(ram_log.shutil,'disk_usage',return_value=usage),patch.object(ram_log.tempfile,'mkdtemp') as create:
            with self.assertRaises(RuntimeError):ram_log.create()
            create.assert_not_called()

    def test_file_and_directory_symlinks_rejected(self):
        root=self.root();source=self.source(root)
        for name,target in [('bad.ulg',source),('other',source.parent)]:
            link=root/name;link.symlink_to(target)
            with self.assertRaises(ValueError):ram_log.paths(root)
            link.unlink()

    def test_root_symlink_rejected(self):
        root=self.root();parent=self.root();link=parent/'link';link.symlink_to(root)
        with self.assertRaises(ValueError):ram_log.validate(link)

    def test_archive_identical_fsync_file_and_directory_preserves_source(self):
        root=self.root();source=self.source(root)
        with tempfile.TemporaryDirectory() as t,patch.object(ram_log.os,'fsync',wraps=os.fsync) as sync:
            dest=Path(t)/source.name;r=ram_log.archive(source,dest,root)
            self.assertEqual(sync.call_count,2)
            self.assertEqual(source.read_bytes(),dest.read_bytes())
            self.assertEqual(r['sha256'],ram_log.digest(source))
            self.assertTrue(r['durable_copy_verified'] and r['volatile_source_retained'])

    def test_existing_archive_never_overwritten(self):
        root=self.root();source=self.source(root)
        with tempfile.TemporaryDirectory() as t:
            dest=Path(t)/source.name;dest.write_bytes(b'historical')
            with self.assertRaises(FileExistsError):ram_log.archive(source,dest,root)
            self.assertEqual(dest.read_bytes(),b'historical');self.assertTrue(source.exists())

    def test_archive_sync_failure_retains_ram(self):
        root=self.root();source=self.source(root);before=source.read_bytes()
        with tempfile.TemporaryDirectory() as t,patch.object(ram_log.os,'fsync',side_effect=OSError('disk fault')):
            with self.assertRaises(OSError):ram_log.archive(source,Path(t)/source.name,root)
            self.assertEqual(source.read_bytes(),before)

    def test_mutated_source_rejected_not_claimed_durable(self):
        root=self.root();source=self.source(root)
        with tempfile.TemporaryDirectory() as t,patch.object(ram_log,'digest',side_effect=['before','after']):
            with self.assertRaisesRegex(RuntimeError,'fingerprint'):ram_log.archive(source,Path(t)/source.name,root)

    def test_foreign_source_rejected(self):
        root=self.root();foreign=self.source(self.root())
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(ValueError):ram_log.archive(foreign,Path(t)/foreign.name,root)

    def test_runner_wires_private_root_no_shared_directory_change(self):
        self.assertIn('ram_log.create()',inspect.getsource(run.Checks.prepare_environment))
        self.assertIn('PX4_SITL_LOG_DIR',inspect.getsource(run.Checks.prepare_environment))
        self.assertIn('ram_log.paths(self.log_root)',inspect.getsource(run.Checks.log_paths))
        self.assertIn('owned_log(self.log_root,self.logs_before)',inspect.getsource(run.Checks.start_heading))

    def test_exact_flight_changes_only_environment_and_postshutdown_archive(self):
        old=(common.CONFIG.parent/'protocol05/flight.py').read_text()
        new=(common.CONFIG/'flight.py').read_text()
        expected=old.replace('from handoff_capture import Handoff, local_xy_ok\n','from handoff_capture import Handoff, local_xy_ok\nimport ram_log\n')
        expected=expected.replace('    old_logs = set(ROOTFS.glob("log/**/*.ulg"))\n','')
        expected=expected.replace('("PX4_SITL_WORLD", "GAZEBO_MASTER_URI")','("PX4_SITL_WORLD", "GAZEBO_MASTER_URI", "PX4_SITL_LOG_DIR")')
        start=expected.index('        for path in sorted(set(ROOTFS.glob("log/**/*.ulg")) - old_logs):')
        end=expected.index('        result["finished_utc"]',start)
        expected=expected[:start]+'''        try:
            for path in checks.log_paths():
                result["logs"].append(ram_log.archive(path,output/path.name,checks.log_root))
        except Exception as exc:
            result["archive_error"]=repr(exc)
            result["success"]=False
'''+expected[end:]
        self.assertEqual(new,expected)


if __name__=='__main__':unittest.main(verbosity=2)
