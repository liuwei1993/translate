class DownsampleProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.ratio = sampleRate / 16000;
    this.cursor = 0;
    this.pending = [];
  }

  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (!channel) {
      return true;
    }
    let index = this.cursor;
    while (index < channel.length) {
      this.pending.push(channel[Math.floor(index)]);
      index += this.ratio;
    }
    this.cursor = index - channel.length;
    while (this.pending.length >= 1600) {
      const chunk = this.pending.splice(0, 1600);
      const pcm = new Int16Array(1600);
      for (let i = 0; i < 1600; i += 1) {
        const sample = Math.max(-1, Math.min(1, chunk[i]));
        pcm[i] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
      }
      this.port.postMessage(pcm.buffer, [pcm.buffer]);
    }
    return true;
  }
}

registerProcessor("downsample-16k", DownsampleProcessor);
