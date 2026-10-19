const assert = require("assert");
const vm = require("vm");
const calculator = require("../templates/decision_cost.js");

function approx(actual, expected, tolerance = 1e-12) {
  assert.ok(Math.abs(actual - expected) <= tolerance, `${actual} != ${expected}`);
}

function assertFiniteResult(result) {
  for (const [key, value] of Object.entries(result)) {
    if (key !== "state" && value !== null) assert.ok(Number.isFinite(value), key);
  }
}

assert.strictEqual(calculator.calculate({
  probability: 0.6,
  move_cost: 80,
  loss_without: 1000,
  loss_after: 100,
}).state, "move");
const move = calculator.calculate({
  probability: 0.6,
  move_cost: 80,
  loss_without: 1000,
  loss_after: 100,
});
approx(move.expected_without, 600);
approx(move.expected_move, 140);
approx(move.benefit, 460);

const keep = calculator.calculate({
  probability: 0.6,
  move_cost: 600,
  loss_without: 1000,
  loss_after: 100,
});
assert.strictEqual(keep.state, "keep");
approx(keep.expected_without, 600);
approx(keep.expected_move, 660);
approx(keep.benefit, -60);

for (const input of [
  { probability: 0, move_cost: 0, loss_without: 100, loss_after: 0 },
  { probability: 1, move_cost: 0, loss_without: 100, loss_after: 0 },
  { probability: 0.5, move_cost: 0, loss_without: 100, loss_after: 100 },
  { probability: 0.5, move_cost: 10, loss_without: 100, loss_after: 100 },
  { probability: 0.5, move_cost: 10, loss_without: 100, loss_after: 120 },
]) {
  const result = calculator.calculate(input);
  assertFiniteResult(result);
}

assert.strictEqual(calculator.calculate({ probability: 0.5, move_cost: 50, loss_without: 100, loss_after: 0 }).state, "tie");
assert.strictEqual(calculator.calculate({ probability: 0.5, move_cost: 50 + 1e-9, loss_without: 100, loss_after: 0 }).state, "tie");
assert.strictEqual(calculator.calculate({ probability: 0.5, move_cost: 50 + 2e-8, loss_without: 100, loss_after: 0 }).state, "keep");
const impossible = calculator.calculate({ probability: 0.2, move_cost: 200, loss_without: 100, loss_after: 0 });
approx(impossible.break_even_probability, 2);
const extreme = calculator.calculate({ probability: 1, move_cost: 1000000000, loss_without: Number.MIN_VALUE, loss_after: 0 });
assert.strictEqual(extreme.break_even_probability, Number.MAX_VALUE);
assertFiniteResult(extreme);

for (const input of [
  { probability: true, move_cost: 1, loss_without: 1, loss_after: 0 },
  { probability: 0.5, move_cost: false, loss_without: 1, loss_after: 0 },
  { probability: 0.5, move_cost: 1, loss_without: "100", loss_after: 0 },
  { probability: 0.5, move_cost: 1, loss_without: null, loss_after: 0 },
  { probability: NaN, move_cost: 1, loss_without: 1, loss_after: 0 },
  { probability: 0.5, move_cost: Infinity, loss_without: 1, loss_after: 0 },
  { probability: -0.01, move_cost: 1, loss_without: 1, loss_after: 0 },
  { probability: 1.01, move_cost: 1, loss_without: 1, loss_after: 0 },
  { probability: 0.5, move_cost: -1, loss_without: 1, loss_after: 0 },
  { probability: 0.5, move_cost: 1000000001, loss_without: 1, loss_after: 0 },
]) {
  assert.throws(() => calculator.calculate(input), /参数|calculate/);
}

const browserContext = { window: {} };
vm.runInNewContext(require("fs").readFileSync(require.resolve("../templates/decision_cost.js"), "utf8"), browserContext);
assert.strictEqual(typeof browserContext.window.MeiyuDecision.calculate, "function");
const browserResult = browserContext.window.MeiyuDecision.calculate({
  probability: 0.6,
  move_cost: 80,
  loss_without: 1000,
  loss_after: 100,
});
assert.strictEqual(JSON.stringify(browserResult), JSON.stringify(move));

console.log("decision_cost.js tests passed");
