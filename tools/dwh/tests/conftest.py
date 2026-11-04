import itertools

import pytest

from fixtures.warehouse import write_warehouse


@pytest.fixture
def make_warehouse(tmp_path):
    counter = itertools.count()

    def _make(mutate=None, drop=()):
        return write_warehouse(tmp_path / f"warehouse{next(counter)}", mutate=mutate, drop=drop)

    return _make
