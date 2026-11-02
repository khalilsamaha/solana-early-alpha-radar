"""Keep every module in exactly one CI partition as new tests are added."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('partitioner',HERE/'check-position-book.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class PartitionTests(unittest.TestCase):
    def test_real_modules_covered_once_and_heavy_suites_isolated(self):
        root=HERE.parent/'position-book'
        groups=[m.selected(root,i) for i in range(9)]
        all_paths=[p for group in groups for p in group]
        self.assertEqual(sorted(all_paths),sorted(root.glob('test_*.py')))
        self.assertEqual(len(set(all_paths)),len(all_paths))
        self.assertTrue(all(groups))
        self.assertEqual([p.name for p in groups[6]],['test_exit_submission.py'])
        self.assertEqual([p.name for p in groups[7]],['test_exit_closure.py'])
        self.assertEqual([p.name for p in groups[8]],['test_exit_accounting.py'])

    def test_new_modules_remain_covered_without_duplicate_dedicated_suites(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            names=['test_exit_submission.py','test_exit_closure.py','test_exit_accounting.py']+[f'test_new_{i:02}.py' for i in range(19)]
            for name in names:(root/name).touch()
            before={p.name:i for i in range(9) for p in m.selected(root,i)}
            (root/'test_added_before_everything.py').touch();names.append('test_added_before_everything.py')
            after={p.name:i for i in range(9) for p in m.selected(root,i)}
            self.assertTrue(all(after[name]==group for name,group in before.items()))
            actual=[p.name for i in range(9) for p in m.selected(root,i)]
            self.assertEqual(sorted(actual),sorted(names));self.assertEqual(len(actual),len(set(actual)))


if __name__=='__main__':unittest.main()
