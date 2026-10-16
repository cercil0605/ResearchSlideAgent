import io
import zipfile

import pytest

from research_slide_agent.files import InputError, validate_file


def test_magic_and_path():
    for name, data in [
        ("fake.pdf", b"garbage"),
        ("../file.csv", b"a,b"),
        ("fake.png", b"%PDF-1.2"),
        ("bad.csv", b"a\0b"),
        ("macro.pptm", b"PK"),
    ]:
        with pytest.raises((InputError, ValueError)):
            validate_file(name, data)


def test_external_office_reference(settings):
    buf = io.BytesIO()
    with zipfile.ZipFile(settings.template) as original, zipfile.ZipFile(buf, "w") as target:
        for name in original.namelist():
            target.writestr(name, original.read(name))
        target.writestr(
            "ppt/external.xml.rels",
            '<Relationships><Relationship TargetMode="External" Target="http://127.0.0.1"/></Relationships>',
        )
    with pytest.raises(InputError, match="External"):
        validate_file("external.pptx", buf.getvalue())


def test_valid_archive(settings):
    assert validate_file("lab.pptx", settings.template.read_bytes()) == "pptx"


def test_file_quota(store):
    p = store.create("alice")
    for i in range(10):
        store.register("alice", p["id"], f"{i}.csv", b"a,b\n1,2")
    with pytest.raises(ValueError, match="FILE_LIMIT"):
        store.register("alice", p["id"], "overflow.csv", b"a,b")
