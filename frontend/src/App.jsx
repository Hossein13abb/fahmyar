import { Routes, Route, Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from './context/AuthContext'
import Navbar from './components/Navbar'
import Login from './pages/Login'
import StudentDashboard from './pages/StudentDashboard'
import AssessmentRoom from './pages/AssessmentRoom'
import ReportView from './pages/ReportView'
import TeacherDashboard from './pages/TeacherDashboard'
import LoadingSpinner from './components/LoadingSpinner'

function RequireAuth({ roles }) {
  const { isAuthenticated, user, booting } = useAuth()
  const location = useLocation()
  if (booting) return <LoadingSpinner label="در حال آماده‌سازی نشست شما…" />
  if (!isAuthenticated) return <Navigate to="/login" replace state={{ from: location.pathname }} />
  if (roles && !roles.includes(user.role)) {
    // دانش‌آموز به پنل معلم دسترسی ندارد و برعکس
    return <Navigate to={user.role === 'student' ? '/dashboard' : '/teacher'} replace />
  }
  return <Outlet />
}

function HomeRedirect() {
  const { isAuthenticated, user } = useAuth()
  if (!isAuthenticated) return <Navigate to="/login" replace />
  return <Navigate to={user.role === 'student' ? '/dashboard' : '/teacher'} replace />
}

export default function App() {
  const { user } = useAuth()
  return (
    <div className="flex min-h-full flex-col">
      <Navbar />
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 sm:px-6 sm:py-8">
        <Routes>
          <Route path="/" element={<HomeRedirect />} />
          <Route path="/login" element={<Login />} />

          <Route element={<RequireAuth roles={['student']} />}>
            <Route path="/dashboard" element={<StudentDashboard />} />
            <Route path="/assessment/:sessionId" element={<AssessmentRoom />} />
            <Route path="/report/:sessionId" element={<ReportView mode="student" />} />
          </Route>

          <Route element={<RequireAuth roles={['teacher', 'admin']} />}>
            <Route path="/teacher" element={<TeacherDashboard />} />
            <Route path="/teacher/report/:studentId/:sessionId" element={<ReportView mode="teacher" />} />
          </Route>

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>

      <footer className="no-print border-t border-brand-100/70 bg-white/60 py-4 text-center">
        <p className="text-[11px] font-medium text-brand-700">
          فهم‌یار — فهمیدن را با آرامش بسنجیم · بدون نمره، بدون رتبه، بدون مقایسه
          <span className="mx-2 text-amber-600">|</span>
          <span className="text-amber-700">⚠️ نمرهٔ آزمون — نه سنجش فهم</span>
          {user ? <span className="mx-2 text-slate-300">•</span> : null}
          {user ? <span className="text-slate-400">{user.username}</span> : null}
        </p>
      </footer>
    </div>
  )
}
