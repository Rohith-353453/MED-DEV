# Synthetic sample records

`synthetic-lab-report.pdf` is fictional training content. It does not represent a real person or clinical report. The local mock OCR adapter recognizes its explicit `CAREFOLIO DEMO FIXTURE V1` marker and returns only the facts printed in that file. Other documents uploaded with mock providers do not receive invented OCR or health data.

Regenerate the PDF with:

```powershell
node samples/create_synthetic_pdf.mjs
```
