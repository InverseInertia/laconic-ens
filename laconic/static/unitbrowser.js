/* The units dialog: which units it lists for a search and a tag, and the user's own tags.
 *
 * The server sends every unit with its standard tags (laconic/unittags.py) and the user's tags,
 * {tag: [unit, ...]}, as stored in settings.json. The user's tags are changed here and sent back
 * whole. Pure functions; runs under Node for tests.
 *
 *   tagList(data, userTags)              every tag to filter by: the standard ones, then the user's
 *   tagsOf(row, userTags)                a unit's tags, standard first
 *   filter(data, userTags, query, tag)   the rows to list: those with the tag (any, for null) whose
 *                                        name or description has every word of the query
 *   addTag(userTags, tag, unit)          a new userTags with the unit tagged
 *   removeTag(userTags, tag, unit)       a new userTags without it; a tag left empty goes
 */
(function (root) {
  'use strict';

  const norm = (tag) => tag.trim().split(/\s+/).join(' ');

  function tagList(data, userTags) {
    const out = [...data.tags];
    for (const t of Object.keys(userTags || {}).sort((a, b) => a.localeCompare(b))) if (!out.includes(t)) out.push(t);
    return out;
  }

  function tagsOf(row, userTags) {
    const out = [...row[2]];
    for (const [t, units] of Object.entries(userTags || {})) if (units.includes(row[0]) && !out.includes(t)) out.push(t);
    return out;
  }

  function filter(data, userTags, query, tag) {
    const words = (query || '').toLowerCase().replace(/^'/, '').split(/\s+/).filter(Boolean);
    return data.units.filter((row) => {
      if (tag && !tagsOf(row, userTags).includes(tag)) return false;
      const hay = (row[0] + ' ' + row[1]).toLowerCase();
      return words.every((w) => hay.includes(w));
    });
  }

  function addTag(userTags, tag, unit) {
    const t = norm(tag), out = { ...userTags };
    if (!t) return out;
    const units = out[t] || [];
    out[t] = units.includes(unit) ? units : [...units, unit];
    return out;
  }

  function removeTag(userTags, tag, unit) {
    const out = { ...userTags };
    if (!out[tag]) return out;
    out[tag] = out[tag].filter((u) => u !== unit);
    if (!out[tag].length) delete out[tag];
    return out;
  }

  const api = { tagList, tagsOf, filter, addTag, removeTag };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.UnitBrowser = api;
})(typeof window !== 'undefined' ? window : globalThis);
