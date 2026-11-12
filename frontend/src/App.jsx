import { Routes, Route, Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from './context/AuthContext'
import Navbar from './components/Navbar'
import Home from './pages/Home'
import Login from './pages/Login'
import StudentDashboard from './pages/StudentDashboard'
import ExamRoom from './pages/ExamRoom'
import ReportView from './pages/ReportView'
import TeacherDashboard from './pages/TeacherDashboard'
import ExamBuilder from './pages/ExamBuilder'
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

export default function App() {
  const { user } = useAuth()
  return (
    <div className="flex min-h-full flex-col">
      <Navbar />
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 sm:px-6 sm:py-8">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/login" element={<Login />} />

          <Route element={<RequireAuth roles={['student']} />}>
            <Route path="/dashboard" element={<StudentDashboard />} />
            <Route path="/exam/:sessionId" element={<ExamRoom />} />
            <Route path="/report/:sessionId" element={<ReportView mode="student" />} />
          </Route>

          <Route element={<RequireAuth roles={['teacher', 'admin']} />}>
            <Route path="/builder" element={<ExamBuilder />} />
            <Route path="/teacher" element={<TeacherDashboard />} />
            <Route path="/teacher/report/:studentId/:sessionId" element={<ReportView mode="teacher" />} />
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
