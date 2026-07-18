import json
from pathlib import Path
import unittest

from coophou.probe.trace import validate_record


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "events"


class CheckedInTraceFixtureTests(unittest.TestCase):
    def test_every_jsonl_record_matches_schema_and_local_order(self):
        paths = sorted(FIXTURE_ROOT.glob("houdini-*/hdk-api-*/*/*/*.jsonl"))
        self.assertTrue(paths, "no generated event traces were found")
        for path in paths:
            with self.subTest(path=path):
                records = [
                    validate_record(json.loads(line))
                    for line in path.read_text(encoding="utf-8").splitlines()
                    if line.strip()
                ]
                self.assertTrue(records)
                self.assertEqual(
                    [record["observation"] for record in records],
                    sorted({record["observation"] for record in records}),
                )
                self.assertEqual({record["adapter"] for record in records}, {path.parent.name})
                self.assertEqual({record["scenario"] for record in records}, {path.stem})


if __name__ == "__main__":
    unittest.main()
