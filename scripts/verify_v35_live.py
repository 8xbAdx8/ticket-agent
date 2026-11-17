"""V3.5 CLI compatibility alias for current unlimited read-only Live validation.

Historical V3.5 reports and budget databases are never rewritten. --resume-rag-only
now explicitly executes one CURRENT Bailian policy case; it does not reuse quota
or claim a new DeepSeek comparison. Default only performs local preflight.
"""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument('--run', action='store_true')
    action.add_argument('--resume-rag-only', action='store_true', help='兼容：显式运行当前千问政策场景，无旧剩余额度语义')
    parser.add_argument('--out', type=Path)
    args = parser.parse_args(argv)
    from scripts.live_providers import main as live
    forwarded = ['--provider', 'bailian', '--scenario', 'policy' if args.resume_rag_only else 'tickets']
    if args.run or args.resume_rag_only:
        forwarded.append('--run')
    if args.out:
        forwarded.extend(['--out', str(args.out)])
    return live(forwarded)


if __name__ == '__main__':
    raise SystemExit(main())

