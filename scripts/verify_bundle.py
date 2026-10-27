"""Launch the actual bundled executable; fail CI on missing Tk/libs or crash."""
import json
import os
from pathlib import Path
import subprocess
import tempfile

with tempfile.TemporaryDirectory() as directory:
    report = Path(directory) / 'self-test.json'
    env = dict(os.environ)
    for key in ('PYTHONHOME', 'PYTHONPATH', 'GROQ_API_KEY'):
        env.pop(key, None)
    subprocess.run(['dist/BoroOCR.app/Contents/MacOS/BoroOCR', '--self-test', str(report)],
                   check=True, timeout=60, env=env)
    result = json.loads(report.read_text())
    assert result['ok'] and result['frozen'], result
    assert result['arch'] == os.environ.get('BUILD_ARCH', result['arch']), result
    print(json.dumps(result))
