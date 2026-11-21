import argparse
import json
import sys
from pathlib import Path

from .validator import InputError, validate


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        print(json.dumps({"error": message}), file=sys.stderr)
        self.exit(2)


def main():
    parser = JsonArgumentParser(description="Assess a local verification contract.")
    for name in ("contract", "baseline", "input", "trust", "evidence-root"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--output", type=Path, help="Write JSON to this file instead of stdout.")
    args = parser.parse_args()
    try:
        report = validate(args.contract, args.baseline, args.input, args.trust, args.evidence_root)
        code = 0 if report["gate_status"] == "passed" else 1
    except InputError as error:
        report = {"error": str(error)}
        code = 2
    text = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        try:
            args.output.write_text(text, encoding="utf-8")
        except OSError as error:
            print(json.dumps({"error": f"Cannot write report: {error}"}), file=sys.stderr)
            return 2
    else:
        print(text, end="")
    return code


if __name__ == "__main__":
    sys.exit(main())
