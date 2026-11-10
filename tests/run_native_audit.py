"""Final caption audit is read-only; re-recognition remains an explicit action."""
import os,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tests.test_subtitle_audit import AuditModelTests,AuditUITests
os.environ['QT_QPA_PLATFORM']='windows'
suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromTestCase(case) for case in (AuditModelTests,AuditUITests))
result=unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(not result.wasSuccessful())
