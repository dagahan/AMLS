import fs from 'node:fs';

import { liteAdaptor } from 'mathjax-full/js/adaptors/liteAdaptor.js';
import { RegisterHTMLHandler } from 'mathjax-full/js/handlers/html.js';
import { TeX } from 'mathjax-full/js/input/tex.js';
import { AllPackages } from 'mathjax-full/js/input/tex/AllPackages.js';
import { mathjax } from 'mathjax-full/js/mathjax.js';
import { SVG } from 'mathjax-full/js/output/svg.js';


/**
 * @typedef {Object} LatexValidationEntry
 * @property {string} field_name
 * @property {string} value
 * @property {boolean} display
 */


/**
 * @typedef {Object} LatexValidationResult
 * @property {boolean} ok
 * @property {string} [field_name]
 * @property {string} [message]
 */


const ADAPTOR = liteAdaptor();
RegisterHTMLHandler(ADAPTOR);


const TEX_INPUT = new TeX({
  packages: AllPackages,
  formatError: (_jax, error) => {
    throw error;
  },
});


const SVG_OUTPUT = new SVG({ fontCache: 'none' });


const MATHJAX_DOCUMENT = mathjax.document('', {
  InputJax: TEX_INPUT,
  OutputJax: SVG_OUTPUT,
});


/**
 * @param {any} error
 * @returns {string}
 */
function extractCleanErrorMessage(error) {
  return String(error?.message ?? error).replace(/\s+/g, ' ').trim();
}


/**
 * @param {LatexValidationEntry} entry
 * @returns {LatexValidationResult}
 */
function checkLatexStructure(entry) {
  try {
    const node = MATHJAX_DOCUMENT.convert(entry.value, {
      display: Boolean(entry.display),
    });
    ADAPTOR.outerHTML(node);

    return { ok: true };
  } catch (error) {
    return {
      ok: false,
      field_name: entry.field_name,
      message: extractCleanErrorMessage(error),
    };
  }
}


/**
 * @returns {void}
 */
function executeValidationSequence() {
  const rawInput = fs.readFileSync(0, 'utf8');
  const validationRequest = JSON.parse(rawInput);
  const latexContentList = Array.isArray(validationRequest.entries)
    ? validationRequest.entries
    : [];

  for (const entry of latexContentList) {
    const result = checkLatexStructure(entry);

    if (!result.ok) {
      process.stdout.write(JSON.stringify(result));
      process.exit(0);
    }
  }

  process.stdout.write(JSON.stringify({ ok: true }));
}


executeValidationSequence();
