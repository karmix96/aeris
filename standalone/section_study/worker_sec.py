"""Independent subprocess worker: run a slice of cases (cache-backed)."""
import json
import sys

import common_sections as C


def main():
    slice_path = sys.argv[1]
    cases = json.loads(open(slice_path).read())
    C.run_cases_serial(cases, verbose=True)


if __name__ == "__main__":
    main()
