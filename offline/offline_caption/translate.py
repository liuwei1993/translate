class PrefixTranslator:
    def __init__(self, prefix: str):
        self.prefix = prefix

    def translate(self, text: str) -> str:
        return f"{self.prefix}:{text}"


class MarianOnnxTranslator:
    def __init__(self, model_dir: str):
        from optimum.onnxruntime import ORTModelForSeq2SeqLM
        from transformers import MarianTokenizer

        self._tokenizer = MarianTokenizer.from_pretrained(model_dir)
        self._model = ORTModelForSeq2SeqLM.from_pretrained(model_dir, use_cache=False, use_merged=False)

    def translate(self, text: str) -> str:
        batch = self._tokenizer(text, return_tensors="pt")
        output = self._model.generate(**batch, max_new_tokens=64)
        return self._tokenizer.decode(output[0], skip_special_tokens=True).strip()
