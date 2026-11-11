import { useState } from 'react'
import type { Findings } from './findings'

interface ValidChecksumFile {
  file: string
  sha256: string
  hashOf?: string
}

interface ValidReleaseChecksums {
  name: string
  files: ValidChecksumFile[]
}

function getUsableReleases(doc: Findings): ValidReleaseChecksums[] {
  if (!doc.data || typeof doc.data !== 'object' || !Array.isArray(doc.data.releases)) {
    return []
  }

  const usable: ValidReleaseChecksums[] = []
  for (const r of doc.data.releases) {
    if (!r || typeof r !== 'object' || typeof r.name !== 'string' || !Array.isArray(r.files)) {
      continue
    }
    const validFiles: ValidChecksumFile[] = []
    for (const f of r.files) {
      if (!f || typeof f !== 'object') continue
      if (typeof f.file !== 'string' || typeof f.sha256 !== 'string') continue
      const hashOf =
        typeof f.hash_of === 'string' && f.hash_of.trim().length > 0 ? f.hash_of : undefined
      validFiles.push({
        file: f.file,
        sha256: f.sha256,
        hashOf,
      })
    }
    if (validFiles.length > 0) {
      usable.push({
        name: r.name,
        files: validFiles,
      })
    }
  }

  return usable
}

export function ResultDetails({ doc }: { doc: Findings }) {
  const [downloadError, setDownloadError] = useState(false)

  const scope =
    typeof doc.x_readyset?.scope === 'string' && doc.x_readyset.scope.trim().length > 0
      ? doc.x_readyset.scope
      : null

  const engineVersion =
    typeof doc.x_readyset?.engine_version === 'string' &&
    doc.x_readyset.engine_version.trim().length > 0
      ? doc.x_readyset.engine_version
      : null

  const generatedAt =
    typeof doc.x_readyset?.generated_at === 'string' &&
    doc.x_readyset.generated_at.trim().length > 0
      ? doc.x_readyset.generated_at
      : null

  let metaLine: string | null = null
  if (engineVersion && generatedAt) {
    metaLine = `Engine version ${engineVersion} · generated ${generatedAt}`
  } else if (engineVersion) {
    metaLine = `Engine version ${engineVersion}`
  } else if (generatedAt) {
    metaLine = `generated ${generatedAt}`
  }

  const usableReleases = getUsableReleases(doc)

  const handleDownload = () => {
    try {
      setDownloadError(false)
      const jsonStr = JSON.stringify(doc, null, 2)
      const blob = new Blob([jsonStr], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'findings.json'
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch {
      setDownloadError(true)
    }
  }

  return (
    <section className="result-details-section" aria-label="About this result">
      <h2>About this result</h2>
      <div className="result-details-card">
        {scope && <p className="result-scope">{scope}</p>}

        {metaLine && <p className="result-meta muted">{metaLine}</p>}

        {usableReleases.length > 0 && (
          <details className="result-checksums">
            <summary className="checksums-summary">File checksums</summary>
            <div className="checksums-content">
              {usableReleases.map((rel, rIdx) => (
                <div key={`${rel.name}-${rIdx}`} className="release-checksums-group">
                  <h3 className="release-subheading">{rel.name}</h3>
                  <ul className="checksums-list">
                    {rel.files.map((f, fIdx) => {
                      const hashOfNote = f.hashOf
                        ? f.hashOf.startsWith('hash of')
                          ? f.hashOf
                          : `hash of ${f.hashOf}`
                        : null

                      return (
                        <li key={`${rel.name}-${f.file}-${fIdx}`} className="checksum-row">
                          <code className="checksum-file">{f.file}</code>
                          <code className="checksum-sha">{f.sha256}</code>
                          {hashOfNote && (
                            <span className="checksum-hashof muted">({hashOfNote})</span>
                          )}
                        </li>
                      )
                    })}
                  </ul>
                </div>
              ))}
            </div>
          </details>
        )}

        <div className="download-action">
          <button
            type="button"
            className="download-button"
            onClick={handleDownload}
          >
            Download findings.json
          </button>
          {downloadError && (
            <p className="download-error muted">The download could not be started.</p>
          )}
          <p className="validator-note muted">
            To check the format, run the organisers&apos; validator on this file (see docs/OUTPUT-CONTRACT.md).
          </p>
        </div>
      </div>
    </section>
  )
}

