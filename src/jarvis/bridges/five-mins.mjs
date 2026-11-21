// 5-Mins (https://github.com/charles2ke/5-Mins) is a static web app. Its
// browser modules in assets/js look places up (cities.js), read the forecast
// (weather.js) and ask the public alert feeds (alerts.js) themselves, and none
// of them touches the page when it is imported, so this adapter imports them
// and calls them as they are, with Node's fetch. Jarvis only gives each request
// a time limit, words a failed request for people and notes the hosts asked.
import { join } from "node:path";
import { pathToFileURL } from "node:url";

// projects.call gives up after 30 seconds, and a lookup makes at most two
// rounds of requests: the place, then the forecast or the feeds.
const REQUEST_SECONDS = 10;

function load(root, name) {
  return import(pathToFileURL(join(root, "assets", "js", name)).href);
}

function failure(error) {
  if (error?.name === "TimeoutError") return `no answer within ${REQUEST_SECONDS} seconds`;
  const reason = error?.cause?.code || error?.cause?.message || error?.message || "network error";
  return `could not be reached (${reason})`;
}

// A fetch for the project's code that records each host it asks in `asked`.
function requester(asked) {
  return async function request(url, init = {}) {
    asked.push(new URL(String(url)).hostname);
    let response;
    try {
      response = await fetch(url, { ...init, signal: AbortSignal.timeout(REQUEST_SECONDS * 1000) });
    } catch (error) {
      throw new Error(failure(error));
    }
    const read = response.json.bind(response);
    response.json = async () => {
      try {
        return await read();
      } catch (error) {
        throw new Error(error instanceof SyntaxError ? "the reply could not be read" : failure(error));
      }
    };
    return response;
  };
}

function moment(value) {
  const date = value === undefined ? new Date() : new Date(value);
  if (Number.isNaN(date.getTime())) throw new Error(`unreadable time ${JSON.stringify(value)}`);
  return date;
}

export default async function setup(root) {
  const [
    { fetchAlerts, isWorldwideAlert, ALERT_WINDOW_DAYS },
    { fetchWeather, formatTemperature, isRoughWeather },
    { searchCities },
  ] = await Promise.all(["alerts.js", "weather.js", "cities.js"].map((name) => load(root, name)));

  // Where to look: the first city 5-Mins suggests for `query`, or `lat`/`lon`.
  // `point` is null when the lookup found nothing or failed (`lookupError`).
  async function locate({ query, lat, lon }, request) {
    if (typeof query !== "string") {
      if (!Number.isFinite(lat) || !Number.isFinite(lon)) throw new Error("a place needs a query or lat and lon");
      return { point: { lat, lon }, place: null, lookupError: null };
    }
    try {
      const [place = null] = await searchCities(query, { fetchImpl: request });
      return { point: place, place, lookupError: null };
    } catch (error) {
      return { point: null, place: null, lookupError: error.message };
    }
  }

  return {
    async places({ query, limit }) {
      const asked = [];
      try {
        return { cities: await searchCities(query, { fetchImpl: requester(asked), limit }), lookupError: null, asked };
      } catch (error) {
        return { cities: [], lookupError: error.message, asked };
      }
    },

    async weather(payload) {
      const asked = [];
      const request = requester(asked);
      const { point, place, lookupError } = await locate(payload, request);
      const answer = { place, lookupError, weather: null, error: null, shown: null, rough: false, asked };
      if (!point) return answer;
      try {
        answer.weather = await fetchWeather(point, { fetchImpl: request });
      } catch (error) {
        answer.error = error.message;
        return answer;
      }
      const unit = answer.weather.units.temperature;
      answer.shown = Object.fromEntries(
        ["temperature", "feelsLike", "high", "low"].map((key) => [key, formatTemperature(answer.weather[key], unit)]),
      );
      answer.rough = isRoughWeather(answer.weather);
      return answer;
    },

    // Worldwide alerts are counted, not listed; space_weather lists them.
    async hazards(payload) {
      const asked = [];
      const request = requester(asked);
      const { point, place, lookupError } = await locate(payload, request);
      const answer = {
        place, lookupError, days: ALERT_WINDOW_DAYS, alerts: [], worldwide: 0, errors: [], feeds: 0, asked,
      };
      if (!point) return answer;
      const before = asked.length;
      const found = await fetchAlerts(point, { fetchImpl: request, now: moment(payload.now) });
      answer.alerts = found.alerts.filter((alert) => !isWorldwideAlert(alert));
      answer.worldwide = found.alerts.length - answer.alerts.length;
      answer.errors = found.errors;
      answer.feeds = asked.length - before;
      return answer;
    },

    // 5-Mins has no lookup for worldwide alerts alone: they come with every
    // place's alerts. So this asks about one point and keeps only those.
    async space_weather({ now }) {
      const asked = [];
      const found = await fetchAlerts({ lat: 0, lon: 0 }, { fetchImpl: requester(asked), now: moment(now) });
      return {
        days: ALERT_WINDOW_DAYS,
        alerts: found.alerts.filter(isWorldwideAlert),
        errors: found.errors,
        feeds: asked.length,
        asked,
      };
    },
  };
}
