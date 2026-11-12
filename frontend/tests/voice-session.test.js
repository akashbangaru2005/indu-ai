import test from "node:test";
import assert from "node:assert/strict";
import { acquireMicrophone, connectVoiceSocket, isExitCommand, isWakePhrase, voiceUrl } from "../src/voice-session.js";

class FakeSocket {
  static last;
  constructor() { FakeSocket.last = this; this.closed = false; }
  close() { this.closed = true; }
  message(data) { this.onmessage({data: JSON.stringify(data)}); }
}

function connect(overrides = {}) {
  return connectVoiceSocket("ws://test", {
    isCurrent: () => true, onCreate() {}, onMessage() {}, onClose() {},
    WebSocketClass: FakeSocket, timeoutMs: 500, ...overrides,
  });
}

test("socket resolves only after backend ready", async () => {
  let resolved = false;
  const promise = connect().then(() => { resolved = true; });
  FakeSocket.last.onopen();
  await Promise.resolve();
  assert.equal(resolved, false);
  FakeSocket.last.message({type: "ready"});
  await promise;
  assert.equal(resolved, true);
});

test("backend configuration errors reject startup with useful details", async () => {
  const promise = connect();
  FakeSocket.last.message({type: "error", message: "API key is missing"});
  await assert.rejects(promise, /API key is missing/);
  assert.equal(FakeSocket.last.closed, true);
});

test("close before ready settles the pending startup", async () => {
  const promise = connect();
  FakeSocket.last.onclose();
  await assert.rejects(promise, /before it was ready/);
});

test("timeout closes the pending connection", async () => {
  await assert.rejects(connect({timeoutMs: 5}), /timed out/);
  assert.equal(FakeSocket.last.closed, true);
});

test("cancellation can close a socket before the upgrade completes", async () => {
  let current = true;
  let registered;
  const promise = connect({isCurrent: () => current, onCreate: (socket) => { registered = socket; }});
  assert.equal(registered, FakeSocket.last);
  current = false;
  registered.onopen();
  await assert.rejects(promise, /cancelled/);
  assert.equal(registered.closed, true);
});

test("stale callbacks cannot affect a replacement session", async () => {
  let current = true;
  let messages = 0;
  const promise = connect({isCurrent: () => current, onMessage: () => messages++});
  FakeSocket.last.message({type: "ready"});
  await promise;
  current = false;
  FakeSocket.last.message({type: "indu_transcript", text: "stale"});
  assert.equal(messages, 0);
});

test("microphone permission granted after cancellation stops every track", async () => {
  let grant;
  let stopped = 0;
  let current = true;
  const promise = acquireMicrophone(() => current, {
    getUserMedia: () => new Promise((resolve) => { grant = resolve; }),
  });
  current = false;
  grant({getTracks: () => [{stop: () => stopped++}, {stop: () => stopped++}]});
  assert.equal(await promise, null);
  assert.equal(stopped, 2);
});

test("normal microphone startup returns the acquired stream", async () => {
  const stream = {getTracks: () => []};
  assert.equal(await acquireMicrophone(() => true, {getUserMedia: async () => stream}), stream);
});

test("selected microphone uses an exact device constraint", async () => {
  let constraints;
  await acquireMicrophone(() => true, {getUserMedia:async options => {constraints = options; return {}; }}, "chosen-device");
  assert.deepEqual(constraints.audio.deviceId, {exact:"chosen-device"});
  assert.equal(constraints.audio.echoCancellation, true);
});

test("wake detection uses complete words at the start", () => {
  assert.equal(isWakePhrase("Hey, Indu! What is Python?"), true);
  assert.equal(isWakePhrase("hey industry"), false);
  assert.equal(isWakePhrase("tell me about hey indu"), false);
});

test("knowledge questions containing exit or quit stay in the conversation", () => {
  assert.equal(isExitCommand("Explain the exit code in Python"), false);
  assert.equal(isExitCommand("How can I quit smoking?"), false);
  assert.equal(isExitCommand("Exit Indu!"), true);
  assert.equal(isExitCommand("Quit Indu."), true);
  for (const phrase of ["Exit Indu", "Bye Indu", "Goodbye Indu", "Stop Indu", "Quit Indu"]) {
    assert.equal(isExitCommand(phrase), true);
  }
  assert.equal(isExitCommand("exit"), false);
  assert.equal(isExitCommand("quit"), false);
  assert.equal(isExitCommand("Please explain how to stop Indu from repeating"), false);
});

test("voice URL supports TLS and backend overrides", () => {
  assert.equal(voiceUrl("https://example.com:8443"), "wss://example.com:8443/ws/voice");
  assert.equal(voiceUrl(undefined, {protocol: "http:", hostname: "localhost"}), "ws://localhost:8000/ws/voice");
});
