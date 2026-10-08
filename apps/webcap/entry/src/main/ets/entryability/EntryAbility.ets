import { AbilityConstant, ConfigurationConstant, UIAbility, Want } from '@kit.AbilityKit';
import { hilog } from '@kit.PerformanceAnalysisKit';
import { window } from '@kit.ArkUI';

const DOMAIN = 0x0000;

function holdScreen(win: window.Window): void {
  win.setWindowKeepScreenOn(true).catch((error: Error) => {
    hilog.error(DOMAIN, 'webcap', 'keep screen on failed: %{public}s', error.message);
  });
}

export default class EntryAbility extends UIAbility {
  private mainWindow?: window.Window;

  onCreate(want: Want, launchParam: AbilityConstant.LaunchParam): void {
    try {
      this.context.getApplicationContext().setColorMode(ConfigurationConstant.ColorMode.COLOR_MODE_NOT_SET);
    } catch (err) {
      hilog.error(DOMAIN, 'webcap', 'Failed to set colorMode. Cause: %{public}s', JSON.stringify(err));
    }
  }

  onWindowStageCreate(windowStage: window.WindowStage): void {
    windowStage.loadContent('pages/Index', (err) => {
      if (err.code) {
        hilog.error(DOMAIN, 'webcap', 'Failed to load the content. Cause: %{public}s', JSON.stringify(err));
      }
    });
    windowStage.getMainWindow().then((win: window.Window) => {
      this.mainWindow = win;
      holdScreen(win);
    }).catch((error: Error) => {
      hilog.error(DOMAIN, 'webcap', 'Failed to get window. Cause: %{public}s', error.message);
    });
  }

  onForeground(): void {
    if (this.mainWindow) {
      holdScreen(this.mainWindow);
    }
  }

  onBackground(): void {
    hilog.info(DOMAIN, 'webcap', 'background');
  }
}
