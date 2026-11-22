import time

from app.adapters.extraction import FixtureExtractionAdapter


class SlowFixture(FixtureExtractionAdapter):
    def extract(self, source_path, languages, page_range, progress_cb):
        time.sleep(0.4)
        return super().extract(source_path, languages, page_range, progress_cb)
