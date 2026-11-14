// The online demo. The page normally asks a small server on your own computer. Here those questions are answered in
// the browser: at first from answers the tool gave for the organisers' practice release, and, once a visitor chooses
// a before and an after release of their own, by the tool's own comparison engine running in this page (Pyodide).
// The files a visitor chooses are read into the browser's memory. They are not uploaded anywhere.
(() => {
  const realFetch = window.fetch.bind(window)
  const here = new URL('.', document.baseURI)
  const KEY = 'readyset-demo-reviews'
  const NEEDS_TOOL = 'Adding an analysis of your own works in the tool on your computer. Here you can compare your own ' +
    'before and after releases against the two built-in analyses.'
  const NO_PATH = 'A path only works in the tool on your computer. Here, choose the folder, all of its files, or a zip.'
  const NO_ENVELOPE = 'A sealed envelope is opened by the tool on your computer, with the organisers\' script. Here, choose the opened release\'s folder instead.'
  const RELEASE_FILES = ['clinical.tsv', 'survival.tsv', 'mutation_gene_level.tsv.gz', 'protein_rppa.tsv.gz', 'copy_number_gistic.tsv.gz', 'rna_hiseq.tsv.gz']
  let live = false                          // true once the visitor has chosen a release of their own
  const pause = () => new Promise(done => setTimeout(done, 60))        // let the page say "Comparing" before the work starts
  const flags = async () => ({ ...(await serverModel() ? { ai_understanding: "an AI model on the team's server" } : {}), voice: await serverVoice() })
  let reviews = {}
  try { reviews = JSON.parse(sessionStorage.getItem(KEY) || '{}') || {} } catch { reviews = {} }
  const keep = () => { try { sessionStorage.setItem(KEY, JSON.stringify(reviews)) } catch { /* kept for this page only */ } }

  const understood = {}                     // one reading per wording, so asking again never changes it
  let modelCheck
  const serverModel = () => (modelCheck ??= realFetch(new URL('api/understand', here)).then(r => (r.ok ? r.json() : {})).then(j => j.available === true).catch(() => false))
  let voiceCheck
  const serverVoice = () => (voiceCheck ??= realFetch(new URL('api/speak', here)).then(r => (r.ok ? r.json() : {})).then(j => j.available === true).catch(() => false))
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
    const both = () => { const now = JSON.parse(python_ready.runPython('readyset_browser.current()')); return now.trusted && now.new }
    if (live && both()) {
      const py = await toolCode()
      await pause()
      py.globals.set('wanted_text', String(wanted || ''))
      const got = JSON.parse(py.runPython('readyset_browser.findings(wanted_text)'))
      if (got.status !== 200) { const e = new Error(got.body.detail); e.status = got.status; throw e }
      return withReviews(got.body)
    }
    const name = recorded(wanted)
    if (!name) return null
    return withReviews(JSON.parse(await load(`data/findings-${name}.json`)))
  }

  const clean = v => String(v || '').trim().slice(0, 500)
  const api = async (url, init) => {
    const path = url.pathname.slice(url.pathname.indexOf('/api/'))
    const method = ((init && init.method) || 'GET').toUpperCase()
    if (path === '/api/health') return json(200, { status: 'ok', service: 'readyset-control-tower', demo: true })
    if (path === '/api/state') {
      if (live) return json(200, { ...JSON.parse((await toolCode()).runPython('readyset_browser.current()')), ...(await flags()) })
      return json(200, { ...JSON.parse(await load('data/state.json')), ...(await flags()) })
    }
    if (path === '/api/upload' && method === 'POST') {
      const name = (url.searchParams.get('name') || '').split('/').pop()
      const batch = url.searchParams.get('batch') || ''
      if (!/^[A-Za-z0-9-]{8,64}$/.test(batch) || !(RELEASE_FILES.includes(name) || name.toLowerCase().endsWith('.zip'))) {
        return json(400, { detail: `${name || 'that file'} is not one of the release's files or a zip` })
      }
      const py = await toolCode()
      const bytes = new Uint8Array(await new Response(init.body).arrayBuffer())
      py.FS.mkdirTree(`/staging/${batch}`)
      py.FS.writeFile(`/staging/${batch}/${RELEASE_FILES.includes(name) ? name : 'upload.zip'}`, bytes)
      return json(200, { saved: name })
    }
    if (path === '/api/release' && method === 'POST') {
      let body
      try { body = JSON.parse(typeof init.body === 'string' ? init.body : await new Response(init.body).text()) } catch { body = null }
      if (!body || !body.batch) return json(400, { detail: NO_PATH })
      const py = await toolCode()
      await pause()
      py.globals.set('use_text', JSON.stringify({ batch: String(body.batch), name: String(body.name || ''), trusted: body.as === 'trusted' }))
      const got = JSON.parse(py.runPython('_u = json.loads(use_text)\nreadyset_browser.use(_u["batch"], _u["name"], _u["trusted"])'))
      if (got.status !== 200) return json(got.status, got.body)
      live = true
      return json(200, { ...got.body, ...(await flags()) })
    }
    if (path === '/api/envelope') return json(400, { detail: NO_ENVELOPE })
    if (path === '/api/report' && method === 'POST') {
      let body
      try { body = JSON.parse(typeof init.body === 'string' ? init.body : await new Response(init.body).text()) } catch { body = {} }
      const doc = await findings(body.for)
      if (!doc) return json(400, { detail: NEEDS_TOOL })
      const py = await toolCode()
      py.globals.set('doc_text', JSON.stringify(doc))
      py.globals.set('by_text', JSON.stringify({ name: String(body.name || ''), role: String(body.role || '') }))
      return new Response(py.runPython('report.render(json.loads(doc_text), json.loads(by_text))'), { status: 200, headers: { 'Content-Type': 'text/html' } })
    }
    if (path === '/api/cells') {
      const fid = url.searchParams.get('finding') || ''
      if (live && python_ready && JSON.parse(python_ready.runPython('readyset_browser.current()')).new) {
        await pause()
        python_ready.globals.set('finding_text', fid)
        const got = JSON.parse(python_ready.runPython('readyset_browser.cells_of(finding_text)'))
        return json(got.status, got.body)
      }
      // The practice release's files are not kept on this page. Show the row that was recorded with its result.
      const doc = JSON.parse(await load('data/findings-all.json'))
      const w = ((doc.x_readyset || {}).witness || {})[fid]
      const f = (doc.findings || []).find(x => x.id === fid)
      if (!w || !f || !(w.values || []).length) return json(400, { detail: 'The practice release\'s files are not kept on this page, so there is nothing more to open for this change. Choose your own before and after releases and every cell can be opened.' })
      const samples = w.values.slice(0, 8)
      return json(200, { finding: fid, file: w.file, releases: w.releases, what_a_row_is: 'a row of the file (one measurement)',
        samples: samples.map(v => ({ id: v.sample, in_trusted: v.before !== null, in_new: v.after !== null })), more_samples: Math.max(0, w.values.length - 8),
        rows: [{ name: w.row, changed: true, cells: samples.map(v => ({ before: v.before, after: v.after, changed: v.before !== v.after })) }],
        rows_in_file: null, rows_that_differ: 1, rows_left_out: 0,
        note: 'The practice release\'s files are not kept on this page, so only the one row recorded with its result is shown. Choose your own before and after releases and every row of the file opens here.' })
    }
    if (path === '/api/speak' && method === 'POST') return realFetch(new URL('api/speak', here), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: init.body })
    if (path === '/api/history') return json(200, { comparisons: [] })
    if (path === '/api/findings') {
      try {
        const doc = await findings(url.searchParams.get('for'))
        return doc ? json(200, doc) : json(400, { detail: NEEDS_TOOL })
      } catch (e) { return json(e.status || 500, { detail: e.message || 'The comparison failed.' }) }
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
      const run = routed => {
        py.globals.set('ask_text', JSON.stringify({ q: body.q, name: body.name || '', role: body.role || '', check: Number(body.check) || 0, routed: routed || '' }))
        return py.runPython(`
_d = json.loads(doc_text); _a = json.loads(ask_text); _who = {"name": _a["name"], "role": _a["role"]}
_route = (lambda _text: _a["routed"]) if _a["routed"] else None
_r = ask.ask(_d, _a["q"], _who, _route)
if _a["check"]:
    _r["consistency"] = ask.consistency(_d, _a["q"], _a["check"], _who, _route)
json.dumps(_r)`)
      }
      let reply = run('')
      // The word list understood nothing and the person switched the model on: ask the server which fixed question
      // is meant. Only the question goes; the findings stay in this browser. The answer is still built here.
      if (body.ai === true && JSON.parse(reply).intent === null) {
        const key = body.q.trim().toLowerCase()
        if (!(key in understood)) {
          try {
            const r = await realFetch(new URL('api/understand', here), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ q: body.q.slice(0, 500) }) })
            if (r.ok) understood[key] = (await r.json()).intent || ''
          } catch { /* no server: it stays "I cannot answer that" */ }
        }
        if (understood[key]) reply = run(understood[key])
      }
      return new Response(reply, { status: 200, headers: { 'Content-Type': 'application/json' } })
    }
    return json(400, { detail: NEEDS_TOOL })
  }

  window.fetch = (input, init) => {
    let url
    try { url = new URL(typeof input === 'string' ? input : input.url, location.href) } catch { return realFetch(input, init) }
    if (url.origin !== location.origin || !url.pathname.includes('/api/')) return realFetch(input, init)
    return api(url, init).catch(() => json(500, { detail: 'The page could not do that just now. Reload it and try again.' }))
  }

  // ---- the tool's own Python (the report writer and the assistant), run here in the browser ------------------------
  let python, python_ready                  // python_ready is set once the engine has loaded; `live` implies it has
  const toolCode = () => (python ??= (async () => {
    await new Promise((ok, fail) => {
      const s = document.createElement('script')
      s.src = 'https://cdn.jsdelivr.net/pyodide/v0.26.4/full/pyodide.js'
      s.onload = ok; s.onerror = () => fail(new Error('could not load'))
      document.head.appendChild(s)
    })
    const py = python_ready = await window.loadPyodide({ indexURL: 'https://cdn.jsdelivr.net/pyodide/v0.26.4/full/' })
    py.FS.mkdirTree('/home/pyodide/control_tower')
    const names = JSON.parse(await load('py/manifest.json'))
    const sources = await Promise.all(names.map(name => load('py/control_tower/' + name)))
    names.forEach((name, i) => py.FS.writeFile('/home/pyodide/control_tower/' + name, sources[i]))
    py.FS.writeFile('/home/pyodide/readyset_browser.py', await load('py/readyset_browser.py'))
    py.FS.mkdirTree('/staging')
    py.runPython('import json\nfrom control_tower import report, ask, changelog\nimport readyset_browser')
    return py
  })().catch(e => { python = undefined; throw e }))

  const save = (text, name, type) => {
    const href = URL.createObjectURL(new Blob([text], { type }))
    const a = Object.assign(document.createElement('a'), { href, download: name })
    document.body.appendChild(a); a.click(); a.remove()
    setTimeout(() => URL.revokeObjectURL(href), 10000)
  }

  let busy = false
  document.addEventListener('click', async event => {
    const link = event.target && event.target.closest ? event.target.closest('a[href*="/api/report"], a[href*="/api/changelog"]') : null
    if (!link) return
    event.preventDefault()
    if (busy) return
    busy = true
    const target = new URL(link.getAttribute('href'), location.href)
    const wanted = target.searchParams.get('for')
    const asChangelog = target.pathname.includes('/api/changelog')
    const label = link.textContent
    link.textContent = asChangelog ? 'Writing the change log…' : 'Writing the report…'
    try {
      const doc = await findings(wanted)
      if (asChangelog) {
        const py = await toolCode()
        py.globals.set('doc_text', JSON.stringify(doc))
        save(py.runPython('changelog.to_csv(json.loads(doc_text))'), 'change-log.csv', 'text/csv')
      } else {
        let html
        try {
          const py = await toolCode()
          py.globals.set('doc_text', JSON.stringify(doc))
          html = py.runPython('report.render(json.loads(doc_text))')
        } catch {
          html = await load(`data/report-${recorded(wanted) || 'all'}.html`)      // the report as recorded, without sign-offs
        }
        save(html, 'audit-report.html', 'text/html')
      }
    } catch { /* the page stays as it was */ } finally {
      busy = false
      if (link.isConnected) link.textContent = label
    }
  }, true)

  // ---- say what this page is ---------------------------------------------------------------------------------------
  const banner = () => {
    const bar = document.createElement('div')
    bar.setAttribute('role', 'note')
    bar.style.cssText = 'background:#3B2F8F;color:#fff;font:500 14px/1.45 system-ui,-apple-system,Segoe UI,sans-serif;padding:10px 16px;text-align:center'
    bar.innerHTML = 'Online demo, showing the organisers’ practice release. To compare your own, press “Compare a different release” and choose a before and an after: ' +
      'the comparison runs in your browser and your files are not uploaded. Sign-offs stay in this browser. ' +
      '<a style="color:#fff;font-weight:700" href="https://github.com/a7ussein/readyset-control-tower#start-here-see-it-running-in-one-minute">Get the tool</a>'
    document.body.insertBefore(bar, document.body.firstChild)
  }
  if (document.body) banner(); else document.addEventListener('DOMContentLoaded', banner)
  // Start the tool's Python quietly once the page has settled, so the first question is answered without a wait.
  addEventListener('load', () => setTimeout(() => { toolCode().catch(() => {}) }, 1500))
})()
