import datetime


class MockDatetime(datetime.datetime):
    fixed_date = None

    @classmethod
    def now(cls):
        return cls.fixed_date
