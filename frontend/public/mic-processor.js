// public/mic-processor.js
// Runs on the audio thread. Downsamples mic audio to 16 kHz mono PCM16
// and posts ~40 ms chunks to the main thread.

const TARGET_RATE = 16000;
const CHUNK_SAMPLES = 640; // 40 ms @ 16 kHz

class MicProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.acc = 0;
    this.cnt = 0;
    this.phase = 0;
    this.out = new Int16Array(CHUNK_SAMPLES);
    this.n = 0;
  }

  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (!channel) return true;

    for (let i = 0; i < channel.length; i++) {
      this.acc += channel[i];
      this.cnt++;
      // Integer clock avoids losing a sample each second at rates such as 44.1 kHz.
      this.phase += TARGET_RATE;

      if (this.phase >= sampleRate) {
        this.phase -= sampleRate;

        const s = Math.max(-1, Math.min(1, this.acc / this.cnt));
        this.out[this.n++] = s < 0 ? s * 32768 : s * 32767;
        this.acc = 0;
        this.cnt = 0;

        if (this.n >= CHUNK_SAMPLES) {
          const chunk = this.out.slice(0).buffer;
          this.port.postMessage(chunk, [chunk]);
          this.n = 0;
        }
      }
    }
    return true;
  }
}

registerProcessor("mic-processor", MicProcessor);
