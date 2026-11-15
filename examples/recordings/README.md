# Recordings

Recorded SAS runs that the mock engine replays offline (spec `CONTRACT.md` section 8.3).
Each `<key>.json` file holds one run; the key depends only on the contract bytes, the
rendered input values and any uploaded files, so R and Python share these files.

To fill this folder, run the demo inputs once against live SAS with recording on:

- Python: `sashiny.connect("oda", record_to="examples/recordings")`, or pick a live
  profile in the demo app (it records automatically).
- R: `sas_connect("oda", record_to = "examples/recordings")`.

Recordings contain SAS output for synthetic example data only. Do not commit
recordings made from real data.

This checkout currently has no recording JSON files. Until recordings are
created and committed, the Offline profile starts normally but displays
"no recording matches these inputs"; create and verify recordings before
building the hosted demo image.
