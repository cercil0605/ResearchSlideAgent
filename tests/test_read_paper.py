import io
import json

import pytest
from PIL import Image
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from research_slide_agent import paper
from research_slide_agent.auth import Auth
from research_slide_agent.config import Settings
from research_slide_agent.files import InputError
from research_slide_agent.server import make_mcp
from research_slide_agent.store import Store

BODY = "The proposed method converts operation logs into editable programs for every task we tested."


def _text(x, y, size, text):
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    return f"BT /F1 {size} Tf {x} {y} Td ({escaped}) Tj ET\n"


def synthetic_paper(extra_pages=0, long_text=False):
    """Two-column-free paper: body text, a red figure box with its caption below, a table caption."""
    writer = PdfWriter()
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"),
                             NameObject("/BaseFont"): NameObject("/Helvetica")})
    pages = [
        [_text(72, 740, 12, "1 Introduction")] + [_text(72, 720 - 12 * i, 10, BODY) for i in range(6)]
        + ["1 0 0 rg 150 420 300 220 re f\n", _text(200, 600, 9, "Logger"),
           _text(72, 400, 10, "Figure 1: System architecture of the proposed pipeline."),
           _text(72, 380, 12, "2 Method")] + [_text(72, 360 - 12 * i, 10, BODY) for i in range(8)],
        [_text(72, 740, 10, "Table 1: Results on three tasks."), _text(72, 720, 10, "Task  RMSE  SD"),
         _text(72, 600, 10, "As Fig. 1 shows, the logger feeds the generator.")]
        + [_text(72, 580 - 12 * i, 10, BODY * (8 if long_text else 1)) for i in range(4)],
    ] + [[_text(72, 700, 10, BODY)] for _ in range(extra_pages)]
    for commands in pages:
        page = writer.add_blank_page(width=612, height=792)
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
        stream = DecodedStreamObject()
        stream.set_data("".join(commands).encode("latin-1"))
        page[NameObject("/Contents")] = writer._add_object(stream)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def test_read_paper_returns_text_sections_and_figures():
    result = paper.read_paper(synthetic_paper())
    assert result["parts"] == 1 and result["total_pages"] == 2 and result["next_part"] is None
    assert [p["page"] for p in result["pages"]] == [1, 2]
    assert {"title": "1 Introduction", "page": 1} in result["sections"]
    figures = {f["id"]: f for f in result["figures"]}
    assert set(figures) == {"Fig. 1", "Table 1"}  # "As Fig. 1 shows" is a mention, not a caption
    assert figures["Fig. 1"]["caption"].startswith("Figure 1: System architecture")
    assert figures["Table 1"]["region"] is None
    region = figures["Fig. 1"]["region"]
    # The red box spans y 420..640 of 792 and x 150..450 of 612: the estimate must contain it without
    # the caption below or the body text above.
    assert region["top"] <= (792 - 640) / 792 and region["bottom"] >= (792 - 420) / 792
    assert region["bottom"] < (792 - 400) / 792 and region["top"] > (792 - 662) / 792
    assert region["left"] <= 150 / 612 and region["right"] >= 450 / 612


def test_long_papers_are_split_under_the_client_output_limit():
    data = synthetic_paper(extra_pages=3, long_text=True)
    monkey_budget = paper.PART_TOKENS
    try:
        paper.PART_TOKENS = 300
        paper._parse.cache_clear()
        first = paper.read_paper(data)
        assert first["parts"] > 1 and first["next_part"] == 2 and "figures" in first
        rest = [paper.read_paper(data, n) for n in range(2, first["parts"] + 1)]
        assert all("figures" not in r for r in rest)
        pages = [p["page"] for r in [first, *rest] for p in r["pages"]]
        assert sorted(set(pages)) == [1, 2, 3, 4, 5]
        with pytest.raises(InputError, match="PART_INVALID"):
            paper.read_paper(data, first["parts"] + 1)
    finally:
        paper.PART_TOKENS = monkey_budget
        paper._parse.cache_clear()


@pytest.mark.parametrize("label,key", [("Fig. 7(b)", ("figure", "7")), ("Figure 3", ("figure", "3")),
                                       ("Figure 2.1", ("figure", "2.1")), ("Fig. 2. TB20e", ("figure", "2")),
                                       ("図2", ("figure", "2")), ("Table 2", ("table", "2")), ("表1", ("table", "1"))])
def test_figure_keys(label, key):
    assert paper.figure_key(label) == key


