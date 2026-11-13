import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'

/** با هر تغییر مسیر (route change)، صفحه را به ابتدای صفحه بازمی‌گرداند. */
export default function ScrollToTop() {
  const { pathname } = useLocation()
  useEffect(() => {
    window.scrollTo(0, 0)
  }, [pathname])
  return null
}
