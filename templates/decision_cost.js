/* Pure cost decision calculator. It does not fetch weather or gate user confirmation. */
(function attachDecisionCalculator(root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    root.MeiyuDecision = factory();
  }
})(
  typeof window !== "undefined"
    ? window
    : typeof globalThis !== "undefined"
      ? globalThis
      : this,
  function createDecisionCalculator() {
    "use strict";

    var BENEFIT_TOLERANCE = 1e-8;
    var MONEY_MAX = 1000000000;
    var MAX_FINITE = Number.MAX_VALUE;

    function invalid(message) {
      throw new Error(message);
    }

    function finiteNumber(value, name) {
      // typeof checks reject null, undefined, strings, and booleans before coercion.
      if (typeof value !== "number" || !Number.isFinite(value)) {
        invalid("参数" + name + "必须是有限实数，不能是布尔值、字符串或空值");
      }
      return value;
    }

    function bounded(value, name, lower, upper) {
      var number = finiteNumber(value, name);
      if (number < lower || number > upper) {
        invalid("参数" + name + "必须在[" + lower + ", " + upper + "]范围内");
      }
      return number;
    }

    function calculate(input) {
      if (input === null || typeof input !== "object" || Array.isArray(input)) {
        invalid("calculate的输入必须是对象");
      }

      var probability = bounded(input.probability, "probability", 0, 1);
      var moveCost = bounded(input.move_cost, "move_cost", 0, MONEY_MAX);
      var lossWithout = bounded(input.loss_without, "loss_without", 0, MONEY_MAX);
      var lossAfter = bounded(input.loss_after, "loss_after", 0, MONEY_MAX);

      var expectedWithout = probability * lossWithout;
      var expectedMove = moveCost + probability * lossAfter;
      var benefit = probability * (lossWithout - lossAfter) - moveCost;
      var state;
      if (Math.abs(benefit) <= BENEFIT_TOLERANCE) {
        state = "tie";
      } else if (benefit > 0) {
        state = "move";
      } else {
        state = "keep";
      }

      var difference = lossWithout - lossAfter;
      var breakEvenProbability = difference > 0 ? moveCost / difference : null;
      // Saturate an unrepresentable positive threshold so the result stays JSON-finite.
      if (breakEvenProbability !== null && !Number.isFinite(breakEvenProbability)) {
        breakEvenProbability = MAX_FINITE;
      }
      var result = {
        state: state,
        probability: probability,
        move_cost: moveCost,
        loss_without: lossWithout,
        loss_after: lossAfter,
        expected_without: expectedWithout,
        expected_move: expectedMove,
        benefit: benefit,
        break_even_probability: breakEvenProbability,
      };

      // Keep the result JSON-finite.
      if (!Object.keys(result).every(function (key) {
        return key === "state" || result[key] === null || Number.isFinite(result[key]);
      })) {
        invalid("计算结果必须是有限数字");
      }
      return result;
    }

    return { calculate: calculate };
  }
);
