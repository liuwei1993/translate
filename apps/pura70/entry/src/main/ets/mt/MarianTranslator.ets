import { fileIo } from '@kit.CoreFileKit';
import { OnnxArkTSType, OnnxEnvironment, OnnxResult, OnnxSession, OnnxTensor } from '@ohos/onnxruntime';
import { SentencePieceTokenizer } from './SentencePiece';

function int64Tensor(values: number[], shape: number[]): OnnxTensor {
  const buffer = new ArrayBuffer(values.length * 8);
  const view = new DataView(buffer);
  for (let i = 0; i < values.length; i++) {
    view.setBigInt64(i * 8, BigInt(values[i]), true);
  }
  return new OnnxTensor(buffer, shape, OnnxArkTSType.INT64);
}

function ones(length: number): number[] {
  const values: number[] = [];
  for (let i = 0; i < length; i++) {
    values.push(1);
  }
  return values;
}

export class MarianTranslator {
  private encoder: OnnxSession;
  private decoder: OnnxSession;
  private tokenizer: SentencePieceTokenizer;
  private static ready: boolean = false;

  constructor(modelDir: string, tokenizerPath: string) {
    if (!MarianTranslator.ready) {
      OnnxEnvironment.InitEnvironment();
      MarianTranslator.ready = true;
    }
    const text = fileIo.readTextSync(tokenizerPath);
    this.tokenizer = SentencePieceTokenizer.fromJson(text);
    this.encoder = OnnxEnvironment.CreateSessionFromModelFile(`${modelDir}/encoder_model.onnx`);
    this.decoder = OnnxEnvironment.CreateSessionFromModelFile(`${modelDir}/decoder_model.onnx`);
  }

  translate(text: string): string {
    const source = text.trim();
    if (source.length === 0) {
      return '';
    }
    const inputIds = this.tokenizer.encode(source);
    const mask = ones(inputIds.length);
    const inputTensor = int64Tensor(inputIds, [1, inputIds.length]);
    const maskTensor = int64Tensor(mask, [1, mask.length]);
    const encoded: OnnxResult = this.encoder.Run({
      'input_ids': inputTensor,
      'attention_mask': maskTensor
    });
    const hidden = encoded.GetValueByName('last_hidden_state') as OnnxTensor;
    const hiddenBuffer = hidden.GetDataAsArrayBuffer();
    const generated: number[] = [this.tokenizer.padId];
    let output = '';
    for (let step = 0; step < 64; step++) {
      const decIds = int64Tensor(generated, [1, generated.length]);
      const decMask = int64Tensor(mask, [1, mask.length]);
      const hiddenTensor = new OnnxTensor(hiddenBuffer, [1, inputIds.length, 512], OnnxArkTSType.FLOAT);
      const decoded: OnnxResult = this.decoder.Run({
        'input_ids': decIds,
        'encoder_attention_mask': decMask,
        'encoder_hidden_states': hiddenTensor
      });
      const logits = decoded.GetValueByName('logits') as OnnxTensor;
      const values = new Float32Array(logits.GetDataAsArrayBuffer());
      const width = 65001;
      const last = (generated.length - 1) * width;
      let best = 0;
      let bestValue = values[last];
      for (let i = 1; i < width; i++) {
        if (values[last + i] > bestValue) {
          bestValue = values[last + i];
          best = i;
        }
      }
      decoded.Close();
      decIds.Close();
      decMask.Close();
      hiddenTensor.Close();
      logits.Close();
      if (best === this.tokenizer.eosId) {
        break;
      }
      generated.push(best);
      output = this.tokenizer.decodeIds(generated);
    }
    encoded.Close();
    inputTensor.Close();
    maskTensor.Close();
    hidden.Close();
    return output;
  }

  close(): void {
    this.encoder.Close();
    this.decoder.Close();
  }
}
