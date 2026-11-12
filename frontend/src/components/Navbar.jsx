import { Link, useNavigate, useLocation } from 'react-router-dom'
import { LogOut, GraduationCap, BookOpenCheck, ShieldCheck } from 'lucide-react'
import { useAuth } from '../context/AuthContext'

const ROLE_META = {
  student: { label: 'دانش‌آموز', cls: 'bg-brand-50 text-brand-800 ring-brand-200', Icon: GraduationCap },
  teacher: { label: 'معلم', cls: 'bg-indigo-50 text-indigo-800 ring-indigo-200', Icon: BookOpenCheck },
  admin: { label: 'مدیر', cls: 'bg-calm-100 text-amber-900 ring-calm-200', Icon: ShieldCheck },
}

function LogoMark() {
  return (
    <svg viewBox="0 0 100 100" className="h-10 w-10 drop-shadow-sm" aria-hidden="true">
      <circle cx="50" cy="50" r="46" fill="#1f6a55" />
      <path
        d="M50 22a18 18 0 0 0-9.5 33c2.4 1.7 3.7 4 3.7 7.2h11.6c0-3.2 1.3-5.5 3.7-7.2A18 18 0 0 0 50 22z"
        fill="#fde9c8"
      />
      <rect x="43.5" y="69" width="13" height="2.6" rx="1.3" fill="#fde9c8" />
      <rect x="45" y="74.5" width="10" height="2.6" rx="1.3" fill="#fde9c8" />
    </svg>
  )
}

export default function Navbar() {
  const { user, logout, isTeacher } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const role = ROLE_META[user?.role] ?? ROLE_META.student
  const onLoginPage = location.pathname.startsWith('/login')

  return (
    <header className="no-print sticky top-0 z-40 border-b border-slate-200/70 bg-white/80 backdrop-blur-xl">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-3 px-4 sm:px-6">
        {/* راست (RTL اول): لوگو + نام */}
        <Link to={isTeacher ? '/staff' : '/dashboard'} className="flex items-center gap-3">
          <LogoMark />
          <span className="leading-tight">
            <span className="block text-[19px] font-black tracking-tight text-brand-900">فهم‌یار</span>
          </span>
        </Link>

        {/* چپ: کاربر + خروج */}
        {user && !onLoginPage && (
          <div className="flex items-center gap-2 sm:gap-3">
            <span className={`chip ring-1 ${role.cls} hidden sm:inline-flex`}>
              <role.Icon className="h-3.5 w-3.5" />
              {role.label}
            </span>
            <span className="max-w-[9rem] truncate text-[13px] font-bold text-brand-900 sm:max-w-[12rem]">
              {user.full_name || user.username}
            </span>
            <button
              onClick={() => {
                logout()
                navigate('/login', { replace: true })
              }}
              title="خروج از حساب"
              aria-label="خروج از حساب"
              className="rounded-2xl border border-brand-100 bg-white/80 p-2 text-brand-700 shadow-sm transition hover:border-brand-200 hover:bg-brand-50 hover:text-brand-900"
            >
              <LogOut className="h-5 w-5" strokeWidth={2} />
            </button>
          </div>
        )}
      </div>
    </header>
  )
}
