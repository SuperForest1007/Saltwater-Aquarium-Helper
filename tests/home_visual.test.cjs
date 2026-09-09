const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const context = vm.createContext({});
vm.runInContext(fs.readFileSync('static/home-visual.js', 'utf8'), context);
const item = values => ({ ideal: { low: 7.5, high: 10 }, records: values.map((value, i) => ({ value, ts: i * 1000 })) });
test('phosphate precision is preserved and floating point noise is removed', () => {
  assert.equal(context.homeValue(.13), '0.13');
  assert.equal(context.homeValue(.008), '0.008');
  assert.equal(context.homeValue(7.7-8.1), '-0.4');
});

test('empty and invalid records do not generate a trend', () => {
  assert.equal(context.homeTrendModel(item([])), null);
  assert.equal(context.homeTrendModel({ records: [{value:null,ts:1},{value:8,ts:null}] }), null);
});
test('a single reading stays centered; identical readings stay flat', () => {
  const single = context.homeTrendModel(item([8]));
  assert.equal(single.points.length, 1);
  assert.equal(single.points[0][0], 84);
  const flat = context.homeTrendModel(item([8,8,8]));
  assert.equal(new Set(flat.points.map(p => p[1])).size, 1);
  assert.equal(flat.delta, 0);
});
test('time spacing and numeric direction come from records without mutation', () => {
  const source = {ideal:{low:7.5,high:10},records:[{ts:10000,value:7.7},{ts:0,value:8.1},{ts:1000,value:7.9}]};
  const before = JSON.stringify(source);
  const model = context.homeTrendModel(source);
  assert.equal(JSON.stringify(source), before);
  assert.equal(model.points[0][0], 20);
  assert.equal(model.points[2][0], 148);
  assert.ok(Math.abs(model.points[1][0] - 32.8) < .001);
  assert.ok(model.points[0][1] < model.points[1][1] && model.points[1][1] < model.points[2][1]);
  assert.ok(Math.abs(model.delta + .4) < .00001);
});
test('only the latest three readings are used; equal timestamps stay finite', () => {
  const model = context.homeTrendModel(item([9,8,7,6]));
  assert.equal(model.records.length,3);
  assert.equal(model.records[0].value,8);
  const duplicate = context.homeTrendModel({records:[{ts:1,value:8},{ts:1,value:7.9}]});
  assert.ok(duplicate.points.flat().every(Number.isFinite));
  assert.equal(duplicate.points[0][0],duplicate.points[1][0]);
});
