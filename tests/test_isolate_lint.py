import pytest
import os
import tempfile
from scripts.check_isolates import lint_file


def test_linter_passes_clean_isolate():
    code = """
from src.core.isolate import BaseIsolate
from src.core.effects import LogEffect

class GoodIsolate(BaseIsolate):
    def handle_message(self, msg):
        self.state = "updated"
        return [LogEffect(level="INFO", message="Done")]
"""
    with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
        f.write(code)
        temp_path = f.name

    try:
        errors = lint_file(temp_path)
        assert len(errors) == 0, f"Expected no errors, got: {errors}"
    finally:
        os.remove(temp_path)


def test_linter_detects_async_def():
    code = """
from src.core.isolate import BaseIsolate

class BadIsolate(BaseIsolate):
    async def handle_message(self, msg):
        return []
"""
    with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
        f.write(code)
        temp_path = f.name

    try:
        errors = lint_file(temp_path)
        assert len(errors) > 0
        assert any("async def" in err for err in errors)
    finally:
        os.remove(temp_path)


def test_linter_detects_await():
    code = """
from src.core.isolate import BaseIsolate

class BadIsolate(BaseIsolate):
    def handle_message(self, msg):
        await self.some_async_call()
        return []
"""
    with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
        f.write(code)
        temp_path = f.name

    try:
        errors = lint_file(temp_path)
        assert len(errors) > 0
        assert any("await" in err for err in errors)
    finally:
        os.remove(temp_path)


def test_linter_detects_forbidden_libs():
    code = """
from src.core.isolate import BaseIsolate

class BadIsolate(BaseIsolate):
    def handle_message(self, msg):
        import requests
        res = requests.get("https://example.com")
        return []
"""
    with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
        f.write(code)
        temp_path = f.name

    try:
        errors = lint_file(temp_path)
        assert len(errors) >= 2  # Import + Call
        assert any("Import of forbidden module" in err for err in errors)
        assert any("Direct call to forbidden module" in err for err in errors)
    finally:
        os.remove(temp_path)
