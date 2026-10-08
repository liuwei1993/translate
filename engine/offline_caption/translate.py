class PrefixTranslator:
    def __init__(self, prefix: str):
        self.prefix = prefix

    def translate(self, text: str) -> str:
        return f"{self.prefix}:{text}"
