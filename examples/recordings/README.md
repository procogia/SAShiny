# Recordings

Recordings are **internal test fixtures** (spec `CONTRACT.md` sections 6.6 and 8.3). The test
suites' internal mock engine can replay them, but the public API cannot. Live engines never write
recordings, and apps cannot run from them. Every user run happens on a live, licensed SAS
system.

If you add a recording here for the demo-scenario tests, it must contain SAS output for the
synthetic example data only. Never commit recordings made from real data.
