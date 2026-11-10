"""Run every test module with a fresh Qt/native runtime, without dropping cases."""
import os,re,subprocess,sys
from pathlib import Path


def main():
    root=Path(__file__).resolve().parents[1]
    env=dict(os.environ,PYTHONPATH=str(root),PYTHONIOENCODING='utf-8')
    total=skipped=0;failed=[]
    for path in sorted((root/'tests').glob('test_*.py')):
        module='tests.'+path.stem
        try:
            run=subprocess.run([sys.executable,'-X','faulthandler','-m','unittest',module,'-q'],cwd=root,env=env,capture_output=True,timeout=180)
            output=(run.stdout+run.stderr).decode('utf-8',errors='replace')
            count=re.search(r'Ran (\d+) tests?',output)
            if count:total+=int(count[1])
            skip=re.search(r'skipped=(\d+)',output)
            if skip:skipped+=int(skip[1])
            if run.returncode or not count:
                failed.append(module);print(output[-16000:],flush=True)
            print(f'{module}: '+('PASS' if not run.returncode and count else 'FAIL'),flush=True)
        except subprocess.TimeoutExpired:
            failed.append(module);print(module+': TIMEOUT',flush=True)
    print(f'TOTAL {total} tests; skipped={skipped}; failed_modules={len(failed)}',flush=True)
    return bool(failed)


if __name__=='__main__':sys.exit(main())
