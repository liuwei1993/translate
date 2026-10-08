import { abilityAccessCtrl, common, Permissions } from '@kit.AbilityKit';
import { audio } from '@kit.AudioKit';
import { BusinessError } from '@kit.BasicServicesKit';
import { hilog } from '@kit.PerformanceAnalysisKit';
import { CaptionEngine } from '../engine/CaptionEngine';
import { stageModels } from '../engine/ModelStore';

interface FrozenLine {
  source: string;
  translation: string;
}

@Entry
@Component
struct Index {
  @State directionZhToEn: boolean = true;
  @State listening: boolean = false;
  @State status: string = '准备听';
  @State liveSource: string = '';
  @State liveTranslation: string = '';
  @State lines: FrozenLine[] = [];
  @State peak: string = '0.00';
  private starting: boolean = false;
  private translationReady: boolean = false;
  private capturer?: audio.AudioCapturer;
  private engine?: CaptionEngine;

  private directionLabel(): string {
    return this.directionZhToEn ? '中文 → 英文' : '英文 → 中文';
  }

  private directionValue(): string {
    return this.directionZhToEn ? 'zh2en' : 'en2zh';
  }

  private async requestMic(): Promise<boolean> {
    const context = this.getUIContext().getHostContext() as common.UIAbilityContext;
    const manager = abilityAccessCtrl.createAtManager();
    const permissions: Array<Permissions> = ['ohos.permission.MICROPHONE'];
    try {
      const result = await manager.requestPermissionsFromUser(context, permissions);
      return result.authResults[0] === abilityAccessCtrl.GrantStatus.PERMISSION_GRANTED;
    } catch (err) {
      const error = err as BusinessError;
      this.status = `麦克风权限失败 ${error.code}`;
      return false;
    }
  }

  private showUpdate(source: string, translation: string, final: boolean): void {
    if (final) {
      const next: FrozenLine[] = [];
      for (let i = 0; i < this.lines.length; i++) {
        next.push(this.lines[i]);
      }
      next.push({ source: source, translation: translation });
      while (next.length > 8) {
        next.shift();
      }
      this.lines = next;
      this.liveSource = '';
      this.liveTranslation = '';
    } else {
      this.liveSource = source;
      this.liveTranslation = translation;
    }
  }

  private async ensureEngine(): Promise<void> {
    if (this.engine !== undefined) {
      return;
    }
    const context = this.getUIContext().getHostContext() as common.UIAbilityContext;
    this.status = '正在准备模型';
    await new Promise<void>((resolve: () => void) => {
      setTimeout(resolve, 50);
    });
    const root = stageModels(context);
    this.engine = new CaptionEngine(context.resourceManager, this.directionValue());
    try {
      this.engine.attachTranslator(root);
      this.translationReady = true;
    } catch (err) {
      const error = err as Error;
      this.translationReady = false;
      hilog.error(0x0001, 'subtitle', 'open mt failed: %{public}s', error.message);
      this.status = '翻译模型没有打开';
    }
  }

  private onSamples(buffer: ArrayBuffer): void {
    const view = new DataView(buffer);
    const count = Math.floor(buffer.byteLength / 2);
    const samples = new Float32Array(count);
    let max = 0;
    for (let i = 0; i < count; i++) {
      const value = view.getInt16(i * 2, true) / 32768;
      samples[i] = value;
      const abs = value < 0 ? -value : value;
      if (abs > max) {
        max = abs;
      }
    }
    this.peak = max.toFixed(2);
    if (this.engine === undefined) {
      return;
    }
    try {
      const update = this.engine.accept(samples, Date.now());
      if (update !== undefined) {
        this.showUpdate(update.source, update.translation, update.final);
        if (update.final && this.engine.problem().length > 0) {
          hilog.error(0x0001, 'subtitle', 'translate failed: %{public}s', this.engine.problem());
          this.status = '翻译失败';
        }
      }
    } catch (err) {
      const error = err as Error;
      this.status = `识别失败 ${error.message}`;
    }
  }

