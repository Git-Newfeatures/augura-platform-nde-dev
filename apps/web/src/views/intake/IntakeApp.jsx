import { useState } from 'react'
import IntakeUpload from './IntakeUpload'
import IntakeMapping from './IntakeMapping'
import IntakeDQ from './IntakeDQ'

const STEPS = ['upload', 'mapping', 'dq']

export default function IntakeApp() {
  const [step, setStep] = useState('upload')
  const [datasetId, setDatasetId] = useState(null)

  return (
    <div className="mx-auto max-w-3xl p-6">
      <h1 className="mb-1 text-xl font-semibold">Data intake</h1>
      <p className="mb-6 text-sm text-muted-foreground">Upload → map to concepts → data-quality report.</p>
      <ol className="mb-6 flex gap-2 text-xs">
        {STEPS.map(s => (
          <li key={s} className={`rounded-full px-3 py-1 ${step === s ? 'bg-[#1A6E7A] text-white' : 'bg-muted text-muted-foreground'}`}>{s}</li>
        ))}
      </ol>
      {step === 'upload' && (
        <IntakeUpload onUploaded={(r) => { setDatasetId(r.dataset.id); setStep('mapping') }} />
      )}
      {step === 'mapping' && datasetId && (
        <IntakeMapping datasetId={datasetId} onNext={() => setStep('dq')} />
      )}
      {step === 'dq' && datasetId && <IntakeDQ datasetId={datasetId} />}
    </div>
  )
}
