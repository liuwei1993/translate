import {
  OnlineModelConfig,
  OnlineRecognizer,
  OnlineRecognizerConfig,
  OnlineStream,
  OnlineTransducerModelConfig
} from 'sherpa_onnx';
import { MarianTranslator } from '../mt/MarianTranslator';

export class CaptionUpdate {
  source: string = '';
  translation: string = '';
  direction: string = '';
  final: boolean = false;
}

function scriptName(text: string): string {
  let han = 0;
  let latin = 0;
  for (let i = 0; i < text.length; i++) {
    const code = text.charCodeAt(i);
    if (code >= 0x4E00 && code <= 0x9FFF) {
      han++;
    } else if ((code >= 65 && code <= 90) || (code >= 97 && code <= 122)) {
      latin++;
    }
  }
  if (han === 0 && latin === 0) {
    return '';
  }
  return han >= latin ? 'zh-en' : 'en-zh';
}

export class CaptionEngine {
  private recognizer: OnlineRecognizer;
  private stream: OnlineStream;
  private zhEn?: MarianTranslator;
  private enZh?: MarianTranslator;
  private lastSource: string = '';
  private lastAt: number = -1000000;
  private translateError: string = '';

  constructor(resourceManager: object) {
    const config = new OnlineRecognizerConfig();
    const model = new OnlineModelConfig();
    const transducer = new OnlineTransducerModelConfig();
    transducer.encoder = 'models/asr/encoder-epoch-99-avg-1.int8.onnx';
    transducer.decoder = 'models/asr/decoder-epoch-99-avg-1.onnx';
    transducer.joiner = 'models/asr/joiner-epoch-99-avg-1.int8.onnx';
    model.transducer = transducer;
    model.tokens = 'models/asr/tokens.txt';
    model.numThreads = 2;
    model.provider = 'cpu';
    config.modelConfig = model;
    config.decodingMethod = 'greedy_search';
    config.enableEndpoint = true;
    config.rule1MinTrailingSilence = 2.4;
    config.rule2MinTrailingSilence = 0.4;
    config.rule3MinUtteranceLength = 20;
    this.recognizer = new OnlineRecognizer(config, resourceManager);
    this.stream = this.recognizer.createStream();
  }

  problem(): string {
    return this.translateError;
  }

  attachTranslator(root: string): void {
    MarianTranslator.closeAll();
    this.zhEn = undefined;
    this.enZh = undefined;
    try {
      const zhEn = new MarianTranslator('zh-en', `${root}/models/mt/zh-en`, `${root}/tok/zh-en.json`);
      const enZh = new MarianTranslator('en-zh', `${root}/models/mt/en-zh`, `${root}/tok/en-zh.json`);
      this.zhEn = zhEn;
      this.enZh = enZh;
      this.translateError = '';
    } catch (err) {
      MarianTranslator.closeAll();
      this.zhEn = undefined;
      this.enZh = undefined;
      throw err as Error;
    }
  }

  accept(samples: Float32Array, now: number): CaptionUpdate | undefined {
    this.stream.acceptWaveform({ samples: samples, sampleRate: 16000 });
    while (this.recognizer.isReady(this.stream)) {
      this.recognizer.decode(this.stream);
    }
    const text = this.recognizer.getResult(this.stream).text.trim();
    const final = this.recognizer.isEndpoint(this.stream);
    if (text.length === 0) {
      return undefined;
    }
    if (!final && text === this.lastSource) {
      return undefined;
    }
    if (!final && (now - this.lastAt) < 300) {
      return undefined;
    }
    const update = new CaptionUpdate();
    update.source = text;
    update.final = final;
    if (final) {
      const name = scriptName(text);
      const translator = name === 'zh-en' ? this.zhEn : name === 'en-zh' ? this.enZh : undefined;
      if (name === 'zh-en') {
        update.direction = '中文 → 英文';
      } else if (name === 'en-zh') {
        update.direction = '英文 → 中文';
      }
      if (translator !== undefined) {
        try {
          update.translation = translator.translate(text);
          this.translateError = '';
        } catch (err) {
          const error = err as Error;
          this.translateError = error.message;
        }
      }
    }
    this.lastSource = text;
    this.lastAt = now;
    if (final) {
      this.recognizer.reset(this.stream);
      this.lastSource = '';
      this.lastAt = -1000000;
    }
    return update;
  }
}
