// ==UserScript==
// @name         Lost in Laminate zhCN Translation
// @namespace    mailto:aboutmetal@sina.com
// @version      1.0.0
// @description  Lost in Laminate 8.0 GPT 汉化 + 人工润色，by aboutmetal (zacmerkl)
// @match        https://iconoclast.neocities.org/Lost%20in%20Laminate%208.0
// @run-at       document-start
// @grant        GM_getResourceText
// @grant        GM_addStyle
// @grant        GM_xmlhttpRequest
// @grant        GM_setValue
// @grant        GM_getValue
// @grant        GM_deleteValue
// @connect      raw.githubusercontent.com
// @connect      localhost
// @resource     translations  https://raw.githubusercontent.com/zacmerkl/lil-cn/main/LiL_cn.json
// ==/UserScript==

/* ------------------------------------------------------------------
 * 样式：黑底主题 + 中文排版增强
 * ---------------------------------------------------------------- */
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
  tw-align {
        max-width: 65% !important;
  }
`);

(function () {
  'use strict';

  /* ----------------------------------------------------------------
   * 配置区：根据需要修改
   * ---------------------------------------------------------------- */
  const REMOTE_URL      = 'https://raw.githubusercontent.com/zacmerkl/lil-cn/main/LiL_cn.json';
  const CACHE_KEY_DICT  = 'LiL_CN_dict';   // 缓存译文JSON字符串
  const CACHE_KEY_HASH  = 'LiL_CN_hash';   // 缓存哈希
  const ASK_BEFORE_RELOAD = true;          // true: 发现新译文时弹窗询问; false: 无提示直接刷新
  const REMOTE_TIMEOUT_MS = 15000;         // 远程请求超时

  /* ----------------------------------------------------------------
   * 加载译文：优先缓存 -> @resource -> 空
   * ---------------------------------------------------------------- */
  let dict = {};
  let sourceTag = 'cache';

  try {
    const cachedStr = GM_getValue(CACHE_KEY_DICT, null);
    if (cachedStr) {
      dict = JSON.parse(cachedStr);
    } else {
      sourceTag = 'resource';
      dict = JSON.parse(GM_getResourceText('translations') || '{}');
    }
  } catch (e) {
    console.error('[LiL-CN] 译文加载失败:', e);
    dict = {};
  }

  /* ----------------------------------------------------------------
   * 翻译函数
   * ---------------------------------------------------------------- */
  function normalize(str) { return String(str).replace(/\r\n?/g, '\n'); }

  function translateOne(el) {
    if (!el || el.nodeType !== 1) return;
    const name = el.getAttribute('name');
    if (!name) return;
    const v = dict[name];
    if (v == null) return;         // 未翻译 -> 保留英文
    const cn = normalize(v);
    // 全量覆盖，避免“拼接残留”
    while (el.firstChild) el.removeChild(el.firstChild);
    el.appendChild(document.createTextNode(cn));
  }

  function translateAllExisting() {
    document.querySelectorAll('tw-passagedata[name]').forEach(translateOne);
  }

  /* ----------------------------------------------------------------
   * 全局 Mutation 监听：捕捉后续解析出的passage
   * ---------------------------------------------------------------- */
  const mo = new MutationObserver(muts => {
    for (const mu of muts) {
      for (const n of mu.addedNodes) {
        if (n.nodeType === 1) {
          if (n.matches?.('tw-passagedata[name]')) {
            translateOne(n);
          } else {
            n.querySelectorAll?.('tw-passagedata[name]').forEach(translateOne);
          }
        }
      }
    }
  });
  mo.observe(document.documentElement, { childList: true, subtree: true });

  /* ----------------------------------------------------------------
   * 多重兜底扫描：初始、DOMContentLoaded、load、短轮询
   * ---------------------------------------------------------------- */
  translateAllExisting();  // 初始
  document.addEventListener('DOMContentLoaded', translateAllExisting, { once: true });
  window.addEventListener('load', translateAllExisting, { once: true });

  let pollCount = 0;
  const pollMax = 10;
  const pollTimer = setInterval(() => {
    translateAllExisting();
    if (++pollCount >= pollMax) clearInterval(pollTimer);
  }, 100);

  /* ----------------------------------------------------------------
   * 后台检查GitHub远程版本 -> 缓存 -> 刷新
   * ---------------------------------------------------------------- */
  checkRemoteAndCache();

  function checkRemoteAndCache() {
    GM_xmlhttpRequest({
      method: 'GET',
      url: REMOTE_URL + '?_=' + Date.now(),  // cache-bust
      timeout: REMOTE_TIMEOUT_MS,
      onload: (r) => {
        if (r.status !== 200) {
          console.warn('[LiL-CN] 远程译文请求失败:', r.status, r.statusText);
          return;
        }
        const txt = r.responseText;
        let remoteDict;
        try {
          remoteDict = JSON.parse(txt);
        } catch (e) {
          console.warn('[LiL-CN] 远程译文解析失败:', e);
          return;
        }
        const remoteHash = simpleHash(txt);
        const localHash  = GM_getValue(CACHE_KEY_HASH, null);

        if (remoteHash !== localHash) {
          console.log('[LiL-CN] 检测到新译文，写缓存…');
          GM_setValue(CACHE_KEY_DICT, txt);
          GM_setValue(CACHE_KEY_HASH, remoteHash);

          // 刷新策略
          if (ASK_BEFORE_RELOAD) {
            // 如果页面隐藏（后台标签），直接刷新；否则询问
            if (document.visibilityState === 'hidden' || confirm('发现新版中文译文，刷新以应用？')) {
              location.reload();
            }
          } else {
            location.reload();
          }
        } else {
          // console.log('[LiL-CN] 译文已是最新。');
        }
      },
      onerror: () => {
        console.warn('[LiL-CN] 远程译文请求错误。');
      }
    });
  }

  /* ----------------------------------------------------------------
   * 简易哈希（32bit滚动，够用）：比较译文是否更新
   * ---------------------------------------------------------------- */
  function simpleHash(str) {
    let h = 0;
    for (let i = 0; i < str.length; i++) {
      h = (h * 31 + str.charCodeAt(i)) | 0;
    }
    return (h >>> 0).toString(16);
  }

})();