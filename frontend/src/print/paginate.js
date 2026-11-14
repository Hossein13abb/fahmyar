/**
 * صفحه‌بندِ سمتِ مرورگر.
 *
 * هیچ محاسبهٔ چیدمانی در پایتون انجام نمی‌شود. بلوک‌ها در DOM واقعی اندازه
 * گرفته می‌شوند و در برگه‌های A4 توزیع می‌گردند، چون تنها مرورگری که ارتفاعِ
 * واقعیِ یک خط فارسی یا یک فرمولِ KaTeX را می‌داند، خودِ مرورگر است.
 *
 * قواعد:
 *  • هر بلوکِ `data-block` اتمی است تا وقتی در یک صفحه جا شود
 *    (سؤال هرگز از گزینه‌هایش جدا نمی‌شود).
 *  • ترتیبِ سند حفظ می‌شود (بسته‌بندی حریصانه).
 *  • بلوکی که از یک صفحهٔ کامل بلندتر است، در مرزِ گره‌های فرزند شکسته می‌شود؛
 *    هرگز میانِ یک واژه یا داخلِ یک فرمولِ KaTeX.
 *  • `data-newpage="1"` پیش از بلوک، صفحهٔ تازه آغاز می‌کند.
 */

const FA = ['۰', '۱', '۲', '۳', '۴', '۵', '۶', '۷', '۸', '۹']

export const toFa = (n) => String(n).replace(/[0-9]/g, (d) => FA[Number(d)])

/* vertical space actually consumed inside a sheet: the bottom edge of the last
   child relative to the body's top.  scrollHeight is unreliable here because a
   flex child is stretched to the container height. */
const usedHeight = (sheet) => {
  const body = sheet.body
  if (!body.lastElementChild) return 0
  const top = body.getBoundingClientRect().top
  const last = body.lastElementChild.getBoundingClientRect()
  return last.bottom - top + mb(body.lastElementChild)
}

const mb = (el) => {
  if (!el || el.nodeType !== 1) return 0
  return parseFloat(getComputedStyle(el).marginBottom) || 0
}

/**
 * ارتفاعِ n فرزندِ اول `parent`، اندازه‌گیری‌شده با Range.
 * Range گره‌های متنی را دقیقاً مثل عناصر می‌سنجد و چیزی را جابه‌جا نمی‌کند.
 */
function heightOfFirst(parent, n) {
  if (n <= 0) return 0
  const kids = parent.childNodes
  const first = kids[0]
  const last = kids[n - 1]
  const range = document.createRange()
  if (first.nodeType === 3) range.setStart(first, 0)
  else range.setStartBefore(first)
  if (last.nodeType === 3) range.setEnd(last, last.textContent.length)
  else range.setEndAfter(last)
  return range.getBoundingClientRect().height + mb(last)
}

function fitCount(parent, limit) {
  const total = parent.childNodes.length
  let lo = 0
  let hi = total
  let best = 0
  while (lo <= hi) {
    const mid = (lo + hi) >> 1
    if (mid === 0) {
      best = 0
      lo = 1
      continue
    }
    if (heightOfFirst(parent, mid) <= limit) {
      best = mid
      lo = mid + 1
    } else {
      hi = mid - 1
    }
  }
  return best
}

/** el را طوری بشکن که سرِ آن در `limit` جا شود. [head, tail|null] */
function splitToFit(el, limit) {
  if (el.getBoundingClientRect().height + mb(el) <= limit) return [el, null]
  const kids = el.childNodes
  if (!kids.length) return [null, el]

  const best = fitCount(el, limit)

  if (best === 0 && kids.length === 1) {
    const only = kids[0]
    if (only.nodeType === 1) {
      const inner = splitToFit(only, limit)
      if (inner[0]) {
        const wrap = el.cloneNode(false)
        wrap.appendChild(inner[0])
        if (inner[1]) {
          el.appendChild(inner[1])
          return [wrap, el]
        }
        return [wrap, null]
      }
    } else if (only.nodeType === 3) {
      /* یک گرهٔ متنیِ بلند: شکستن روی مرزِ واژه، هرگز میانِ واژه */
      const words = only.textContent.split(/(\s+)/)
      let cut = -1
      let lo = 1
      let hi = words.length
      while (lo <= hi) {
        const mid = (lo + hi) >> 1
        const probe = document.createRange()
        probe.setStart(only, 0)
        probe.setEnd(only, words.slice(0, mid).join('').length)
        if (probe.getBoundingClientRect().height <= limit) {
          cut = mid
          lo = mid + 1
        } else {
          hi = mid - 1
        }
      }
      if (cut > 0) {
        const headWrap = el.cloneNode(false)
        const tailWrap = el.cloneNode(false)
        headWrap.appendChild(document.createTextNode(words.slice(0, cut).join('')))
        tailWrap.appendChild(document.createTextNode(words.slice(cut).join('')))
        Array.prototype.slice.call(el.childNodes).forEach((n) => tailWrap.appendChild(n))
        return [headWrap, tailWrap]
      }
    }
    return [null, el]
  }
  if (best === 0) return [null, el]

  const head = el.cloneNode(false)
  const moves = Array.prototype.slice.call(el.childNodes, 0, best)
  moves.forEach((n) => head.appendChild(n))
  return [head, el.childNodes.length ? el : null]
}

