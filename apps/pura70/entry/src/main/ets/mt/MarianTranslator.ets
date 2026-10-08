import { fileIo } from '@kit.CoreFileKit';
import { closeModels, openModels, translateIds } from 'libmt.so';
import { SentencePieceTokenizer } from './SentencePiece';

export class MarianTranslator {
  private name: string;
  private tokenizer: SentencePieceTokenizer;

  constructor(name: string, modelDir: string, tokenizerPath: string) {
    this.name = name;
    const text = fileIo.readTextSync(tokenizerPath);
    this.tokenizer = SentencePieceTokenizer.fromJson(text);
    openModels(name, `${modelDir}/encoder_model.onnx`, `${modelDir}/decoder_model.onnx`);
  }

  translate(text: string): string {
    const source = text.trim();
    if (source.length === 0) {
      return '';
    }
    const ids = translateIds(this.name, this.tokenizer.encode(source), this.tokenizer.padId, this.tokenizer.eosId);
    return this.tokenizer.decodeIds(ids);
  }

  static closeAll(): void {
    closeModels();
  }
}
