import fs from 'node:fs';

import { mathjax } from 'mathjax-full/js/mathjax.js';
import { TeX } from 'mathjax-full/js/input/tex.js';
import { AllPackages } from 'mathjax-full/js/input/tex/AllPackages.js';
import { SVG } from 'mathjax-full/js/output/svg.js';
import { liteAdaptor } from 'mathjax-full/js/adaptors/liteAdaptor.js';
import { RegisterHTMLHandler } from 'mathjax-full/js/handlers/html.js';

const adaptor = liteAdaptor();
RegisterHTMLHandler(adaptor);

const tex = new TeX({
  packages: AllPackages,
  formatError: (_jax, error) => {
    throw error;
  },
});
const svg = new SVG({ fontCache: 'none' });
const html = mathjax.document('', { InputJax: tex, OutputJax: svg });

function normalizeErrorMessage(error) {
  return String(error?.message ?? error).replace(/\s+/g, ' ').trim();
}

function validateEntry(entry) {
  try {
    const node = html.convert(entry.value, { display: Boolean(entry.display) });
    adaptor.outerHTML(node);
    return { ok: true };
  } catch (error) {
    return {
      ok: false,
      field_name: entry.field_name,
      message: normalizeErrorMessage(error),
    };
  }
}

const rawInput = fs.readFileSync(0, 'utf8');
const payload = JSON.parse(rawInput);
const entries = Array.isArray(payload.entries) ? payload.entries : [];

for (const entry of entries) {
  const result = validateEntry(entry);
  if (!result.ok) {
    process.stdout.write(JSON.stringify(result));
    process.exit(0);
  }
}

process.stdout.write(JSON.stringify({ ok: true }));
