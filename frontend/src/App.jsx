import { Routes, Route, Navigate, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from './context/AuthContext'
import Navbar from './components/Navbar'
import Home from './pages/Home'
import StudentDashboard from './pages/StudentDashboard'
import ExamRoom from './pages/ExamRoom'
import ReportView from './pages/ReportView'
import SchoolStaffDashboard from './pages/SchoolStaffDashboard'
import LoadingSpinner from './components/LoadingSpinner'

// نقش‌های کادر مدرسه — هرکدام مستقیماً به SchoolStaffDashboard هدایت می‌شوند
const STAFF_ROLES = ['teacher', 'admin', 'school_staff']

function homeFor(user) {
  return user?.role === 'student' ? '/dashboard' : '/staff'
}

/** کارنامهٔ کیفی یک دانش‌آموز (کادر مدرسه) — «بازگشت به داشبورد مدرسه» همیشه به تب ۲ برمی‌گردد */
function StaffReport() {
  const navigate = useNavigate()
  return (
    <ReportView
      mode="teacher"
      onBackToDashboard={() => navigate('/staff', { state: { tab: 'results' } })}
    />
  )
}

function RequireAuth({ roles }) {
  const { isAuthenticated, user, booting } = useAuth()
  const location = useLocation()
  if (booting) return <LoadingSpinner label="در حال آماده‌سازی نشست شما…" />
  if (!isAuthenticated) {
    // تنها درگاه ورود، صفحهٔ اصلی (Landing Page) است
    return <Navigate to="/" replace state={{ from: location.pathname }} />
  }
  if (roles && !roles.includes(user.role)) {
    // دانش‌آموز به پنل کادر مدرسه دسترسی ندارد و برعکس
    return <Navigate to={homeFor(user)} replace />
  }
  return <Outlet />
}

/** اگر کاربر لاگین باشد، هرگز صفحه اصلی (Landing) را نمی‌بیند — مستقیم به داشبوردش می‌رود */
function Landing() {
  const { isAuthenticated, user, booting } = useAuth()
  if (booting) return <LoadingSpinner label="در حال آماده‌سازی نشست شما…" />
  if (isAuthenticated) return <Navigate to={homeFor(user)} replace />
  return <Home />
}

export default function App() {
  const { user } = useAuth()
  return (
    <div className="flex min-h-full flex-col">
      <Navbar />
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 sm:px-6 sm:py-8">
        <Routes>
          <Route path="/" element={<Landing />} />

          <Route element={<RequireAuth roles={['student']} />}>
            <Route path="/dashboard" element={<StudentDashboard />} />
            <Route path="/exam/:sessionId" element={<ExamRoom />} />
            <Route path="/report/:sessionId" element={<ReportView mode="student" />} />
          </Route>

          <Route element={<RequireAuth roles={STAFF_ROLES} />}>
            <Route path="/staff" element={<SchoolStaffDashboard />} />
            <Route path="/staff/report/:studentId/:sessionId" element={<StaffReport />} />
            {/* مسیرهای قدیمی — برای سازگاری به داشبورد جدید هدایت می‌شوند */}
            <Route path="/builder" element={<Navigate to="/staff" replace />} />
            <Route path="/teacher" element={<Navigate to="/staff" replace />} />
            <Route path="/teacher/report/:studentId/:sessionId" element={<Navigate to="/staff" replace />} />
          </Route>

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>

      <footer className="no-print border-t border-slate-200/70 bg-white/70 py-4 backdrop-blur">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-2 px-4 text-[11px] font-medium text-slate-500 sm:px-6">
          <span className="font-bold text-brand-800">فهم‌یار</span>
          {user ? <span className="text-slate-400">{user.full_name || user.username}</span> : <span>سامانهٔ فهم‌سنجی تشخیصی</span>}
        </div>
      </footer>
    </div>
  )
}