def test_unknown_figure_is_reported():
    with pytest.raises(InputError, match="FIGURE_NOT_FOUND"):
        paper.find_figure(synthetic_paper(), "Fig. 9")


@pytest.mark.asyncio
async def test_tools_read_crop_by_number_and_number_the_caption(settings, tmp_path):
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    (inputs / "paper.pdf").write_bytes(synthetic_paper())
    local = Settings(local=True, data_dir=settings.data_dir, template=settings.template,
                     input_dirs=(inputs,), output_dir=tmp_path / "out")
    store = Store(local)
    mcp = make_mcp(store, local, Auth(local))

    async def call(name, **args):
        result = await mcp.call_tool(name, args)
        text = "".join(getattr(c, "text", "") for c in result.content)
        return json.loads(text), result

    project, _ = await call("create_project")
    pid = project["id"]
    source, _ = await call("register_local_file", presentation_id=pid, path=str(inputs / "paper.pdf"))
    sid = source["source_id"]
    read, _ = await call("read_paper", presentation_id=pid, source_id=sid)
    assert read["source_id"] == sid and any(f["id"] == "Fig. 1" for f in read["figures"])

    crop, result = await call("crop_pdf_region", presentation_id=pid, source_id=sid, figure="Figure 1", dpi=72)
    assert crop["figure"] == "Fig. 1" and crop["page"] == 1
    image = next(c for c in result.content if getattr(c, "type", "") == "image")
    import base64
    with Image.open(io.BytesIO(base64.b64decode(image.data))) as png:
        red = sum(n for n, p in png.convert("RGB").getcolors(1 << 24) if p[0] > 200 and p[1] < 60)
        assert red > png.width * png.height * 0.5  # mostly the figure, not text
    assert store.file(LOCAL_OWNER, pid, crop["source_id"])["origin"]["figure"] == "Fig. 1"

    with pytest.raises(Exception, match="FIGURE_REGION_UNKNOWN"):
        await mcp.call_tool("crop_pdf_region", {"presentation_id": pid, "source_id": sid, "figure": "Table 1"})
    with pytest.raises(Exception, match="PDF_REGION_INVALID"):
        await mcp.call_tool("crop_pdf_region", {"presentation_id": pid, "source_id": sid})

    from pathlib import Path

    from research_slide_agent.figures import number_captions
    from research_slide_agent.models import SlideSpec

    raw = json.loads(Path("examples/research-format.slidespec.json").read_text())
    slide = next(s for s in raw["slides"] if s["prototype_id"] == "results_figure")
    slide.pop("diagram_spec", None)
    slide["replacements"].pop("図題", None)
    ref = {"source_id": sid, "locator": "p.1"}
    slide.update(slide_order=1, image_references=[{"id": "fig", "source_id": crop["source_id"], "caption": "全体構成"}],
                 source_references=[ref], citations=[{"source": ref, "author": "Test", "year": 2026,
                                                      "target_id": "fig"}])
    raw.update(presentation_id=pid, purpose_mode="general", slides=[slide])
    spec = SlideSpec.model_validate(raw)
    sources = {f["id"]: {**f, "origin": json.dumps(f["origin"]) if f["origin"] else None}
               for f in store.files(LOCAL_OWNER, pid)}
    added = number_captions(spec, sources)
    assert added and added[0]["caption"] == "Fig. 1 全体構成"

LOCAL_OWNER = "local-user"


def test_dense_pages_are_split_against_the_remaining_budget():
    parts = paper._parts(["漢" * 30000, "a" * 1000], reserved=5000)
    assert len(parts) >= 2
    for part in parts:
        assert paper.estimate_tokens(json.dumps(part, ensure_ascii=False)) <= paper.PART_TOKENS
    assert "".join(p["text"] for part in parts for p in part if p["page"] == 1) == "漢" * 30000


@pytest.mark.parametrize("line,caption,strong", [
    ("Fig. 2. TB20e 3D Model", True, True), ("図1 システム構成", True, False),
    ("Figure 1 System architecture", True, False), ("Figure 1 shows the system", False, False),
    ("図1に示すように", False, False), ("Table 2 is larger", False, False),
    ("Figure 2.1: Architecture", True, True), ("Figure 2.2 Results", True, False),
])
def test_captions_with_and_without_punctuation(line, caption, strong):
    match, is_strong = paper._caption(line)
    assert bool(match) is caption and is_strong is strong
