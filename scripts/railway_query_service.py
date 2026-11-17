"""Start the independent query service; localhost only, disabled by default."""
import argparse
import os
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--provider', choices=['disabled', 'synthetic-test', 'train-assistant'], default='disabled')
    parser.add_argument('--port', type=int, default=8540)
    parser.add_argument('--upstream-client', type=Path)
    parser.add_argument('--allow-live-queries', action='store_true')
    parser.add_argument('--origin-request-budget', type=int, default=12)
    parser.add_argument('--evidence-directory', type=Path)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error('port must be 1024..65535')
    if args.provider == 'train-assistant' and (not args.allow_live_queries or args.upstream_client is None or args.evidence_directory is None):
        parser.error('real queries require source file, explicit authorization flag, and a new evidence directory')
    for key in list(os.environ):
        if key.startswith(('AGENT_', 'DEEPSEEK_', 'DASHSCOPE_', 'LANGCHAIN_', 'LANGSMITH_')) or key.endswith(('_API_KEY', '_TOKEN')):
            del os.environ[key]
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    sys.dont_write_bytecode = True
    from services.railway_query.app import create_app
    from services.railway_query.providers import DisabledProvider, SyntheticProvider, TrainAssistantProvider
    import uvicorn
    if args.provider == 'train-assistant':
        args.evidence_directory.mkdir(parents=True, exist_ok=False)
        provider = TrainAssistantProvider(args.upstream_client, authorized=True,
                    evidence=args.evidence_directory/'origin-requests.jsonl', origin_budget=args.origin_request_budget)
    else:
        provider = SyntheticProvider() if args.provider == 'synthetic-test' else DisabledProvider()
    uvicorn.run(create_app(provider), host='127.0.0.1', port=args.port, access_log=False, log_level='warning')


if __name__ == '__main__':
    main()
