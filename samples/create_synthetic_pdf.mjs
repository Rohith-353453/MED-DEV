import { writeFile } from 'node:fs/promises'

const lines = [
  'CAREFOLIO DEMO FIXTURE V1',
  'SYNTHETIC SAMPLE - NOT A REAL PATIENT OR CLINICAL REPORT',
  'Carefolio Community Diagnostics',
  'LABORATORY REPORT',
  'Patient: Synthetic Demo',
  'Report date: 2026-01-15',
  '',
  'Test             Result       Reference range       Source flag',
  'HGB              12.8 g/dL    12.0-16.0             N',
  'Platelets        420 x10^3/uL 150-400               H',
  '',
  'All names and values in this document are fictional training data.',
  'This sample does not describe a real person or provide medical advice.',
]

const escapePdf = (value) => value.replaceAll('\\', '\\\\').replaceAll('(', '\\(').replaceAll(')', '\\)')
const text = ['BT', '/F1 10 Tf', '55 750 Td', '15 TL']
for (const line of lines) text.push(`(${escapePdf(line)}) Tj`, 'T*')
text.push('ET')
const stream = Buffer.from(text.join('\n'), 'ascii')
const objects = [
  '<< /Type /Catalog /Pages 2 0 R >>',
  '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
  '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
  '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
  `<< /Length ${stream.length} >>\nstream\n${stream.toString('ascii')}\nendstream`,
]

const chunks = [Buffer.from('%PDF-1.4\n', 'ascii')]
const offsets = [0]
let offset = chunks[0].length
objects.forEach((body, index) => {
  offsets.push(offset)
  const object = Buffer.from(`${index + 1} 0 obj\n${body}\nendobj\n`, 'ascii')
  chunks.push(object)
  offset += object.length
})
const xrefOffset = offset
const xref = [`xref\n0 ${objects.length + 1}\n`, '0000000000 65535 f \n']
for (const objectOffset of offsets.slice(1)) xref.push(`${String(objectOffset).padStart(10, '0')} 00000 n \n`)
xref.push(`trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xrefOffset}\n%%EOF\n`)
chunks.push(Buffer.from(xref.join(''), 'ascii'))
await writeFile(new URL('./synthetic-lab-report.pdf', import.meta.url), Buffer.concat(chunks))
