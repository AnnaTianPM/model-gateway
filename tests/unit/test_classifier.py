"""Tests for request feature extraction and rule classifier."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


def test_extract_features_simple():
    from app.routing.request_features import extract_features
    body = {
        "messages": [{"role": "user", "content": "Hello world"}],
        "max_tokens": 100,
    }
    features = extract_features(body)
    assert features.estimated_input_tokens > 0
    assert features.minimum_context_length > features.estimated_input_tokens
    assert features.has_images is False
    assert features.has_tools is False


def test_extract_features_with_image():
    from app.routing.request_features import extract_features
    body = {
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": "What is this?"},
            {"type": "image_url", "image_url": {"url": "http://x"}}
        ]}],
    }
    features = extract_features(body)
    assert features.has_images is True


def test_extract_features_with_tools():
    from app.routing.request_features import extract_features
    body = {
        "messages": [{"role": "user", "content": "Use the calculator"}],
        "tools": [{"type": "function", "function": {"name": "calc", "parameters": {}}}],
    }
    features = extract_features(body)
    assert features.has_tools is True
    assert features.tools_count == 1


def test_classify_coding():
    from app.routing.rule_classifier import classify
    from app.routing.request_features import extract_features
    body = {
        "messages": [{"role": "user", "content": "Write a Python function to sort a list. Here's the code:\n```python\ndef sort(lst):\n    pass\n```"}],
        "max_tokens": 1000,
    }
    features = extract_features(body)
    result = classify(features)
    assert result.task_type == "coding"


def test_classify_vision():
    from app.routing.rule_classifier import classify
    from app.routing.request_features import extract_features
    body = {
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": "What's in this image?"},
            {"type": "image_url", "image_url": {"url": "http://x"}}
        ]}],
    }
    features = extract_features(body)
    result = classify(features)
    assert result.task_type == "vision"
    assert "vision" in result.required_capabilities


def test_classify_tools():
    from app.routing.rule_classifier import classify
    from app.routing.request_features import extract_features
    body = {
        "messages": [{"role": "user", "content": "Calculate something"}],
        "tools": [{"type": "function", "function": {"name": "calc"}}],
    }
    features = extract_features(body)
    result = classify(features)
    assert result.task_type == "tools"
    assert "tools" in result.required_capabilities


def test_classify_general():
    from app.routing.rule_classifier import classify
    from app.routing.request_features import extract_features
    body = {
        "messages": [{"role": "user", "content": "What is the weather like?"}],
    }
    features = extract_features(body)
    result = classify(features)
    assert result.task_type == "general"


def test_difficulty_easy():
    from app.routing.rule_classifier import classify
    from app.routing.request_features import extract_features
    body = {
        "messages": [{"role": "user", "content": "Hi"}],
        "max_tokens": 100,
    }
    features = extract_features(body)
    result = classify(features)
    assert result.difficulty == "easy"


def test_difficulty_hard_with_large_input():
    from app.routing.rule_classifier import classify
    from app.routing.request_features import extract_features
    # Create a large input (> 16K tokens ~ 64K chars)
    large_text = "a" * 70000
    body = {
        "messages": [{"role": "user", "content": large_text}],
        "max_tokens": 5000,
    }
    features = extract_features(body)
    result = classify(features)
    assert result.difficulty in ("medium", "hard")
