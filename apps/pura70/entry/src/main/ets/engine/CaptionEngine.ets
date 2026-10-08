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
  final: boolean = false;
}

export class CaptionEngine {
  private recognizer: OnlineRecognizer;
  private stream: OnlineStream;
  private translator?: MarianTranslator;
  private root: string = '';
  private direction: string;
  private lastSource: string = '';
  private lastAt: number = -1000000;
  private translateError: string = '';

  constructor(resourceManager: object, direction: string) {
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
    this.direction = direction;
  }

  problem(): string {
    return this.translateError;
  }

  attachTranslator(root: string): void {
    this.root = root;
    this.closeTranslator();
    this.loadTranslator();
  }

  setDirection(direction: string): void {
    if (this.direction === direction) {
      return;
    }
    this.direction = direction;
    this.lastSource = '';
    this.lastAt = -1000000;
    this.recognizer.reset(this.stream);
    if (this.root.length === 0) {
      return;
    }
    this.closeTranslator();
    try {
      this.loadTranslator();
      this.translateError = '';
    } catch (err) {
      const error = err as Error;
      this.translateError = error.message;
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
    if (final && this.translator !== undefined) {
      try {
        update.translation = this.translator.translate(text);
        this.translateError = '';
      } catch (err) {
        const error = err as Error;
        this.translateError = error.message;
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

  private loadTranslator(): void {
    const name = this.direction === 'en2zh' ? 'en-zh' : 'zh-en';
    this.translator = new MarianTranslator(`${this.root}/models/mt/${name}`, `${this.root}/tok/${name}.json`);
    this.translateError = '';
  }

  private closeTranslator(): void {
    if (this.translator !== undefined) {
      this.translator.close();
      this.translator = undefined;
    }
  }
}
