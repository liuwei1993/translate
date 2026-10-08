import { abilityAccessCtrl, common, Permissions } from '@kit.AbilityKit';
import { audio } from '@kit.AudioKit';
import { webview } from '@kit.ArkWeb';
import { util } from '@kit.ArkTS';
import { BusinessError } from '@kit.BasicServicesKit';
import { hilog } from '@kit.PerformanceAnalysisKit';

const PAGE_URL = 'http://8.130.163.41:9000/';

let startMic: () => void = (): void => {};
let stopMic: () => void = (): void => {};

class MicBridge {
  start(): void {
    startMic();
  }

  stop(): void {
    stopMic();
  }
}

@Entry
@Component
struct Index {
  private controller: webview.WebviewController = new webview.WebviewController();
  private bridge: MicBridge = new MicBridge();
  private base64: util.Base64Helper = new util.Base64Helper();
  private capturer?: audio.AudioCapturer;
  private starting: boolean = false;
  private pendingGrant?: Promise<boolean>;
  private pcmParts: ArrayBuffer[] = [];
  private pcmBytes: number = 0;
  private flushScheduled: boolean = false;
  @State status: string = '';
  @State micAllowed: boolean = true;

  aboutToAppear(): void {
    startMic = (): void => {
      this.startCapture();
    };
    stopMic = (): void => {
      this.stopCapture();
    };
    this.ensureMicPermission();
  }

  aboutToDisappear(): void {
    this.stopCapture();
  }

  private queuePcm(buffer: ArrayBuffer): void {
    this.pcmParts.push(buffer);
    this.pcmBytes += buffer.byteLength;
    if (this.pcmBytes >= 3200) {
      this.flushPcm();
      return;
    }
    if (this.flushScheduled) {
      return;
    }
    this.flushScheduled = true;
    setTimeout((): void => {
      this.flushScheduled = false;
      this.flushPcm();
    }, 100);
  }

  private flushPcm(): void {
    if (this.pcmBytes === 0) {
      return;
    }
    const merged = new Uint8Array(this.pcmBytes);
    let offset = 0;
    for (let i = 0; i < this.pcmParts.length; i++) {
      const part = new Uint8Array(this.pcmParts[i]);
      merged.set(part, offset);
      offset += part.byteLength;
    }
    this.pcmParts = [];
    this.pcmBytes = 0;
    this.pushPcm(merged.buffer);
  }

  private pushPcm(buffer: ArrayBuffer): void {
    const encoded = this.base64.encodeToStringSync(new Uint8Array(buffer));
    const script = `window.onHarmonyPcm && window.onHarmonyPcm(${JSON.stringify(encoded)})`;
    try {
      this.controller.runJavaScript(script);
    } catch (err) {
      const error = err as Error;
      hilog.error(0x0002, 'webcap', 'push pcm failed: %{public}s', error.message);
    }
  }

  private denyMic(): void {
    try {
      this.controller.runJavaScript('window.onHarmonyMicDenied && window.onHarmonyMicDenied()');
    } catch (err) {
      const error = err as Error;
      hilog.error(0x0002, 'webcap', 'deny mic failed: %{public}s', error.message);
    }
  }

  private context(): common.UIAbilityContext {
    return this.getUIContext().getHostContext() as common.UIAbilityContext;
  }

  private micAlreadyGranted(manager: abilityAccessCtrl.AtManager, tokenId: number): boolean {
    try {
      const current = manager.checkAccessTokenSync(tokenId, 'ohos.permission.MICROPHONE');
      return current === abilityAccessCtrl.GrantStatus.PERMISSION_GRANTED;
    } catch (err) {
      const error = err as BusinessError;
      hilog.error(0x0002, 'webcap', 'check mic failed: %{public}d', error.code);
      return false;
    }
  }

