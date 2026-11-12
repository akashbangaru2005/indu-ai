import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

for (const rate of [16000, 44100, 48000]) {
  test(`worklet produces 40ms mono PCM16 frames at ${rate} Hz input`, () => {
    let Processor;
    const chunks = [];
    const context = vm.createContext({
      sampleRate: rate,
      AudioWorkletProcessor: class { constructor() { this.port = {postMessage: (chunk) => chunks.push(chunk)}; } },
      registerProcessor: (_, processor) => { Processor = processor; },
    });
    vm.runInContext(readFileSync(new URL("../public/mic-processor.js", import.meta.url), "utf8"), context);
    const processor = new Processor();
    // One second of clipped positive samples: 25 frames of 640 PCM16 samples.
    for (let offset = 0; offset < rate; offset += 128) {
      processor.process([[new Float32Array(Math.min(128, rate - offset)).fill(2)]]);
    }
    assert.equal(chunks.length, 25);
    assert.ok(chunks.every((chunk) => chunk.byteLength === 1280));
    assert.equal(new Int16Array(chunks[0])[0], 32767);
  });
}
