// Small, deterministic baseline. This is frequency-based extraction, not TextRank or an LLM.
const STOP = new Set(("a about above after again all also am an and any are as at be because " +
  "been before being below between both but by can could did do does doing down during each " +
  "few for from further had has have having he her here hers herself him himself his how i " +
  "if in into is it its itself just me more most my myself no nor not now of off on once " +
  "only or other our ours ourselves out over own same she should so some such than that " +
  "the their theirs them themselves then there these they this those through to too under " +
  "until up very was we were what when where which while who whom why will with would you " +
  "your yours yourself yourselves read learn page website cookies privacy rights reserved").split(" "));

export function redact(text) {
  return text.replace(/\b[\w.+-]+@[\w.-]+\.[a-z]{2,}\b/gi, "[redacted]")
    .replace(/\b(?:sk-|ghp_|github_pat_)[A-Za-z0-9_-]{12,}\b/g, "[redacted]")
    .replace(/\b(?:\d[ -]?){13,19}\b/g, "[redacted]");
}

export function words(text) {
  return (text.toLowerCase().match(/[a-z][a-z0-9+#.-]{1,39}/g) || [])
    .filter(w => !STOP.has(w) && w !== "redacted");
}

export function contextFromText(text, title) {
  const safe = redact(text.slice(0, 30000)).replace(/\s+/g, " ").trim();
  const counts = new Map();
  for (const word of words(safe + " " + title + " " + title)) {
    counts.set(word, (counts.get(word) || 0) + 1);
  }
  const keywords = [...counts].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, 10).map(([word]) => word);
  const sentences = (safe.match(/[^.!?]+[.!?]+|[^.!?]+$/g) || [safe])
    .map(s => s.trim()).filter(s => s.length >= 35 && s.length < 1200).slice(0, 160);
  const scored = sentences.map((sentence, index) => {
    const terms = words(sentence);
    const score = terms.reduce((sum, w) => sum + Math.log(1 + (counts.get(w) || 0)), 0)
      / Math.sqrt(Math.max(terms.length, 1));
    return {sentence, index, score};
  }).sort((a, b) => b.score - a.score || a.index - b.index).slice(0, 4)
    .sort((a, b) => a.index - b.index);
  const summary = (scored.map(s => s.sentence).join(" ") || safe).slice(0, 1200);
  if (summary.length < 40 || keywords.length < 3) {
    throw new Error("This page has too little readable English text. Open an article first.");
  }
  return {title: redact(title).slice(0, 300), summary, keywords};
}
