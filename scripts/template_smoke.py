"""Exercise all canonical roles with explicit synthetic, non-research content."""

import json
from pathlib import Path

from research_slide_agent.engine import generate
from research_slide_agent.models import SlideSpec


def make_spec(template=None):
    return SlideSpec.model_validate_json(Path('examples/research-format.slidespec.json').read_text())


if __name__ == '__main__':
    template = Path('templates/lab-template.pptx')
    output = Path('artifacts/template-check/presentation.pptx')
    spec = make_spec(template)
    manifest = generate(template, spec, output)
    output.with_suffix('.spec.json').write_text(spec.model_dump_json(indent=2))
    print(json.dumps({'quality': manifest['quality'], 'pptx': str(output)}, ensure_ascii=False))
