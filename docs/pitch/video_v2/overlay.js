// Injected into every page while recording: a visible cursor with click ripples, an animated chapter title and
// timed subtitles. record.mjs calls window.__ss.start({ chapter, n, subs }) when a scene starts.
;(() => {
  if (window.__ss) return
  const css = `
  #ss-layer{position:fixed;inset:0;pointer-events:none;z-index:2147483647;font-family:'Geist Variable','Geist',-apple-system,'Segoe UI',Arial,sans-serif}
  #ss-cursor{position:absolute;left:0;top:0;width:30px;height:30px;transform:translate(-4px,-3px);opacity:0;transition:opacity .3s;filter:drop-shadow(0 3px 6px rgba(0,0,0,.35))}
  .ss-ripple{position:absolute;width:18px;height:18px;margin:-9px 0 0 -9px;border-radius:50%;border:3px solid #1A73E8;animation:ssrip .6s ease-out forwards}
  @keyframes ssrip{from{transform:scale(.3);opacity:1}to{transform:scale(3.2);opacity:0}}
  #ss-chapter{position:absolute;left:36px;bottom:112px;display:flex;align-items:center;gap:16px;padding:14px 26px 14px 18px;border-radius:18px;
    background:rgba(255,255,255,.96);box-shadow:0 12px 40px rgba(8,18,38,.28);transform:translateX(-120%);opacity:0;transition:transform .7s cubic-bezier(.2,.9,.2,1),opacity .5s}
  #ss-chapter.on{transform:none;opacity:1}
  #ss-chapter .n{font-size:15px;font-weight:700;color:#fff;background:#1A73E8;border-radius:10px;padding:6px 10px;letter-spacing:.04em}
  #ss-chapter .t{font-size:24px;font-weight:700;color:#202124}
  #ss-chapter .d{display:flex;gap:5px}#ss-chapter .d i{width:9px;height:9px;border-radius:50%;display:block}
  #ss-sub{position:absolute;left:50%;bottom:30px;transform:translate(-50%,12px);max-width:74%;padding:12px 22px;border-radius:14px;text-align:center;
    background:rgba(8,18,38,.82);color:#fff;font-size:25px;line-height:1.3;font-weight:500;opacity:0;transition:opacity .25s,transform .25s}
  #ss-sub.on{opacity:1;transform:translate(-50%,0)}`
  const mount = () => {
    if (document.getElementById('ss-layer')) return
    const st = document.createElement('style'); st.textContent = css; document.head.appendChild(st)
    const L = document.createElement('div'); L.id = 'ss-layer'
    L.innerHTML = `<svg id="ss-cursor" viewBox="0 0 24 24"><path d="M4 2l15 9.5-6.6 1.3 3.9 7.4-2.9 1.5-3.9-7.5L4 19z" fill="#fff" stroke="#202124" stroke-width="1.4" stroke-linejoin="round"/></svg>
      <div id="ss-chapter"><span class="d"><i style="background:#1A73E8"></i><i style="background:#EA4335"></i><i style="background:#FBBC04"></i><i style="background:#34A853"></i></span><span class="n"></span><span class="t"></span></div>
      <div id="ss-sub"></div>`
    document.body.appendChild(L)
    const cur = L.querySelector('#ss-cursor')
    if (location.protocol === 'file:') cur.style.display = 'none' // no cursor on the motion cards
    addEventListener('mousemove', e => { cur.style.left = e.clientX + 'px'; cur.style.top = e.clientY + 'px'; cur.style.opacity = 1 }, true)
    addEventListener('mousedown', e => { const r = document.createElement('div'); r.className = 'ss-ripple'; r.style.left = e.clientX + 'px'; r.style.top = e.clientY + 'px'; L.appendChild(r); setTimeout(() => r.remove(), 700) }, true)
    // The local build shows a "Live mode" dispatch banner; the demo runs as a dry run, so keep it off screen.
    setInterval(() => document.querySelectorAll('main div, main p').forEach(el => {
      if (el.childElementCount < 6 && /^\s*Live mode/.test(el.textContent || '') && el.offsetHeight < 120) el.style.display = 'none'
    }), 200)
  }
  if (document.readyState === 'loading') addEventListener('DOMContentLoaded', mount); else mount()
  window.__ss = {
    start({ chapter, n, subs }) {
      mount()
      const ch = document.getElementById('ss-chapter'), sub = document.getElementById('ss-sub')
      if (chapter) {
        ch.querySelector('.n').textContent = n; ch.querySelector('.t').textContent = chapter
        setTimeout(() => ch.classList.add('on'), 250); setTimeout(() => ch.classList.remove('on'), 4200)
      }
      for (const s of subs || []) {
        setTimeout(() => { sub.textContent = s.text; sub.classList.add('on') }, s.t0 * 1000)
        setTimeout(() => { if (sub.textContent === s.text) sub.classList.remove('on') }, s.t1 * 1000 - 80)
      }
      document.body.classList.add('go')
    },
  }
})()
