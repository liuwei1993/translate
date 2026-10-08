import { common } from '@kit.AbilityKit';
import { fileIo } from '@kit.CoreFileKit';

const FILES: string[] = [
  'models/mt/zh-en/encoder_model.onnx',
  'models/mt/zh-en/decoder_model.onnx',
  'models/mt/en-zh/encoder_model.onnx',
  'models/mt/en-zh/decoder_model.onnx',
  'tok/zh-en.json',
  'tok/en-zh.json'
];

function parentDir(path: string): string {
  const slash = path.lastIndexOf('/');
  return slash < 0 ? path : path.substring(0, slash);
}

function exists(path: string): boolean {
  try {
    return fileIo.accessSync(path);
  } catch (err) {
    return false;
  }
}

function ensureDir(path: string): void {
  if (!exists(path)) {
    fileIo.mkdirSync(path);
  }
}

function copyRaw(context: common.UIAbilityContext, relative: string, dest: string): void {
  const raw = context.resourceManager.getRawFdSync(relative);
  let same = false;
  if (exists(dest)) {
    const stat = fileIo.statSync(dest);
    same = stat.size === raw.length;
  }
  if (same) {
    context.resourceManager.closeRawFdSync(relative);
    return;
  }
  const destFile = fileIo.openSync(dest,
    fileIo.OpenMode.READ_WRITE | fileIo.OpenMode.CREATE | fileIo.OpenMode.TRUNC);
  fileIo.lseek(raw.fd, raw.offset, fileIo.WhenceType.SEEK_SET);
  const buffer = new ArrayBuffer(1024 * 1024);
  let remaining = raw.length;
  while (remaining > 0) {
    const length = remaining > buffer.byteLength ? buffer.byteLength : remaining;
    const read = fileIo.readSync(raw.fd, buffer, { length: length });
    if (read <= 0) {
      break;
    }
    fileIo.writeSync(destFile.fd, buffer, { length: read });
    remaining -= read;
  }
  fileIo.closeSync(destFile.fd);
  context.resourceManager.closeRawFdSync(relative);
}

export function stageModels(context: common.UIAbilityContext): string {
  const root = `${context.filesDir}/offline`;
  ensureDir(context.filesDir);
  ensureDir(root);
  ensureDir(`${root}/models`);
  ensureDir(`${root}/models/mt`);
  ensureDir(`${root}/models/mt/zh-en`);
  ensureDir(`${root}/models/mt/en-zh`);
  ensureDir(`${root}/tok`);
  for (let i = 0; i < FILES.length; i++) {
    const relative = FILES[i];
    const dest = `${root}/${relative}`;
    ensureDir(parentDir(dest));
    copyRaw(context, relative, dest);
  }
  return root;
}