function makePage(mount) {
  const page = document.createElement('div')
  page.className = 'page'
  const body = document.createElement('div')
  body.className = 'page-body'
  const foot = document.createElement('div')
  foot.className = 'print-footer'
  page.appendChild(body)
  page.appendChild(foot)
  mount.appendChild(page)
  return { page, body, foot }
}

/**
 * فرمولِ چندخطی را از حالت درون‌خطی بیرون می‌آورد.
 *
 * وقتی `$$\begin{aligned}…\end{aligned}$$` وسطِ یک جمله بیاید، remark-math آن را
 * ریاضیِ درون‌خطی می‌شناسد؛ اما alined/array/matrix ارتفاعی بیش از ارتفاع خط
 * دارند و کادر خط آن‌ها را در بر نمی‌گیرد، پس فرمول روی متنِ بالا و پایین
 * می‌افتد. هر فرمولی که از یک‌ونیم برابرِ اندازهٔ متن بلندتر است به بلوکِ
 * تمام‌عرض تبدیل می‌شود. این اصلاح فقط در مسیر چاپ اجرا می‌شود و پیش‌نمایش را
 * دست نمی‌زند.
 */
export function paginate(flow, footerLeft = '') {
  if (!flow) return 0

  const mount = document.createElement('div')
  mount.id = 'mount'
  document.body.appendChild(mount)

  let cur = null
  const startPage = () => {
    const made = makePage(mount)
    cur = { page: made.page, body: made.body, used: 0 }
    return cur
  }

  startPage()
  /* ارتفاعِ قابل‌استفاده از برگهٔ خالی خوانده می‌شود، پس هندسهٔ صفحه در
     جاوااسکریپت تکرار نمی‌شود */
  const limit = cur.body.clientHeight

  const queue = Array.prototype.slice
    .call(flow.childNodes)
    .filter((n) => n.nodeType === 1)

  let guard = 0
  while (queue.length) {
    if (guard++ > 20000) break /* شبکهٔ ایمنی: هرگز بی‌نهایت حلقه نزن */

    const block = queue.shift()
    const forceNew = block.getAttribute('data-newpage') === '1'
    const h = block.getBoundingClientRect().height + mb(block)

    if (forceNew && cur.used > 0) startPage()
    if (cur.used > 0 && cur.used + h > limit + 0.5) startPage()

    if (h <= limit) {
      cur.body.appendChild(block)
      /* re-measure in its final container: the estimate above was taken while
         the block sat in #flow, where the available width can differ, so using
         it to account for space would drift and leave a gap at the page foot */
      cur.used = usedHeight(cur)
      continue
    }

    /* بلندتر از یک صفحهٔ کامل: سرِ برازنده را بگذار، بقیه را به صفحهٔ بعد ببر */
    const parts = splitToFit(block, limit - cur.used)
    if (parts[0]) {
      cur.body.appendChild(parts[0])
      cur.used = usedHeight(cur)
    }
    if (parts[1]) queue.unshift(parts[1])
    else if (!parts[0]) queue.unshift(block) /* تقسیم‌ناپذیر: یک‌بار سرریز */
    startPage()
  }

  const pages = Array.prototype.slice.call(mount.querySelectorAll('.page'))
  const total = pages.length
  pages.forEach((page, idx) => {
    const foot = page.querySelector('.print-footer')
    if (!foot) return
    const left = document.createElement('span')
    left.textContent = footerLeft
    const pg = document.createElement('span')
    pg.className = 'print-footer-pg'
    pg.textContent = `صفحهٔ ${toFa(idx + 1)} از ${toFa(total)}`
    foot.appendChild(left)
    foot.appendChild(pg)
  })

  flow.remove()

  /* An audit hook the engine reads: anything sticking out of a sheet means the
     paginator misjudged and the sheet will be scaled by the packer.  Reported
     rather than silently rescaled. */
  const overflow = []
  pages.forEach((page, idx) => {
    const body = page.querySelector('.page-body')
    if (body && body.scrollHeight > body.clientHeight + 1) {
      overflow.push({ page: idx + 1, over: body.scrollHeight - body.clientHeight })
    }
  })
  window.__PDF_OVERFLOW__ = overflow

  return total
}

/** انتظارِ واقعی: فونت‌ها + تصاویر + دو فریمِ رندر، سپس صفحه‌بندی. */
export async function readyForCapture() {
  if (document.fonts && document.fonts.ready) {
    try {
      await document.fonts.ready
    } catch (e) {
      /* ignore */
    }
  }

  const imgs = Array.prototype.slice.call(document.images || [])
  await Promise.all(
    imgs.map(
      (img) =>
        new Promise((resolve) => {
          if (img.complete && img.naturalWidth > 0) return resolve()
          img.addEventListener('load', resolve, { once: true })
          img.addEventListener('error', resolve, { once: true })
          setTimeout(resolve, 3000)
        }),
    ),
  )

  /* KaTeX ممکن است بعد از رندر، فونت‌های بیشتری طلب کند */
  if (document.fonts && document.fonts.ready) {
    try {
      await document.fonts.ready
    } catch (e) {
      /* ignore */
    }
  }

  const flow = document.getElementById('flow')
  const footerLeft = window.__EXAM__?.footer || ''
  const pages = paginate(flow, footerLeft)

  await new Promise((r) => requestAnimationFrame(r))
  await new Promise((r) => requestAnimationFrame(r))
  void document.body.offsetHeight

  window.__PDF_PAGES__ = pages
  return pages
}
