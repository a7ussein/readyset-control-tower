// The online demo. The page normally asks a small server on your own computer; here those questions are answered
// from answers the tool gave when it compared the organisers' practice release. Nothing is uploaded anywhere.
(() => {
  const realFetch = window.fetch.bind(window)
  const here = new URL('.', document.baseURI)
  const KEY = 'readyset-demo-reviews'
  const NEEDS_TOOL = 'This online demo shows one comparison the tool has already run. To compare your own release or add ' +
    'your own analysis, download the tool: it runs on your computer and nothing is uploaded.'
  let reviews = {}
  try { reviews = JSON.parse(sessionStorage.getItem(KEY) || '{}') || {} } catch { reviews = {} }
  const keep = () => { try { sessionStorage.setItem(KEY, JSON.stringify(reviews)) } catch { /* kept for this page only */ } }

  const texts = {}
  const load = name => (texts[name] ??= realFetch(new URL(name, here)).then(r => { if (!r.ok) throw new Error(name); return r.text() }))
  const json = (status, body) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

  // Which recorded answer fits the question asked: both analyses, or one of them.
  const recorded = wanted => {
    const ids = [...new Set(String(wanted || '').split(',').map(s => s.trim()).filter(Boolean))].sort()
    if (ids.length === 0 || ids.join(',') === 'A1,A2') return 'all'
    if (ids.length === 1 && (ids[0] === 'A1' || ids[0] === 'A2')) return ids[0]
    return null
  }

  // The same thing the tool's server does with a saved review: the finding stops waiting, and the decision on its
  // fix is written into the shared `decisions` field.
  const withReviews = doc => {
    const x = doc.x_readyset || (doc.x_readyset = {})
    const keys = x.review_keys || {}
    const releases = (doc.data && doc.data.releases) || []
    const release = releases.length ? String(releases[releases.length - 1].name) : ''
    x.reviews = Object.entries(keys).filter(([, k]) => reviews[k]).map(([fid, k]) => ({ ...reviews[k], finding: fid, release }))
    let decisions = Array.isArray(doc.decisions) ? doc.decisions.filter(d => d && typeof d === 'object') : []
    for (const f of doc.findings || []) {
      const r = reviews[keys[f.id]]
      if (!r) continue
      f.needs_human_review = false
      const who = r.reviewer || 'a reviewer who gave no name'
      let said = r.status === 'confirmed' ? 'Confirmed as a real problem' : 'Dismissed as an expected change'
      if (r.status === 'confirmed' && r.fix === 'approved') said += ', and the suggested fix approved,'
      const reason = `${said} by ${who}` + (r.note ? `: ${r.note}` : '.')
      const verdict = r.status === 'dismissed' ? 'reject' : (r.fix === 'approved' ? 'approve' : null)
      for (const repair of Array.isArray(doc.repairs) ? doc.repairs : []) {
        if (verdict && repair && (repair.addresses || []).includes(f.id) && repair.id) {
          decisions = decisions.filter(d => d.repair_id !== repair.id)
          decisions.push({ repair_id: repair.id, decision: verdict, reason, reviewer_role: r.role || 'not stated', original_preserved: true })
        }
      }
    }
    if (decisions.length) doc.decisions = decisions
    return doc
  }

  const findings = async wanted => {
    const name = recorded(wanted)
    if (!name) return null
    return withReviews(JSON.parse(await load(`data/findings-${name}.json`)))
  }

  const clean = v => String(v || '').trim().slice(0, 500)
  const api = async (url, init) => {
    const path = url.pathname.slice(url.pathname.indexOf('/api/'))
    const method = ((init && init.method) || 'GET').toUpperCase()
    if (path === '/api/health') return json(200, { status: 'ok', service: 'readyset-control-tower', demo: true })
    if (path === '/api/state') return json(200, JSON.parse(await load('data/state.json')))
    if (path === '/api/findings') {
      const doc = await findings(url.searchParams.get('for'))
      return doc ? json(200, doc) : json(400, { detail: NEEDS_TOOL })
    }
    if (path === '/api/reviews' && method === 'POST') {
      let body
      try { body = JSON.parse(typeof init.body === 'string' ? init.body : await new Response(init.body).text()) } catch { body = null }
      if (!body || typeof body.key !== 'string' || !body.key || !['confirmed', 'dismissed', 'cleared'].includes(body.status)) {
        return json(400, { detail: 'a review needs a key and a status of confirmed, dismissed or cleared' })
      }
      if (body.status === 'cleared') delete reviews[body.key]
      else {
        reviews[body.key] = { key: body.key, status: body.status, fix: body.fix === 'approved' && body.status === 'confirmed' ? 'approved' : '',
          reviewer: clean(body.reviewer), role: clean(body.role), note: clean(body.note), at: new Date().toISOString().slice(0, 19) + '+00:00' }
      }
      keep()
      return json(200, { saved: body.status !== 'cleared', kept_in: 'this browser only' })
    }
    if (path === '/api/ask' && method === 'POST') {
      let body
      try { body = JSON.parse(typeof init.body === 'string' ? init.body : await new Response(init.body).text()) } catch { body = null }
      if (!body || typeof body.q !== 'string' || !body.q.trim() || body.q.length > 500) return json(400, { detail: 'ask a question of up to 500 characters' })
      const doc = await findings(body.for)
      if (!doc) return json(400, { detail: NEEDS_TOOL })
      let py
      try { py = await toolCode() } catch { return json(500, { detail: 'The assistant could not start in this browser. Reload the page and try again.' }) }
      py.globals.set('doc_text', JSON.stringify(doc))
      py.globals.set('ask_text', JSON.stringify({ q: body.q, name: body.name || '', role: body.role || '', check: Number(body.check) || 0 }))
      const reply = py.runPython(`
_d = json.loads(doc_text); _a = json.loads(ask_text); _who = {"name": _a["name"], "role": _a["role"]}
_r = ask.ask(_d, _a["q"], _who)
if _a["check"]:
    _r["consistency"] = ask.consistency(_d, _a["q"], _a["check"], _who)
json.dumps(_r)`)
      return new Response(reply, { status: 200, headers: { 'Content-Type': 'application/json' } })
    }
    return json(400, { detail: NEEDS_TOOL })
  }

  window.fetch = (input, init) => {
    let url
    try { url = new URL(typeof input === 'string' ? input : input.url, location.href) } catch { return realFetch(input, init) }
    if (url.origin !== location.origin || !url.pathname.includes('/api/')) return realFetch(input, init)
    return api(url, init).catch(() => json(500, { detail: 'The demo could not load its recorded answer. Reload the page.' }))
  }

  // ---- the tool's own Python (the report writer and the assistant), run here in the browser ------------------------
  let python
  const toolCode = () => (python ??= (async () => {
    await new Promise((ok, fail) => {
      const s = document.createElement('script')
      s.src = 'https://cdn.jsdelivr.net/pyodide/v0.26.4/full/pyodide.js'
      s.onload = ok; s.onerror = () => fail(new Error('could not load'))
      document.head.appendChild(s)
    })
    const py = await window.loadPyodide({ indexURL: 'https://cdn.jsdelivr.net/pyodide/v0.26.4/full/' })
    py.FS.mkdirTree('/home/pyodide/control_tower')
    for (const name of ['__init__.py', 'report.py', 'ask.py']) py.FS.writeFile('/home/pyodide/control_tower/' + name, await load('py/control_tower/' + name))
    py.runPython('import json\nfrom control_tower import report, ask')
    return py
  })().catch(e => { python = undefined; throw e }))

  const save = (html, name) => {
    const href = URL.createObjectURL(new Blob([html], { type: 'text/html' }))
    const a = Object.assign(document.createElement('a'), { href, download: name })
    document.body.appendChild(a); a.click(); a.remove()
    setTimeout(() => URL.revokeObjectURL(href), 10000)
  }

  let busy = false
  document.addEventListener('click', async event => {
    const link = event.target && event.target.closest ? event.target.closest('a[href*="/api/report"]') : null
    if (!link) return
    event.preventDefault()
    if (busy) return
    busy = true
    const wanted = new URL(link.getAttribute('href'), location.href).searchParams.get('for')
    const label = link.textContent
    link.textContent = 'Writing the report…'
    try {
      const doc = await findings(wanted)
      let html
      try {
        const py = await toolCode()
        py.globals.set('doc_text', JSON.stringify(doc))
        html = py.runPython('report.render(json.loads(doc_text))')
      } catch {
        html = await load(`data/report-${recorded(wanted) || 'all'}.html`)      // the report as recorded, without sign-offs
      }
      save(html, 'audit-report.html')
    } finally {
      busy = false
      if (link.isConnected) link.textContent = label
    }
  }, true)

  // ---- say what this page is ---------------------------------------------------------------------------------------
  const banner = () => {
    const bar = document.createElement('div')
    bar.setAttribute('role', 'note')
    bar.style.cssText = 'background:#3B2F8F;color:#fff;font:500 14px/1.45 system-ui,-apple-system,Segoe UI,sans-serif;padding:10px 16px;text-align:center'
    bar.innerHTML = 'Online demo. This is the organisers’ practice release, as the tool compared it. Change the question, open a finding, ' +
      'sign it off, ask it a question, download the report. Your sign-offs stay in this browser. With your own data the tool runs on your computer and uploads nothing. ' +
      '<a style="color:#fff;font-weight:700" href="https://github.com/a7ussein/readyset-control-tower#start-here-see-it-running-in-one-minute">Get the tool</a>'
    document.body.insertBefore(bar, document.body.firstChild)
  }
  if (document.body) banner(); else document.addEventListener('DOMContentLoaded', banner)
  // Start the tool's Python quietly once the page has settled, so the first question is answered without a wait.
  addEventListener('load', () => setTimeout(() => { toolCode().catch(() => {}) }, 1500))
})()
