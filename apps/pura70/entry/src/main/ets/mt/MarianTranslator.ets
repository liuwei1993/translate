import { fileIo } from '@kit.CoreFileKit';
import { closeModels, openModels, translateIds } from 'libmt.so';
import { SentencePieceTokenizer } from './SentencePiece';

export class MarianTranslator {
  private tokenizer: SentencePieceTokenizer;

  constructor(modelDir: string, tokenizerPath: string) {
    const text = fileIo.readTextSync(tokenizerPath);
    this.tokenizer = SentencePieceTokenizer.fromJson(text);
    openModels(`${modelDir}/encoder_model.onnx`, `${modelDir}/decoder_model.onnx`);
  }

  translate(text: string): string {
    const source = text.trim();
    if (source.length === 0) {
      return '';
    }
    const ids = translateIds(this.tokenizer.encode(source), this.tokenizer.padId, this.tokenizer.eosId);
    return this.tokenizer.decodeIds(ids);
  }

  close(): void {
    closeModels();
  }
}
