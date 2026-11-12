// Jarvis website: instant search, category filters, the demo terminal and
// a few small touches. Everything works on the page that was served; there
// are no network requests and no third-party code.
(function () {
  "use strict";

  const root = document.documentElement;
  const motionQuery = window.matchMedia ? window.matchMedia("(prefers-reduced-motion: reduce)") : null;
  const reduceMotion = () => Boolean(motionQuery && motionQuery.matches);
  const $ = (selector, scope) => (scope || document).querySelector(selector);
  const $$ = (selector, scope) => Array.from((scope || document).querySelectorAll(selector));

  function debounce(fn, wait) {
    let timer = null;
    return function (...args) {
      window.clearTimeout(timer);
      timer = window.setTimeout(() => fn.apply(this, args), wait);
    };
  }

  function make(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  // ---------------------------------------------------------------- text --

  const COMBINING_MARKS = /[\u0300-\u036f]/g;
  const WORD_CHAR = /[\p{L}\p{N}]/u;

  function fold(text) {
    return text.normalize("NFD").replace(COMBINING_MARKS, "").toLowerCase();
  }

  // Folds one character at a time so a match in the folded copy maps back
  // onto the original characters for highlighting.
  function foldWithMap(text) {
    let folded = "";
    const map = [];
    for (let i = 0; i < text.length; i += 1) {
      const piece = fold(text[i]);
      for (let j = 0; j < piece.length; j += 1) map.push(i);
      folded += piece;
    }
    map.push(text.length);
    return { text: folded, map };
  }

  function splitTerms(query) {
    return fold(query).split(/[^\p{L}\p{N}]+/u).filter(Boolean);
  }

  const SUFFIXES = ["iety", "ious", "ness", "ment", "ing", "ies", "ied", "ous", "ers", "ed", "es", "ly", "er", "s", "y"];

  function stem(term) {
    for (const suffix of SUFFIXES) {
      if (term.length - suffix.length >= 4 && term.endsWith(suffix)) return term.slice(0, -suffix.length);
    }
    return term;
  }

  function startsWord(haystack, needle) {
    let index = haystack.indexOf(needle);
    while (index !== -1) {
      if (index === 0 || !WORD_CHAR.test(haystack[index - 1])) return true;
      index = haystack.indexOf(needle, index + 1);
    }
    return false;
  }

  function fieldScore(text, needle, weights) {
    if (text.indexOf(needle) === -1) return 0;
    if (text === needle) return weights[0];
    return startsWord(text, needle) ? weights[1] : weights[2];
  }

  // Optimal string alignment distance, giving up once it exceeds ``limit``.
  function editDistance(a, b, limit) {
    if (Math.abs(a.length - b.length) > limit) return limit + 1;
    let before = null;
    let previous = Array.from({ length: b.length + 1 }, (_, j) => j);
    for (let i = 1; i <= a.length; i += 1) {
      const current = [i];
      let best = i;
      for (let j = 1; j <= b.length; j += 1) {
        const cost = a[i - 1] === b[j - 1] ? 0 : 1;
        let value = Math.min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost);
        if (before && i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1]) {
          value = Math.min(value, before[j - 2] + 1);
        }
        current[j] = value;
        if (value < best) best = value;
      }
      if (best > limit) return limit + 1;
      before = previous;
      previous = current;
    }
    return previous[b.length];
  }

  // ------------------------------------------------------------- search --

  const grid = $("#skill-grid");
  const input = $("#q");
  if (!grid || !input) return;

  const form = $("#search-form");
  const explorer = $("#skills");
  const chipBox = $("#chips");
  const chips = $$(".chip", chipBox);
  const resultCount = $("#result-count");
  const resultStatus = $("#result-status");
  const notice = $("#did-you-mean");
  const emptyState = $("#empty-state");
  const emptyTitle = $("#empty-title");
  const emptyElsewhere = $("#empty-elsewhere");
  const showAllWrap = $("#show-all-wrap");
  const showAllButton = $("#show-all");

  const NAME = [120, 45, 22];
  const DESCRIPTION = [30, 12, 5];
  const EXAMPLE = [30, 9, 3];
  const TOPIC = [32, 12, 4];
  const CATEGORY = [10, 6, 2];

  const labels = {};
  const entries = $$(".card", grid).map((card, position) => {
    const nameEl = $(".card-title", card);
    const descEl = $(".card-desc", card);
    const examples = $$(".example", card).map((el) => ({ el, raw: el.textContent, folded: foldWithMap(el.textContent) }));
    const topics = $$(".topic-list li", card).map((li) => ({ raw: li.textContent, folded: fold(li.textContent) }));
    const category = card.getAttribute("data-category");
    const label = $(".badge", card).textContent;
    labels[category] = label;
    return {
      card,
      position,
      category,
      featured: card.hasAttribute("data-featured"),
      name: { el: nameEl, raw: nameEl.textContent, folded: foldWithMap(nameEl.textContent) },
      nameWords: fold(nameEl.textContent.replace(/-/g, " ")),
      desc: { el: descEl, raw: descEl.textContent, folded: foldWithMap(descEl.textContent) },
      examples,
      topics,
      label: fold(label),
      matchesEl: $(".matches", card),
      marked: false,
    };
  });

  function scoreTerm(entry, needle) {
    let score = Math.max(fieldScore(entry.nameWords, needle, NAME), fieldScore(entry.name.folded.text, needle, NAME));
    score += fieldScore(entry.desc.folded.text, needle, DESCRIPTION);
    let best = 0;
    for (const example of entry.examples) best = Math.max(best, fieldScore(example.folded.text, needle, EXAMPLE));
    score += best;
    best = 0;
    let hits = 0;
    for (const topic of entry.topics) {
      const value = fieldScore(topic.folded, needle, TOPIC);
      if (value) {
        hits += 1;
        best = Math.max(best, value);
      }
    }
    score += best + Math.min(hits, 10);
    score += fieldScore(entry.label, needle, CATEGORY);
    return score;
  }

  // Every term must match somewhere; a term may also match through its stem.
  function search(terms) {
    const results = [];
    for (const entry of entries) {
      let total = 0;
      const needles = [];
      let matchedAll = true;
      for (const term of terms) {
        let score = scoreTerm(entry, term);
        let needle = term;
        if (!score) {
          const base = stem(term);
          if (base !== term) {
            score = Math.round(scoreTerm(entry, base) * 0.6);
            needle = base;
          }
        }
        if (!score) {
          matchedAll = false;
          break;
        }
        total += score;
        needles.push(needle);
      }
      if (matchedAll) results.push({ entry, score: total, needles });
    }
    return results;
  }

  let vocabulary = null;

  function buildVocabulary() {
    const counts = new Map();
    const add = (text) => {
      for (const word of text.split(/[^\p{L}\p{N}]+/u)) {
        if (word.length >= 3) counts.set(word, (counts.get(word) || 0) + 1);
      }
    };
    for (const entry of entries) {
      add(entry.nameWords);
      add(entry.desc.folded.text);
      entry.examples.forEach((example) => add(example.folded.text));
      entry.topics.forEach((topic) => add(topic.folded));
      add(entry.label);
    }
    return counts;
  }

  // Replaces each term that matches nothing with the closest known word.
  function correct(terms) {
    vocabulary = vocabulary || buildVocabulary();
    let changed = false;
    const fixed = terms.map((term) => {
      if (term.length < 3 || search([term]).length) return term;
      const limit = term.length <= 4 ? 1 : 2;
      let bestWord = null;
      let bestDistance = limit + 1;
      let bestCount = 0;
      for (const [word, count] of vocabulary) {
        const distance = editDistance(term, word, limit);
        if (distance < bestDistance || (distance === bestDistance && distance <= limit && count > bestCount)) {
          bestWord = word;
          bestDistance = distance;
          bestCount = count;
        }
      }
      if (bestWord && bestDistance <= limit) {
        changed = true;
        return bestWord;
      }
      return term;
    });
    return changed ? fixed : null;
  }

  // ---------------------------------------------------------- highlights --

  function paint(el, raw, folded, needles) {
    const ranges = [];
    for (const needle of needles || []) {
      let from = 0;
      let at = folded.text.indexOf(needle, from);
      while (needle && at !== -1) {
        ranges.push([folded.map[at], folded.map[at + needle.length]]);
        from = at + needle.length;
        at = folded.text.indexOf(needle, from);
      }
    }
    if (!ranges.length) {
      if (el.firstElementChild) el.textContent = raw;
      return;
    }
    ranges.sort((a, b) => a[0] - b[0] || b[1] - a[1]);
    const merged = [];
    for (const range of ranges) {
      const last = merged[merged.length - 1];
      if (last && range[0] <= last[1]) last[1] = Math.max(last[1], range[1]);
      else merged.push(range.slice());
    }
    const fragment = document.createDocumentFragment();
    let cursor = 0;
    for (const [start, end] of merged) {
      if (start > cursor) fragment.append(raw.slice(cursor, start));
      fragment.append(make("mark", "", raw.slice(start, end)));
      cursor = end;
    }
    if (cursor < raw.length) fragment.append(raw.slice(cursor));
    el.replaceChildren(fragment);
  }

  function highlight(entry, needles) {
    if (!needles && !entry.marked) return;
    paint(entry.name.el, entry.name.raw, entry.name.folded, needles);
    paint(entry.desc.el, entry.desc.raw, entry.desc.folded, needles);
    entry.examples.forEach((example) => paint(example.el, example.raw, example.folded, needles));

    const found = needles ? entry.topics.filter((topic) => needles.some((needle) => topic.folded.includes(needle))) : [];
    if (found.length) {
      const line = document.createDocumentFragment();
      line.append(make("span", "matches-label", found.length === 1 ? "Topic: " : "Topics: "));
      found.slice(0, 5).forEach((topic, index) => {
        if (index) line.append(", ");
        const span = make("span");
        paint(span, topic.raw, foldWithMap(topic.raw), needles);
        line.append(span);
      });
      if (found.length > 5) line.append(` and ${found.length - 5} more`);
      entry.matchesEl.replaceChildren(line);
      entry.matchesEl.hidden = false;
    } else if (!entry.matchesEl.hidden) {
      entry.matchesEl.hidden = true;
      entry.matchesEl.replaceChildren();
    }
    entry.marked = Boolean(needles);
  }

  // --------------------------------------------------------------- state --

  const state = { category: "all", expanded: false };
  const validCategories = new Set(chips.map((chip) => chip.getAttribute("data-category")));

  const announce = debounce((text) => {
    resultStatus.textContent = text;
  }, 450);

  function plural(count, word) {
    return `${count} ${word}${count === 1 ? "" : "s"}`;
  }

  function setCount(parts, quiet) {
    const fragment = document.createDocumentFragment();
    let text = "";
    for (const part of parts) {
      if (typeof part === "string") {
        fragment.append(part);
        text += part;
      } else {
        fragment.append(make("strong", "", part.strong));
        text += part.strong;
      }
    }
    resultCount.replaceChildren(fragment);
    if (!quiet) announce(text);
  }

  function render(options) {
    const animate = Boolean(options && options.animate) && !reduceMotion();
    const quiet = Boolean(options && options.quiet);
    const raw = input.value.trim();
    let terms = splitTerms(raw);
    let results = terms.length ? search(terms) : null;
    let corrected = null;

    if (terms.length && !results.length) {
      const fixed = correct(terms);
      if (fixed) {
        const retry = search(fixed);
        if (retry.length) {
          corrected = fixed;
          results = retry;
          terms = fixed;
        }
      }
    }

    const pool = results || entries.map((entry) => ({ entry, score: 0, needles: null }));
    const counts = { all: pool.length };
    for (const result of pool) counts[result.entry.category] = (counts[result.entry.category] || 0) + 1;

    for (const chip of chips) {
      const category = chip.getAttribute("data-category");
      const count = counts[category] || 0;
      $(".chip-count", chip).textContent = String(count);
      chip.classList.toggle("is-empty", count === 0);
      chip.setAttribute("aria-pressed", String(category === state.category));
    }

    let visible = pool.filter((result) => state.category === "all" || result.entry.category === state.category);
    const featuredOnly = !results && state.category === "all" && !state.expanded;
    if (featuredOnly) visible = visible.filter((result) => result.entry.featured);
    visible.sort((a, b) => b.score - a.score || a.entry.position - b.entry.position);

    const shown = new Map(visible.map((result) => [result.entry, result]));
    for (const entry of entries) {
      const result = shown.get(entry);
      if (result && entry.card.hidden && animate) {
        entry.card.classList.remove("is-entering");
        void entry.card.offsetWidth;
        entry.card.classList.add("is-entering");
      }
      entry.card.hidden = !result;
      highlight(entry, result ? result.needles : null);
    }

    const order = visible.map((result) => result.entry.card);
    const current = Array.from(grid.children).filter((card) => !card.hidden);
    if (order.some((card, index) => current[index] !== card)) {
      const rest = entries.filter((entry) => !shown.has(entry)).map((entry) => entry.card);
      grid.append(...order, ...rest);
    }

    const inCategory = state.category === "all" ? "" : ` in ${labels[state.category]}`;
    const shownQuery = corrected ? corrected.join(" ") : raw;
    if (!results) {
      if (featuredOnly) setCount(["Showing ", { strong: String(visible.length) }, ` featured skills of ${entries.length}`], quiet);
      else if (state.category === "all") setCount(["Showing all ", { strong: String(visible.length) }, " skills"], quiet);
      else setCount([{ strong: String(visible.length) }, ` ${labels[state.category]} ${visible.length === 1 ? "skill" : "skills"}`], quiet);
    } else if (visible.length) {
      setCount([{ strong: String(visible.length) }, ` ${visible.length === 1 ? "skill matches" : "skills match"} “${shownQuery}”${inCategory}`], quiet);
    } else {
      setCount([`No skills match “${raw}”${inCategory}`], quiet);
    }

    if (corrected && visible.length) {
      notice.replaceChildren(
        `No matches for “${raw}”. Showing results for `,
        make("strong", "", corrected.join(" ")),
        " instead."
      );
      notice.hidden = false;
    } else {
      notice.hidden = true;
    }

    emptyState.hidden = visible.length > 0;
    if (!visible.length) {
      emptyTitle.textContent = `No skills match “${raw}”${inCategory}`;
      emptyElsewhere.hidden = !(state.category !== "all" && pool.length);
    }
    showAllWrap.hidden = !featuredOnly;
  }

  function syncUrl() {
    const params = new URLSearchParams(window.location.search);
    const query = input.value.trim();
    if (query) params.set("q", query);
    else params.delete("q");
    if (state.category !== "all") params.set("cat", state.category);
    else params.delete("cat");
    const search = params.toString();
    const url = window.location.pathname + (search ? `?${search}` : "") + window.location.hash;
    if (url !== window.location.pathname + window.location.search + window.location.hash) {
      window.history.replaceState(window.history.state, "", url);
    }
  }
  const scheduleUrl = debounce(syncUrl, 300);

  function headerOffset() {
    const header = $(".site-header");
    return header && getComputedStyle(header).position === "sticky" ? header.offsetHeight : 0;
  }

  function scrollToResults() {
    const top = explorer.getBoundingClientRect().top + window.scrollY - headerOffset();
    window.scrollTo({ top, behavior: reduceMotion() ? "auto" : "smooth" });
  }

  function focusSearch() {
    const rect = input.getBoundingClientRect();
    if (rect.top < headerOffset() || rect.bottom > window.innerHeight) scrollToResults();
    input.focus({ preventScroll: true });
    input.select();
  }

  function setQuery(text, options) {
    input.value = text;
    render({ animate: true });
    scheduleUrl();
    if (options && options.focus) input.focus({ preventScroll: true });
  }

  input.addEventListener("input", () => {
    render({ animate: true });
    scheduleUrl();
  });

  input.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      if (input.value) {
        event.preventDefault();
        setQuery("");
      } else {
        input.blur();
      }
    }
  });

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    render();
    syncUrl();
    scrollToResults();
    if (window.matchMedia && window.matchMedia("(hover: none)").matches) input.blur();
  });

  chipBox.addEventListener("click", (event) => {
    const chip = event.target.closest(".chip");
    if (!chip) return;
    const category = chip.getAttribute("data-category");
    state.category = category === state.category && category !== "all" ? "all" : category;
    render({ animate: true });
    scheduleUrl();
  });

  document.addEventListener("click", (event) => {
    const suggestion = event.target.closest(".suggestion");
    if (suggestion) {
      setQuery(suggestion.getAttribute("data-query"), { focus: true });
      return;
    }
    const action = event.target.closest("[data-action]");
    if (!action) return;
    if (action.getAttribute("data-action") === "clear") {
      setQuery("", { focus: true });
    } else if (action.getAttribute("data-action") === "all-categories") {
      state.category = "all";
      render({ animate: true });
      scheduleUrl();
    }
  });

  showAllButton.addEventListener("click", () => {
    const before = new Set(entries.filter((entry) => !entry.card.hidden));
    state.expanded = true;
    render({ animate: true });
    const first = entries.find((entry) => !entry.card.hidden && !before.has(entry));
    if (first) {
      first.card.setAttribute("tabindex", "-1");
      first.card.focus({ preventScroll: true });
    }
  });

  document.addEventListener("keydown", (event) => {
    const target = event.target;
    const typing = target && (target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName));
    if (event.key === "/" && !typing && !event.ctrlKey && !event.metaKey && !event.altKey) {
      event.preventDefault();
      focusSearch();
    } else if ((event.key === "k" || event.key === "K") && (event.ctrlKey || event.metaKey) && !event.altKey) {
      event.preventDefault();
      focusSearch();
    }
  });

  // A link to a card that is filtered out shows every skill first.
  function revealHashTarget(scroll) {
    let id = "";
    try {
      id = decodeURIComponent(window.location.hash.slice(1));
    } catch (error) {
      return;
    }
    const target = id && document.getElementById(id);
    if (!target || !target.classList.contains("card")) return;
    if (target.hidden) {
      input.value = "";
      state.category = "all";
      state.expanded = true;
      render();
      syncUrl();
    }
    if (scroll) target.scrollIntoView({ block: "start", behavior: reduceMotion() ? "auto" : "smooth" });
  }
  window.addEventListener("hashchange", () => revealHashTarget(true));

  const params = new URLSearchParams(window.location.search);
  const startCategory = params.get("cat");
  if (startCategory && validCategories.has(startCategory)) state.category = startCategory;
  input.value = params.get("q") || "";
  const hashCard = window.location.hash.startsWith("#skill-") && document.getElementById(window.location.hash.slice(1));
  if (hashCard) state.expanded = true;
  render({ quiet: true });
  if (hashCard) revealHashTarget(false);
  else if (input.value || state.category !== "all") window.requestAnimationFrame(() => scrollToResults());

  // --------------------------------------------------------- sticky dock --

  const sentinel = $("#dock-sentinel");
  const dock = $("#search-dock");
  if (sentinel && dock && "IntersectionObserver" in window) {
    let observer = null;
    const watch = () => {
      if (observer) observer.disconnect();
      const offset = headerOffset();
      observer = new IntersectionObserver(
        ([entry]) => dock.classList.toggle("is-stuck", !entry.isIntersecting && entry.boundingClientRect.top < offset + 1),
        { rootMargin: `-${offset + 1}px 0px 0px 0px`, threshold: 0 }
      );
      observer.observe(sentinel);
    };
    watch();
    window.addEventListener("resize", debounce(watch, 200));
  }

  // ----------------------------------------------------------- clipboard --

  const toast = $("#toast");
  let toastTimer = null;

  function showToast(message) {
    toast.textContent = message;
    toast.classList.add("is-visible");
    window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(() => toast.classList.remove("is-visible"), 1800);
  }

  function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(text);
    return new Promise((resolve, reject) => {
      const area = make("textarea", "visually-hidden");
      area.value = text;
      area.setAttribute("readonly", "");
      document.body.append(area);
      area.select();
      try {
        if (document.execCommand("copy")) resolve();
        else reject(new Error("Copy command was refused"));
      } catch (error) {
        reject(error);
      } finally {
        area.remove();
      }
    });
  }

  document.addEventListener("click", (event) => {
    const button = event.target.closest(".copy");
    if (!button) return;
    const text = button.getAttribute("data-copy");
    copyText(text).then(
      () => {
        button.textContent = "Copied";
        button.classList.add("is-copied");
        showToast(`Copied: ${text}`);
        window.setTimeout(() => {
          button.textContent = "Copy";
          button.classList.remove("is-copied");
        }, 1600);
      },
      () => showToast("Copying is blocked here. Select the text and copy it instead.")
    );
  });

  // --------------------------------------------------------------- theme --

  const toggle = $("#theme-toggle");
  const themeColors = { dark: "#070b18", light: "#f5f7ff" };

  function storedTheme() {
    try {
      return window.localStorage.getItem("jarvis-theme");
    } catch (error) {
      return null;
    }
  }

  function currentTheme() {
    return root.getAttribute("data-theme") === "light" ? "light" : "dark";
  }

  function applyTheme(theme) {
    root.setAttribute("data-theme", theme);
    const label = `Switch to ${theme === "dark" ? "light" : "dark"} theme`;
    toggle.setAttribute("aria-label", label);
    toggle.title = label;
    if (storedTheme()) {
      $$('meta[name="theme-color"]').forEach((meta) => meta.setAttribute("content", themeColors[theme]));
    }
  }

  if (toggle) {
    toggle.hidden = false;
    applyTheme(currentTheme());
    toggle.addEventListener("click", () => {
      const next = currentTheme() === "dark" ? "light" : "dark";
      try {
        window.localStorage.setItem("jarvis-theme", next);
      } catch (error) {
        // Storage can be blocked; the choice then lasts for this page view.
      }
      applyTheme(next);
    });
    const systemLight = window.matchMedia ? window.matchMedia("(prefers-color-scheme: light)") : null;
    if (systemLight && systemLight.addEventListener) {
      systemLight.addEventListener("change", (event) => {
        if (!storedTheme()) applyTheme(event.matches ? "light" : "dark");
      });
    }
  }

  // ---------------------------------------------------------------- demo --

  const terminal = $("#terminal-body");
  const log = $("#terminal-log");
  const demoNode = $("#demo-data");
  const tabs = $$(".demo-tab");
  let demos = [];
  try {
    demos = demoNode ? JSON.parse(demoNode.textContent) : [];
  } catch (error) {
    demos = [];
  }
  let frame = 0;
  let pause = 0;

  function stopTyping() {
    window.cancelAnimationFrame(frame);
    window.clearTimeout(pause);
  }

  function type(target, text, duration, done) {
    let start = null;
    const step = (now) => {
      if (start === null) start = now;
      const progress = Math.min(1, (now - start) / duration);
      target.textContent = text.slice(0, Math.round(text.length * progress));
      terminal.scrollTop = terminal.scrollHeight;
      if (progress < 1) frame = window.requestAnimationFrame(step);
      else done();
    };
    frame = window.requestAnimationFrame(step);
  }

  function playDemo(index, animate) {
    const demo = demos[index];
    if (!demo || !terminal || !log) return;
    stopTyping();
    tabs.forEach((tab, i) => tab.setAttribute("aria-pressed", String(i === index)));

    const promptText = make("span", "term-prompt");
    const promptLine = make("p", "term-line");
    promptLine.append(make("span", "term-you", "you>"), " ", promptText);
    const replyText = make("span", "term-text");
    const reply = make("pre", "term-reply");
    reply.append(make("span", "term-jarvis", "jarvis>"), " ", replyText);
    const cursor = make("span", "cursor");
    cursor.setAttribute("aria-hidden", "true");
    log.replaceChildren(promptLine);

    const finish = () => {
      replyText.textContent = demo.reply;
      const next = make("p", "term-line");
      next.append(make("span", "term-you", "you>"), " ", cursor);
      log.append(next);
      log.setAttribute("aria-busy", "false");
      terminal.scrollTop = terminal.scrollHeight;
    };

    if (!animate || reduceMotion()) {
      promptText.textContent = demo.prompt;
      log.append(reply);
      finish();
      return;
    }
    log.setAttribute("aria-busy", "true");
    promptLine.append(cursor);
    type(promptText, demo.prompt, Math.min(1000, 32 * demo.prompt.length), () => {
      pause = window.setTimeout(() => {
        log.append(reply);
        reply.append(cursor);
        type(replyText, demo.reply, Math.min(900, 5 * demo.reply.length), finish);
      }, 260);
    });
  }

  tabs.forEach((tab, index) => tab.addEventListener("click", () => playDemo(index, true)));

  if (terminal && demos.length && "IntersectionObserver" in window && !reduceMotion()) {
    const watcher = new IntersectionObserver(
      (items) => {
        if (items.some((item) => item.isIntersecting)) {
          watcher.disconnect();
          playDemo(0, true);
        }
      },
      { threshold: 0.45 }
    );
    watcher.observe(terminal);
  }

  // -------------------------------------------------------------- reveal --

  const reveals = $$(".reveal");
  if ("IntersectionObserver" in window && !reduceMotion()) {
    const revealer = new IntersectionObserver(
      (items) => {
        for (const item of items) {
          if (item.isIntersecting) {
            item.target.classList.add("is-visible");
            revealer.unobserve(item.target);
          }
        }
      },
      { rootMargin: "0px 0px -6% 0px", threshold: 0.06 }
    );
    reveals.forEach((el, index) => {
      el.style.transitionDelay = `${(index % 3) * 70}ms`;
      revealer.observe(el);
    });
    root.classList.add("reveal-ready");
  } else {
    reveals.forEach((el) => el.classList.add("is-visible"));
  }
})();