  private async start(): Promise<void> {
    if (this.listening || this.starting) {
      return;
    }
    this.starting = true;
    const allowed = await this.requestMic();
    if (!allowed) {
      this.status = '需要麦克风才能出字幕';
      this.starting = false;
      return;
    }
    try {
      await this.ensureEngine();
    } catch (err) {
      const error = err as BusinessError;
      this.status = `模型准备失败 ${error.message}`;
      this.starting = false;
      return;
    }
    const streamInfo: audio.AudioStreamInfo = {
      samplingRate: audio.AudioSamplingRate.SAMPLE_RATE_16000,
      channels: audio.AudioChannel.CHANNEL_1,
      sampleFormat: audio.AudioSampleFormat.SAMPLE_FORMAT_S16LE,
      encodingType: audio.AudioEncodingType.ENCODING_TYPE_RAW
    };
    const capturerInfo: audio.AudioCapturerInfo = {
      source: audio.SourceType.SOURCE_TYPE_MIC,
      capturerFlags: 0
    };
    try {
      this.capturer = await audio.createAudioCapturer({
        streamInfo: streamInfo,
        capturerInfo: capturerInfo
      });
      this.capturer.on('readData', (buffer: ArrayBuffer) => {
        this.onSamples(buffer);
      });
      await this.capturer.start();
      this.listening = true;
      this.status = this.translationReady ? '正在听' : '正在听，翻译未就绪';
    } catch (err) {
      const error = err as BusinessError;
      this.status = `打开麦克风失败 ${error.code}`;
    }
    this.starting = false;
  }

  private async stop(): Promise<void> {
    if (this.capturer) {
      try {
        await this.capturer.stop();
        await this.capturer.release();
      } catch (err) {
        const error = err as BusinessError;
        this.status = `停止失败 ${error.code}`;
      }
      this.capturer = undefined;
    }
    this.listening = false;
    if (this.status === '正在听') {
      this.status = '已停止';
    }
  }

  aboutToDisappear(): void {
    this.stop();
  }

  build() {
    Column() {
      Row() {
        Button(this.directionLabel())
          .onClick(() => {
            this.directionZhToEn = !this.directionZhToEn;
            this.liveSource = '';
            this.liveTranslation = '';
            if (this.engine !== undefined) {
              this.engine.setDirection(this.directionValue());
              this.translationReady = this.engine.problem().length === 0;
              if (!this.translationReady) {
                hilog.error(0x0001, 'subtitle', 'switch mt failed: %{public}s', this.engine.problem());
                this.status = '翻译模型没有打开';
              } else if (this.listening) {
                this.status = '正在听';
              }
            }
          })
        Blank()
        Text(this.status)
          .fontSize(14)
          .fontColor('#AAAAAA')
      }
      .width('100%')
      .padding(16)

      List({ space: 12 }) {
        ForEach(this.lines, (line: FrozenLine, index: number) => {
          ListItem() {
            Column() {
              Text(line.translation.length > 0 ? line.source : '')
                .fontSize(16)
                .fontColor('#CCCCCC')
                .width('100%')
              Text(line.translation.length > 0 ? line.translation : line.source)
                .fontSize(20)
                .fontColor('#FFFFFF')
                .width('100%')
            }
            .alignItems(HorizontalAlign.Start)
            .width('100%')
          }
        }, (line: FrozenLine, index: number) => `${index}-${line.source}`)
      }
      .layoutWeight(1)
      .width('100%')
      .padding({ left: 16, right: 16 })

      Column() {
        Text(this.liveTranslation.length > 0 ? this.liveSource : '')
          .fontSize(18)
          .fontColor('#DDDDDD')
          .width('100%')
        Text(this.liveTranslation.length > 0 ? this.liveTranslation : this.liveSource)
          .fontSize(28)
          .fontColor('#FFFFFF')
          .width('100%')
        Text(`音量 ${this.peak}`)
          .fontSize(12)
          .fontColor('#888888')
      }
      .width('100%')
      .padding(16)
      .alignItems(HorizontalAlign.Start)

      Button(this.listening ? '停止' : '开始')
        .width('90%')
        .margin({ bottom: 24 })
        .onClick(() => {
          if (this.listening) {
            this.stop();
          } else {
            this.start();
          }
        })
    }
    .width('100%')
    .height('100%')
    .backgroundColor('#111111')
  }
}
