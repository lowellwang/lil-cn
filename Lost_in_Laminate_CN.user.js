// ==UserScript==
// @name         Lost in Laminate zhCN Translation (10.0f)
// @namespace    mailto:aboutmetal@sina.com
// @version      1.1.0
// @description  Lost in Laminate 8.0 GPT 汉化 + 人工润色，by aboutmetal (zacmerkl)
// @match        https://iconoclast.neocities.org/Lost%20in%20Laminate%2010.0f/Lost%20in%20Laminate%2010.0f
// @run-at       document-start
// @grant        GM_getResourceText
// @grant        GM_addStyle
// @grant        GM_xmlhttpRequest
// @grant        GM_setValue
// @grant        GM_getValue
// @connect      raw.githubusercontent.com
// @updateURL    https://raw.githubusercontent.com/zacmerkl/lil-cn/main/Lost_in_Laminate_CN.user.js
// @downloadURL  https://raw.githubusercontent.com/zacmerkl/lil-cn/main/Lost_in_Laminate_CN.user.js
// @supportURL   https://github.com/zacmerkl/lil-cn/issues
// @homepage     https://github.com/zacmerkl/lil-cn
// @resource     translations_init  https://raw.githubusercontent.com/zacmerkl/lil-cn/main/LiL-10.0f-zhCN.json
// ==/UserScript==

/* -------- CONFIG -------- */
const REMOTE_URL        = 'https://raw.githubusercontent.com/zacmerkl/lil-cn/main/LiL-10.0f-zhCN.json';
const CACHE_KEY_DICT    = 'LiL-10.0f-zhCN_dict';
const CACHE_KEY_HASH    = 'LiL-10.0f-zhCN_hash';
const ASK_BEFORE_RELOAD = true;
const REMOTE_TIMEOUT_MS = 15000;
/* ------------------------ */

/* -------- 排版增强 ------- */
GM_addStyle(`
  tw-story tw-passage {
    line-height: 1.8em !important;
    font-size: 14pt;
    font-family: "Open Sans", sans-serif !important;
    letter-spacing: 0.01em;
    color: #E0E0E0;
  }
  tw-story tw-passage p {
    margin: 1em 0 1em 0 !important;
  }
  tw-story tw-passage b,
  tw-story tw-passage strong {
    font-size: 16pt !important;
    letter-spacing: 0.05em !important;
    color: #FFFFFF;
  }
  tw-story tw-passage em,
  tw-story tw-passage i {
    letter-spacing: 0.05em !important;
    border-bottom: 1px dotted currentColor !important;
    padding: 0 1px !important;
  }
`);
/* ------------------------ */

(async function () {
  'use strict';

  /* ------ load from cache / embedded resource ------ */
  let translations = {};
  try {
    const cached = GM_getValue(CACHE_KEY_DICT, null);
    if (cached) translations = JSON.parse(cached);
    else {
      const embedded = GM_getResourceText('translations_init');
      if (embedded) translations = JSON.parse(embedded);
    }
  } catch (e) { console.error('[LiL‑CN] Initial translation load failed', e); }

  /* ------ apply to already present nodes ------ */
  const normalize = s => String(s).replace(/\r\n?/g, '\n');
  const applyToNode = node => {
    const name = node.getAttribute?.('name');
    if (!name || !(name in translations)) return;
    const newText = translations[name];
    if (normalize(node.textContent) !== normalize(newText)) node.textContent = newText;
  };
  const applyAll = () => document.querySelectorAll('tw-passagedata[name]')
      .forEach(applyToNode);

  /* apply early & observe */
  applyAll();
  const ob = new MutationObserver(muts => muts.forEach(mu => mu.addedNodes.forEach(applyToNode)));
  ob.observe(document.documentElement, {childList:true, subtree:true});
  window.addEventListener('load', applyAll, {once:true});

  /* ------ ETag‑based update ------ */
  try {
    const {json,newEtag} = await fetchWithETag(RAW_TRANSLATION_URL,
      GM_getValue(CACHE_KEY_ETAG, ''));
    if (json) {
      const newDict = JSON.parse(json);
      const changed = JSON.stringify(newDict) !== JSON.stringify(translations);
      if (changed) {
        GM_setValue(CACHE_KEY_DICT, json);
        translations = newDict;
        applyAll();
        if (ASK_ON_UPDATE && document.readyState==='complete') {
          if (confirm('检测到翻译更新，是否刷新页面应用？')) location.reload();
        }
      }
      if (newEtag) GM_setValue(CACHE_KEY_ETAG, newEtag);
    }
  } catch (e) {
    console.warn('[LiL‑CN] Translation update check failed:', e);
  }
})();

/* ===== helper: fetch with ETag ===== */
function fetchWithETag(url, etag) {
  return new Promise((resolve, reject) => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), FETCH_TIMEOUT);

    fetch(url, {
      method: 'GET',
      cache: 'no-cache',
      headers: etag ? {'If-None-Match': etag} : {},
      signal: controller.signal
    })
    .then(async resp => {
      clearTimeout(timer);
      if (resp.status === 304) {
        resolve({json: null, newEtag: etag}); // not modified
      } else if (resp.ok) {
        const txt = await resp.text();
        resolve({json: txt, newEtag: resp.headers.get('etag') || ''});
      } else {
        reject(new Error('HTTP '+resp.status));
      }
    })
    .catch(reject);
  });
}
