"""Exercise actual MP4/SRT export options in the installed Windows runtime."""
import os,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tests.test_export_options import ExportOptionsTests
from tests.test_organization import VideoOutputTests
os.environ['QT_QPA_PLATFORM']='windows'
suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromTestCase(case) for case in (ExportOptionsTests,VideoOutputTests))
result=unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(not result.wasSuccessful())
