---
name: install-webcap
description: >-
  Build the web shell in apps/webcap (译口同声, com.univoice.app) and install it
  on a connected Huawei phone. Use when the user asks to install the web
  version, webpage, or 译口同声 onto a Huawei, HarmonyOS, or Pura device, or to
  run scripts/install_webcap.sh.
---

# 把网页版装到华为手机

只运行仓库里的脚本。不要自己调用 `hvigor`、`hdc` 或 `devecocli`。

在仓库根目录执行：

```bash
scripts/install_webcap.sh
```

编译并安装 `apps/webcap`，然后打开 `com.univoice.app/EntryAbility`。

## 参数

- 只连着一台手机：不加参数。
- 用户指定了序列号或设备名，或连着多台：`scripts/install_webcap.sh <序列号或设备名>`。
- 用户说包已经编过、只要重装：加上 `--skip-build`。
- 用户要先卸掉旧包：加上 `--uninstall`。

其他 `devecocli run` 参数原样跟在序列号后面。

## 完成标准

脚本退出码为 0，并且输出里同时有：

- `App installed successfully`
- `start ability successfully`

把脚本打印的 `安装到 …` 那一行里的设备名和序列号告诉用户。

## 失败时

- 没有设备，或连着多台却没指定：把脚本的提示原样说明。请用户打开 USB 调试并连上手机，或从列出的序列号里选一台。不要猜序列号。
- 找不到 `devecocli` 或 Java：展示脚本的报错，不要另找一套编译命令。
- 这个技能只安装 `apps/webcap`。`apps/pura70` 是另一套离线字幕应用，不要用这个脚本安装。
