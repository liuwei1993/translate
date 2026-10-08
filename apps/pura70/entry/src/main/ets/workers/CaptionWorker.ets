import { worker, ThreadWorkerGlobalScope, MessageEvents } from '@kit.ArkTS';
import {
  OnlineModelConfig,
  OnlineRecognizer,
  OnlineRecognizerConfig,
  OnlineStream,
  OnlineTransducerModelConfig
} from 'sherpa_onnx';
import { MarianTranslator } from '../mt/MarianTranslator';

const port: ThreadWorkerGlobalScope = worker.workerPort;

class Engine {
  recognizer?: OnlineRecognizer;
  stream?: OnlineStream;
  zhEn?: MarianTranslator;
  enZh?: MarianTranslator;
  direction: string = 'zh2en';
  lastSource: string = '';
  lastAt: number = -1000000;
  minIntervalMs: number = 300;

  load(root: string): void {
    const config = new OnlineRecognizerConfig();
    const model = new OnlineModelConfig();
    const transducer = new OnlineTransducerModelConfig();
    transducer.encoder = `${root}/models/asr/encoder-epoch-99-avg-1.int8.onnx`;
    transducer.decoder = `${root}/models/asr/decoder-epoch-99-avg-1.onnx`;
    transducer.joiner = `${root}/models/asr/joiner-epoch-99-avg-1.int8.onnx`;
    model.transducer = transducer;
    model.tokens = `${root}/models/asr/tokens.txt`;
    model.numThreads = 2;
    model.provider = 'cpu';
    config.modelConfig = model;
    config.decodingMethod = 'greedy_search';
    config.enableEndpoint = true;
    config.rule1MinTrailingSilence = 2.4;
    config.rule2MinTrailingSilence = 0.4;
    config.rule3MinUtteranceLength = 20;
    this.recognizer = new OnlineRecognizer(config);
    this.stream = this.recognizer.createStream();
    this.zhEn = new MarianTranslator(`${root}/models/mt/zh-en`, `${root}/tok/zh-en.json`);
    this.enZh = new MarianTranslator(`${root}/models/mt/en-zh`, `${root}/tok/en-zh.json`);
  }

  setDirection(direction: string): void {
    this.direction = direction;
    this.lastSource = '';
    this.lastAt = -1000000;
    if (this.recognizer !== undefined && this.stream !== undefined) {
      this.recognizer.reset(this.stream);
    }
  }

  private translator(): MarianTranslator | undefined {
    return this.direction === 'en2zh' ? this.enZh : this.zhEn;
  }

  accept(samples: Float32Array, now: number): void {
    if (this.recognizer === undefined || this.stream === undefined) {
      return;
    }
    this.stream.acceptWaveform({ samples: samples, sampleRate: 16000 });
    while (this.recognizer.isReady(this.stream)) {
      this.recognizer.decode(this.stream);
    }
    const result = this.recognizer.getResult(this.stream);
    const text = result.text.trim();
    const final = this.recognizer.isEndpoint(this.stream);
    if (text.length === 0) {
      return;
    }
    if (!final && text === this.lastSource) {
      return;
    }
    if (!final && (now - this.lastAt) < this.minIntervalMs) {
      return;
    }
    const translator = this.translator();
    const translation = translator === undefined ? '' : translator.translate(text);
    this.lastSource = text;
    this.lastAt = now;
    port.postMessage({
      type: 'caption',
      source: text,
      translation: translation,
      final: final
    });
    if (final) {
      this.recognizer.reset(this.stream);
      this.lastSource = '';
      this.lastAt = -1000000;
    }
  }
}

const engine = new Engine();

port.onmessage = (event: MessageEvents) => {
  const data = event.data as Record<string, Object>;
  const type = data['type'] as string;
  try {
    if (type === 'load') {
      engine.load(data['root'] as string);
      port.postMessage({ type: 'ready' });
      return;
    }
    if (type === 'direction') {
      engine.setDirection(data['direction'] as string);
      return;
    }
    if (type === 'audio') {
      const samples = new Float32Array(data['samples'] as ArrayBuffer);
      engine.accept(samples, data['now'] as number);
    }
  } catch (err) {
    const error = err as Error;
    port.postMessage({ type: 'error', message: error.message });
  }
};
