from app.config import get_settings
from app.ui import build_demo


def test_gradio_demo_builds_without_launch():
    demo = build_demo(get_settings())
    assert demo is not None
    assert len(demo.blocks) > 0
