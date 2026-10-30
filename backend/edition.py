"""Which edition of AeroDent this process runs.

``AERODENT_EDITION=standalone`` is the desktop edition: one clinic, one local SQLite file, no
platform administration, no trial sign-up and no landing page. Everything else (the clinic
screens and their API) is the same code as the online edition.
"""

import os

STANDALONE = os.getenv("AERODENT_EDITION", "").strip().lower() == "standalone"
