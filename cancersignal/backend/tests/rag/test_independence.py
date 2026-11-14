import subprocess
import sys


def test_rag_imports_without_extraction_or_downstream_pipeline():
    script = '''
import importlib.abc
import sys
class BlockDownstream(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith(("app.rag.extraction", "app.analysis", "app.reasoning", "app.services.analysis_service")):
            raise AssertionError("RAG must not import downstream code: " + fullname)
sys.meta_path.insert(0, BlockDownstream())
from app.rag.engine import RetrievalEngine
from app.rag.indexing import index_patient
from app.rag.repository import PatientRepository
from app.rag.cli import main
'''
    subprocess.run([sys.executable, "-c", script], check=True, capture_output=True, text=True)
