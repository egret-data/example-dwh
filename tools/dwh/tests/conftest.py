import itertools
import json

import pytest

from dwh.lint import Context, run_lint
from dwh.manifest import load_manifest
from dwh.warehouse import load_warehouse
from fixtures.warehouse import write_warehouse


@pytest.fixture
def make_warehouse(tmp_path):
    counter = itertools.count()

    def _make(mutate=None, drop=()):
        return write_warehouse(tmp_path / f"warehouse{next(counter)}", mutate=mutate, drop=drop)

    return _make


@pytest.fixture
def write_manifest(tmp_path):
    counter = itertools.count()

    def _write(builder):
        path = tmp_path / f"manifest{next(counter)}.json"
        path.write_text(json.dumps(builder.build()))
        return path

    return _write


@pytest.fixture
def lint(make_warehouse, write_manifest):
    """Lint `builder` against MINIMAL (after `mutate`); return finding codes, optionally by prefix."""

    def _lint(builder, mutate=None, prefix=None):
        ctx = Context(load_warehouse(make_warehouse(mutate=mutate)), load_manifest(write_manifest(builder)))
        return [f.code for f in run_lint(ctx) if prefix is None or f.code.startswith(prefix)]

    return _lint
