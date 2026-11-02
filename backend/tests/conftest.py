import os
import sys
import tempfile
from pathlib import Path

_tmp = tempfile.mkdtemp(prefix="vo-test-")
os.environ["VO_DATA_DIR"] = _tmp
os.environ["VO_STAGE_DELAY_SECONDS"] = "0"
os.environ["VO_LLM_PROVIDER"] = "none"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
