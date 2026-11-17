class PaidSpeech:
    engine_version = "paid-fixture-v1"
    paid = True

    def synthesize(self, units, voice, language):
        raise AssertionError("A budget-refused provider must never be called")
