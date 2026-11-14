import React from 'react'
import ReactDOM from 'react-dom/client'
import 'katex/dist/katex.min.css'
import PrintExam from './PrintExam.jsx'
import { readyForCapture } from './paginate.js'
import './print.css'

/* ریشهٔ رندرِ چاپ/PDF.
   داده از window.__EXAM__ می‌آید؛ استایل از باندل محلی؛ هیچ شبکه‌ای در کار نیست. */
ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <PrintExam />
  </React.StrictMode>,
)

/* صفحه‌بندی پس از کامیتِ React؛ موتور PDF تا اتمامِ این پرامیس صبر می‌کند. */
window.__readyForCapture = readyForCapture
