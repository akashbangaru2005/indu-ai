import test from "node:test";
import assert from "node:assert/strict";
import {backendCompatibility} from "../src/api.js";

test("old backend reports a restart instruction instead of enabling absent routes", () => {
  const result = backendCompatibility({name:"Indu", version:"0.6.1"});
  assert.equal(result.compatible, false);
  assert.match(result.message, /0\.6\.1/);
  assert.match(result.message, /restarting/);
});
test("current backend is enabled only when required routes and Gemini text exist", () => {
  const info = {name:"Indu", api_contract:1, features:["contacts","whatsapp_previews","gemini_text","continuous_voice","secure_setup","reminders","live_information"]};
  assert.equal(backendCompatibility(info).compatible, true);
  assert.equal(backendCompatibility({...info,features:["contacts"]}).compatible, false);
  assert.equal(backendCompatibility({...info,name:"Another app"}).compatible, false);
  assert.equal(backendCompatibility({...info,features:["contacts","whatsapp_previews","gemini_text"]}).compatible, false);
});
