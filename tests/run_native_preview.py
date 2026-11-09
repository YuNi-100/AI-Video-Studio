"""Preview fitting and compact layout checks using real Windows widgets."""
import os,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ['STUDIO_NATIVE_PREVIEW_TEST']='1'
from tests.test_preview_fit import PreviewFitTests,CompactTimelineTests
from tests.test_workspace_search import WorkspaceSearchTests
from tests.test_seek_slider import SeekSliderTests
os.environ['QT_QPA_PLATFORM']='windows'
suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromTestCase(case) for case in (PreviewFitTests,CompactTimelineTests,SeekSliderTests,WorkspaceSearchTests))
result=unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(not result.wasSuccessful())