  private async askMic(): Promise<boolean> {
    const context = this.context();
    const manager = abilityAccessCtrl.createAtManager();
    const permission: Permissions = 'ohos.permission.MICROPHONE';
    if (this.micAlreadyGranted(manager, context.applicationInfo.accessTokenId)) {
      this.micAllowed = true;
      this.status = '';
      return true;
    }
    try {
      const result = await manager.requestPermissionsFromUser(context, [permission]);
      const granted = result.authResults[0] === abilityAccessCtrl.GrantStatus.PERMISSION_GRANTED;
      this.micAllowed = granted;
      this.status = granted ? '' : '需要麦克风权限才能听';
      return granted;
    } catch (err) {
      const error = err as BusinessError;
      this.micAllowed = false;
      this.status = `麦克风权限失败 ${error.code}`;
      return false;
    }
  }

  private ensureMicPermission(): Promise<boolean> {
    if (this.pendingGrant) {
      return this.pendingGrant;
    }
    const task = this.askMic();
    this.pendingGrant = task;
    task.then((): void => {
      this.pendingGrant = undefined;
    }).catch((): void => {
      this.pendingGrant = undefined;
    });
    return task;
  }

  private async openMicSetting(): Promise<void> {
    const context = this.context();
    const manager = abilityAccessCtrl.createAtManager();
    try {
      await manager.requestPermissionOnSetting(context, ['ohos.permission.MICROPHONE']);
    } catch (err) {
      const error = err as BusinessError;
      this.status = `打开权限设置失败 ${error.code}`;
    }
    if (this.micAlreadyGranted(manager, context.applicationInfo.accessTokenId)) {
      this.micAllowed = true;
      this.status = '';
    } else {
      this.micAllowed = false;
      this.status = '需要麦克风权限才能听';
    }
  }

  private async installShellHook(): Promise<void> {
    const context = this.context();
    try {
      const bytes = await context.resourceManager.getRawFileContent('shell.js');
      const script = util.TextDecoder.create('utf-8').decodeToString(bytes);
      await this.controller.runJavaScript(script);
    } catch (err) {
      const error = err as Error;
      hilog.error(0x0002, 'webcap', 'install shell failed: %{public}s', error.message);
    }
  }

  private async startCapture(): Promise<void> {
    if (this.capturer || this.starting) {
      return;
    }
    this.starting = true;
    const allowed = await this.ensureMicPermission();
    if (!allowed) {
      this.denyMic();
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
        const copy = buffer.slice(0);
        setTimeout((): void => {
          this.queuePcm(copy);
        }, 0);
      });
      await this.capturer.start();
      this.status = '';
    } catch (err) {
      const error = err as BusinessError;
      this.status = `打开麦克风失败 ${error.code}`;
      this.capturer = undefined;
      this.denyMic();
    }
    this.starting = false;
  }

  private async stopCapture(): Promise<void> {
    this.pcmParts = [];
    this.pcmBytes = 0;
    const current = this.capturer;
    this.capturer = undefined;
    if (!current) {
      return;
    }
    try {
      await current.stop();
      await current.release();
    } catch (err) {
      const error = err as BusinessError;
      hilog.error(0x0002, 'webcap', 'stop mic failed: %{public}d', error.code);
    }
  }

  build() {
    Column() {
      if (this.status.length > 0) {
        Text(this.status)
          .fontSize(14)
          .fontColor('#E4B15A')
          .width('100%')
          .padding({ left: 16, right: 16, top: 8 })
      }
      if (!this.micAllowed) {
        Button('允许麦克风')
          .width('90%')
          .margin({ top: 8, bottom: 8 })
          .onClick(() => {
            this.openMicSetting();
          })
      }
      Web({ src: PAGE_URL, controller: this.controller })
        .javaScriptAccess(true)
        .domStorageAccess(true)
        .onlineImageAccess(true)
        .imageAccess(true)
        .javaScriptProxy({
          object: this.bridge,
          name: 'harmonyShell',
          methodList: ['start', 'stop'],
          controller: this.controller
        })
        .onPermissionRequest((event: OnPermissionRequestEvent) => {
          event.request.grant(event.request.getAccessibleResource());
        })
        .onSslErrorEventReceive((event: OnSslErrorEventReceiveEvent) => {
          event.handler.handleConfirm();
        })
        .onPageEnd(() => {
          this.installShellHook();
        })
        .width('100%')
        .layoutWeight(1)
    }
    .width('100%')
    .height('100%')
    .backgroundColor('#14160F')
  }
}
