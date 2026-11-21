// Portfolio-Watcher (https://github.com/charles2ke/Portfolio-Watcher) keeps its
// investment maths in TypeScript modules under src/research/. Each action
// below imports the modules it needs and calls their exported functions on
// the numbers Jarvis read from the user's message. The adapter only reshapes
// those numbers into the arguments the functions take; every figure in the
// result comes from the project.
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import { registerProjectHooks } from "./hooks.mjs";

// JSON has no undefined, so Jarvis sends null for "not given"; undefined lets
// the project's own default parameters apply.
const given = (value) => value ?? undefined;

// assumptionsFromCompany is where the project turns a beta into a discount
// rate. It reads a whole company record, so this one carries the beta and
// neutral placeholders for everything else.
function companyWithBeta(beta) {
  return {
    fundamentals: {
      beta,
      revenue: 1,
      revenueGrowth: 0,
      operatingMargin: 0,
      taxRate: 0,
      depreciation: 0,
      capex: 0,
      workingCapitalChange: 0,
      evToEbitda: 0,
      netDebt: 0,
      dilutedShares: 0,
    },
    prices: [{ close: 0 }],
  };
}

export default async function setup(root) {
  registerProjectHooks(root);
  const research = (name) => import(pathToFileURL(join(root, "src", "research", `${name}.ts`)).href);

  return {
    async capm({ beta }) {
      const dcf = await research("dcf");
      return {
        costOfEquity: dcf.assumptionsFromCompany(companyWithBeta(beta)).wacc,
        riskFreeRate: dcf.RISK_FREE_RATE,
        equityRiskPremium: dcf.EQUITY_RISK_PREMIUM,
      };
    },

    async dcf({ fcf, growth, years, discount, beta, terminalGrowth, exitMultiple, netDebt, shares, price }) {
      const dcf = await research("dcf");
      const estimate = dcf.assumptionsFromCompany(companyWithBeta(beta ?? 0));
      if (discount == null && beta == null) throw new Error("a DCF needs a discount rate or a beta");
      // The project's model builds free cash flow from revenue. With a 100%
      // operating margin and no tax, depreciation, capex or working capital,
      // its free cash flow is the one the user typed, growing at their rate.
      const assumptions = {
        revenue: fcf,
        revenueGrowth: new Array(years ?? estimate.revenueGrowth.length).fill(growth ?? 0),
        operatingMargin: 1,
        taxRate: 0,
        depreciationPercentOfRevenue: 0,
        capexPercentOfRevenue: 0,
        workingCapitalPercentOfRevenue: 0,
        wacc: discount ?? estimate.wacc,
        terminalGrowth: terminalGrowth ?? dcf.DEFAULT_TERMINAL_GROWTH,
        exitMultiple: exitMultiple ?? 0,
        netDebt: netDebt ?? 0,
        dilutedShares: shares ?? 0,
        currentPrice: price ?? 0,
      };
      const byMultiple = exitMultiple != null;
      return {
        value: dcf.valueDcf(assumptions, byMultiple ? "exit-multiple" : "perpetuity"),
        perpetuity: byMultiple && terminalGrowth != null ? dcf.valueDcf(assumptions, "perpetuity") : null,
        discountRate: assumptions.wacc,
        terminalGrowth: assumptions.terminalGrowth,
        riskFreeRate: dcf.RISK_FREE_RATE,
        equityRiskPremium: dcf.EQUITY_RISK_PREMIUM,
      };
    },

    async fibonacci({ low, high }) {
      const { fibonacciLevels } = await research("technicals");
      return fibonacciLevels(low, high);
    },

    // Each indicator Jarvis wants arrives as an object of its settings.
    async technicals({ values, sma, ema, rsi, macd, bollinger }) {
      const technicals = await research("technicals");
      const result = {};
      if (sma) result.sma = technicals.sma(values, sma.period);
      if (ema) result.ema = technicals.ema(values, ema.period);
      if (rsi) result.rsi = technicals.rsi(values, given(rsi.period));
      if (macd) result.macd = technicals.macd(values, given(macd.fast), given(macd.slow), given(macd.signal));
      if (bollinger) result.bollinger = technicals.bollinger(values, given(bollinger.period), given(bollinger.multiple));
      return result;
    },

    async risk({ values, prices, confidence }) {
      const [universe, risk, quant] = await Promise.all([research("universe"), research("risk"), research("quant")]);
      const returns = prices ? universe.dailyReturns(values) : values;
      return {
        count: returns.length,
        volatility: risk.annualisedVolatility(returns),
        valueAtRisk: risk.historicalVar(returns, given(confidence)),
        expectedShortfall: risk.expectedShortfall(returns, given(confidence)),
        maxDrawdown: risk.maxDrawdown(returns),
        mean: quant.mean(returns),
        median: quant.median(returns),
        stdDev: quant.stdDev(returns),
        skewness: quant.skewness(returns),
        kurtosis: quant.kurtosis(returns),
        tStatistic: quant.tStatistic(returns),
        // returnProfile works from price points and reads only their closes.
        annualisedReturnPercent: prices
          ? quant.returnProfile(values.map((close) => ({ close }))).annualisedReturnPercent
          : null,
      };
    },

    // With years, the year-by-year rows; without, the project's own horizons.
    async drip({ initialInvestment, annualContribution, startingYieldPercent, dividendGrowth, priceGrowth, years }) {
      const { simulateDrip, dripScenarios } = await research("dividends");
      const plan = { initialInvestment, annualContribution, startingYieldPercent, dividendGrowth, priceGrowth };
      const run = (reinvest) =>
        years == null ? dripScenarios({ ...plan, reinvest }) : simulateDrip({ ...plan, reinvest, years });
      return { reinvest: run(true), payout: run(false) };
    },
  };
}
