from pathlib import Path

import pytest

from offline_caption.translate import MarianOnnxTranslator

ZH_EN = Path(__file__).resolve().parents[2] / "models" / "mt" / "zh-en"


@pytest.mark.skipif(not (ZH_EN / "encoder_model.onnx").is_file(), reason="MT model is not exported")
def test_marian_translates_a_short_chinese_sentence():
    translator = MarianOnnxTranslator(str(ZH_EN))
    text = translator.translate("这个多少钱")
    assert text
    assert text != "这个多少钱"
    lowered = text.lower()
    assert "how much" in lowered or "price" in lowered or "cost" in lowered


EN_ZH = Path(__file__).resolve().parents[2] / "models" / "mt" / "en-zh"


@pytest.mark.skipif(not (EN_ZH / "encoder_model.onnx").is_file(), reason="MT model is not exported")
def test_marian_translates_a_short_english_sentence():
    translator = MarianOnnxTranslator(str(EN_ZH))
    text = translator.translate("How much is this?")
    assert text
    assert "多少" in text or "钱" in text
