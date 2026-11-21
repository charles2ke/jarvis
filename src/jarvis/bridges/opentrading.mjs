// OpenTrading (https://github.com/charles2ke/OpenTrading) is a paper-trading
// app. Its demo stocks and indices, prices, order checks, fills and portfolio
// valuation are in src/core/trading.js, and the way it reads and writes a
// saved portfolio is in src/core/storage.js. Both are plain ES modules that
// don't touch the page, so this adapter imports them and calls their exports.
// Jarvis keeps the portfolio in its own memory and sends it with each request.
// Nothing here applies live quotes or makes a request, so every price is the
// app's built-in demo value.
import { join } from "node:path";
import { pathToFileURL } from "node:url";

export default async function setup(root) {
  const load = (file) => import(pathToFileURL(join(root, file)).href);
  const trading = await load("src/core/trading.js");
  const { loadPortfolio, savePortfolio } = await load("src/core/storage.js");

  // The saved portfolio as the app reads it back from its storage, where
  // anything it doesn't accept becomes a fresh portfolio.
  function read(saved) {
    return {
      portfolio: loadPortfolio({ getItem: () => JSON.stringify(saved ?? null) }),
      discarded: saved != null && !trading.isPortfolio(saved),
    };
  }

  // The portfolio as the app writes it to its storage (it refuses bad ones).
  function written(portfolio) {
    let text = "null";
    savePortfolio({ setItem: (_key, value) => { text = value; } }, portfolio);
    return JSON.parse(text);
  }

  // The most shares validateOrder() accepts for this order right now, found by
  // asking it about larger and larger quantities; 0 when it accepts none.
  function most(portfolio, order) {
    const accepts = (quantity) => trading.validateOrder(portfolio, { ...order, quantity }) === "";
    let low = 0;
    let high = 1;
    while (high <= Number.MAX_SAFE_INTEGER && accepts(high)) {
      low = high;
      high *= 2;
    }
    while (high - low > 1) {
      const middle = low + Math.floor((high - low) / 2);
      if (accepts(middle)) low = middle;
      else high = middle;
    }
    return low;
  }

  return {
    market() {
      return {
        startingCash: trading.STARTING_CASH,
        instruments: trading.marketInstruments(),
        indices: trading.indices,
      };
    },

    search({ query = "" }) {
      return { instruments: trading.searchInstruments(query), indices: trading.searchIndices(query) };
    },

    portfolio({ portfolio: saved }) {
      const { portfolio, discarded } = read(saved);
      return { discarded, summary: trading.summarizePortfolio(portfolio) };
    },

    // order is {symbol, side, quantity}; a quantity of "all" sells every share held.
    order({ portfolio: saved, order = {} }) {
      const { portfolio: before, discarded } = read(saved);
      const was = trading.summarizePortfolio(before);
      const held = was.positions.find((position) => position.symbol === order.symbol)?.quantity ?? 0;
      const request = { symbol: order.symbol, side: order.side, quantity: order.quantity === "all" ? held : order.quantity };
      const { portfolio: after, error } = trading.executeOrder(before, request);
      return {
        discarded,
        error,
        quantity: request.quantity,
        held,
        cashBefore: was.cash,
        most: error ? most(before, request) : null,
        portfolio: error ? null : written(after),
        summary: trading.summarizePortfolio(after),
      };
    },

    reset({ portfolio: saved }) {
      const { portfolio: before } = read(saved);
      const fresh = written(trading.createPortfolio());
      return {
        cleared: trading.summarizePortfolio(before).positions.length,
        portfolio: fresh,
        summary: trading.summarizePortfolio(fresh),
      };
    },
  };
}
