import os,sys,unittest
from pathlib import Path
root=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
os.environ['STUDIO_NATIVE_MEDIA_TEST']='1'
from tests import test_timeline_editing as test_module
os.environ['QT_QPA_PLATFORM']='windows'
suite=unittest.defaultTestLoader.loadTestsFromName('TimelineTests.test_combined_continuous_play_crosses_clip_boundary',test_module)
result=unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(0 if result.wasSuccessful() else 1)
