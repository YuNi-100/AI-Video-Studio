"""Run the workspace interactions against actual Windows widgets."""
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tests.test_workspace_search import WorkspaceSearchTests
os.environ['QT_QPA_PLATFORM']='windows'
result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(WorkspaceSearchTests))
sys.exit(not result.wasSuccessful())
